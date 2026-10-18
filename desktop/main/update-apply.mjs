/**
 * 文件级增量包应用器。由 RenpyBox.exe 以 ELECTRON_RUN_AS_NODE=1 拉起，
 * 主进程退出后再改安装目录，避免覆盖正在运行的 exe。
 *
 * 只依赖 Node 标准库。核心校验与提交是纯函数，测试不必走 zip 二进制。
 */
import { createHash } from 'node:crypto';
import { spawn } from 'node:child_process';
import { createReadStream, createWriteStream } from 'node:fs';
import { appendFile, chmod, copyFile, mkdir, open, readFile, readdir, rename, rm, stat, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { Transform } from 'node:stream';
import { pipeline } from 'node:stream/promises';
import { fileURLToPath } from 'node:url';
import { createInflateRaw } from 'node:zlib';

export const FORMAT_PATCH = 'renpybox-patch/1';
export const FORMAT_MANIFEST = 'renpybox-update-manifest/1';
export const PATCH_META_NAME = '_patch_meta.json';
export const MANIFEST_NAME = '_update_manifest.json';
const STAGING_DIR_NAME = '_update_staging';
const ERROR_NAME = '_update_error.json';
const LOG_NAME = '_update_apply.log';
const PID_WAIT_MS = 120_000;
const RESERVED_FILE_NAMES = new Set([PATCH_META_NAME, MANIFEST_NAME]);

const failure = (message, code = 'APPLY') => Object.assign(new Error(message), { code });

/** 安装目录内的相对 POSIX 路径。拒绝绝对路径、`..`、盘符、反斜杠和用户数据。 */
export function normalizePatchPath(value) {
  if (typeof value !== 'string' || value.length === 0) throw failure(`非法更新路径：${value}`);
  if (value.includes('\\')) throw failure(`非法更新路径（反斜杠）：${value}`);
  if (value.startsWith('/')) throw failure(`非法更新路径（绝对路径）：${value}`);
  if (/^[A-Za-z]:/.test(value) || value.includes(':')) throw failure(`非法更新路径（盘符）：${value}`);
  const parts = value.split('/');
  if (parts.some(part => part === '' || part === '.' || part === '..')) {
    throw failure(`非法更新路径：${value}`);
  }
  if (parts[0].toLowerCase() === 'storage') throw failure(`拒绝用户数据路径：${value}`);
  return value;
}

function assertEntry(rel, entry) {
  if (!entry || typeof entry !== 'object') throw failure(`文件记录无效：${rel}`);
  if (!Number.isSafeInteger(entry.size) || entry.size < 0) throw failure(`文件大小无效：${rel}`);
  if (!/^[a-f0-9]{64}$/i.test(String(entry.sha256 ?? ''))) throw failure(`文件校验值无效：${rel}`);
}

function assertPathList(values, label) {
  if (!Array.isArray(values)) throw failure(`${label}必须是数组`);
  const seen = new Set();
  const paths = [];
  for (const value of values) {
    const rel = normalizePatchPath(value);
    if (RESERVED_FILE_NAMES.has(rel)) throw failure(`拒绝协议文件：${rel}`);
    const key = rel.toLowerCase();
    if (seen.has(key)) throw failure(`路径重复：${rel}`);
    seen.add(key);
    paths.push(rel);
  }
  return paths;
}

/** 校验 `_patch_meta.json`。通过后返回规范化副本。 */
export function parsePatchMeta(meta) {
  if (!meta || typeof meta !== 'object') throw failure('补丁元数据无效');
  if (meta.format !== FORMAT_PATCH) throw failure(`补丁格式无效：${meta.format}`);
  if (typeof meta.version !== 'string' || !meta.version) throw failure('补丁版本无效');
  if (typeof meta.base_version !== 'string' || !meta.base_version) throw failure('补丁基线版本无效');
  if (!meta.files || typeof meta.files !== 'object' || Array.isArray(meta.files)) throw failure('补丁文件表无效');
  const deleted = assertPathList(meta.deleted, '删除列表');
  const files = {};
  const fileKeys = new Set();
  for (const [raw, entry] of Object.entries(meta.files)) {
    const rel = normalizePatchPath(raw);
    if (RESERVED_FILE_NAMES.has(rel)) throw failure(`拒绝协议文件：${rel}`);
    const key = rel.toLowerCase();
    if (fileKeys.has(key) || deleted.some(item => item.toLowerCase() === key)) throw failure(`路径重复：${rel}`);
    assertEntry(rel, entry);
    fileKeys.add(key);
    files[rel] = { size: entry.size, sha256: String(entry.sha256).toLowerCase() };
  }
  const manifest = meta.manifest;
  if (!manifest || typeof manifest !== 'object') throw failure('目标清单无效');
  if (manifest.format !== FORMAT_MANIFEST || manifest.version !== meta.version) {
    throw failure('目标清单与补丁版本不一致');
  }
  return {
    format: meta.format,
    version: meta.version,
    base_version: meta.base_version,
    files,
    deleted,
    manifest,
  };
}

function insideRoot(root, rel) {
  const target = path.resolve(root, ...normalizePatchPath(rel).split('/'));
  const relative = path.relative(path.resolve(root), target);
  if (relative === '' || relative.startsWith('..') || path.isAbsolute(relative)) {
    throw failure(`路径越出安装目录：${rel}`);
  }
  return target;
}

async function fileDigest(filePath) {
  const hash = createHash('sha256');
  let size = 0;
  await pipeline(createReadStream(filePath), new Transform({
    transform(chunk, _encoding, callback) {
      size += chunk.length;
      hash.update(chunk);
      callback();
    },
  }));
  return { size, sha256: hash.digest('hex') };
}

/** 逐个核对暂存文件的大小和 sha256。任一不符即抛错，调用方不得提交。 */
export async function verifyStagedFiles(stagingDir, files) {
  for (const [rel, entry] of Object.entries(files)) {
    assertEntry(rel, entry);
    const filePath = insideRoot(stagingDir, rel);
    let digest;
    try {
      digest = await fileDigest(filePath);
    } catch (error) {
      throw failure(`暂存文件缺失：${rel}（${error.message}）`, 'HASH_MISMATCH');
    }
    if (digest.size !== entry.size || digest.sha256 !== String(entry.sha256).toLowerCase()) {
      throw failure(`文件校验失败：${rel}`, 'HASH_MISMATCH');
    }
  }
}

async function makeWritable(filePath) {
  try {
    const info = await stat(filePath);
    if ((info.mode & 0o200) === 0) await chmod(filePath, info.mode | 0o200);
  } catch (error) {
    if (error?.code !== 'ENOENT') throw error;
  }
}

/** Windows 上 rename 不能覆盖已存在文件，先去掉只读再删掉目标。 */
async function replaceFile(from, to, renameFile, rmFile) {
  await makeWritable(to);
  try {
    await renameFile(from, to);
    return;
  } catch (error) {
    if (!['EPERM', 'EEXIST', 'EACCES', 'EBUSY'].includes(error?.code)) throw error;
  }
  // ponytail: 最多 5 次。Windows 在进程刚退出时仍可能短暂锁文件；仍失败则交给全量安装包。
  let lastError;
  for (let attempt = 0; attempt < 5; attempt += 1) {
    try {
      await makeWritable(to);
      await rmFile(to, { force: true });
      await renameFile(from, to);
      return;
    } catch (error) {
      lastError = error;
      if (!['EPERM', 'EEXIST', 'EACCES', 'EBUSY', 'ENOTEMPTY'].includes(error?.code)) throw error;
      await new Promise(resolve => setTimeout(resolve, 100 * (attempt + 1)));
    }
  }
  throw lastError;
}

/**
 * 校验通过后逐个提交：先写 `<target>.new`，再改名覆盖。
 * 全部成功后删除 `deleted`，并写出安装目录清单。
 */
export async function commitStagedFiles({
  installDir,
  stagingDir,
  files,
  deleted = [],
  manifest = null,
  copyFile: copyImpl = copyFile,
  renameFile = rename,
  rmFile = rm,
}) {
  const written = [];
  for (const rel of Object.keys(files)) {
    const staged = insideRoot(stagingDir, rel);
    const target = insideRoot(installDir, rel);
    const next = `${target}.new`;
    try {
      await mkdir(path.dirname(target), { recursive: true });
      await mkdir(path.dirname(next), { recursive: true });
      await copyImpl(staged, next);
      written.push(next);
      await replaceFile(next, target, renameFile, rmFile);
    } catch (error) {
      throw failure(`提交失败：${rel}（${error.message}）`, 'COMMIT');
    }
  }
  for (const rel of deleted) {
    const target = insideRoot(installDir, rel);
    try {
      await makeWritable(target);
      await rmFile(target, { force: true });
    } catch (error) {
      throw failure(`删除旧文件失败：${rel}（${error.message}）`, 'COMMIT');
    }
  }
  if (manifest) {
    const target = path.join(installDir, MANIFEST_NAME);
    const next = `${target}.new`;
    await writeFile(next, JSON.stringify(manifest));
    await replaceFile(next, target, renameFile, rmFile);
  }
  return written;
}

function parseArgs(argv) {
  const out = {};
  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (!token.startsWith('--')) continue;
    out[token.slice(2)] = argv[index + 1];
    index += 1;
  }
  return out;
}

function pidAlive(pid) {
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    return error?.code === 'EPERM';
  }
}

/** 轮询直到 pid 退出。超时抛 WAIT_TIMEOUT，调用方不得改安装文件。 */
export async function waitForPid(pid, {
  timeoutMs = PID_WAIT_MS,
  intervalMs = 200,
  isAlive = pidAlive,
  sleep = ms => new Promise(resolve => setTimeout(resolve, ms)),
  now = Date.now,
} = {}) {
  if (!Number.isSafeInteger(pid) || pid <= 0) throw failure(`无效的进程号：${pid}`);
  const started = now();
  while (isAlive(pid)) {
    if (now() - started >= timeoutMs) throw failure('等待应用退出超时，已中止且未改动文件', 'WAIT_TIMEOUT');
    await sleep(intervalMs);
  }
}

async function readAt(fh, position, length) {
  const buffer = Buffer.alloc(length);
  const { bytesRead } = await fh.read(buffer, 0, length, position);
  if (bytesRead !== length) throw failure('补丁包读取不完整');
  return buffer;
}

function zip64Extra(extra, need) {
  let offset = 0;
  while (offset + 4 <= extra.length) {
    const id = extra.readUInt16LE(offset);
    const size = extra.readUInt16LE(offset + 2);
    const start = offset + 4;
    const end = start + size;
    if (end > extra.length) break;
    if (id === 1) {
      let cursor = start;
      const out = {};
      const take = () => {
        if (cursor + 8 > end) throw failure('zip64 扩展不完整');
        const value = extra.readBigUInt64LE(cursor);
        cursor += 8;
        if (value > BigInt(Number.MAX_SAFE_INTEGER)) throw failure('补丁文件过大');
        return Number(value);
      };
      if (need.uncompressed) out.uncompressed = take();
      if (need.compressed) out.compressed = take();
      if (need.localOffset) out.localOffset = take();
      return out;
    }
    offset = end;
  }
  throw failure('补丁包缺少 zip64 扩展');
}

/** 读取中央目录。只接受存储和 deflate，拒绝加密与符号链接。 */
export async function listZipMembers(zipPath) {
  const fh = await open(zipPath, 'r');
  try {
    const { size } = await fh.stat();
    if (size < 22) throw failure('补丁包不是有效的 zip');
    const tailSize = Math.min(size, 22 + 0xffff);
    const tail = await readAt(fh, size - tailSize, tailSize);
    let eocd = -1;
    for (let index = tail.length - 22; index >= 0; index -= 1) {
      if (tail.readUInt32LE(index) === 0x06054b50) { eocd = index; break; }
    }
    if (eocd < 0) throw failure('补丁包缺少中央目录');
    let count = tail.readUInt16LE(eocd + 10);
    let directorySize = tail.readUInt32LE(eocd + 12);
    let directoryOffset = tail.readUInt32LE(eocd + 16);
    if (count === 0xffff || directorySize === 0xffffffff || directoryOffset === 0xffffffff) {
      if (eocd < 20) throw failure('补丁包缺少 zip64 目录');
      const locator = eocd - 20;
      if (tail.readUInt32LE(locator) !== 0x07064b50) throw failure('补丁包缺少 zip64 定位');
      const recordOffset = Number(tail.readBigUInt64LE(locator + 8));
      const record = await readAt(fh, recordOffset, 56);
      if (record.readUInt32LE(0) !== 0x06064b50) throw failure('补丁包 zip64 目录无效');
      count = Number(record.readBigUInt64LE(32));
      directorySize = Number(record.readBigUInt64LE(40));
      directoryOffset = Number(record.readBigUInt64LE(48));
    }
    const directory = await readAt(fh, directoryOffset, directorySize);
    const members = [];
    let cursor = 0;
    for (let index = 0; index < count; index += 1) {
      if (cursor + 46 > directory.length || directory.readUInt32LE(cursor) !== 0x02014b50) {
        throw failure('补丁包中央目录损坏');
      }
      const flags = directory.readUInt16LE(cursor + 8);
      const method = directory.readUInt16LE(cursor + 10);
      let compressed = directory.readUInt32LE(cursor + 20);
      let uncompressed = directory.readUInt32LE(cursor + 24);
      const nameLength = directory.readUInt16LE(cursor + 28);
      const extraLength = directory.readUInt16LE(cursor + 30);
      const commentLength = directory.readUInt16LE(cursor + 32);
      const externalAttr = directory.readUInt32LE(cursor + 38);
      let localOffset = directory.readUInt32LE(cursor + 42);
      const nameStart = cursor + 46;
      const nameEnd = nameStart + nameLength;
      const extraEnd = nameEnd + extraLength;
      if (extraEnd + commentLength > directory.length) throw failure('补丁包中央目录损坏');
      const name = directory.toString('utf8', nameStart, nameEnd);
      const extra = directory.subarray(nameEnd, extraEnd);
      const need = {
        uncompressed: uncompressed === 0xffffffff,
        compressed: compressed === 0xffffffff,
        localOffset: localOffset === 0xffffffff,
      };
      if (need.uncompressed || need.compressed || need.localOffset) {
        const extended = zip64Extra(extra, need);
        if (need.uncompressed) uncompressed = extended.uncompressed;
        if (need.compressed) compressed = extended.compressed;
        if (need.localOffset) localOffset = extended.localOffset;
      }
      members.push({ name, flags, method, compressed, uncompressed, externalAttr, localOffset });
      cursor = extraEnd + commentLength;
    }
    return members;
  } finally {
    await fh.close();
  }
}

function memberFileName(name) {
  if (name.endsWith('/')) return '';
  return name;
}

export function assertZipMemberNames(members) {
  const seen = new Set();
  for (const member of members) {
    const raw = memberFileName(member.name);
    if (!raw) {
      normalizePatchPath(member.name.slice(0, -1));
      continue;
    }
    const rel = normalizePatchPath(raw);
    const key = rel.toLowerCase();
    if (seen.has(key)) throw failure(`补丁包路径重复：${rel}`);
    seen.add(key);
    if ((member.flags & 1) !== 0) throw failure(`补丁包含加密条目：${rel}`);
    const unixMode = (member.externalAttr >>> 16) & 0xffff;
    if ((unixMode & 0o170000) === 0o120000) throw failure(`补丁包含符号链接：${rel}`);
    if (member.method !== 0 && member.method !== 8) throw failure(`不支持的压缩方式：${rel}`);
  }
}

async function extractMember(zipPath, member, destination) {
  const fh = await open(zipPath, 'r');
  try {
    const local = await readAt(fh, member.localOffset, 30);
    if (local.readUInt32LE(0) !== 0x04034b50) throw failure(`本地文件头无效：${member.name}`);
    const dataOffset = member.localOffset + 30 + local.readUInt16LE(26) + local.readUInt16LE(28);
    await mkdir(path.dirname(destination), { recursive: true });
    if (member.compressed === 0) {
      await writeFile(destination, Buffer.alloc(0));
      return;
    }
    const source = createReadStream(zipPath, { start: dataOffset, end: dataOffset + member.compressed - 1 });
    const output = createWriteStream(destination);
    if (member.method === 0) await pipeline(source, output);
    else await pipeline(source, createInflateRaw(), output);
  } finally {
    await fh.close();
  }
}

/** 只解压 `files` 中列出的成员，其它成员忽略。 */
export async function extractPatchFiles(zipPath, stagingDir, files) {
  const members = await listZipMembers(zipPath);
  assertZipMemberNames(members);
  const byName = new Map();
  for (const member of members) {
    const rel = memberFileName(member.name);
    if (rel) byName.set(rel, member);
  }
  for (const rel of Object.keys(files)) {
    const member = byName.get(rel);
    if (!member) throw failure(`补丁包缺少文件：${rel}`, 'HASH_MISMATCH');
    await extractMember(zipPath, member, insideRoot(stagingDir, rel));
  }
}

/**
 * 增量包只对生成它时的那一版有效。基线对不上就把整个包丢掉，
 * 否则会盖出一个旧文件残留、新文件覆盖的混合安装，还会把错误的清单写成正确。
 */
export async function assertPatchBase({ installDir, baseVersion, meta }) {
  if (baseVersion && meta.base_version !== baseVersion) {
    throw failure(`增量包基线不匹配：补丁基于 ${meta.base_version}，当前 ${baseVersion}`, 'BASE_MISMATCH');
  }
  const manifestPath = path.join(installDir, MANIFEST_NAME);
  let installed;
  try {
    installed = JSON.parse(await readFile(manifestPath, 'utf8'));
  } catch (error) {
    // 0.9.x 的安装包里没有清单，属于正常情况，交给 --base-version 把关。
    if (error?.code === 'ENOENT') return;
    throw failure(`已装清单无法读取：${error.message}`, 'BASE_MISMATCH');
  }
  if (typeof installed?.version === 'string' && installed.version && installed.version !== meta.base_version) {
    throw failure(`已装版本 ${installed.version} 与增量包基线 ${meta.base_version} 不一致`, 'BASE_MISMATCH');
  }
}

export async function readPatchMeta(zipPath) {
  const members = await listZipMembers(zipPath);
  assertZipMemberNames(members);
  const found = members.filter(member => member.name === PATCH_META_NAME);
  if (found.length !== 1) throw failure(`补丁包必须且只能包含一个 ${PATCH_META_NAME}`);
  const stagingParent = path.dirname(zipPath);
  const tempDir = path.join(stagingParent, `.patch-meta-${process.pid}`);
  await mkdir(tempDir, { recursive: true });
  const tempFile = path.join(tempDir, PATCH_META_NAME);
  try {
    await extractMember(zipPath, found[0], tempFile);
    return JSON.parse(await readFile(tempFile, 'utf8'));
  } finally {
    await rm(tempDir, { recursive: true, force: true }).catch(() => {});
  }
}

async function logLine(installDir, message) {
  const line = `[${new Date().toISOString()}] ${message}\n`;
  await appendFile(path.join(installDir, LOG_NAME), line).catch(() => {});
}

async function writeErrorFile(installDir, meta, error) {
  const payload = {
    version: meta?.base_version || '',
    patchVersion: meta?.version || '',
    error: error?.message || String(error),
    at: new Date().toISOString(),
  };
  await writeFile(path.join(installDir, ERROR_NAME), JSON.stringify(payload));
}

/**
 * 重启时要启动安装目录里真实存在的主程序。
 *
 * --app-exe 传进来的是更新前的路径；主程序在 0.9.2 改过名（RenpyBox New UI.exe →
 * RenpyBox.exe），增量包会把旧名删掉，直接启动旧路径会失败。
 */
export async function resolveLaunchExe(installDir, appExe, manifestVersion) {
  const candidates = [];
  if (appExe) candidates.push(appExe);
  const manifestPath = path.join(installDir, MANIFEST_NAME);
  try {
    const manifest = JSON.parse(await readFile(manifestPath, 'utf8'));
    if (manifest?.version === manifestVersion && manifest.files && typeof manifest.files === 'object') {
      for (const rel of Object.keys(manifest.files)) {
        // 只要安装根目录那一层的主程序，resources/ 里的不是入口
        if (!rel.includes('/') && /^renpybox.*\.exe$/i.test(rel)) {
          candidates.push(path.join(installDir, rel));
        }
      }
    }
  } catch { /* 没有清单时退回目录扫描 */ }
  for (const candidate of candidates) {
    try {
      const info = await stat(candidate);
      if (info.isFile()) return candidate;
    } catch { /* 继续找下一个 */ }
  }
  // 最后兜底：扫安装根目录，挑主程序名
  try {
    const entries = await readdir(installDir, { withFileTypes: true });
    const exe = entries
      .filter(entry => entry.isFile() && /^renpybox.*\.exe$/i.test(entry.name))
      .sort((a, b) => a.name.length - b.name.length)[0];
    if (exe) return path.join(installDir, exe.name);
  } catch { /* 安装目录都读不到，只能放弃重启 */ }
  return '';
}

function relaunchApp(appExe) {
  if (!appExe) return;
  const child = spawn(appExe, [], { detached: true, stdio: 'ignore' });
  child.unref();
}

export async function applyPatchCli(argv = process.argv.slice(2)) {
  const args = parseArgs(argv);
  const installDir = args['install-dir'] || '';
  const patch = args.patch || '';
  const appExe = args['app-exe'] || '';
  const baseVersion = args['base-version'] || '';
  const pid = Number(args.pid);
  const shouldRelaunch = args.relaunch === '1';
  let meta = null;
  const relaunch = async () => {
    if (!shouldRelaunch) return;
    // 主程序可能在这次更新里改过名，按安装目录的实际内容决定启动哪个 exe。
    const target = await resolveLaunchExe(installDir, appExe, meta?.version || '');
    if (target) relaunchApp(target);
    else await logLine(installDir, '找不到主程序，未能自动重启');
  };
  const finish = async (code, error) => {
    if (error) {
      await logLine(installDir, `失败：${error.message}`);
      if (error.code !== 'WAIT_TIMEOUT' && installDir) {
        await writeErrorFile(installDir, meta, error).catch(() => {});
        await relaunch();
      }
    } else {
      await relaunch();
    }
    return code;
  };
  try {
    if (!installDir || !patch) throw failure('缺少 --patch 或 --install-dir');
    await logLine(installDir, `开始应用增量包 ${patch}，等待进程 ${pid}`);
    await waitForPid(pid);
    await logLine(installDir, '主进程已退出，开始校验补丁');
    meta = parsePatchMeta(await readPatchMeta(patch));
    await assertPatchBase({ installDir, baseVersion, meta });
    const stagingDir = path.join(installDir, STAGING_DIR_NAME);
    await rm(stagingDir, { recursive: true, force: true });
    await mkdir(stagingDir, { recursive: true });
    try {
      await extractPatchFiles(patch, stagingDir, meta.files);
      await verifyStagedFiles(stagingDir, meta.files);
    } catch (error) {
      await rm(stagingDir, { recursive: true, force: true }).catch(() => {});
      throw error;
    }
    await logLine(installDir, `校验通过，提交 ${Object.keys(meta.files).length} 个文件`);
    await commitStagedFiles({
      installDir,
      stagingDir,
      files: meta.files,
      deleted: meta.deleted,
      manifest: meta.manifest,
    });
    await rm(stagingDir, { recursive: true, force: true });
    await rm(path.join(installDir, ERROR_NAME), { force: true }).catch(() => {});
    await logLine(installDir, `增量更新完成：${meta.version}`);
    return finish(0);
  } catch (error) {
    return finish(1, error);
  }
}

const invoked = process.argv[1] ? path.resolve(process.argv[1]) : '';
if (invoked && invoked === path.resolve(fileURLToPath(import.meta.url))) {
  applyPatchCli().then(code => process.exit(code));
}
