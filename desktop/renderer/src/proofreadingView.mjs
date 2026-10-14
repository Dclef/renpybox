// 校对台的纯业务判定：不依赖 React，便于 node:test 直接覆盖。
// 口径对齐 frontend/Proofreading/ProofreadingPage.py 的 _build_match_indices / _on_batch_replace_clicked
// 与 frontend/Proofreading/FilterDialog.py 的 _filter_items / _export_filtered_items

/** 术语未生效问题的告警类型，对齐 module/ResultChecker.py 的 WarningType.GLOSSARY。 */
export const GLOSSARY_WARNING = 'GLOSSARY';

/** 没有任何问题行在筛选结果里的占位标记，对齐 FilterDialog.NO_WARNING_TAG。 */
export const NO_WARNING = 'NO_WARNING';

/** 「术语表多选」为空时的占位值；antd Select 不接受空字符串做选项值。 */
export const TERM_ANY = '__ANY__';

/**
 * 编译正则。
 *
 * 对齐 Qt5：搜索固定 re.IGNORECASE，批量替换按大小写开关决定 flags，非法正则只返回
 * 可读提示而不抛异常（Qt5 分别用 search_regex_invalid / batch_replace_invalid_regex 提示）。
 * 用 RegExp 构造函数是刻意的：SearchCard 输入过程中不完整的 `(` 也必须只变成提示。
 */
export function compilePattern(source, { regex, caseSensitive } = {}) {
  const text = String(source ?? '');
  if (!text) return { ok: true, pattern: null };
  if (!regex) return { ok: true, pattern: null };
  try {
    return { ok: true, pattern: new RegExp(text, caseSensitive ? '' : 'i') };
  } catch (failure) {
    return { ok: false, error: failure instanceof Error ? failure.message : String(failure) };
  }
}

/** 单条文本是否命中关键词：正则按 Qt5 的 IGNORECASE，纯文本按大小写开关。 */
export function matchesKeyword(text, keyword, options = {}) {
  const haystack = String(text ?? '');
  const needle = String(keyword ?? '');
  if (!needle) return false;
  if (options.regex) {
    const compiled = compilePattern(needle, { regex: true, caseSensitive: false });
    if (!compiled.ok) return false;
    return compiled.pattern.test(haystack);
  }
  if (options.caseSensitive) return haystack.includes(needle);
  return haystack.toLowerCase().includes(needle.toLowerCase());
}

/**
 * 命中行下标，对齐 _build_match_indices：
 * 原文或译文任一命中即算一行；搜索永远匹配当前筛选结果。
 */
export function matchRowIndices(rows, keyword, options = {}) {
  const needle = String(keyword ?? '');
  if (!needle) return [];
  if (options.regex && !compilePattern(needle, { regex: true, caseSensitive: false }).ok) return [];
  const indices = [];
  (rows ?? []).forEach((row, index) => {
    if (matchesKeyword(row?.src, needle, options) || matchesKeyword(row?.dst, needle, options)) indices.push(index);
  });
  return indices;
}

/**
 * 匹配跳转：在当前匹配上前后移动，越界回环，对齐 _on_search_next_clicked / _on_search_prev_clicked。
 * 没有匹配时返回 -1，调用方据此触发重新搜索。
 */
export function stepMatch(current, total, delta) {
  if (total <= 0) return -1;
  const base = Number.isFinite(current) ? Math.trunc(current) : -1;
  const next = base + delta;
  if (next < 0) return total - 1;
  if (next >= total) return 0;
  return next;
}

/**
 * 批量替换的替换函数。
 *
 * 对齐 _on_batch_replace_clicked 的四种组合：正则走 pattern.sub；纯文本不区分大小写时
 * 必须转义关键词并用函数式替换，避免 replacement 里的 `$1` / 反斜杠被当成反向引用。
 * 正则模式的 `\1` / `\g<name>` 反向引用按 Qt5（Python re.sub）口径翻译成 JS 的 `$1` / `$<name>`。
 */
export function makeReplacer(find, replacement, options = {}) {
  const needle = String(find ?? '');
  const value = String(replacement ?? '');
  if (!needle) return (text) => String(text ?? '');
  if (options.regex) {
    const compiled = compilePattern(needle, { regex: true, caseSensitive: options.caseSensitive !== false });
    // 正则非法时调用方必须先拦下来（compilePattern 的结果会被 UI 检查）；这里退化为不改写。
    if (!compiled.ok) return (text) => String(text ?? '');
    // 对齐 Python re.sub：替换全部命中，所以补上全局标志。
    const pattern = globalPattern(compiled.pattern);
    const template = toJsTemplate(value);
    return (text) => String(text ?? '').replace(pattern, template);
  }
  if (options.caseSensitive !== false) return (text) => String(text ?? '').split(needle).join(value);
  const pattern = new RegExp(escapeRegExp(needle), 'ig');
  return (text) => String(text ?? '').replace(pattern, () => value);
}

/** Python re.sub 的 `\1` / `\g<name>` 反向引用写法 → JS String.replace 的 `$1` / `$<name>`；`$` 交给 JS 原生处理。 */
function toJsTemplate(value) {
  return value.replace(/\\g<([^>]+)>|\\([1-9])/g, (match, named, numbered) => (
    named ? '$<' + named + '>' : '$' + numbered
  ));
}

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/** 补上全局标志：收集匹配与替换都必须覆盖全部命中，对齐 Python 的 findall / sub。 */
function globalPattern(pattern) {
  return pattern.global ? pattern : new RegExp(pattern.source, pattern.flags + 'g');
}

/** 单条文本被替换命中的次数。 */
export function countMatches(text, find, options = {}) {
  const haystack = String(text ?? '');
  const needle = String(find ?? '');
  if (!needle) return 0;
  if (options.regex) {
    const compiled = compilePattern(needle, { regex: true, caseSensitive: options.caseSensitive !== false });
    if (!compiled.ok) return 0;
    return haystack.match(globalPattern(compiled.pattern))?.length ?? 0;
  }
  if (options.caseSensitive !== false) {
    let count = 0;
    let cursor = haystack.indexOf(needle);
    while (cursor >= 0) { count += 1; cursor = haystack.indexOf(needle, cursor + needle.length); }
    return count;
  }
  const pattern = new RegExp(escapeRegExp(needle), 'gi');
  return haystack.match(pattern)?.length ?? 0;
}

/**
 * 批量替换的影响范围预览，对齐 BatchReplaceDialog 的 SCOPE_SELECTED / SCOPE_FILTERED 与执行前提示。
 * 只统计真正会被改写的行，未命中的行不会进入提交列表。
 */
export function replaceImpact(rows, find, replacement, options = {}) {
  const needle = String(find ?? '');
  const compiled = options.regex ? compilePattern(needle, { regex: true, caseSensitive: options.caseSensitive !== false }) : { ok: true };
  if (!needle || !compiled.ok) return { rows: [], matchCount: 0, invalidRegex: !compiled.ok, error: compiled.error };
  const replacer = makeReplacer(needle, replacement, options);
  const changed = [];
  let matchCount = 0;
  for (const row of rows ?? []) {
    const before = String(row?.dst ?? '');
    const after = replacer(before);
    if (after === before) continue;
    matchCount += countMatches(before, needle, options);
    changed.push({ id: row?.id, version: row?.version, before, after });
  }
  return { rows: changed, matchCount, invalidRegex: false };
}

/** 一条译文里命中的术语（原文→译名对），用于推导筛选维度里的术语表列表。 */
export function glossaryTermsOf(row) {
  return Array.isArray(row?.glossary_terms) ? row.glossary_terms : [];
}

/** 可选术语表：只取「术语未生效」行带来的词条，对齐 FilterDialog._init_term_list。 */
export function collectGlossaryTerms(rows) {
  const terms = new Map();
  for (const row of rows ?? []) {
    if (!Array.isArray(row?.warnings) || !row.warnings.includes(GLOSSARY_WARNING)) continue;
    for (const term of glossaryTermsOf(row)) {
      const src = String(term?.src ?? '');
      const dst = String(term?.dst ?? '');
      if (!src && !dst) continue;
      const key = src + '\u0000' + dst;
      if (!terms.has(key)) terms.set(key, { key, src, dst, label: src + ' -> ' + dst });
    }
  }
  return [...terms.values()].sort((left, right) => left.label.localeCompare(right.label, 'zh-Hans-CN'));
}

/** 可选问题类型：问题行带出的告警类型，外加「没有检测到问题」占位项。 */
export function collectWarnings(rows) {
  const values = new Set();
  for (const row of rows ?? []) {
    for (const warning of Array.isArray(row?.warnings) ? row.warnings : []) values.add(String(warning));
  }

  if ((rows ?? []).some((row) => !row?.warnings?.length)) values.add(NO_WARNING);
  return [...values].sort();
}

function normalizeSelection(selection) {
  if (!selection) return null;
  const values = selection instanceof Set ? [...selection] : selection;
  return Array.isArray(values) && values.length ? new Set(values.map(String)) : null;
}

/**
 * 客户端筛选求值，对齐 FilterDialog。各维度是「与」关系；
 * 值为空数组或 null 表示该维度未限制（Qt5 用 None 表达同样的意思）。
 */
export function filterRows(rows, filters = {}) {
  const statuses = normalizeSelection(filters.statuses);
  const files = normalizeSelection(filters.files);
  const warnings = normalizeSelection(filters.warnings);
  const terms = normalizeSelection(filters.terms);
  const termValues = terms
    ? [...terms].filter((value) => value && value !== TERM_ANY).map((value) => value.split('\u0000')[1] ?? value).filter(Boolean)
    : [];

  return (rows ?? []).filter((row) => {
    if (statuses && !statuses.has(String(row?.status ?? ''))) return false;
    if (files && !files.has(String(row?.file_path ?? ''))) return false;
    if (warnings) {
      const rowWarnings = (Array.isArray(row?.warnings) ? row.warnings : []).map(String);
      if (rowWarnings.length) { if (!rowWarnings.some((warning) => warnings.has(warning))) return false; }
      else if (!warnings.has(NO_WARNING)) return false;
    }
    if (termValues.length) {
      const dst = String(row?.dst ?? '');
      if (!termValues.some((value) => dst.includes(value))) return false;
    }
    return true;
  });
}

/** 分页切片：页码越界时回落到最后一页，避免筛选后停在空页。 */
export function pageSlice(rows, page, limit) {
  const size = Math.max(1, Math.trunc(Number(limit) || 1));
  const total = Math.ceil((rows?.length ?? 0) / size);
  const pages = Math.max(1, total);
  const current = Math.min(Math.max(1, Math.trunc(Number(page) || 1)), pages);
  const start = (current - 1) * size;
  return { items: (rows ?? []).slice(start, start + size), page: current, pages };
}

/** 导出条目：字段与 Qt5 _export_filtered_items 写出的 JSON 报告一致。 */
export function buildExportRecords(rows) {
  return (rows ?? []).map((row) => ({
    file_path: String(row?.file_path ?? ''),
    status: String(row?.status ?? ''),
    warnings: (Array.isArray(row?.warnings) ? row.warnings : []).map(String),
    src: String(row?.src ?? ''),
    dst: String(row?.dst ?? ''),
  }));
}

/** 导出文件名对齐 Qt5 的 proofreading_filter_report_<时间戳>.json。 */
export function exportFilename(now = new Date()) {
  const pad = (value) => String(value).padStart(2, '0');
  return 'proofreading_filter_report_'
    + String(now.getFullYear()) + pad(now.getMonth() + 1) + pad(now.getDate())
    + '_' + pad(now.getHours()) + pad(now.getMinutes()) + pad(now.getSeconds())
    + '.json';
}

/** 导出文本：与 Python json.dump(..., ensure_ascii=False, indent=2) 保持同样的缩进口径。 */
export function exportText(rows) {
  return JSON.stringify(buildExportRecords(rows), null, 2);
}
