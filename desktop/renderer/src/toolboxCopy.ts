import type { ToolGroup, ToolSpec } from './tools';
import type { Lang } from './i18n';

export const TOOLBOX_COPY = {
  ZH: {
    title: "Ren'Py 工具箱", description: '从抽取、翻译到应用译文，按需选择你的下一步',
    search: '搜索工具、用途或关键词', all: '全部工具', categories: '工具分类',
    results: '搜索结果', empty: '没有找到匹配的工具', reset: '清除筛选',
    projectRequired: '需先选择游戏目录', selectProject: '选择游戏目录', project: '项目设置',
    unbound: '先选择游戏目录，即可使用检查与润色、应用译文和术语表等项目工具。',
    count: (value: number) => `${value} 款工具`, open: (title: string) => `打开${title}`,
    groups: {
      flow: ['推荐流程', '完成翻译、检查并应用到游戏'],
      translate: ['翻译方式', '按文件类型选择抽取与翻译方式'],
      asset: ['资源与词表', '整理文本、姓名和翻译资源'],
      engineer: ['工程与修复', '处理脚本、归档与游戏适配'],
    } satisfies Record<ToolGroup, [string, string]>,
  },
  EN: {
    title: "Ren'Py Toolbox", description: 'Choose the next step, from extraction and translation to applying your work',
    search: 'Search tools, tasks or keywords', all: 'All tools', categories: 'Tool categories',
    results: 'Search results', empty: 'No matching tools', reset: 'Clear filters',
    projectRequired: 'Select a game folder first', selectProject: 'Select game folder', project: 'Project settings',
    unbound: 'Select a game folder to use proofreading, apply translations and manage project terminology.',
    count: (value: number) => `${value} ${value === 1 ? 'tool' : 'tools'}`, open: (title: string) => `Open ${title}`,
    groups: {
      flow: ['Recommended', 'Translate, review and apply your work'],
      translate: ['Translation', 'Choose how to extract and translate text'],
      asset: ['Text & assets', 'Organize text, names and translation assets'],
      engineer: ['Engineering', 'Work with scripts, archives and game patches'],
    } satisfies Record<ToolGroup, [string, string]>,
  },
};

const ENGLISH_TOOLS: Record<string, [string, string]> = {
  continue_translation: ['Resume translation', 'Continue an unfinished translation task'],
  one_key_translate: ['One-click translation', 'Choose a game folder to extract and translate its text'],
  proofreading: ['Review & polish', 'Review quality reports, edit translations and export results'],
  apply_translation: ['Apply translations', 'Write translated text into the game’s TL folder'],
  font_replace: ['Install fonts', 'Add bundled fonts and the corresponding interface adjustments'],
  add_language: ['Add language switch', 'Let players switch the game’s language'],
  set_default_language: ['Default language', 'Choose the language used when the game starts'],
  local_glossary: ['Glossary', 'Keep project names and terminology consistent'],
  text_preserve: ['Preserved text', 'Protect variables and code that should stay untranslated'],
  rpy_extraction_settings: ['RPY extraction rules', 'Manage extraction rules and profiles for source and TL scripts'],
  extract_to_tl: ['Extract to TL', 'Extract using the official tools or runtime extraction'],
  direct_rpy_translate: ['Translate RPY', 'Translate tl/*.rpy files directly'],
  hook_translate: ['HOOK translation', 'Run the game to capture and translate its text'],
  source_translate: ['Translate source', 'Translate game/*.rpy source scripts directly'],
  hook_supplement: ['Fill missing text', 'Find text missed by extraction and generate a supplement'],
  extract_json: ['Extract to JSON', 'Export text for manual translation, then import it into TL'],
  honorific_placeholder: ['Honorific bridge', 'Manage placeholders and mappings for honorifics'],
  ma_suite: ['Structure export', 'Export and import structured translation resources'],
  batch_correction: ['Batch correction', 'Apply text corrections across translation files'],
  name_extraction: ['Extract names', 'Collect names from scripts for consistent translation'],
  pack_unpack: ['Archives & decompilation', 'Pack, unpack and decompile game resources'],
  error_repair: ['Script repair', 'Scan and fix script issues: indentation, duplicates, empty blocks, leftover incremental folders, formatting'],
  translation_reuse: ['Reuse translations', 'Match and reuse translations from another project'],
  formatter: ['Format scripts', 'Normalize script formatting'],
  android_build: ['Android build', 'Install the SDK, sign and build APKs; pack shell archives and strip / restore the X- prefix.'],
  html_import: ['Import HTML', 'Import HTML translation results into game scripts'],
  game_mod: ['Game mods', 'Apply supported game modifications and patches'],
};

/** Keep the Qt registry and project requirements authoritative; localize presentation only. */
export function localizeTool(tool: ToolSpec, lang: Lang): ToolSpec {
  const copy = lang === 'EN' ? ENGLISH_TOOLS[tool.key] : undefined;
  return copy ? { ...tool, title: copy[0], description: copy[1] } : tool;
}
