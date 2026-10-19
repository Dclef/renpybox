/**
 * 字体页纯函数：原字体解析与扫描摘要，对齐 Qt5 FontReplacePage / FontReplacer。
 * 文案常量独立于此，避免改动其他 CLI 正在写的 i18n。
 */

/** Qt `font_replace_default_language_global_replacement`；注入时回落 chinese。 */
export const FONT_DEFAULT_LANGUAGE_VALUE = '__default__';

export const FONT_DEFAULT_LANGUAGE_LABEL = {
  ZH: '默认语言 (全局替换)',
  EN: 'Default Language (Global Replacement)',
};

/** 已扫描且引用数为 0 时的下拉占位（区别于尚未扫描）。 */
export const FONT_SCAN_NO_REFS_LABEL = {
  ZH: '扫描完成，未检测到字体引用',
  EN: 'Scan complete: no font references detected',
};

export const FONT_SCAN_STALE_LABEL = {
  ZH: '扫描结果已过期，请重新扫描后再替换。',
  EN: 'Scan results are outdated. Rescan before replacing fonts.',
};

/** 写入失败副作用条上的备份路径前缀（不改共用 i18n）。 */
export const FONT_BACKUP_SIDE_EFFECT_LABEL = {
  ZH: '备份：{path}',
  EN: 'Backup: {path}',
};

export const FONT_RESTORE_OK_LABEL = {
  ZH: '已从备份完整恢复',
  EN: 'Fully restored from backup',
};

export const FONT_RESTORE_PARTIAL_LABEL = {
  ZH: '仅部分恢复，请检查备份路径',
  EN: 'Only partially restored; check the backup path',
};

export const FONT_BROWSE_LABEL = {
  ZH: '浏览',
  EN: 'Browse',
};

export const FONT_GAME_DIR_HINT = {
  ZH: '可手动指定项目根或 game 目录；默认使用当前绑定项目',
  EN: 'Optionally set a project root or game folder; defaults to the bound project',
};

/** 用户清空目录后的警告（对齐 Qt font_replace_select_game_folder_first）。 */
export const FONT_GAME_DIR_EMPTY_LABEL = {
  ZH: '请先选择游戏目录',
  EN: 'Select the game folder first.',
};

/** 手动目录是否可用于 status / 写入（空串不得回退绑定项目）。 */
export function fontGameDirReady(gamePath = '') {
  return Boolean(String(gamePath || '').trim());
}

/** 组装字体 status URL；有效路径带 game_path；空输入显式空 query，禁止静默绑定。 */
export function fontToolsStatusPath(gamePath = '') {
  const trimmed = String(gamePath || '').trim();
  if (!trimmed) return '/api/font-tools?game_path=';
  return `/api/font-tools?game_path=${encodeURIComponent(trimmed)}`;
}

/**
 * 提交体 game_path：
 * - 空输入 → 显式 { game_path: '' }，由 API 拒绝（不依赖省略回退）
 * - 与绑定目录相同 → 省略字段（旧调用兼容）
 * - 其它有效路径 → 带 game_path
 */
export function fontToolsGamePathPayload(gamePath, boundGamePath = '') {
  const trimmed = String(gamePath || '').trim();
  if (!trimmed) return { game_path: '' };
  const bound = String(boundGamePath || '').trim();
  if (bound && trimmed.replace(/\\/g, '/').toLowerCase() === bound.replace(/\\/g, '/').toLowerCase()) {
    return {};
  }
  return { game_path: trimmed };
}

export function formatFontBackupSideEffect(path, lang = 'ZH') {
  const value = String(path || '').trim();
  if (!value) return '';
  return fontCopy(FONT_BACKUP_SIDE_EFFECT_LABEL, lang).replace('{path}', value);
}

/** 根据 Job.result.restored / 文案判断恢复提示（中英）。 */
export function formatFontRestoreHint(result, lang = 'ZH') {
  if (!result || typeof result !== 'object') return '';
  if (result.restored === true) return fontCopy(FONT_RESTORE_OK_LABEL, lang);
  const message = String(result.message || '');
  if (
    result.restored === false
    && (result.backup_path || result.backup_name || message.includes('部分恢复') || message.includes('自动恢复未成功'))
  ) {
    return fontCopy(FONT_RESTORE_PARTIAL_LABEL, lang);
  }
  return '';
}

export function fontCopy(table, lang = 'ZH') {
  return table[lang === 'EN' ? 'EN' : 'ZH'] || table.ZH;
}

/** 与 API resolve_original_fonts 一致：全部 / 手输 / 检测选中。 */
export function resolveOriginalFonts({ replaceAll, selectedFont, originalFont, detected }) {
  const manual = String(originalFont ?? '').trim();
  const selected = String(selectedFont ?? '').trim();
  const refs = Array.isArray(detected) ? detected.map(String) : [];
  if (replaceAll) return refs;
  if (manual) return [manual];
  if (selected) return [selected];
  return null;
}

/** 提交替换前前端预检：需有原字体目标。 */
export function replaceFontsReady({ replaceAll, selectedFont, originalFont, detected }) {
  return resolveOriginalFonts({ replaceAll, selectedFont, originalFont, detected }) !== null;
}

/** 扫描摘要文案占位填充。 */
export function formatFontScanSummary(template, { fontCount = 0, fontFileCount = 0, langCount = 0 } = {}) {
  return String(template || '')
    .replaceAll('{font_count}', String(fontCount))
    .replaceAll('{font_file_count}', String(fontFileCount))
    .replaceAll('{lang_count}', String(langCount));
}

/** 语言下拉：默认语言选项 → 空选，再由 resolveTargetLanguage 回落 chinese。 */
export function resolveFontInjectLanguage(selected, custom, defaultLanguage = 'chinese') {
  const customText = String(custom ?? '').trim();
  if (customText) return customText;
  const selectedText = String(selected ?? '').trim();
  if (!selectedText || selectedText === FONT_DEFAULT_LANGUAGE_VALUE) {
    return String(defaultLanguage || 'chinese');
  }
  return selectedText;
}

/** 检测下拉占位：区分尚未扫描 / 扫描完成无引用。 */
export function fontDetectedPlaceholder({ fontsScanned, scanStale, fontRefCount }, labels) {
  if (fontsScanned && !scanStale) {
    return fontRefCount > 0 ? undefined : labels.noRefs;
  }
  return labels.notScanned;
}
