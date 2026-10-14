/** 翻译方式工具的 requiresProject（新 UI 一律 false）；与 tools.ts 对齐，有意异于 Qt ToolRegistry。 */
export const TOOL_REQUIRES_PROJECT: Readonly<{
  rpy_extraction_settings: boolean;
  extract_to_tl: boolean;
  direct_rpy_translate: boolean;
  hook_translate: boolean;
  source_translate: boolean;
  hook_supplement: boolean;
  extract_json: boolean;
}>;
