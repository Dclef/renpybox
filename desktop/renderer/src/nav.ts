/**
 * 导航：侧栏 4 段（与旧版一致）。校对台、术语表、禁翻表、称呼桥接只经工具箱进入。
 */

import type { NavIconName } from './icons';
import type { TextKey } from './i18n';

/** 主页面 key：与 Python 侧 object_name / 页面标识对应 */
export type PageKey =
  | 'translation'
  | 'proofreading'
  | 'glossary'
  | 'preserve'
  | 'honorific'
  | 'onekey'
  | 'onekey-apply'
  | 'pack-unpack'
  | 'ma-suite'
  | 'batch-correction'
  | 'name-extraction'
  | 'direct-rpy-translate'
  | 'source-translate'
  | 'hook-translate'
  | 'hook-supplement'
  | 'font-replace'
  | 'rpy-extraction'
  | 'extract-to-tl'
  | 'extract-json'
  | 'add-language'
  | 'set-default-language'
  | 'error-repair'
  | 'translation-reuse'
  | 'formatter'
  | 'android-build'
  | 'html-import'
  | 'game-mod'
  | 'agent'
  | 'project'
  | 'platform'
  | 'toolbox'
  | 'workbench'
  | 'story-blueprint'
  | 'basic-settings'
  | 'expert-settings'
  | 'custom-prompt'
  | 'app-settings';

export interface NavItem {
  key: PageKey;
  /** LocalizerZH 里的 key，便于回查原文 */
  labelKey: TextKey;
  icon: NavIconName;
  /** 工具箱承载的工具页。停留在这些页面时，工具箱项保持选中。 */
  members?: PageKey[];
}

const PAGES: NavItem[] = [
  { key: 'translation', labelKey: 'app_translation_page', icon: 'Languages' },
  { key: 'proofreading', labelKey: 'app_proofreading_page', icon: 'SpellCheck' },
  { key: 'agent', labelKey: 'app_agent_page', icon: 'Bot' },
  { key: 'project', labelKey: 'app_project_page', icon: 'FolderCog' },
  { key: 'platform', labelKey: 'app_platform_page', icon: 'Plug' },
  { key: 'toolbox', labelKey: 'app_renpy_toolbox_page', icon: 'Wrench' },
  { key: 'glossary', labelKey: 'app_glossary_page', icon: 'BookOpenText' },
  { key: 'preserve', labelKey: 'app_text_preserve_page', icon: 'BookOpenText' },
  { key: 'honorific', labelKey: 'app_honorific_page', icon: 'BookOpenText' },
  { key: 'onekey', labelKey: 'app_onekey_page', icon: 'Languages' },
  { key: 'onekey-apply', labelKey: 'app_onekey_apply_page', icon: 'FolderCog' },
  { key: 'pack-unpack', labelKey: 'app_pack_unpack_page', icon: 'Wrench' },
  { key: 'ma-suite', labelKey: 'app_ma_suite_page', icon: 'Wrench' },
  { key: 'batch-correction', labelKey: 'app_batch_correction_page', icon: 'Wrench' },
  { key: 'name-extraction', labelKey: 'app_name_extraction_page', icon: 'Wrench' },
  { key: 'direct-rpy-translate', labelKey: 'app_direct_rpy_translate_page', icon: 'Languages' },
  { key: 'source-translate', labelKey: 'app_source_translate_page', icon: 'Languages' },
  { key: 'hook-translate', labelKey: 'app_hook_translate_page', icon: 'Languages' },
  { key: 'hook-supplement', labelKey: 'app_hook_supplement_page', icon: 'Languages' },
  { key: 'font-replace', labelKey: 'app_font_replace_page', icon: 'Wrench' },
  { key: 'rpy-extraction', labelKey: 'app_rpy_extraction_page', icon: 'Wrench' },
  { key: 'extract-to-tl', labelKey: 'app_extract_to_tl_page', icon: 'Wrench' },
  { key: 'extract-json', labelKey: 'app_extract_json_page', icon: 'Wrench' },
  { key: 'add-language', labelKey: 'app_add_language_page', icon: 'Wrench' },
  { key: 'set-default-language', labelKey: 'app_set_default_language_page', icon: 'Wrench' },
  { key: 'error-repair', labelKey: 'app_error_repair_page', icon: 'Wrench' },
  { key: 'translation-reuse', labelKey: 'app_translation_reuse_page', icon: 'Wrench' },
  { key: 'formatter', labelKey: 'app_formatter_page', icon: 'Wrench' },
  { key: 'android-build', labelKey: 'app_android_build_page', icon: 'Wrench' },
  { key: 'html-import', labelKey: 'app_html_import_page', icon: 'Wrench' },
  { key: 'game-mod', labelKey: 'app_game_mod_page', icon: 'Wrench' },
  { key: 'workbench', labelKey: 'app_workbench_page', icon: 'UsersRound' },
  { key: 'story-blueprint', labelKey: 'app_story_blueprint_page', icon: 'Waypoints' },
  { key: 'basic-settings', labelKey: 'app_basic_settings_page', icon: 'SlidersHorizontal' },
  { key: 'expert-settings', labelKey: 'app_expert_settings_page', icon: 'SlidersHorizontal' },
  { key: 'custom-prompt', labelKey: 'app_custom_prompt_navigation_item', icon: 'SlidersHorizontal' },
];

/** BOTTOM 位置的应用设置项（在原壳里始终可见，不受专家模式影响） */
export const APP_SETTINGS_NAV: NavItem = {
  key: 'app-settings',
  labelKey: 'app_settings_page',
  icon: 'Settings',
};

const page = (key: PageKey): NavItem => PAGES.find((item) => item.key === key)!;

export const TOOLBOX_PAGES: PageKey[] = ['proofreading', 'glossary', 'preserve', 'honorific', 'onekey', 'onekey-apply', 'pack-unpack', 'ma-suite', 'batch-correction', 'name-extraction', 'direct-rpy-translate', 'source-translate', 'hook-translate', 'hook-supplement', 'font-replace', 'rpy-extraction', 'extract-to-tl', 'extract-json', 'add-language', 'set-default-language', 'error-repair', 'translation-reuse', 'formatter', 'android-build', 'html-import', 'game-mod'];

/** 侧栏四段。段间留白，不显示分组标题。 */
export const NAV_SECTIONS: NavItem[][] = [
  [page('translation'), page('agent')],
  [page('project'), page('platform')],
  [{ ...page('toolbox'), members: TOOLBOX_PAGES }, page('workbench'), page('story-blueprint')],
  [page('basic-settings'), page('expert-settings'), page('custom-prompt')],
];

export const ALL_NAV_ITEMS: NavItem[] = [...PAGES, APP_SETTINGS_NAV];

export function findNavItem(key: PageKey): NavItem {
  return ALL_NAV_ITEMS.find((item) => item.key === key) ?? ALL_NAV_ITEMS[0];
}

export function isNavCurrent(item: NavItem, active: PageKey): boolean {
  return item.key === active || item.members?.includes(active) === true;
}
