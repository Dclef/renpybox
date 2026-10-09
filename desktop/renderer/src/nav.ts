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
  | 'agent'
  | 'project'
  | 'platform'
  | 'toolbox'
  | 'workbench'
  | 'basic-settings'
  | 'expert-settings'
  | 'custom-prompt'
  | 'app-settings';

export interface NavItem {
  key: PageKey;
  /** LocalizerZH 里的 key，便于回查原文 */
  labelKey: TextKey;
  label: string;
  icon: NavIconName;
  /** 工具箱承载的工具页。停留在这些页面时，工具箱项保持选中。 */
  members?: PageKey[];
}

const PAGES: NavItem[] = [
  { key: 'translation', labelKey: 'app_translation_page', label: '翻译任务', icon: 'Languages' },
  { key: 'proofreading', labelKey: 'app_proofreading_page', label: '平行校对台', icon: 'SpellCheck' },
  { key: 'agent', labelKey: 'app_agent_page', label: 'Agent 助手', icon: 'Bot' },
  { key: 'project', labelKey: 'app_project_page', label: '项目设置', icon: 'FolderCog' },
  { key: 'platform', labelKey: 'app_platform_page', label: '接口管理', icon: 'Plug' },
  { key: 'toolbox', labelKey: 'app_renpy_toolbox_page', label: "Ren'Py 工具箱", icon: 'Wrench' },
  { key: 'glossary', labelKey: 'app_glossary_page', label: '术语表', icon: 'BookOpenText' },
  { key: 'preserve', labelKey: 'app_text_preserve_page', label: '禁翻表', icon: 'BookOpenText' },
  { key: 'honorific', labelKey: 'app_honorific_page', label: '称呼桥接', icon: 'BookOpenText' },
  { key: 'workbench', labelKey: 'app_workbench_page', label: '角色 / 世界观工作台', icon: 'UsersRound' },
  { key: 'basic-settings', labelKey: 'app_basic_settings_page', label: '基础设置', icon: 'SlidersHorizontal' },
  { key: 'expert-settings', labelKey: 'app_expert_settings_page', label: '专家设置', icon: 'SlidersHorizontal' },
  { key: 'custom-prompt', labelKey: 'app_custom_prompt_navigation_item', label: '翻译提示', icon: 'SlidersHorizontal' },
];

/** BOTTOM 位置的应用设置项（在原壳里始终可见，不受专家模式影响） */
export const APP_SETTINGS_NAV: NavItem = {
  key: 'app-settings',
  labelKey: 'app_settings_page',
  label: '应用设置',
  icon: 'Settings',
};

const page = (key: PageKey): NavItem => PAGES.find((item) => item.key === key)!;

export const TOOLBOX_PAGES: PageKey[] = ['proofreading', 'glossary', 'preserve', 'honorific'];

/** 侧栏四段。段间留白，不显示分组标题。 */
export const NAV_SECTIONS: NavItem[][] = [
  [page('translation'), page('agent')],
  [page('project'), page('platform')],
  [{ ...page('toolbox'), members: TOOLBOX_PAGES }, page('workbench')],
  [page('basic-settings'), page('expert-settings'), page('custom-prompt')],
];

export const ALL_NAV_ITEMS: NavItem[] = [...PAGES, APP_SETTINGS_NAV];

export function findNavItem(key: PageKey): NavItem {
  return ALL_NAV_ITEMS.find((item) => item.key === key) ?? ALL_NAV_ITEMS[0];
}

export function isNavCurrent(item: NavItem, active: PageKey): boolean {
  return item.key === active || item.members?.includes(active) === true;
}
