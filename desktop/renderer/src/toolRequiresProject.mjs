/**
 * 翻译方式工具的 requiresProject：新 UI 一律为 false。
 * 2026-10-12 用户决策（只改新 UI）：只有「推荐流程」分组 + 术语表 / 禁翻表 保留「需先选择游戏目录」门禁；
 * Qt5 frontend/RenpyToolbox/ToolRegistry.py 仍是 11 个 requires_project=True，这是有意的两侧偏差。
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
