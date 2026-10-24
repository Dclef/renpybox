/**
 * 开发启动器：一条命令同时起 vite 与（可选）Electron。
 *
 * 后端由本脚本统一托管：网页与桌面共用同一 sidecar，关掉 Electron
 * 不会带走后端；Ctrl+C 结束本脚本时才停掉。
 *
 * 用法：
 *   npm run dev       vite + Electron（Electron 以 EXTERNAL 模式接入）
 *   npm run dev:web   仅 vite + sidecar（浏览器打开）
 */
import { spawn, spawnSync } from 'node:child_process';
import { createRequire } from 'node:module';
import { existsSync, readdirSync, statSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { Sidecar } from '../main/sidecar.js';
import { stdioConsole } from '../main/stdio-console.js';

const DESKTOP_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const require = createRequire(import.meta.url);
const webOnly = process.argv.includes('--web');
const viteBinary = path.join(DESKTOP_ROOT, 'node_modules', 'vite', 'bin', 'vite.js');

// 先检查开发依赖，避免前端无法启动时仍拉起后端。
if (!existsSync(viteBinary)) {
  stdioConsole.error('[dev] Vite 依赖缺失，请在 desktop 目录执行 npm ci --include=dev 后重试。');
  process.exit(1);
}
let electronBinary;
if (!webOnly) {
  try {
    // 保留包入口解析，以兼容 Electron 自带的缓存安装逻辑。
    electronBinary = require('electron');
    if (typeof electronBinary !== 'string' || !existsSync(electronBinary)) {
      throw new Error('未找到 Electron 可执行文件。');
    }
  } catch (error) {
    const repair = error.code === 'MODULE_NOT_FOUND'
      ? 'npm ci --include=dev'
      : 'node node_modules/electron/install.js';
    stdioConsole.error(`[dev] Electron 运行时不可用：${error.message}\n[dev] 请在 desktop 目录执行 ${repair} 后重试。`);
    process.exit(1);
  }
}
const sidecar = new Sidecar({ onLog: stdioConsole.log });

const SIDECAR_PORT = Number(process.env.RENPYBOX_SIDECAR_PORT || 9712);
const WEB_PORT = Number(process.env.RENPYBOX_WEB_PORT || 5173);
const WEB_URL = `http://127.0.0.1:${WEB_PORT}`;

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

/**
 * 后端代码新鲜度检测。
 *
 * dev 会复用端口上已有的 sidecar，但复用的可能是一个旧代码启动的进程：
 * 它没有后来新增的路由，前端会得到一片 404（真实事故：story_blueprint
 * 路由上线后剧情蓝图页整页 Not Found）。版本号相同、代码却旧了的情况，
 * 现有的 app_version 握手校验查不出来，只能比「进程启动时间」与
 * 「api/ 与 module/ 下 .py 的最新修改时间」。
 *
 * 默认行为只有「警告」：仍然复用同端口上那个进程，绝不自动杀它。
 * 只有显式设置 RENPYBOX_DEV_RESTART_STALE=1 才会自动重启，且结束前必须核对
 * 命令行同时满足「包含本项目根目录」且「python 跑 desktop/sidecar/main.py」；
 * 核对不通过只警告。绝不按进程名批量杀。
 * 取不到启动时间或源码时间时，保持原复用行为，只打印一行提示。
 */
const REPO_ROOT = path.resolve(DESKTOP_ROOT, '..');
const SOURCE_DIRS = [path.join(REPO_ROOT, 'api'), path.join(REPO_ROOT, 'module')];
// 进程创建时间与文件 mtime 的采样抖动容差，避免刚存盘就启动时误判成旧代码。
const STALE_TOLERANCE_MS = 500;
// 读进程创建时间只是辅助检测：宁可放弃检测，也不能把启动拖住。
const PROCESS_PROBE_TIMEOUT_MS = 3000;

function formatClock(ms) {
  const date = new Date(ms);
  const pad = (value) => String(value).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} `
    + `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
}

function latestPythonMtimeMs() {
  let latest = null;
  const walk = (dir) => {
    let entries;
    try {
      entries = readdirSync(dir, { withFileTypes: true });
    } catch {
      return;
    }
    for (const entry of entries) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        if (entry.name === '__pycache__' || entry.name === 'node_modules') continue;
        walk(full);
      } else if (entry.isFile() && entry.name.endsWith('.py')) {
        try {
          const { mtimeMs } = statSync(full);
          if (Number.isFinite(mtimeMs) && (latest === null || mtimeMs > latest)) latest = mtimeMs;
        } catch {
          // 单个文件读不到就跳过，不影响整体判断
        }
      }
    }
  };
  for (const dir of SOURCE_DIRS) walk(dir);
  return latest;
}

function readProcessSnapshot(pid) {
  const isWindows = process.platform === 'win32';
  const command = isWindows ? 'powershell' : 'ps';
  const args = isWindows
    ? ['-NoProfile', '-NonInteractive', '-Command',
      `$p = Get-CimInstance Win32_Process -Filter 'ProcessId=${Number(pid)}' -ErrorAction SilentlyContinue; `
      + 'if ($p) { [pscustomobject]@{ name = $p.Name; '
      + "created = $p.CreationDate.ToUniversalTime().ToString('o'); "
      + 'command = $p.CommandLine } | ConvertTo-Json -Compress }']
    : ['-o', 'etimes=,command=', '-p', String(pid)];
  let stdout;
  try {
    const result = spawnSync(command, args, {
      encoding: 'utf8',
      windowsHide: true,
      timeout: PROCESS_PROBE_TIMEOUT_MS,
    });
    if (result.error || result.status !== 0) return null;
    stdout = String(result.stdout || '').trim();
  } catch {
    return null;
  }
  if (!stdout) return null;
  if (isWindows) {
    try {
      const raw = JSON.parse(stdout);
      return {
        name: String(raw.name || ''),
        command: String(raw.command || ''),
        startedMs: Date.parse(raw.created),
      };
    } catch {
      return null;
    }
  }
  // ps 的 etimes 是已运行秒数，据此反推启动时间，避免解析本地化时间串。
  const match = /^(\d+)\s+([\s\S]*)$/.exec(stdout);
  if (!match) return null;
  return { name: '', command: match[2].trim(), startedMs: Date.now() - Number(match[1]) * 1000 };
}

function isOwnProjectSidecar(snapshot) {
  if (!snapshot || !Number.isFinite(snapshot.startedMs)) return false;
  const normalize = (value) => String(value || '').replace(/\\/g, '/').toLowerCase();
  const command = normalize(snapshot.command);
  if (!command) return false;
  // 必须指向本项目目录，避免误杀其它项目的 sidecar。
  if (!command.includes(normalize(REPO_ROOT))) return false;
  // 必须是 desktop/sidecar/main.py 这个入口（打包版是单个可执行文件，不在此列）。
  if (!/(^|\s|\/)desktop\/sidecar\/main\.py(\s|$)/.test(command)) return false;
  const executable = normalize(command.split(/\s+/)[0]);
  return /(^|\/)(python[0-9.]*w?)(\.exe)?$/.test(executable);
}

async function probeExistingBackend(port) {
  try {
    const response = await fetch(`http://127.0.0.1:${port}/health`, { signal: AbortSignal.timeout(1500) });
    if (!response.ok) return null;
    const info = await response.json();
    if (!info || info.ok !== true || info.mode !== 'api') return null;
    return Number(info.pid) > 0 ? info : null;
  } catch {
    return null;
  }
}

function terminateVerifiedSidecar(pid) {
  const result = process.platform === 'win32'
    ? spawnSync('taskkill', ['/pid', String(pid), '/t', '/f'], { windowsHide: true, encoding: 'utf8', timeout: 20000 })
    : spawnSync('kill', ['-TERM', String(pid)], { windowsHide: true, encoding: 'utf8', timeout: 20000 });
  return !result.error && result.status === 0;
}

async function waitForPortFree(port, timeoutMs = 8000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (!(await probeExistingBackend(port))) return true;
    await sleep(300);
  }
  return false;
}

/** 醒目警告：复用旧代码后端会有整页 404，这里给出可照抄的处置命令。 */
function warnStaleBackend(port, pid, startedMs, codeMs) {
  const killHint = process.platform === 'win32'
    ? `taskkill /F /PID ${pid}`
    : `kill -TERM ${pid}`;
  stdioConsole.error('');
  stdioConsole.error('================ 警告：复用的后端可能是旧代码 ================');
  stdioConsole.error(`[dev] 端口 ${port} 上已有后端 pid=${pid}，仍会按原逻辑复用它。`);
  stdioConsole.error(`[dev] 后端启动时间：${formatClock(startedMs)}`);
  stdioConsole.error(`[dev] 代码最新修改：${formatClock(codeMs)}（api/ 或 module/ 下的 .py）`);
  stdioConsole.error('[dev] 后端启动早于代码修改，说明它加载的是旧代码，新增路由不会存在。');
  stdioConsole.error(`[dev] 若页面出现接口 404（如剧情蓝图 Not Found），说明这个后端是旧代码：先 ${killHint} 再重新启动即可。`);
  stdioConsole.error('============================================================');
  stdioConsole.error('');
}

async function restartStaleBackend(port) {
  const info = await probeExistingBackend(port);
  if (!info) return;
  const pid = Number(info.pid);

  const codeMs = latestPythonMtimeMs();
  if (!Number.isFinite(codeMs)) {
    stdioConsole.log(`[dev] 端口 ${port} 上已有后端 pid=${pid}，但读不到 api/ 或 module/ 的源码时间，跳过旧代码检测。`);
    return;
  }
  const snapshot = readProcessSnapshot(pid);
  if (!snapshot || !Number.isFinite(snapshot.startedMs)) {
    stdioConsole.log(`[dev] 端口 ${port} 上已有后端 pid=${pid}，但读不到它的进程启动时间，跳过旧代码检测。`);
    return;
  }
  if (codeMs <= snapshot.startedMs + STALE_TOLERANCE_MS) return;

  warnStaleBackend(port, pid, snapshot.startedMs, codeMs);

  // 默认只警告、继续复用：dev 的既有语义是「复用同端口上已有的后端」。
  if (process.env.RENPYBOX_DEV_RESTART_STALE !== '1') {
    stdioConsole.log('[dev] 默认不结束该进程。确需自动重启旧后端，可设 RENPYBOX_DEV_RESTART_STALE=1 后重跑。');
    return;
  }

  if (!isOwnProjectSidecar(snapshot)) {
    stdioConsole.error(`[dev] 该进程 pid=${pid} 不像本项目的 sidecar（命令行未同时含项目路径与 desktop/sidecar/main.py），出于安全不重启它。命令行：${snapshot.command || '(读取不到)'}`);
    return;
  }
  if (!terminateVerifiedSidecar(pid)) {
    stdioConsole.error(`[dev] 结束旧后端 pid=${pid} 失败，继续复用；如遇 404 请手动关闭该进程。`);
    return;
  }
  stdioConsole.log(`[dev] 已自动重启以加载新路由（结束旧后端 pid=${pid}）`);
  if (!(await waitForPortFree(port))) {
    stdioConsole.error(`[dev] 旧后端 pid=${pid} 已结束，但端口 ${port} 仍被占用，请手动检查。`);
  }
}

async function waitForWeb(timeoutMs = 60_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(`${WEB_URL}/`, { signal: AbortSignal.timeout(1500) });
      if (response.ok) return true;
    } catch {
      // vite 还没起来
    }
    await sleep(400);
  }
  return false;
}

const children = [];
let shuttingDown = false;

async function stopAll(code) {
  if (shuttingDown) return;
  shuttingDown = true;
  for (const child of children) {
    if (!child.killed) {
      try {
        child.kill();
      } catch {
        // 已经退了
      }
    }
  }
  await sidecar.stop();
  process.exit(code);
}

process.on('SIGINT', () => stopAll(0));
process.on('SIGTERM', () => stopAll(0));

stdioConsole.log(`[dev] sidecar 端口 ${SIDECAR_PORT}，渲染端 ${WEB_URL}`);

// 复用已有后端之前先确认它不是旧代码启动的，否则新加的路由会全 404。
// 默认行为是「只在终端里警告」，复用语义完全不变；自动重启必须显式开关。
if (process.env.RENPYBOX_SKIP_STALE_CHECK !== '1') {
  try {
    await restartStaleBackend(SIDECAR_PORT);
  } catch (error) {
    stdioConsole.error(`[dev] 旧代码检测失败，继续复用已有后端：${error.message}`);
  }
}

try {
  await sidecar.start();
} catch (error) {
  stdioConsole.error(`[dev] 后端启动失败：${error.message}`);
  await stopAll(1);
}

const vite = spawn(
  process.execPath,
  [viteBinary, '--config', 'renderer/vite.config.ts'],
  { cwd: DESKTOP_ROOT, stdio: ['ignore', 'inherit', 'inherit'], env: process.env },
);
children.push(vite);
vite.on('error', error => { stdioConsole.error(`[dev] Vite 启动失败：${error.message}`); void stopAll(1); });
vite.on('exit', (code) => {
  stdioConsole.log(`[dev] vite 退出（${code}）`);
  stopAll(code ?? 0);
});

if (!(await waitForWeb())) {
  stdioConsole.error('[dev] vite 未就绪，停止开发服务');
  await stopAll(1);
}

if (webOnly) {
  stdioConsole.log(`[dev] 网页与真实后端已就绪：${WEB_URL}`);
  stdioConsole.log('[dev] 可同时打开 Electron（npm run dev:shell）；关掉任一客户端不会杀死后端。Ctrl+C 停止。');
} else {
  // ELECTRON_RUN_AS_NODE=1 会让 electron.exe 以纯 Node 模式跑，必须清掉
  const electronEnv = {
    ...process.env,
    VITE_DEV_SERVER_URL: WEB_URL,
    RENPYBOX_SIDECAR_PORT: String(SIDECAR_PORT),
    // 后端由本脚本托管；Electron 只复用，退出时不互杀
    RENPYBOX_SIDECAR_EXTERNAL: '1',
  };
  delete electronEnv.ELECTRON_RUN_AS_NODE;

  stdioConsole.log('[dev] 启动 Electron；后端由开发脚本托管，关窗不会断开网页端');
  const electron = spawn(electronBinary, ['.'], {
    cwd: DESKTOP_ROOT,
    stdio: ['ignore', 'inherit', 'inherit'],
    env: electronEnv,
  });
  children.push(electron);
  electron.on('error', (error) => {
    stdioConsole.error(`[dev] Electron 启动失败：${error.message}`);
    stopAll(1);
  });
  electron.on('exit', (code) => {
    stdioConsole.log(`[dev] Electron 退出（${code}）；vite 与后端仍在运行，可继续用浏览器或再次打开桌面端`);
    // 不再 stopAll：允许网页继续联调同一后端
  });
}
