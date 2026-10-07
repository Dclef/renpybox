/**
 * 开发启动器：一条命令同时起 vite 与 Electron。
 *
 * 为什么需要它：`npm run dev` 只起 Electron，而 dev 模式下窗口要从 vite dev
 * server 加载渲染端。单起 Electron 会得到 ERR_CONNECTION_REFUSED —— 端口对不上，
 * 而不是「vite 没开」这种能一眼看懂的提示。
 *
 * 端口在这里统一给 Electron 传进去，避免 main.js 的默认值与 vite 实际端口漂移。
 *
 * 用法：npm run dev          （等价于 node scripts/dev.mjs）
 */
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url);
const DESKTOP_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

const SIDECAR_PORT = Number(process.env.RENPYBOX_SIDECAR_PORT || 9712);
const WEB_PORT = Number(process.env.RENPYBOX_WEB_PORT || 5173);
const WEB_URL = `http://127.0.0.1:${WEB_PORT}`;

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function waitForWeb(timeoutMs = 60_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(`${WEB_URL}/`);
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

function stopAll(code) {
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
  process.exit(code);
}

process.on('SIGINT', () => stopAll(0));
process.on('SIGTERM', () => stopAll(0));

console.log(`[dev] sidecar 端口 ${SIDECAR_PORT}，渲染端 ${WEB_URL}`);

const vite = spawn(
  process.execPath,
  [path.join(DESKTOP_ROOT, 'node_modules', 'vite', 'bin', 'vite.js'), '--config', 'renderer/vite.config.ts'],
  { cwd: DESKTOP_ROOT, stdio: ['ignore', 'inherit', 'inherit'], env: process.env },
);
children.push(vite);
vite.on('exit', (code) => {
  console.log(`[dev] vite 退出（${code}）`);
  stopAll(code ?? 0);
});

if (!(await waitForWeb())) {
  console.error('[dev] vite 未就绪，放弃启动 Electron');
  stopAll(1);
}

// ELECTRON_RUN_AS_NODE=1 会让 electron.exe 以纯 Node 模式跑，必须清掉
const electronEnv = {
  ...process.env,
  VITE_DEV_SERVER_URL: WEB_URL,
  RENPYBOX_SIDECAR_PORT: String(SIDECAR_PORT),
};
delete electronEnv.ELECTRON_RUN_AS_NODE;

console.log('[dev] 启动 Electron；sidecar 由主进程自动拉起并守护');
const electronBinary = path.join(
  DESKTOP_ROOT,
  'node_modules',
  'electron',
  'dist',
  process.platform === 'win32' ? 'electron.exe' : 'electron',
);
const electron = spawn(electronBinary, ['.'], {
  cwd: DESKTOP_ROOT,
  stdio: ['ignore', 'inherit', 'inherit'],
  env: electronEnv,
});
children.push(electron);
electron.on('exit', (code) => {
  console.log(`[dev] Electron 退出（${code}）`);
  stopAll(code ?? 0);
});