/**
 * 用 Electron 运行脚本或应用，并清掉宿主环境里的 ELECTRON_RUN_AS_NODE。
 *
 * DSH、VS Code 扩展宿主等 Electron 宿主会把 ELECTRON_RUN_AS_NODE=1 传给子进程，
 * 此时 electron.exe 会退化成纯 Node，`require('electron').app` 为 undefined，
 * 检查脚本会在 `app.setPath` 处报 “Cannot read properties of undefined” 。
 * 统一走这个入口后，npm script 在仓库根目录（npm run <script> --prefix desktop）
 * 和 desktop 目录里的行为一致。
 *
 * 用法：node scripts/run-electron.mjs <electron 参数...>，例如
 *   node scripts/run-electron.mjs scripts/check-ui.cjs
 *   node scripts/run-electron.mjs .
 */
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const electron = require('electron');
const args = process.argv.slice(2);
if (args.length === 0) {
  console.error('[electron] 缺少参数：需要至少一个 electron 参数，例如 scripts/check-ui.cjs 或 .');
  process.exit(2);
}

const env = { ...process.env };
delete env.ELECTRON_RUN_AS_NODE;

const child = spawn(electron, args, { stdio: 'inherit', env, windowsHide: false });
child.on('error', error => {
  console.error(`[electron] 启动失败：${error.message || error}`);
  process.exit(1);
});
child.on('exit', (code, signal) => {
  if (signal) process.kill(process.pid, signal);
  process.exit(code ?? 1);
});
