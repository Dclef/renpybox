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
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { Sidecar } from '../main/sidecar.js';

const DESKTOP_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const require = createRequire(import.meta.url);
const webOnly = process.argv.includes('--web');
const sidecar = new Sidecar({ onLog: console.log });

const SIDECAR_PORT = Number(process.env.RENPYBOX_SIDECAR_PORT || 9712);
const WEB_PORT = Number(process.env.RENPYBOX_WEB_PORT || 5173);
const WEB_URL = `http://127.0.0.1:${WEB_PORT}`;

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

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

console.log(`[dev] sidecar 端口 ${SIDECAR_PORT}，渲染端 ${WEB_URL}`);

try {
  await sidecar.start();
} catch (error) {
  console.error(`[dev] 后端启动失败：${error.message}`);
  await stopAll(1);
}

const vite = spawn(
  process.execPath,
  [path.join(DESKTOP_ROOT, 'node_modules', 'vite', 'bin', 'vite.js'), '--config', 'renderer/vite.config.ts'],
  { cwd: DESKTOP_ROOT, stdio: ['ignore', 'inherit', 'inherit'], env: process.env },
);
children.push(vite);
vite.on('error', error => { console.error(`[dev] Vite 启动失败：${error.message}`); void stopAll(1); });
vite.on('exit', (code) => {
  console.log(`[dev] vite 退出（${code}）`);
  stopAll(code ?? 0);
});

if (!(await waitForWeb())) {
  console.error('[dev] vite 未就绪，停止开发服务');
  await stopAll(1);
}

if (webOnly) {
  console.log(`[dev] 网页与真实后端已就绪：${WEB_URL}`);
  console.log('[dev] 可同时打开 Electron（npm run dev:shell）；关掉任一客户端不会杀死后端。Ctrl+C 停止。');
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

  console.log('[dev] 启动 Electron；后端由开发脚本托管，关窗不会断开网页端');
  let electronBinary;
  try {
    // 通过 Electron 包入口解析真实二进制；缺失时可触发其缓存安装逻辑。
    electronBinary = require('electron');
    if (typeof electronBinary !== 'string' || !existsSync(electronBinary)) throw new Error('运行 npm rebuild electron --foreground-scripts 修复 Electron 安装。');
  } catch (error) {
    console.error(`[dev] Electron 运行时不可用：${error.message}`);
    await stopAll(1);
  }
  const electron = spawn(electronBinary, ['.'], {
    cwd: DESKTOP_ROOT,
    stdio: ['ignore', 'inherit', 'inherit'],
    env: electronEnv,
  });
  children.push(electron);
  electron.on('error', (error) => {
    console.error(`[dev] Electron 启动失败：${error.message}`);
    stopAll(1);
  });
  electron.on('exit', (code) => {
    console.log(`[dev] Electron 退出（${code}）；vite 与后端仍在运行，可继续用浏览器或再次打开桌面端`);
    // 不再 stopAll：允许网页继续联调同一后端
  });
}
