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

function resolvePython() {
  const candidates = [
    process.env.RENPYBOX_PYTHON,
    path.join(SIDECAR_DIR, '.venv', 'Scripts', 'python.exe'),
    path.join(SIDECAR_DIR, '.venv', 'bin', 'python'),
  ].filter(Boolean);
  for (const c of candidates) if (existsSync(c)) return c;
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
    this.onLog(`[sidecar] 启动 ${python}`);
    this.proc = spawn(
      python,
      [
        '-m', 'uvicorn', 'main:app',
        '--host', '127.0.0.1',
        '--port', String(SIDECAR_PORT),
        '--log-level', 'warning',
      ],
      { cwd: SIDECAR_DIR, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] },
    );

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