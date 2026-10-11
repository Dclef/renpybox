/**
 * 网页端更新状态文案与操作可见性 —— 对齐 Qt5 AppSettingsPage.refresh_update_ui。
 * 纯函数，供 SettingsPage 与 node:test 共用，避免把状态机写进组件里难测。
 */

/** @param {string} tag */
export function displayVersion(tag) {
  const match = /^(?:RenpyBox_)?v?(\d+(?:\.\d+){2,3})$/.exec(String(tag || '').trim());
  return match ? `v${match[1]}` : String(tag || '');
}

/** @param {number} size */
export function formatMegabytes(size) {
  const value = Number(size);
  const bytes = Number.isFinite(value) ? Math.max(0, value) : 0;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/**
 * @param {{
 *   status?: string,
 *   latest?: { tag_name?: string },
 *   downloaded_size?: number,
 *   total_size?: number,
 *   error?: string,
 *   new_version?: boolean,
 *   can_install?: boolean,
 * }} update
 * @param {boolean} checking
 */
export function resolveWebUpdateUi(update, checking = false) {
  const status = String(update?.status || 'NONE');
  const latest = update?.latest && typeof update.latest === 'object' ? update.latest : {};
  const tag = displayVersion(String(latest.tag_name || ''));
  const downloaded = Number(update?.downloaded_size) || 0;
  const total = Number(update?.total_size) || 0;
  const progress = Math.max(0, Math.min(100, Math.round((downloaded / Math.max(1, total)) * 100)));
  const showProgress = status === 'UPDATING';
  const showCancel = status === 'UPDATING';
  const showInstall = status === 'DOWNLOADED' || Boolean(update?.can_install);
  // 与 Qt `_known_update_available` + status==NEW_VERSION 一致；已可安装时不再展示下载入口
  const offerUpdate = !showInstall && (
    status === 'NEW_VERSION' || (status === 'NONE' && Boolean(update?.new_version))
  );

  let statusText = '尚未检查更新';
  if (checking) {
    statusText = '检查中…';
  } else if (status === 'NEW_VERSION') {
    statusText = `发现新版本 ${tag}`.trim();
  } else if (status === 'UPDATING') {
    statusText = `正在下载 ${formatMegabytes(downloaded)} / ${formatMegabytes(total)}`;
  } else if (status === 'DOWNLOADED' || update?.can_install) {
    statusText = '下载完成，重启后生效';
  } else if (offerUpdate) {
    statusText = `发现新版本 ${tag}`.trim();
  } else if (String(update?.error || '').trim()) {
    statusText = '检查更新失败，请重试';
  } else if (latest.tag_name) {
    statusText = '已是最新版本';
  }

  return {
    status,
    statusText,
    progress,
    offerUpdate,
    showProgress,
    showCancel,
    showInstall,
    tag,
  };
}
