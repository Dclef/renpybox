/**
 * 更新提示用的纯函数（可被 node --test 直接导入，不依赖 React）。
 */

/** 取更新日志里第一个版本段落，避免把整份 CHANGELOG 塞进弹窗。 */
export function latestChangelogSection(markdown) {
  const text = String(markdown ?? '');
  const start = text.indexOf('## ');
  if (start < 0) return text.trim();
  const rest = text.slice(start);
  const next = rest.indexOf('\n## ', 1);
  return (next < 0 ? rest : rest.slice(0, next)).trim();
}

/**
 * 判断是否要弹「发现新版本」。
 *
 * 只有：安装版 + 状态为 available + 有版本号 + 该版本没被用户忽略过。
 * dismissed 存的是用户点过「稍后再说」的版本号。
 */
export function shouldOfferUpdate(update, dismissed = '') {
  if (!update || update.packaged !== true) return false;
  if (update.status !== 'available') return false;
  const version = String(update.version ?? '').trim();
  if (!version) return false;
  return version !== String(dismissed ?? '').trim();
}

/**
 * 是否需要弹「已更新到 x.y.z」。
 *
 * previous 是上次运行记录的版本；没有记录（首次运行）不算更新，
 * 与当前版本相同也不算。
 */
export function shouldAnnounceUpdate(previous, current) {
  const from = String(previous ?? '').trim();
  const to = String(current ?? '').trim();
  if (!to) return false;
  return from !== '' && from !== to;
}
