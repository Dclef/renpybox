/** 代码格式化页：状态路径与默认选项。 */

export function formatterStatusPath(folder) {
  const value = String(folder || '').trim();
  if (!value) return '/api/formatter';
  return `/api/formatter?folder=${encodeURIComponent(value)}`;
}

export const FORMATTER_DEFAULTS = {
  preserveComments: true,
  fixIndent: true,
  removeTrailing: true,
};

/** 提交用的 owner 快照：有绑定则用 status.owner_project_key，未绑定为空。 */
export function formatterOwnerProjectKey(status) {
  return String(status?.owner_project_key ?? '').trim();
}

/**
 * @param {{ success_count?: number, failed_files?: string[] } | null | undefined} result
 * @param {'ZH'|'EN'} lang
 */
export function formatFormatterSummary(result, lang = 'ZH') {
  if (!result) return '';
  const ok = Number(result.success_count ?? 0);
  const failed = Array.isArray(result.failed_files) ? result.failed_files.length : 0;
  if (lang === 'EN') {
    let text = `Successfully processed ${ok} RPY file(s)`;
    if (failed) text += `; ${failed} failed`;
    return text;
  }
  let text = `成功处理 ${ok} 个 RPY`;
  if (failed) text += `；${failed} 个失败`;
  return text;
}
