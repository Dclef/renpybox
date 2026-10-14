/**
 * 语言工具 / 字体注入页的纯函数：目标语言解析与前端预校验。
 * 保持与 Qt5 SetDefaultLanguagePage / FontReplacePage 行为一致。
 */

/** 自定义名优先，否则用下拉选中值；都空时回落 defaultLanguage。 */
export function resolveTargetLanguage(selected, custom, defaultLanguage = 'chinese') {
  const customText = String(custom ?? '').trim();
  if (customText) return customText;
  const selectedText = String(selected ?? '').trim();
  if (selectedText) return selectedText;
  return String(defaultLanguage || 'chinese');
}

/** 默认语言：提交前确认 tl/<language> 已在后端回报的语言列表中。 */
export function defaultLanguagePathReady(language, languages) {
  const name = String(language ?? '').trim();
  if (!name) return false;
  return Array.isArray(languages) && languages.includes(name);
}

/** 字体注入：允许已有语言，也允许 chinese（新建汉化）或非空自定义名。 */
export function fontInjectLanguageReady(language) {
  return Boolean(String(language ?? '').trim());
}
