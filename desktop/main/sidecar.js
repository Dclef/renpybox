/**
 * Python sidecar 进程守护。
 *
 * 仿 DeepSeek Harness 的 "bundled runtime" 模式：壳负责把 sidecar 拉起来、
 * 探活、崩溃重启、退出时清理进程树。业务逻辑全部留在 Python 侧。
 */
import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const DESKTOP_ROOT = path.resolve(__dirname, '..');
const SIDECAR_DIR = path.join(DESKTOP_ROOT, 'sidecar');

export const SIDECAR_PORT = Number(process.env.RENPYBOX_SIDECAR_PORT || 9712);
export const SIDECAR_URL = `http://127.0.0.1:${SIDECAR_PORT}`;
export const SIDECAR_WS = `ws://127.0.0.1:${SIDECAR_PORT}/ws`;

const MAX_RESTARTS = 3;

// api 模式要用项目自己的解释器（3.10，全套依赖都在里面：
// openpyxl / tiktoken / unrpa / opencc / translators / translators 依赖链都在那）；
// bench 模式只需要 fastapi + uvicorn，用 sidecar/.venv 就够。
const PROJECT_PYTHON =
  process.env.RENPYBOX_PROJECT_PYTHON || 'C:/Program Files/Python/python3.10/python.exe';

function resolvePython() {
  const bench = process.env.RENPYBOX_SIDECAR_BENCH === '1';
  const candidates = [process.env.RENPYBOX_PYTHON];

  if (bench) {
    candidates.push(path.join(SIDECAR_DIR, '.venv', 'Scripts', 'python.exe'));
    candidates.push(path.join(SIDECAR_DIR, '.venv', 'bin', 'python'));
  } else {
    candidates.push(PROJECT_PYTHON);
  }

  for (const c of candidates.filter(Boolean)) if (existsSync(c)) return c;
  return 'python';
}

export class Sidecar {
  constructor({ onLog } = {}) {
    this.proc = null;
    this.onLog = onLog || (() => {});
    this.restarts = 0;
    this.stopping = false;
  }

  async start() {
    const python = resolvePython();
    const args = [path.join(SIDECAR_DIR, 'main.py')];
    if (process.env.RENPYBOX_SIDECAR_BENCH === '1') args.push('--bench');

    this.onLog(`[sidecar] 启动 ${python} ${args.join(' ')}`);
    this.proc = spawn(python, args, {
      cwd: SIDECAR_DIR,
      windowsHide: true,
      stdio: ['ignore', 'pipe', 'pipe'],
      env: {
        ...process.env,
        RENPYBOX_SIDECAR_PORT: String(SIDECAR_PORT),
        QT_QPA_PLATFORM: process.env.QT_QPA_PLATFORM || 'offscreen',
      },
    });

    this.proc.stdout.on('data', (d) => this.onLog(`[sidecar] ${String(d).trim()}`));
    this.proc.stderr.on('data', (d) => this.onLog(`[sidecar:err] ${String(d).trim()}`));
    this.proc.on('exit', (code, signal) => {
      this.onLog(`[sidecar] 退出 code=${code} signal=${signal}`);
      if (this.stopping) return;
      if (this.restarts >= MAX_RESTARTS) {
        this.onLog('[sidecar] 超过重启上限，放弃');
        return;
      }
      const delay = 500 * 2 ** this.restarts;
      this.restarts += 1;
      this.onLog(`[sidecar] ${delay}ms 后第 ${this.restarts} 次重启`);
      setTimeout(() => this.start().catch((e) => this.onLog(`[sidecar] 重启失败 ${e}`)), delay);
    });

    return this.waitHealthy();
  }

  async waitHealthy(timeoutMs = 30000) {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      try {
        const res = await fetch(`${SIDECAR_URL}/health`);
        if (res.ok) return res.json();
      } catch {
        /* 还没起来，继续等 */
      }
      await new Promise((r) => setTimeout(r, 200));
    }
    throw new Error('sidecar 健康检查超时');
  }

  async stop() {
    this.stopping = true;
    const pid = this.proc?.pid;
    if (!pid) return;
    this.onLog(`[sidecar] 清理进程树 pid=${pid}`);
    await new Promise((resolve) => {
      const killer =
        process.platform === 'win32'
          ? spawn('taskkill', ['/pid', String(pid), '/t', '/f'], { windowsHide: true })
          : spawn('kill', ['-TERM', String(pid)]);
      killer.on('exit', () => resolve());
      killer.on('error', () => resolve());
      setTimeout(resolve, 3000);
    });
    this.proc = null;
  }
}