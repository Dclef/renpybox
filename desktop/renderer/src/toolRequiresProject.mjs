/** 翻译方式工具的 requiresProject，与 tools.ts / Qt ToolRegistry 对齐；供 node:test 使用（勿 import tools.ts，含 svg）。 */
export const TOOL_REQUIRES_PROJECT = Object.freeze({
  rpy_extraction_settings: false,
  extract_to_tl: false,
  direct_rpy_translate: false,
  hook_translate: true,
  source_translate: true,
  hook_supplement: true,
  extract_json: false,
});
