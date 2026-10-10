// Agent 页的纯展示逻辑：不依赖 React，便于 node:test 直接覆盖。

/**
 * 工具卡片状态文案。后端拒绝/超时/项目变化都会落成 failed，
 * 这里按 code 区分，避免用户把「已拒绝」误读成执行出错。
 */
export function toolStatusInfo(tool) {
  const status = tool?.status;
  const code = String(tool?.code ?? '');
  if (status === 'running') return { label: '执行中', tone: 'running' };
  if (status === 'done') return { label: '已完成', tone: 'done' };
  if (status === 'cancelled' || code === 'USER_CANCELLED') return { label: '已取消', tone: 'cancelled' };
  if (code === 'CONFIRMATION_TIMEOUT') return { label: '确认超时', tone: 'cancelled' };
  if (code === 'CONFIRMATION_STALE') return { label: '项目已变化', tone: 'cancelled' };
  return { label: '失败', tone: 'failed' };
}

/** 对齐 ProjectPaths._language_from_tl_path：取最近的 tl/<语言> 目录名，路径不含 tl 时返回空串。 */
export function languageFromTlPath(path) {
  const parts = String(path ?? '').split(/[\\/]/).filter(Boolean);
  for (let index = parts.length - 2; index >= 0; index -= 1) {
    if (parts[index].toLowerCase() === 'tl') return parts[index + 1];
  }
  return '';
}
