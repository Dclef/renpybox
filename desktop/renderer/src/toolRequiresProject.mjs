/**
 * 翻译方式工具的 requiresProject：新 UI 一律为 false（可独立选目录打开）。
 * 2026-10-12 用户决策（只改新 UI）：门禁仅限推荐流程中除一键翻译外的动作，以及术语表 / 禁翻表；
 * 一键翻译保持为选项目入口（requiresProject=false）。Qt5 ToolRegistry 仍是 11 个 True，有意偏差。
 * 供 node:test 使用（勿 import tools.ts，含 svg）。
 */
export const TOOL_REQUIRES_PROJECT = Object.freeze({
  rpy_extraction_settings: false,
  extract_to_tl: false,
  direct_rpy_translate: false,
  hook_translate: false,
  source_translate: false,
  hook_supplement: false,
  extract_json: false,
});
