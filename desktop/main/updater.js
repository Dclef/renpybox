import { spawn } from 'node:child_process';
import { createWriteStream } from 'node:fs';
import { mkdir, rename, rm } from 'node:fs/promises';
import path from 'node:path';
import { Readable, Transform } from 'node:stream';
import { pipeline } from 'node:stream/promises';

/**
 * 桌面更新：直接查 GitHub Releases 的桌面发布，只用安装包资产。
 *
 * 有意不使用 electron-updater：那条链路要求每次发布同时上传 blockmap 与 newui.yml，
 * 这两个文件会出现在面向用户的 release 资产里。这里改为自己查 API、自己下载、
 * 自己拉起安装包，所以 release 只需要放 exe 与 zip。
 * 代价：没有差分（block-level）下载，每次更新都是全量安装包。
 */

export const DEFAULT_UPDATE_REPO = 'dclef/renpybox';
export const DESKTOP_TAG_PATTERN = /^v?(\d+)\.(\d+)\.(\d+)(?:-newui\.(\d+))?$/;
const INSTALLER_PATTERN = /^RenpyBox-NewUI-.+-x64[.]exe$/i;
const API_ROOT = 'https://api.github.com';
const USER_AGENT = 'RenpyBox-NewUI';
const REQUEST_HEADERS = Object.freeze({
  accept: 'application/vnd.github+json',
  'user-agent': USER_AGENT,
  'x-github-api-version': '2022-11-28',
});

/** 支持正式版和旧 New UI 测试版；Qt 发布的 RenpyBox_v* 标签不属于桌面更新。 */
export function parseDesktopVersion(value) {
  const match = DESKTOP_TAG_PATTERN.exec(String(value ?? '').trim());
  if (!match) return null;
  return { major: Number(match[1]), minor: Number(match[2]), patch: Number(match[3]), build: match[4] === undefined ? null : Number(match[4]) };
}

/** 版本比较：left 更新返回正数。无法解析的一侧视为更旧。 */
export function compareDesktopVersions(left, right) {
  const a = parseDesktopVersion(left);
  const b = parseDesktopVersion(right);
  if (!a && !b) return 0;
  if (!a) return -1;
  if (!b) return 1;
  for (const key of ['major', 'minor', 'patch']) {
    if (a[key] !== b[key]) return a[key] > b[key] ? 1 : -1;
  }
  if (a.build === b.build) return 0;
  if (a.build === null) return 1;
  if (b.build === null) return -1;
  return a.build > b.build ? 1 : -1;
}

/** 发布里的 Windows x64 安装包（zip / blockmap 一律忽略）。 */
export function selectInstallerAsset(release) {
  const assets = Array.isArray(release?.assets) ? release.assets : [];
  return assets.find(asset => INSTALLER_PATTERN.test(String(asset?.name ?? ''))) ?? null;
}

/** 正式版只接收正式发布；测试版也能升级到正式版。 */
export function pickLatestRelease(releases, currentVersion) {
  const stable = parseDesktopVersion(currentVersion)?.build === null;
  const candidates = (Array.isArray(releases) ? releases : [])
    .filter(release => release && release.draft !== true)
    .filter(release => parseDesktopVersion(release.tag_name) && selectInstallerAsset(release))
    .filter(release => !stable || (release.prerelease !== true && parseDesktopVersion(release.tag_name).build === null))
    .filter(release => compareDesktopVersions(release.tag_name, currentVersion) > 0);
  return candidates.sort((a, b) => compareDesktopVersions(b.tag_name, a.tag_name))[0] ?? null;
}

/** 把内部错误翻译成界面上能直接看的文案。 */
export function friendlyUpdateError(error) {
  switch (error?.kind) {
    case 'not-published': return 'GitHub 尚未发布可用的桌面版本，发布后可检查更新。';
    case 'rate-limited': return 'GitHub 接口访问受限（可能触发频率限制），请稍后重试。';
    case 'network': return `无法连接 GitHub：${error.message || '网络不可用'}`;
    case 'download': return `下载更新失败：${error.message || '网络中断'}`;
    case 'install': return `启动安装程序失败：${error.message || '未知原因'}`;
    default: return error?.message || '更新失败，请重试。';
  }
}

async function defaultRequestJson(url) {
  let response;
  try {
    response = await fetch(url, { headers: REQUEST_HEADERS });
  } catch (error) {
    throw Object.assign(new Error(error?.message || '网络不可用'), { kind: 'network', cause: error });
  }
  if (response.status === 404) throw Object.assign(new Error('仓库或版本不存在'), { kind: 'not-published' });
  if (response.status === 403 || response.status === 429) throw Object.assign(new Error(`GitHub 返回 ${response.status}`), { kind: 'rate-limited' });
  if (!response.ok) throw Object.assign(new Error(`GitHub 返回 ${response.status}`), { kind: 'network' });
  return response.json();
}

async function defaultDownloadFile(url, destination, { onProgress, signal } = {}) {
  const directory = path.dirname(destination);
  if (directory) await mkdir(directory, { recursive: true });
  const partial = `${destination}.part`;
  let response;
  try {
    response = await fetch(url, { headers: { 'user-agent': USER_AGENT }, signal });
  } catch (error) {
    throw Object.assign(new Error(error?.message || '网络不可用'), { kind: 'network', cause: error });
  }
  if (!response.ok) throw Object.assign(new Error(`GitHub 返回 ${response.status}`), { kind: 'download' });
  const total = Number(response.headers.get('content-length') || 0);
  let received = 0;
  const counter = new Transform({
    transform(chunk, _encoding, callback) {
      received += chunk.length;
      onProgress?.({ received, total });
      callback(null, chunk);
    },
  });
  try {
    await pipeline(Readable.fromWeb(response.body), counter, createWriteStream(partial));
    await rename(partial, destination);
  } catch (error) {
    await rm(partial, { force: true }).catch(() => {});
    if (error?.kind) throw error;
    throw Object.assign(new Error(error?.message || '写入文件失败'), { kind: 'download', cause: error });
  }
  return { path: destination, size: received, total };
}

async function defaultLaunchInstaller(filePath) {
  await new Promise((resolve, reject) => {
    const child = spawn(filePath, [], { detached: true, stdio: 'ignore' });
    child.once('error', error => reject(Object.assign(error, { kind: 'install' })));
    child.once('spawn', () => { child.unref(); resolve(); });
  });
}

/**
 * 显式维护桌面更新状态，状态字段与旧实现保持一致，
 * 渲染端（应用设置）与壳窗口（update-dialog）都直接读这套字段。
 */
export function createDesktopUpdater({
  packaged,
  version,
  broadcast = () => {},
  log = console,
  beforeInstall = async () => {},
  afterInstallFailure = async () => {},
  quit = () => {},
  tempDir = '',
  repo = DEFAULT_UPDATE_REPO,
  requestJson = defaultRequestJson,
  downloadFile = defaultDownloadFile,
  launchInstaller = defaultLaunchInstaller,
}) {
  let state = {
    status: packaged ? 'idle' : 'dev',
    packaged,
    currentVersion: version,
    version: '',
    error: '',
    progress: 0,
    releaseNotes: '',
    releaseUrl: `https://github.com/${repo}/releases`,
  };
  let checkPromise;
  let downloadPromise;
  let controller;
  let installerPath = '';
  let installing = false;
  let cancelling = false;

  const snapshot = () => ({ ...state });
  const update = next => { state = { ...state, ...next }; broadcast(snapshot()); return snapshot(); };
  const failed = error => {
    log.error('[update]', error);
    return update({ status: 'error', error: friendlyUpdateError(error) });
  };

  return {
    state: snapshot,
    check() {
      if (!packaged) return Promise.resolve(snapshot());
      if (downloadPromise || ['downloading', 'downloaded'].includes(state.status)) return Promise.resolve(snapshot());
      if (checkPromise) return checkPromise;
      update({ status: 'checking', error: '', progress: 0 });
      checkPromise = Promise.resolve()
        .then(() => requestJson(`${API_ROOT}/repos/${repo}/releases?per_page=50`))
        .then(releases => {
          const release = pickLatestRelease(releases, version);
          if (!release) return update({ status: 'latest', version: '', progress: 0, error: '', releaseNotes: '', releaseUrl: `https://github.com/${repo}/releases` });
          const asset = selectInstallerAsset(release);
          return update({
            status: 'available',
            version: String(release.tag_name ?? '').replace(/^v/, ''),
            error: '',
            progress: 0,
            releaseNotes: typeof release.body === 'string' ? release.body : '',
            releaseUrl: typeof release.html_url === 'string' && release.html_url ? release.html_url : `https://github.com/${repo}/releases`,
            assetName: String(asset.name ?? ''),
            assetUrl: String(asset.browser_download_url ?? ''),
            assetSize: Number(asset.size) || 0,
          });
        })
        .catch(failed)
        .finally(() => { checkPromise = undefined; });
      return checkPromise;
    },
    download() {
      if (downloadPromise) return downloadPromise;
      if (!packaged) return Promise.reject(new Error('开发模式不下载应用更新，请使用安装版测试。'));
      if (state.status !== 'available') return Promise.reject(new Error('请先检查更新，确认存在可下载的新版本。'));
      const assetUrl = state.assetUrl;
      if (!assetUrl) return Promise.reject(new Error('发布版本缺少 Windows 安装包资产。'));
      const assetName = state.assetName || `RenpyBox-NewUI-${state.version}-x64.exe`;
      const destination = path.join(tempDir || '.', assetName);
      cancelling = false;
      controller = new AbortController();
      update({ status: 'downloading', progress: 0, error: '' });
      downloadPromise = Promise.resolve()
        .then(() => downloadFile(assetUrl, destination, {
          signal: controller.signal,
          onProgress: ({ received, total }) => {
            if (cancelling) return;
            update({ status: 'downloading', progress: total > 0 ? Math.round((received / total) * 100) : 0 });
          },
        }))
        .then(result => {
          installerPath = result?.path || destination;
          return update({ status: 'downloaded', progress: 100, error: '', filePath: installerPath });
        })
        .catch(error => (cancelling || error?.name === 'AbortError'
          ? update({ status: 'available', progress: 0, error: '' })
          : failed(error)))
        .finally(() => { downloadPromise = undefined; controller = undefined; cancelling = false; });
      return downloadPromise;
    },
    cancel() {
      if (downloadPromise && controller) {
        cancelling = true;
        controller.abort();
      }
      return snapshot();
    },
    async install() {
      if (!packaged) throw new Error('开发模式不安装应用更新，请使用安装版测试。');
      if (state.status !== 'downloaded' || !installerPath) throw new Error('更新尚未下载完成。');
      if (installing) return snapshot();
      installing = true;
      try {
        await beforeInstall();
        await launchInstaller(installerPath);
        // The installer was launched successfully; the main process can now
        // continue through its normal shutdown cleanup.
        quit();
        return snapshot();
      } catch (error) {
        installing = false;
        try { await afterInstallFailure(); } catch (restartError) { log.error('[update] backend recovery failed', restartError); }
        return failed(error?.kind ? error : Object.assign(error ?? new Error('未知原因'), { kind: 'install' }));
      }
    },
  };
}
