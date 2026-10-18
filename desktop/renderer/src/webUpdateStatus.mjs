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
 * 说明本次更新是增量还是全量，以及省了多少下载量。
 *
 * 增量包只对生成它的那一版有效：跨版本（如 0.9.0 → 0.9.2）会自动走全量包，
 * 这里如实说明，避免用户以为「增量没生效」是 bug。
 *
 * @param {{
 *   mode?: string,
 *   deltaAssetSize?: number,
 *   assetSize?: number,
 * }} update
 * @returns {{ kind: 'delta' | 'full' | '', savedBytes: number, modeSize: number, fullSize: number }}
 */
export function describeUpdateDelivery(update) {
  const mode = update?.mode === 'delta' ? 'delta' : update?.mode === 'full' ? 'full' : '';
  const deltaSize = Number(update?.deltaAssetSize) || 0;
  const fullSize = Number(update?.assetSize) || 0;
  const savedBytes = mode === 'delta' && deltaSize > 0 && fullSize > deltaSize ? fullSize - deltaSize : 0;
  return {
    kind: /** @type {'delta' | 'full' | ''} */ (mode),
    savedBytes,
    modeSize: mode === 'delta' ? deltaSize : fullSize,
    fullSize,
  };
}

/**
 * @param {{
 *   status?: string,
 *   latest?: { tag_name?: string, delivery?: string },
 *   downloaded_size?: number,
 *   total_size?: number,
 *   error?: string,
 *   new_version?: boolean,
 *   can_install?: boolean,
 *   release_url?: string,
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
  const delivery = String(latest.delivery || '');
  const isDesktopMigration = status === 'DESKTOP_AVAILABLE' || delivery === 'desktop';
  // UPDATING / DOWNLOADED 优先于迁移提示（与后端 busy 契约一致）
  const showProgress = status === 'UPDATING';
  const showCancel = status === 'UPDATING';
  const showInstall = !isDesktopMigration && (status === 'DOWNLOADED' || Boolean(update?.can_install));
  const offerMigration = !showProgress && !showInstall && isDesktopMigration && (
    status === 'DESKTOP_AVAILABLE' || Boolean(update?.new_version)
  );
  // 与 Qt `_known_update_available` + status==NEW_VERSION 一致；迁移与已可安装时不再展示下载入口
  const offerUpdate = !showInstall && !offerMigration && (
    status === 'NEW_VERSION' || (status === 'NONE' && Boolean(update?.new_version))
  );

  let statusText = '尚未检查更新';
  if (checking) {
    statusText = '检查中…';
  } else if (status === 'UPDATING') {
    statusText = `正在下载 ${formatMegabytes(downloaded)} / ${formatMegabytes(total)}`;
  } else if (showInstall) {
    statusText = '下载完成，重启后生效';
  } else if (offerMigration) {
    statusText = `桌面版 ${tag} 已可用`.trim();
  } else if (status === 'NEW_VERSION' || offerUpdate) {
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
    offerMigration,
    showProgress,
    showCancel,
    showInstall,
    tag,
  };
}
