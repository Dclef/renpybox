/**
 * 运行日志的导出与定位。
 *
 * 只做纯粹的路径/文件逻辑，不碰 electron 与对话框，便于 node:test 直接覆盖；
 * main.js 负责弹保存对话框、写系统剪贴板与调 shell.showItemInFolder。
 */
import { mkdir, readFile, stat, writeFile } from 'node:fs/promises';
import path from 'node:path';

/** 日志来源 → 文件名，与 main.js 的 app:read-logs 保持同一口径。 */
export const LOG_SOURCES = { app: 'app.log', desktop: 'desktop.log' };

export function resolveLogFile(logDirectory, source = 'app') {
  const filename = LOG_SOURCES[source];
  if (!filename) throw new Error('未知日志类型');
  return path.join(logDirectory, filename);
}

/** 导出文件名：renpybox-<source>-YYYYMMDD-HHMMSS.log。 */
export function exportFilename(source = 'app', now = new Date()) {
  const pad = (value) => String(value).padStart(2, '0');
  const stamp = `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}`
    + `-${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`;
  return `renpybox-${source}-${stamp}.log`;
}

/**
 * 把整份日志文件写到 destination。
 *
 * 日志文件还没生成（ENOENT）时退化为写界面当前显示的快照；两者都没有内容时返回
 * `{ written: false }`，由界面给出可读提示，而不是留下一个空文件。
 */
export async function writeLogExport({ source = 'app', logDirectory, destination, snapshot = '' }) {
  const target = resolveLogFile(logDirectory, source);
  let content = null;
  try {
    content = await readFile(target, 'utf8');
  } catch (error) {
    if (error.code !== 'ENOENT') throw error;
  }
  if (content === null) content = typeof snapshot === 'string' ? snapshot : '';
  if (!content) return { written: false, source: target, bytes: 0 };
  await mkdir(path.dirname(destination), { recursive: true });
  await writeFile(destination, content, 'utf8');
  return { written: true, source: target, bytes: Buffer.byteLength(content, 'utf8') };
}

/** 「打开日志」的目标：文件存在就定位文件，否则退回日志目录。 */
export async function logRevealTarget(logDirectory, source = 'app') {
  const target = resolveLogFile(logDirectory, source);
  try {
    const info = await stat(target);
    if (info.isFile()) return { kind: 'file', path: target };
  } catch (error) {
    if (error.code !== 'ENOENT') throw error;
  }
  return { kind: 'directory', path: logDirectory };
}
