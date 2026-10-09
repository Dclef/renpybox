/**
 * Python sidecar 进程守护。
 *
 * 仿 DeepSeek Harness 的 "bundled runtime" 模式：壳负责把 sidecar 拉起来、
 * 探活、崩溃重启、退出时清理进程树。业务逻辑全部留在 Python 侧。
 *
 * 所有权规则（网页 / 桌面共用）：
 *   - 已有健康后端 → 复用，不接管生命周期（owned=false）
 *   - RENPYBOX_SIDECAR_EXTERNAL=1 → 只等待，不启动、不杀死
 *   - 本进程 spawn 出来的 → owned=true，退出时才 taskkill
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

function externalMode() {
  const value = String(process.env.RENPYBOX_SIDECAR_EXTERNAL || '').trim().toLowerCase();
  return value === '1' || value === 'true' || value === 'yes';
}

// sidecar 跑真实业务逻辑，需要项目自己的解释器（3.10，openpyxl / tiktoken /
// unrpa / opencc / translators 依赖链都在那）。
function resolvePython() {
  const configured = process.env.RENPYBOX_PYTHON || process.env.RENPYBOX_PROJECT_PYTHON;
  if (configured) {
    if (!existsSync(configured)) throw new Error(`Python 路径不存在：${configured}`);
    return configured;
  }
  const executable = process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python';
  const candidates = [
    process.env.VIRTUAL_ENV && path.join(process.env.VIRTUAL_ENV, executable),
    path.join(DESKTOP_ROOT, '..', '.venv', executable),
    path.join(SIDECAR_DIR, '.venv', executable),
    process.env.LOCALAPPDATA && path.join(process.env.LOCALAPPDATA, 'Programs/Python/Python310/python.exe'),
  ];
  return candidates.find(candidate => candidate && existsSync(candidate)) || (process.platform === 'win32' ? 'python' : 'python3');
}

export class Sidecar {
  constructor({ onLog } = {}) {
    this.proc = null;
    this.owned = false;
    this.onLog = onLog || (() => {});
    this.restarts = 0;
    this.stopping = false;
    this.restartTimer = null;
    this.lastFailure = null;
  }

  async probe() {
    const response = await fetch(`${SIDECAR_URL}/health`, { signal: AbortSignal.timeout(1000) });
    const info = response.ok ? await response.json() : null;
    if (info?.ok && info.mode === 'api' && info.app_version) return info;
    return null;
  }

  async start() {
    if (this.stopping) throw new Error('sidecar 已停止');

    if (!this.proc && this.restarts === 0) {
      try {
        const info = await this.probe();
        if (info) {
          this.owned = false;
          this.onLog(`[sidecar] 复用已运行的后端 pid=${info.pid}（本进程不接管生命周期）`);
          return info;
        }
      } catch {}
    }

    if (externalMode()) {
      this.owned = false;
      this.onLog('[sidecar] EXTERNAL 模式：等待外部后端就绪，不会启动或杀死进程');
      return this.waitHealthy();
    }

    const python = resolvePython();
    const args = [path.join(SIDECAR_DIR, 'main.py')];
    this.lastFailure = null;
    this.owned = true;

    this.onLog(`[sidecar] 启动 ${python} ${args.join(' ')}`);
    this.proc = spawn(python, args, {
      cwd: path.resolve(DESKTOP_ROOT, '..'),
      windowsHide: true,
      stdio: ['ignore', 'pipe', 'pipe'],
      env: {
        ...process.env,
        RENPYBOX_SIDECAR_PORT: String(SIDECAR_PORT),
        QT_QPA_PLATFORM: process.env.QT_QPA_PLATFORM || 'offscreen',
        PYTHONUTF8: '1',
      },
    });

    this.proc.stdout.on('data', (d) => this.onLog(`[sidecar] ${String(d).trim()}`));
    this.proc.stderr.on('data', (d) => this.onLog(`[sidecar:err] ${String(d).trim()}`));
    this.proc.on('error', (error) => {
      this.lastFailure = `无法启动 Python：${error.message}。请用 RENPYBOX_PYTHON 指定已安装项目依赖的解释器。`;
      this.onLog(`[sidecar:err] ${this.lastFailure}`);
    });
    this.proc.on('exit', (code, signal) => {
      this.lastFailure = `Python 后端退出（${code ?? signal}），请检查上方日志和解释器依赖。`;
      this.onLog(`[sidecar] 退出 code=${code} signal=${signal}`);
      this.proc = null;
      if (this.stopping || !this.owned) return;
      if (this.restarts >= MAX_RESTARTS) {
        this.onLog('[sidecar] 超过重启上限，放弃');
        return;
      }
      const delay = 500 * 2 ** this.restarts;
      this.restarts += 1;
      this.onLog(`[sidecar] ${delay}ms 后第 ${this.restarts} 次重启`);
      this.restartTimer = setTimeout(() => this.start().catch((e) => this.onLog(`[sidecar] 重启失败 ${e}`)), delay);
    });

    return this.waitHealthy();
  }

  async waitHealthy(timeoutMs = 30000) {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      if (this.stopping) throw new Error('sidecar 已停止');
      if (this.lastFailure) throw new Error(this.lastFailure);
      try {
        const info = await this.probe();
        if (info) return info;
      } catch {
        /* 还没起来，继续等 */
      }
      await new Promise((r) => setTimeout(r, 200));
    }
    throw new Error(
      externalMode()
        ? `外部 sidecar 健康检查超时（${SIDECAR_URL}）。请先运行 npm run sidecar 或 npm run dev:web。`
        : 'sidecar 健康检查超时',
    );
  }

  async stop() {
    this.stopping = true;
    if (this.restartTimer) clearTimeout(this.restartTimer);
    if (!this.owned) {
      this.onLog('[sidecar] 未接管生命周期，退出时保留后端供网页/其它客户端继续使用');
      return;
    }
    const pid = this.proc?.pid;
    if (!pid) return;
    this.onLog(`[sidecar] 清理本进程启动的后端 pid=${pid}`);
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
    this.owned = false;
  }
}
