import { spawn } from 'node:child_process';
import { readFile, rm } from 'node:fs/promises';
import path from 'node:path';

import { downloadInstaller } from './updater-download.js';
import { downloadCandidates } from './updater-mirror.js';
import { deltaAssetName, selectDeltaAsset, spawnDeltaApplier as defaultSpawnDeltaApplier } from './updater-delta.js';
import {
  DESKTOP_TAG_PATTERN,
  compareDesktopVersions,
  parseDesktopVersion,
  pickLatestRelease,
  selectInstallerAsset,
} from './updater-release.js';

/**
 * 桌面更新：直接查 GitHub Releases 的桌面发布，只用安装包资产。
 *
 * 有意不使用 electron-updater：那条链路要求每次发布同时上传 blockmap 与 app-update.yml，
 * 这些文件会出现在面向用户的 release 资产里。这里改为自己查 API、自己下载、
 * 自己拉起安装包，所以 release 只需要放 exe 与 zip。
 * 有增量包（RenpyBox-<ver>-x64.delta.zip）时优先文件级更新；下载或拉起失败则回退全量安装包。
 *
 * 发布解析在 updater-release.js（安装包必须与标签版本同名），
 * 下载校验在 updater-download.js（大小 + 逐字节 SHA-256）。
 */

export const DEFAULT_UPDATE_REPO = 'dclef/renpybox';
export { DESKTOP_TAG_PATTERN, compareDesktopVersions, parseDesktopVersion, pickLatestRelease, selectInstallerAsset };
const API_ROOT = 'https://api.github.com';
const USER_AGENT = 'RenpyBox';
const REQUEST_HEADERS = Object.freeze({
  accept: 'application/vnd.github+json',
  'user-agent': USER_AGENT,
  'x-github-api-version': '2022-11-28',
});

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

async function defaultRequestJson(url, fetchImpl = fetch) {
  let response;
  try {
    response = await fetchImpl(url, { headers: REQUEST_HEADERS });
  } catch (error) {
    throw Object.assign(new Error(error?.message || '网络不可用'), { kind: 'network', cause: error });
  }
  if (response.status === 404) throw Object.assign(new Error('仓库或版本不存在'), { kind: 'not-published' });
  if (response.status === 403 || response.status === 429) throw Object.assign(new Error(`GitHub 返回 ${response.status}`), { kind: 'rate-limited' });
  if (!response.ok) throw Object.assign(new Error(`GitHub 返回 ${response.status}`), { kind: 'network' });
  return response.json();
}

/**
 * 默认下载实现：交给 updater-download.js，只有发布资产的大小与 SHA-256
 * 都对得上时才会把文件交给安装流程；注入 downloadFile 的测试可自行决定行为。
 *
 * 直连 GitHub 资产常被墙（objects.githubusercontent.com），这里按候选顺序
 * 依次尝试：直连 → 公共镜像。第一个完整通过校验的即成功。
 */
async function defaultDownloadFile(url, destination, options = {}) {
  const { fetchImpl = fetch, onProgress, signal, expectedSize, expectedDigest } = options;
  const candidates = downloadCandidates(url);
  let lastError;
  for (const candidate of candidates) {
    try {
      return await downloadInstaller(candidate, destination, { fetchImpl, onProgress, signal, expectedSize, expectedDigest });
    } catch (error) {
      lastError = error;
      if (error?.name === 'AbortError') throw error;
    }
  }
  throw lastError ?? Object.assign(new Error('没有可用的下载地址'), { kind: 'download' });
}

/**
 * NSIS 安装参数：把当前安装目录作为默认值传进去。
 *
 * 不传的话安装器永远默认到 `%LOCALAPPDATA%\Programs\RenpyBox`，用户把应用
 * 装在 D 盘更新时会被「搬」到 C 盘，还会留下两份。
 * NSIS 的 /D 必须是最后一个参数，且路径不能带引号（含空格也一样），
 * 所以调用方要用 windowsVerbatimArguments 原样传参。
 */
export function installerArgs(installDir) {
  const dir = typeof installDir === 'string' ? installDir.trim() : '';
  return dir ? [`/D=${dir}`] : [];
}

async function defaultLaunchInstaller(filePath, { installDir = '' } = {}) {
  await new Promise((resolve, reject) => {
    const args = installerArgs(installDir);
    const child = spawn(filePath, args, {
      detached: true,
      stdio: 'ignore',
      // 必须原样传参：Node 默认会给含空格的参数加引号，NSIS 解析不了 /D="C:\a b"。
      windowsVerbatimArguments: args.length > 0,
    });
    child.once('error', error => reject(Object.assign(error, { kind: 'install' })));
    child.once('spawn', () => { child.unref(); resolve(); });
  });
}

/**
 * 读取并清除增量应用器留下的失败记录。
 *
 * 增量包在主进程退出之后才被应用，失败发生在没有 UI 的时刻：应用器只能把
 * 原因写进安装目录的 `_update_error.json`。不读它的话，用户看到的现象是
 * 「点了更新、重启后还是旧版本」，界面上没有任何解释。
 */
export async function readApplyError(installDir) {
  if (!installDir) return null;
  const file = path.join(installDir, '_update_error.json');
  let text;
  try {
    text = await readFile(file, 'utf8');
  } catch {
    return null;
  }
  // 无论解析成功与否都删掉：同一条失败只提示一次。
  await rm(file, { force: true }).catch(() => {});
  try {
    const payload = JSON.parse(text);
    return {
      version: String(payload?.patchVersion ?? ''),
      error: String(payload?.error ?? ''),
    };
  } catch {
    return { version: '', error: '' };
  }
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
  fetchImpl = fetch,
  requestJson = url => defaultRequestJson(url, fetchImpl),
  downloadFile = defaultDownloadFile,
  launchInstaller = defaultLaunchInstaller,
  spawnDeltaApplier = defaultSpawnDeltaApplier,
  deltaScriptPath = '',
  electronExe = process.execPath,
  /** 当前安装目录：更新时作为安装器的默认目标，避免被搬到 C 盘。 */
  installDir = '',
  /** 上一次增量应用留在安装目录里的失败记录；测试可注入。 */
  readApplyError: readApplyErrorImpl = () => readApplyError(installDir),
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
    mode: '',
    deltaAssetName: '',
    deltaAssetUrl: '',
    deltaAssetSize: 0,
    deltaAssetDigest: '',
  };
  let checkPromise;
  let downloadPromise;
  let controller;
  let installerPath = '';
  let installing = false;
  let cancelling = false;
  /** 上一次增量应用失败的版本与原因：只提示一次，之后强制走全量。 */
  let applyFailure = null;

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
        // 上次增量应用失败过的话，先把它捞出来：同一版本不再给增量包，
        // 否则用户会一直重复「下载增量 → 重启 → 还是旧版」。
        .then(() => readApplyErrorImpl())
        .catch(() => null)
        .then(past => {
          applyFailure = past && past.version ? past : null;
          return requestJson(`${API_ROOT}/repos/${repo}/releases?per_page=50`);
        })
        .then(releases => {
          const release = pickLatestRelease(releases, version);
          if (!release) return update({
            status: 'latest', version: '', progress: 0, error: '', releaseNotes: '',
            releaseUrl: `https://github.com/${repo}/releases`,
            mode: '', deltaAssetName: '', deltaAssetUrl: '', deltaAssetSize: 0, deltaAssetDigest: '',
          });
          const asset = selectInstallerAsset(release);
          const nextVersion = String(release.tag_name ?? '').replace(/^v/, '');
          // 同一版本刚失败过增量应用：这次只提示原因，并走全量安装包。
          const skipDelta = Boolean(applyFailure && applyFailure.version === nextVersion);
          const delta = skipDelta ? null : selectDeltaAsset(release, { currentVersion: version });
          return update({
            status: 'available',
            version: nextVersion,
            error: skipDelta ? `上次增量更新失败（${applyFailure.error || '未知原因'}），本次将使用完整安装包` : '',
            progress: 0,
            mode: '',
            releaseNotes: typeof release.body === 'string' ? release.body : '',
            releaseUrl: typeof release.html_url === 'string' && release.html_url ? release.html_url : `https://github.com/${repo}/releases`,
            assetName: String(asset.name ?? ''),
            assetUrl: String(asset.browser_download_url ?? ''),
            assetSize: Number(asset.size) || 0,
            assetDigest: String(asset.digest ?? ''),
            deltaAssetName: delta ? String(delta.name ?? '') : '',
            deltaAssetUrl: delta ? String(delta.browser_download_url ?? '') : '',
            deltaAssetSize: delta ? (Number(delta.size) || 0) : 0,
            deltaAssetDigest: delta ? String(delta.digest ?? '') : '',
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
      if (!assetUrl && !state.deltaAssetUrl) return Promise.reject(new Error('发布版本缺少 Windows 安装包资产。'));
      // 增量包文件名带基线版本；只有基线等于当前版本时 selectDeltaAsset 才会选中它，
      // 跨版本（如 0.9.0 → 0.9.2）一律走全量安装包。
      const deltaFileName = state.deltaAssetUrl
        ? (state.deltaAssetName || deltaAssetName(state.version, state.currentVersion))
        : '';
      cancelling = false;
      controller = new AbortController();
      update({ status: 'downloading', progress: 0, error: '', mode: state.deltaAssetUrl ? 'delta' : 'full' });
      const fetchAsset = (url, name, size, digest, mode) => {
        const destination = path.join(tempDir || '.', name);
        update({ status: 'downloading', progress: 0, error: '', mode });
        return downloadFile(url, destination, {
          fetchImpl,
          signal: controller.signal,
          expectedSize: size,
          expectedDigest: digest,
          onProgress: ({ received, total }) => {
            if (cancelling) return;
            update({ status: 'downloading', progress: total > 0 ? Math.round((received / total) * 100) : 0, mode });
          },
        }).then(result => {
          installerPath = result?.path || destination;
          return update({ status: 'downloaded', progress: 100, error: '', filePath: installerPath, mode });
        });
      };
      downloadPromise = Promise.resolve()
        .then(async () => {
          if (state.deltaAssetUrl) {
            try {
              return await fetchAsset(
                state.deltaAssetUrl,
                deltaFileName,
                state.deltaAssetSize,
                state.deltaAssetDigest,
                'delta',
              );
            } catch (error) {
              if (cancelling || error?.name === 'AbortError') throw error;
              log.error('[update] 增量包下载失败，改下完整安装包', error);
            }
          }
          if (!assetUrl) throw Object.assign(new Error('发布版本缺少 Windows 安装包资产。'), { kind: 'download' });
          return fetchAsset(
            assetUrl,
            state.assetName || `RenpyBox-${state.version}-x64.exe`,
            state.assetSize,
            state.assetDigest,
            'full',
          );
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
        if (state.mode === 'delta') {
          await spawnDeltaApplier({
            electronExe,
            scriptPath: deltaScriptPath,
            patchPath: installerPath,
            installDir,
            appExe: electronExe,
            pid: process.pid,
            baseVersion: state.currentVersion,
            relaunch: true,
            tempDir: tempDir || installDir,
          });
        } else {
          await launchInstaller(installerPath, { installDir });
        }
        // 安装器或增量应用器已拉起，主进程可以走正常退出清理。
        quit();
        return snapshot();
      } catch (error) {
        if (state.mode === 'delta') {
          installing = false;
          installerPath = '';
          try { await afterInstallFailure(); } catch (restartError) { log.error('[update] backend recovery failed', restartError); }
          log.error('[update]', error);
          return update({
            status: 'available',
            mode: '',
            error: '增量更新失败，将回退到完整安装包',
            progress: 0,
            filePath: '',
            deltaAssetName: '',
            deltaAssetUrl: '',
            deltaAssetSize: 0,
            deltaAssetDigest: '',
          });
        }
        installing = false;
        try { await afterInstallFailure(); } catch (restartError) { log.error('[update] backend recovery failed', restartError); }
        return failed(error?.kind ? error : Object.assign(error ?? new Error('未知原因'), { kind: 'install' }));
      }
    },
  };
}
