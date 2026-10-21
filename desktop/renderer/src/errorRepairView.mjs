/** 脚本修复页：状态路径、默认选项与结果摘要（中英就地双语）。 */

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
 * 修复类型 → 中英标签。键与后端 ErrorRepairer 的 issue type 一一对应。
 * 未登记的类型原样显示 type 名，避免新增类型时界面空白。
 */
export const REPAIR_TYPE_LABELS = {
  indent: { ZH: '缩进（Tab）', EN: 'Indentation (tabs)' },
  empty_block: { ZH: '空翻译块', EN: 'Empty blocks' },
  duplicate_old_new: { ZH: '重复译文', EN: 'Duplicate strings' },
  unescaped_dialogue_quotes: { ZH: '对话引号未转义', EN: 'Unescaped dialogue quotes' },
  indentation_level: { ZH: '缩进层级', EN: 'Indentation level' },
  quotes: { ZH: '引号规范', EN: 'Quote normalization' },
  syntax: { ZH: '语法', EN: 'Syntax' },
  placeholder_missing: { ZH: '占位符缺失', EN: 'Missing placeholder' },
  placeholder_extra: { ZH: '占位符多余', EN: 'Extra placeholder' },
  placeholder_rewritten: { ZH: '占位符被改写', EN: 'Rewritten placeholder' },
  linebreak_mismatch: { ZH: '换行不一致', EN: 'Line-break mismatch' },
  extra_empty_string: { ZH: '多余空串', EN: 'Extra empty string' },
  incremental_leftover: { ZH: '残留增量目录', EN: 'Leftover incremental folder' },
};

/**
 * @param {string} type
 * @param {'ZH'|'EN'} lang
 * @returns {string}
 */
export function repairTypeLabel(type, lang = 'ZH') {
  const entry = REPAIR_TYPE_LABELS[type];
  return (entry && entry[lang]) || String(type || '');
}

/**
 * 扫描摘句。新后端给 fixable/manual/environment 分组计数，旧结果只有总数 → 退回旧句式。
 * @param {{
 *   total_issues?: number, affected_files?: number, report?: Record<string, unknown[]>,
 *   fixable_issues?: number, manual_issues?: number, environment_issues?: unknown[],
 * }} | null | undefined} result
 * @param {'ZH'|'EN'} lang
 */
export function formatScanSummary(result, lang = 'ZH') {
  if (!result) return lang === 'EN' ? 'Not scanned' : '尚未扫描';
  const total = Number(result.total_issues ?? 0);
  const grouped = result.fixable_issues !== undefined
    || result.manual_issues !== undefined
    || Array.isArray(result.environment_issues);
  if (grouped) {
    const fixable = Number(result.fixable_issues ?? 0);
    const manual = Number(result.manual_issues ?? 0);
    const environment = Array.isArray(result.environment_issues) ? result.environment_issues.length : 0;
    if (lang === 'EN') {
      return `Found ${total} issue(s): ${fixable} auto-fixable, ${manual} manual, ${environment} environment`;
    }
    return `发现 ${total} 个问题（可自动修复 ${fixable} 个，需人工 ${manual} 个，环境问题 ${environment} 个）`;
  }
  const files = result.affected_files ?? (result.report ? Object.keys(result.report).length : 0);
  if (lang === 'EN') return `Found ${total} issue(s) in ${files} file(s)`;
  return `发现 ${total} 个问题（${files} 个文件）`;
}

/**
 * 修复摘句：文件/条数 + 失败 + 环境处理 + 剩余或未复扫。
 * @param {{
 *   fixed_files?: number, fixed_items?: number, failed_files?: number,
 *   environment_fixes?: Array<{ ok?: boolean }>, remaining_issues?: number | null, rescan_skipped?: boolean,
 * } | null | undefined} result
 * @param {'ZH'|'EN'} lang
 */
export function formatRepairSummary(result, lang = 'ZH') {
  if (!result) return '';
  const files = Number(result.fixed_files ?? 0);
  const items = Number(result.fixed_items ?? 0);
  const failed = Number(result.failed_files ?? 0);
  const envFixes = Array.isArray(result.environment_fixes) ? result.environment_fixes : [];
  const envOk = envFixes.filter((item) => item && item.ok === true).length;
  const envFailed = envFixes.length - envOk;
  const remaining = Number(result.remaining_issues ?? 0);
  // 复扫未完成时后端给 remaining_issues=null：剩余数量未知，不能显示成 0。
  const skipped = result.rescan_skipped === true || result.remaining_issues === null;
  if (lang === 'EN') {
    let text = `Fixed ${files} file(s), ${items} change(s)`;
    if (failed) text += `; ${failed} file(s) failed`;
    if (envOk) text += `; handled ${envOk} environment issue(s)`;
    if (envFailed) text += `; ${envFailed} environment issue(s) failed`;
    return text + (skipped
      ? '; repair or rescan did not finish, remaining issues unknown'
      : `; ${remaining} issue(s) still need manual work`);
  }
  let text = `已修复 ${files} 个文件、${items} 处`;
  if (failed) text += `；${failed} 个文件失败`;
  if (envOk) text += `；已处理 ${envOk} 个环境问题`;
  if (envFailed) text += `；${envFailed} 个环境问题处理失败`;
  return text + (skipped ? '；修复或复扫未完成，剩余问题数量未知' : `；仍有 ${remaining} 个问题需人工处理`);
}

/**
 * 按类型明细：计数降序，同数按标签排序 → 「重复译文 283、缩进 2」。
 * @param {Record<string, number> | null | undefined} counts
 * @param {'ZH'|'EN'} lang
 */
export function formatTypeBreakdown(counts, lang = 'ZH') {
  const rows = Object.entries(counts ?? {})
    .map(([type, count]) => ({ type, count: Number(count ?? 0) }))
    .filter((row) => Number.isFinite(row.count) && row.count > 0)
    .map((row) => ({ ...row, label: repairTypeLabel(row.type, lang) }));
  if (!rows.length) return '';
  rows.sort((left, right) => right.count - left.count
    || left.label.localeCompare(right.label, lang === 'EN' ? 'en' : 'zh-Hans-CN'));
  return rows.map((row) => `${row.label} ${row.count}`).join(lang === 'EN' ? ', ' : '、');
}

/**
 * 扫描结果是否有可处理内容（决定结果区/环境卡片是否值得展示）。
 * @param {{
 *   total_issues?: number, fixable_issues?: number, manual_issues?: number,
 *   environment_issues?: unknown[], manual_sample?: unknown[],
 * } | null | undefined} result
 */
export function scanIsActionable(result) {
  if (!result) return false;
  if (Number(result.total_issues ?? 0) > 0) return true;
  if (Number(result.fixable_issues ?? 0) > 0) return true;
  if (Number(result.manual_issues ?? 0) > 0) return true;
  if (Array.isArray(result.environment_issues) && result.environment_issues.length > 0) return true;
  return Array.isArray(result.manual_sample) && result.manual_sample.length > 0;
}

/**
 * 修复结果应该用什么色调：成功 / 有残留需人工 / 失败。
 * @param {{
 *   success?: boolean, partial?: boolean, failed_files?: number,
 *   environment_fixes?: Array<{ ok?: boolean }>, remaining_issues?: number, rescan_skipped?: boolean,
 * } | null | undefined} result
 * @returns {'success'|'warning'|'error'}
 */
export function fixTone(result) {
  if (!result) return 'error';
  if (result.success === false) return 'error';
  const failed = Number(result.failed_files ?? 0);
  const envFailed = (Array.isArray(result.environment_fixes) ? result.environment_fixes : [])
    .filter((item) => !item || item.ok !== true).length;
  const remaining = Number(result.remaining_issues ?? 0);
  if (result.partial || result.rescan_skipped || failed > 0 || envFailed > 0 || remaining > 0) return 'warning';
  return 'success';
}

/**
 * 旧版摘句：仅保留文件/条数/失败，供其它调用方兼容。
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

/** 安全集默认全开（Tab→空格、行尾空格、空块、重复译文、对话引号）；高级项默认关。 */
export const ERROR_REPAIR_DEFAULTS = {
  fixIndent: true,
  fixTrailingSpaces: true,
  fixEmptyBlocks: true,
  fixDuplicates: true,
  fixDialogueQuotes: true,
  fixIndentLevel: false,
  fixQuotes: false,
  // 修复后顺带跑一次 Ren'Py Lint 复检：并入同一次任务，不用再单独检查一遍。
  fixLintAfter: true,
};

/**
 * 环境问题卡片的修复请求体：fix_* 全关，只处理 path 指向的那一个残留目录。
 * @param {{ folder: string, action: 'merge'|'move', path: string, ownerKey: string }} input
 */
export function buildEnvironmentFixBody({ folder, action, path, ownerKey }) {
  return {
    folder,
    fix_indent: false,
    fix_trailing_spaces: false,
    fix_empty_blocks: false,
    fix_duplicates: false,
    fix_dialogue_quotes: false,
    fix_indent_level: false,
    fix_quotes: false,
    fix_environment: true,
    environment_action: action,
    environment_path: String(path || ''),
    confirm: true,
    owner_project_key: ownerKey,
  };
}

/** 提交用的 owner 快照：有绑定则用 status.owner_project_key，未绑定为空。 */
export function errorRepairOwnerProjectKey(status) {
  return String(status?.owner_project_key ?? '').trim();
}
