/** 错误修复页：状态路径与摘要文案（中英就地双语）。 */

/**
 * @param {string} folder
 * @returns {string}
 */
export function errorRepairStatusPath(folder) {
  const value = String(folder || '').trim();
  if (!value) return '/api/error-repair';
  return `/api/error-repair?folder=${encodeURIComponent(value)}`;
}

/**
 * @param {{ total_issues?: number, affected_files?: number, report?: Record<string, unknown[]> } | null | undefined} result
 * @param {'ZH'|'EN'} lang
 */
export function formatScanSummary(result, lang = 'ZH') {
  if (!result) return lang === 'EN' ? 'Not scanned' : '尚未扫描';
  const total = Number(result.total_issues ?? 0);
  const files = result.affected_files ?? (result.report ? Object.keys(result.report).length : 0);
  if (lang === 'EN') return `Found ${total} issue(s) in ${files} file(s)`;
  return `发现 ${total} 个问题（${files} 个文件）`;
}

/**
 * @param {{ fixed_files?: number, fixed_items?: number, failed_files?: number } | null | undefined} result
 * @param {'ZH'|'EN'} lang
 */
export function formatFixSummary(result, lang = 'ZH') {
  if (!result) return '';
  const files = Number(result.fixed_files ?? 0);
  const items = Number(result.fixed_items ?? 0);
  const failed = Number(result.failed_files ?? 0);
  if (lang === 'EN') {
    let text = `Fixed ${files} file(s), ${items} change(s)`;
    if (failed) text += `; ${failed} file(s) failed`;
    return text;
  }
  let text = `已修复 ${files} 个文件、${items} 处`;
  if (failed) text += `；${failed} 个文件失败`;
  return text;
}

/** Qt 默认：Tab 转空格开，其余修复关 */
export const ERROR_REPAIR_DEFAULTS = {
  fixIndent: true,
  fixIndentLevel: false,
  fixQuotes: false,
  fixDialogueQuotes: false,
  fixEmptyBlocks: false,
};

/** 提交用的 owner 快照：有绑定则用 status.owner_project_key，未绑定为空。 */
export function errorRepairOwnerProjectKey(status) {
  return String(status?.owner_project_key ?? '').trim();
}
