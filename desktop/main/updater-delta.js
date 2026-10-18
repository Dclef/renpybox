/**
 * 桌面增量包选择与应用器拉起。
 *
 * 增量包是相对某一版安装生成的，文件名里必须带基线版本：
 * `RenpyBox-<version>-from-<base>-x64.delta.zip`。
 * 只挑基线等于当前运行版本的增量包，跨版本升级直接走全量安装包，
 * 否则会把旧版文件和新版文件混在一起。
 *
 * 安装目录里的 RenpyBox.exe 会被补丁自己覆盖，所以先把当前 exe 复制到临时目录再执行。
 * copyFile / spawn 可注入，便于单测不碰真实安装目录。
 */
import { spawn as defaultSpawn } from 'node:child_process';
import { copyFile as defaultCopyFile, mkdir, readdir, rm } from 'node:fs/promises';
import path from 'node:path';

import { compareDesktopVersions, desktopVersionString } from './updater-release.js';

/** 增量包的规范文件名：目标版本 + 基线版本。 */
export function deltaAssetName(version, baseVersion) {
  return `RenpyBox-${version}-from-${baseVersion}-x64.delta.zip`.toLowerCase();
}

/** 找到能从 `currentVersion` 直接升级到发布版本的增量包。没有则返回 null。 */
export function selectDeltaAsset(release, { currentVersion } = {}) {
  const version = desktopVersionString(release?.tag_name);
  const base = desktopVersionString(currentVersion);
  if (!version || !base) return null;
  if (compareDesktopVersions(version, currentVersion) <= 0) return null;
  const expectedName = deltaAssetName(version, base);
  const assets = Array.isArray(release?.assets) ? release.assets : [];
  return assets.find(asset => (
    String(asset?.name ?? '').toLowerCase() === expectedName
    && Number.isSafeInteger(asset?.size) && asset.size > 0
    && /^https?:\/\//i.test(String(asset?.browser_download_url ?? ''))
  )) ?? null;
}

function waitUntilSpawned(child) {
  if (!child || typeof child.once !== 'function') {
    child?.unref?.();
    return Promise.resolve();
  }
  return new Promise((resolve, reject) => {
    child.once('error', reject);
    child.once('spawn', () => {
      child.unref?.();
      resolve();
    });
  });
}

/** 清掉上一次更新留下的应用器副本（每版一个 240MB 的 exe，不清理会越堆越多）。 */
async function removeStaleCopies(tempDir, readdirImpl, rmImpl) {
  try {
    const names = await readdirImpl(tempDir);
    await Promise.all(names
      .filter(name => /^RenpyBoxUpdate_.*\.exe$/i.test(name))
      .map(name => rmImpl(path.join(tempDir, name), { force: true }).catch(() => {})));
  } catch {
    // 临时目录不存在或无权限时不影响本次更新。
  }
}

/**
 * 复制 electron 可执行文件和 update-apply.mjs 到临时目录，再以 node 模式拉起。
 * 返回时子进程已 detach。
 */
export async function spawnDeltaApplier({
  electronExe,
  scriptPath,
  patchPath,
  installDir,
  appExe,
  pid,
  baseVersion,
  relaunch = false,
  tempDir,
  copyFile = defaultCopyFile,
  spawn = defaultSpawn,
  readdir: readdirImpl = readdir,
  rm: rmImpl = rm,
  now = Date.now,
} = {}) {
  if (!tempDir) throw Object.assign(new Error('缺少增量更新临时目录'), { kind: 'install' });
  if (!baseVersion) throw Object.assign(new Error('缺少增量包基线版本'), { kind: 'install' });
  await mkdir(tempDir, { recursive: true });
  await removeStaleCopies(tempDir, readdirImpl, rmImpl);
  const copiedExe = path.join(tempDir, `RenpyBoxUpdate_${pid}_${now()}.exe`);
  const copiedScript = path.join(tempDir, 'update-apply.mjs');
  await copyFile(electronExe, copiedExe);
  await copyFile(scriptPath, copiedScript);
  const child = spawn(copiedExe, [
    copiedScript,
    '--patch', patchPath,
    '--install-dir', installDir,
    '--app-exe', appExe,
    '--pid', String(pid),
    '--base-version', baseVersion,
    '--relaunch', relaunch ? '1' : '0',
  ], {
    detached: true,
    stdio: 'ignore',
    env: { ...process.env, ELECTRON_RUN_AS_NODE: '1' },
  });
  try {
    await waitUntilSpawned(child);
  } catch (error) {
    throw Object.assign(error, { kind: 'install' });
  }
  return { child, copiedExe };
}
