import { spawn } from 'node:child_process';
import path from 'node:path';

import { downloadInstaller } from './updater-download.js';
import { GITHUB_DOWNLOAD_MIRRORS, downloadCandidates } from './updater-mirror.js';
import {
  DESKTOP_TAG_PATTERN,
  compareDesktopVersions,
  parseDesktopVersion,
  pickLatestRelease,
  selectInstallerAsset,
} from './updater-release.js';

/**
 * 桌面更新：直接查 GitHub Releases 的桌面发布，只用完整安装包（exe）。
 *
 * 有意不使用 electron-updater：那条链路要求每次发布同时上传 blockmap 与 app-update.yml，
 * 这些文件会出现在面向用户的 release 资产里。这里改为自己查 API、自己下载、
 * 自己拉起安装包，所以 release 只需要放 exe 与 zip。
 *
 * 更新只有一条路径：下载 `RenpyBox-<ver>-x64.exe` 后拉起 NSIS 安装器，
 * 一步升到最新版。原来的「优先文件级增量包、失败回退全量」已移除：
 * 增量包只覆盖上一版基线，跨版本用不上，应用失败还要再下一次全量，
 * 用户实际体验是白下一次 100MB+ 的增量包。
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
    case 'download': return `下载更新失败：${error.message || '网络中断'}（已下载部分已保留，重试会自动续传）`;
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

/** 首字节超时：候选在这个时间内一个字节都没给，就当作不可用换下一个。 */
const STALL_TIMEOUT_MS = 12000;
/** 同一候选最多尝试几次：第二次还失败就换候选（镜像多，没必要死磕一条）。 */
const MAX_ATTEMPTS = 2;
/** 退避：1s → 2s，封顶 4s。.part 会保留，重试自动走 Range 续传。 */
const backoffMs = attempt => Math.min(4000, 1000 * 2 ** (attempt - 1));

const abortedError = cause => Object.assign(
  new Error(cause?.message || '下载已取消'),
  { name: 'AbortError', cause },
);

/** 候选主机名（只用于文案；解析失败就退回原串）。 */
function hostOf(candidate) {
  try { return new URL(candidate).host; } catch { return String(candidate); }
}

/**
 * 首字节超时的错误：**故意不用 AbortError**。
 * stall 只是「这条镜像不通」，要换候选继续下；而 AbortError 在上层被当成
 * 用户取消（回到 available、不报错），两者混在一起会让卡死的镜像静默失败。
 */
const stallError = (candidate, stallTimeoutMs) => Object.assign(
  new Error(`连接 ${hostOf(candidate)} 在 ${Math.max(1, Math.round(stallTimeoutMs / 1000))} 秒内没有返回任何数据`),
  { kind: 'download', retryable: true, stall: true },
);

/**
 * 默认下载实现：交给 updater-download.js，只有发布资产的大小与 SHA-256
 * 都对得上时才会把文件交给安装流程；注入 downloadFile 的测试可自行决定行为。
 *
 * 候选顺序见 updater-mirror.js：镜像优先，直连兜底。
 *
 * 两条保护，针对国内网络最常见的两种坏情况：
 * 1. **首字节超时**：候选 STALL_TIMEOUT_MS 内没有任何数据就 abort 它、立刻换下一个；
 *    收到第一块数据后撤掉计时器——只限制「多久开始下」，不限制「下多久」，
 *    否则慢速大文件会被误杀。
 * 2. **有限重试**：同一候选最多 MAX_ATTEMPTS 次，退避 1s/2s（封顶 4s）。
 *    中断后 .part 会保留，下一次尝试带 Range 续传，所以重试不会从零重下几百 MB。
 *
 * 用户主动取消（外层 signal）与 stall 必须分开：前者原样抛 AbortError、不重试也不换
 * 候选；后者走内部 controller，只当作这条候选不可用。
 * 403/404 这类换镜像才有用的错误（retryable === false）也立刻跳到下一个候选。
 */
/**
 * 生效的镜像清单：用户在设置页填的优先，没有/非法/空列表则回退内置默认。
 *
 * 注意不能把空数组直接交给 downloadCandidates：那样候选只剩直连一条，
 * 国内会挂满超时，等于把「没配置」当成「不要镜像」。
 */
function resolveMirrors(mirrors) {
  const value = typeof mirrors === 'function' ? mirrors() : mirrors;
  return Array.isArray(value) && value.length > 0 ? value : GITHUB_DOWNLOAD_MIRRORS;
}

/**
 * 从 config.json 读用户配置的更新镜像前缀（纯函数，不依赖 electron，可直接单测）。
 *
 * 只接受 http(s) 且以 / 结尾的字符串前缀；清洗后为空说明「用内置默认」，
 * 返回 null 而不是空数组，避免调用方误当成「一条镜像都不要」。
 */
export function readUpdateMirrors(configPath, readFileSync) {
  if (!configPath) return null;
  try {
    const config = JSON.parse(readFileSync(configPath, 'utf8'));
    const list = config?.update_mirror_urls;
    if (!Array.isArray(list)) return null;
    const cleaned = list
      .filter(item => typeof item === 'string')
      .map(item => item.trim())
      .filter(item => item !== ''
        && (item.startsWith('https://') || item.startsWith('http://'))
        && item.endsWith('/'));
    return cleaned.length > 0 ? cleaned : null;
  } catch {
    return null;
  }
}

export async function downloadWithMirrors(url, destination, options = {}) {
  const {
    fetchImpl = fetch, onProgress, signal, expectedSize, expectedDigest,
    sleepImpl = ms => new Promise(resolve => setTimeout(resolve, ms)),
    stallTimeoutMs = STALL_TIMEOUT_MS,
    // 用户配置的镜像前缀；null/空数组/非数组都回退内置默认。
    mirrors,
    // 开代理时不套镜像：原始地址已由代理出口访问，镜像只会更慢。
    proxyEnabled = false,
  } = options;
  const candidates = proxyEnabled ? [url] : downloadCandidates(url, resolveMirrors(mirrors));
  let lastError;
  for (const candidate of candidates) {
    for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt += 1) {
      if (signal?.aborted) throw abortedError();
      // 每次尝试独占一个内部 controller：stall 走它，用户取消由外层 signal 转发进来。
      const controller = new AbortController();
      const forwardAbort = () => controller.abort();
      signal?.addEventListener?.('abort', forwardAbort, { once: true });
      let stalled = false;
      let started = false;
      const timer = stallTimeoutMs > 0
        ? setTimeout(() => { stalled = true; controller.abort(); }, stallTimeoutMs)
        : null;
      try {
        return await downloadInstaller(candidate, destination, {
          fetchImpl,
          signal: controller.signal,
          expectedSize,
          expectedDigest,
          onProgress: event => {
            if (!started) {
              // 首字节到了就撤掉计时器：剩下的时间不再限制，大文件慢慢下也要下完。
              started = true;
              if (timer !== null) clearTimeout(timer);
            }
            onProgress?.(event);
          },
        });
      } catch (error) {
        lastError = error;
        // 用户主动取消：原样抛出，不重试、也不换候选。
        if (signal?.aborted) throw error?.name === 'AbortError' ? error : abortedError(error);
        // 首字节超时：这条候选不通，立刻换下一个（不计退避）。
        if (stalled) {
          lastError = stallError(candidate, stallTimeoutMs);
          break;
        }
        if (error?.name === 'AbortError') throw error;
        if (error?.retryable === false || attempt === MAX_ATTEMPTS) break;
        await sleepImpl(backoffMs(attempt));
      } finally {
        if (timer !== null) clearTimeout(timer);
        signal?.removeEventListener?.('abort', forwardAbort);
      }
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
  /** 用户配置的镜像列表：每次下载重新读，改完设置无需重启。返回 null 表示用内置默认。 */
  mirrorsFor = () => null,
  /** 网络代理是否开启：每次下载现读，开启时 fetchAsset 不传镜像候选。 */
  proxyEnabledFor = () => false,
  // 裸引用即可：mirrors 由 fetchAsset 每次下载时读取并传进来，
  // 这样注入自定义 downloadFile 的调用方也能拿到用户镜像，不会静默丢配置。
  downloadFile = downloadWithMirrors,
  launchInstaller = defaultLaunchInstaller,
  /** 当前安装目录：更新时作为安装器的默认目标，避免被搬到 C 盘。 */
  installDir = '',
}) {
  let state = {
    status: packaged ? 'idle' : 'dev',
    packaged,
    currentVersion: version,
    version: '',
    error: '',
    progress: 0,
    downloadedBytes: 0,
    totalBytes: 0,
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

  /**
   * 下载安装包并上报进度。
   *
   * 路径只有一个：发布里的完整安装包 exe。落盘位置取临时目录 +
   * 发布资产名（缺失时用规范名），下载结果与校验在 downloadFile 里完成。
   */
  const fetchAsset = async (url, name, size, digest, { signal } = {}) => {
    const destination = path.join(tempDir || '.', name);
    update({ status: 'downloading', progress: 0, downloadedBytes: 0, error: '' });
    const result = await downloadFile(url, destination, {
      fetchImpl,
      signal,
      expectedSize: size,
      expectedDigest: digest,
      // 每次下载现读用户配置（不缓存）：改完设置无需重启。
      // 放在这里而不是包装默认 downloadFile：注入的下载实现同样能拿到。
      mirrors: mirrorsFor(),
      proxyEnabled: proxyEnabledFor(),
      onProgress: ({ received, total }) => {
        if (cancelling) return;
        // 进度条之外还要给出「已下载 / 总大小」，用户才能判断还要等多久。
        update({
          status: 'downloading',
          progress: total > 0 ? Math.round((received / total) * 100) : 0,
          downloadedBytes: Math.max(0, Number(received) || 0),
          totalBytes: total > 0 ? Number(total) : (Number(size) || 0),
        });
      },
    });
    installerPath = result?.path || destination;
    return update({
      status: 'downloaded',
      progress: 100,
      downloadedBytes: Number(state.totalBytes) || Number(size) || 0,
      filePath: installerPath,
    });
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
          if (!release) return update({
            status: 'latest', version: '', progress: 0, error: '', releaseNotes: '',
            releaseUrl: `https://github.com/${repo}/releases`,
          });
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
            totalBytes: Number(asset.size) || 0,
            downloadedBytes: 0,
            assetDigest: String(asset.digest ?? ''),
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
      cancelling = false;
      controller = new AbortController();
      const signal = controller.signal;
      downloadPromise = fetchAsset(
        assetUrl,
        state.assetName || `RenpyBox-${state.version}-x64.exe`,
        state.assetSize,
        state.assetDigest,
        { signal },
      )
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
        await launchInstaller(installerPath, { installDir });
        // 安装器已拉起，主进程可以走正常退出清理。
        quit();
        return snapshot();
      } catch (error) {
        // 安装器没拉起来：把后端拉回可用状态，并把失败原因交回界面。
        try { await afterInstallFailure(); } catch (restartError) { log.error('[update] backend recovery failed', restartError); }
        return failed(error?.kind ? error : Object.assign(error ?? new Error('未知原因'), { kind: 'install' }));
      } finally {
        installing = false;
      }
    },
  };
}
