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
import { spawn, spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { createInterface } from 'node:readline';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const DESKTOP_ROOT = path.resolve(__dirname, '..');
const DEFAULT_SIDECAR_DIR = path.join(DESKTOP_ROOT, 'sidecar');

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
function importsSidecarDeps(executable) {
  try {
    const result = spawnSync(executable, ['-c', 'import fastapi, uvicorn'], {
      stdio: 'ignore',
      timeout: 20000,
      windowsHide: true,
    });
    return result.status === 0;
  } catch {
    return false;
  }
}

function resolvePython(sidecarDir = DEFAULT_SIDECAR_DIR) {
  const configured = process.env.RENPYBOX_PYTHON || process.env.RENPYBOX_PROJECT_PYTHON;
  if (configured) {
    if (!existsSync(configured)) throw new Error(`Python 路径不存在：${configured}`);
    return configured;
  }
  const executable = process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python';
  const candidates = [
    process.env.VIRTUAL_ENV && path.join(process.env.VIRTUAL_ENV, executable),
    path.join(DESKTOP_ROOT, '..', '.venv', executable),
    path.join(sidecarDir, '.venv', executable),
    process.env.LOCALAPPDATA && path.join(process.env.LOCALAPPDATA, 'Programs/Python/Python310/python.exe'),
    process.platform === 'win32' ? 'C:\\Program Files\\Python\\python3.10\\python.exe' : '',
    process.platform === 'win32' ? 'python' : 'python3',
  ].filter(Boolean);
  const ready = candidates.find((candidate) => {
    if (candidate !== 'python' && candidate !== 'python3' && !existsSync(candidate)) return false;
    return importsSidecarDeps(candidate);
  });
  if (!ready) throw new Error('没有找到已安装 fastapi 的 Python。请设置 RENPYBOX_PYTHON 指向项目解释器。');
  return ready;
}

export class Sidecar {
  constructor({ onLog, sidecarDir = DEFAULT_SIDECAR_DIR, pythonRoot, appRoot, resourceRoot, backendExecutable, expectedAppVersion, allowReuse = true } = {}) {
    this.proc = null;
    this.owned = false;
    this.onLog = onLog || (() => {});
    this.sidecarDir = sidecarDir;
    this.pythonRoot = pythonRoot || path.resolve(sidecarDir, '..', '..');
    this.appRoot = appRoot;
    this.resourceRoot = resourceRoot;
    this.backendExecutable = backendExecutable;
    this.expectedAppVersion = expectedAppVersion;
    this.allowReuse = allowReuse;
    this.startPromise = null;
    this.stopPromise = null;
    this.restarts = 0;
    this.stopping = false;
    this.restartTimer = null;
    this.lastFailure = null;
  }

  async probe() {
    const response = await fetch(`${SIDECAR_URL}/health`, { signal: AbortSignal.timeout(1000) });
    const info = response.ok ? await response.json() : null;
    if (!info?.ok || info.mode !== 'api' || !info.app_version) throw new Error('端口 9712 已被其他服务占用，请关闭冲突服务后重试。');
    const normalize = value => String(value).replace(/^v/, '');
    if (this.expectedAppVersion && normalize(info.app_version) !== normalize(this.expectedAppVersion)) {
      throw new Error(`后端版本 ${info.app_version} 与当前应用 ${this.expectedAppVersion} 不匹配。请关闭旧后端后重试。`);
    }
    const appRoot = typeof this.appRoot === 'function' ? this.appRoot() : this.appRoot;
    if (appRoot && path.resolve(info.config_path || '').toLowerCase() !== path.resolve(appRoot, 'config.json').toLowerCase()) {
      throw new Error('端口 9712 上的后端使用其他配置目录，请关闭旧后端后重试。');
    }
    if (this.proc?.pid && info.pid !== this.proc.pid) throw new Error('端口 9712 上的后端并非本次启动的进程。');
    return info;
  }

  start() {
    if (!this.startPromise) this.startPromise = this.startOnce().finally(() => { this.startPromise = null; });
    return this.startPromise;
  }

  async startOnce() {
    if (this.stopping) throw new Error('sidecar 已停止');
    if (this.proc) return this.waitHealthy();
    const restarting = this.restarts > 0;

    if (!this.proc && this.restarts === 0) {
      let info;
      try {
        info = await this.probe();
      } catch (error) {
        if (error.cause?.code !== 'ECONNREFUSED') throw error;
      }
      if (this.stopping) throw new Error('sidecar 已停止');
      if (info) {
        if (!this.allowReuse) throw new Error('端口 9712 已有后端运行，请关闭开发版或其他 RenpyBox 后重试。');
        this.owned = false;
        this.onLog(`[sidecar] 复用后端 pid=${info.pid}`);
        return info;
      }
    }

    if (!this.backendExecutable && externalMode()) {
      this.owned = false;
      this.onLog('[sidecar] EXTERNAL 模式：等待外部后端就绪，不会启动或杀死进程');
      return this.waitHealthy();
    }

    if (this.backendExecutable && !existsSync(this.backendExecutable)) throw new Error('安装包缺少 Python 后端，请重新安装完整的 RenpyBox 安装包。');
    const python = this.backendExecutable || resolvePython(this.sidecarDir);
    const args = this.backendExecutable ? [] : [path.join(this.sidecarDir, 'main.py')];
    this.lastFailure = null;
    this.owned = true;

    this.onLog(`[sidecar] 启动 ${python} ${args.join(' ')}`);
    if (this.stopping) throw new Error('sidecar 已停止');
    const child = this.proc = spawn(python, args, {
      cwd: this.backendExecutable ? (typeof this.appRoot === 'function' ? this.appRoot() : this.appRoot) || path.dirname(python) : this.pythonRoot,
      windowsHide: true,
      stdio: ['ignore', 'pipe', 'pipe'],
      env: {
        ...process.env,
        RENPYBOX_SIDECAR_PORT: String(SIDECAR_PORT),
        QT_QPA_PLATFORM: process.env.QT_QPA_PLATFORM || 'offscreen',
        PYTHONUTF8: '1',
        ...(this.backendExecutable ? { PYTHONPATH: '', PYTHONHOME: '' } : { PYTHONPATH: [this.pythonRoot, process.env.PYTHONPATH].filter(Boolean).join(path.delimiter) }),
        ...(this.appRoot ? { RENPYBOX_APP_ROOT: typeof this.appRoot === 'function' ? this.appRoot() : this.appRoot } : {}),
        ...(this.resourceRoot ? { RENPYBOX_RESOURCE_ROOT: typeof this.resourceRoot === 'function' ? this.resourceRoot() : this.resourceRoot } : {}),
      },
    });

    for (const [stream, prefix] of [[this.proc.stdout, '[backend]'], [this.proc.stderr, '[backend:stderr]']]) {
      createInterface({ input: stream, crlfDelay: Infinity }).on('line', line => this.onLog(`${prefix} ${line}`));
    }
    this.proc.on('error', (error) => {
      this.lastFailure = `无法启动 Python：${error.message}。请用 RENPYBOX_PYTHON 指定已安装项目依赖的解释器。`;
      this.onLog(`[sidecar:err] ${this.lastFailure}`);
    });
    child.on('exit', (code, signal) => {
      this.lastFailure = `Python 后端退出（${code ?? signal}），请检查上方日志和解释器依赖。`;
      this.onLog(`[sidecar] 退出 code=${code} signal=${signal}`);
      if (this.proc === child) this.proc = null;
      if (this.stopping || !this.owned) return;
      if (this.restarts >= MAX_RESTARTS) {
        this.onLog('[sidecar] 超过重启上限，放弃');
        return;
      }
      const delay = 500 * 2 ** this.restarts;
      this.restarts += 1;
      this.onLog(`[sidecar] ${delay}ms 后第 ${this.restarts} 次重启`);
      this.restartTimer = setTimeout(() => this.start().catch((e) => { if (!this.stopping) this.onLog(`[sidecar] 重启失败 ${e}`); }), delay);
    });

    try {
      return await this.waitHealthy();
    } catch (error) {
      if (this.stopping || !restarting) await this.stop();
      else await this.terminateOwnedProcess();
      throw error;
    }
  }

  async waitHealthy(timeoutMs = 30000) {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      if (this.stopping) throw new Error('sidecar 已停止');
      if (this.lastFailure) throw new Error(this.lastFailure);
      try {
        const info = await this.probe();
        if (this.stopping) throw new Error('sidecar 已停止');
        if (info) return info;
      } catch (error) {
        if (error.cause?.code !== 'ECONNREFUSED' && error.name !== 'TimeoutError') throw error;
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

  stop() {
    this.stopping = true;
    if (this.restartTimer) clearTimeout(this.restartTimer);
    if (!this.stopPromise) this.stopPromise = this.terminateOwnedProcess().finally(() => { this.owned = false; });
    return this.stopPromise;
  }

  async terminateOwnedProcess() {
    if (!this.owned) {
      this.onLog('[sidecar] 未接管生命周期，退出时保留后端供网页/其它客户端继续使用');
      return;
    }
    const child = this.proc;
    const pid = child?.pid;
    if (!pid) return;
    this.onLog(`[sidecar] 清理本进程启动的后端 pid=${pid}`);
    await new Promise((resolve) => {
      const killer =
        process.platform === 'win32'
          ? spawn('taskkill', ['/pid', String(pid), '/t', '/f'], { windowsHide: true })
          : spawn('kill', ['-TERM', String(pid)]);
      const timer = setTimeout(resolve, 3000);
      timer.unref();
      const done = () => { clearTimeout(timer); resolve(); };
      killer.on('exit', done);
      killer.on('error', done);
    });
    if (this.proc === child) this.proc = null;
  }
}
