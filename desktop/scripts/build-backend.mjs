import { spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const desktop = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
if (process.platform !== 'win32' || process.arch !== 'x64') {
  throw new Error('Build the Windows x64 backend on Windows x64 (or use the desktop GitHub workflow).');
}
const configured = process.env.RENPYBOX_BUILD_PYTHON || process.env.RENPYBOX_PYTHON;
const candidates = [
  configured,
  path.join(desktop, 'runtime', 'build-venv', 'Scripts', 'python.exe'),
  path.join(desktop, '..', '.venv', 'Scripts', 'python.exe'),
];
const python = candidates.find(candidate => candidate && existsSync(candidate)) || configured || 'python';
const result = spawnSync(python, [path.join(desktop, 'scripts', 'build-backend.py'), ...process.argv.slice(2)], {
  cwd: path.dirname(desktop), windowsHide: true, stdio: 'inherit',
  env: { ...process.env, PYTHONUTF8: '1' },
});
if (result.error) throw new Error(`Cannot run the build interpreter: ${result.error.message}`);
process.exit(result.status ?? 1);
