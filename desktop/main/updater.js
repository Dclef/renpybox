import { createRequire } from 'node:module';
const { CancellationToken } = createRequire(import.meta.url)('builder-util-runtime');

/** Explicit desktop update state, independent of the Python ZIP updater. */
export function createDesktopUpdater({ autoUpdater, packaged, version, broadcast, log, beforeInstall }) {
  let state = { status: packaged ? 'idle' : 'dev', packaged, currentVersion: version, version: '', error: '', progress: 0, releaseNotes: '', releaseUrl: 'https://github.com/dclef/RenpyBox/releases' };
  let checkPromise;
  let downloadPromise;
  let cancellationToken;
  let installing = false;
  let cancelling = false;
  const snapshot = () => ({ ...state });
  const update = next => { state = { ...state, ...next }; broadcast(snapshot()); return snapshot(); };
  const failed = error => {
    log.error('[update]', error);
    const message = error?.code === 'ERR_UPDATER_NO_PUBLISHED_VERSIONS'
      ? 'GitHub 尚未发布可用的 New UI 测试版本，发布后可检查更新。'
      : error?.code === 'ERR_UPDATER_CHANNEL_FILE_NOT_FOUND'
        ? '发布版本缺少更新配置，请确认同时上传安装包、blockmap 和 newui.yml。'
        : error?.message || String(error);
    return update({ status: 'error', error: message });
  };
  if (packaged) {
    autoUpdater.autoDownload = false;
    autoUpdater.autoInstallOnAppQuit = false;
    autoUpdater.allowPrerelease = true;
    autoUpdater.channel = 'newui';
    autoUpdater.allowDowngrade = false;
    autoUpdater.logger = log;
    autoUpdater.on('checking-for-update', () => update({ status: 'checking', error: '', progress: 0 }));
    autoUpdater.on('update-available', info => update({ status: 'available', version: info.version, error: '', releaseNotes: typeof info.releaseNotes === 'string' ? info.releaseNotes : '', releaseUrl: `https://github.com/dclef/RenpyBox/releases/tag/v${info.version}` }));
    autoUpdater.on('update-not-available', () => update({ status: 'latest', version: '', error: '', progress: 0 }));
    autoUpdater.on('download-progress', info => { if (!cancelling) update({ status: 'downloading', progress: Math.round(info.percent) }); });
    autoUpdater.on('update-downloaded', info => update({ status: 'downloaded', version: info.version, progress: 100, error: '' }));
    autoUpdater.on('update-cancelled', () => update({ status: 'available', progress: 0, error: '' }));
    autoUpdater.on('error', error => { if (!cancelling) failed(error); });
  }
  return {
    state: snapshot,
    check() {
      if (!packaged || downloadPromise || ['downloaded', 'downloading'].includes(state.status)) return Promise.resolve(snapshot());
      if (checkPromise) return checkPromise;
      checkPromise = Promise.resolve().then(() => autoUpdater.checkForUpdates()).then(snapshot).catch(failed).finally(() => { checkPromise = undefined; });
      return checkPromise;
    },
    download() {
      if (downloadPromise) return downloadPromise;
      if (!packaged || state.status !== 'available') return Promise.reject(new Error('请先检查更新，确认存在可下载的新版本。'));
      cancelling = false;
      const token = new CancellationToken();
      cancellationToken = token;
      update({ status: 'downloading', progress: 0, error: '' });
      downloadPromise = Promise.resolve().then(() => autoUpdater.downloadUpdate(token)).then(snapshot).catch(error => token.cancelled ? update({ status: 'available', progress: 0, error: '' }) : failed(error)).finally(() => { downloadPromise = undefined; cancellationToken = undefined; cancelling = false; });
      return downloadPromise;
    },
    cancel() {
      if (downloadPromise && cancellationToken) {
        cancelling = true;
        cancellationToken.cancel();
      }
      return snapshot();
    },
    async install() {
      if (!packaged || state.status !== 'downloaded') throw new Error('更新尚未下载完成。');
      if (installing) return snapshot();
      installing = true;
      try {
        await beforeInstall();
        autoUpdater.quitAndInstall(false, true);
        return snapshot();
      } catch (error) { installing = false; return failed(error); }
    },
  };
}
