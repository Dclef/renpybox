/**
 * 导航结构沿用 frontend/AppFluentWindow.py 的页面顺序和分组。
 * 每项保留单行图标和文字；品牌、折叠尺寸与选中状态由 App.tsx/styles.css 管理。
 * 标签文本取自 module/Localizer/LocalizerZH.py 的真实 key。
 */

import type { NavIconName } from './icons';

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
  labelKey: string;
  label: string;
  /**
   * 图标名 —— 对应 AppFluentWindow.py 里 addSubInterface 传入的
   * FluentIcon.*（渲染端没有那套字体图标，按语义在 icons.tsx 里补齐）。
   */
  icon: NavIconName;
}

/** 主区导航项：顺序即 AppFluentWindow.add_pages() 的顺序 */
const MAIN_NAV: NavItem[] = [
  { key: 'translation', labelKey: 'app_translation_page', label: '翻译任务', icon: 'Languages' },
  { key: 'proofreading', labelKey: 'proofreading_page', label: '平行校对台', icon: 'SpellCheck' },
  { key: 'agent', labelKey: 'app_agent_page', label: 'Agent 助手', icon: 'Bot' },
  { key: 'project', labelKey: 'app_project_page', label: '项目设置', icon: 'FolderCog' },
  { key: 'platform', labelKey: 'app_platform_page', label: '接口管理', icon: 'Plug' },
  { key: 'toolbox', labelKey: 'app_renpy_toolbox_page', label: "Ren'Py 工具箱", icon: 'Wrench' },
  { key: 'glossary', labelKey: 'local_glossary', label: '术语表', icon: 'BookOpenText' },
  { key: 'preserve', labelKey: 'text_preserve', label: '禁翻表', icon: 'ShieldBan' },
  { key: 'honorific', labelKey: 'honorific_placeholder', label: '称呼桥接', icon: 'Variable' },
  { key: 'workbench', labelKey: 'app_workbench_page', label: '角色 / 世界观工作台', icon: 'UsersRound' },
  { key: 'basic-settings', labelKey: 'app_basic_settings_page', label: '基础设置', icon: 'SlidersHorizontal' },
  { key: 'expert-settings', labelKey: 'app_expert_settings_page', label: '专家设置', icon: 'FlaskConical' },
  { key: 'custom-prompt', labelKey: 'app_custom_prompt_navigation_item', label: '翻译提示', icon: 'MessageSquareText' },
];

/** BOTTOM 位置的应用设置项（在原壳里始终可见，不受专家模式影响） */
export const APP_SETTINGS_NAV: NavItem = {
  key: 'app-settings',
  labelKey: 'app_settings_page',
  label: '应用设置',
  icon: 'Settings',
};

const GROUP_BEFORE: Partial<Record<PageKey, string>> = {
  translation: '翻译工作区',
  project: '项目配置',
  toolbox: '工具与资产',
  'basic-settings': '翻译设置',
};

export type NavEntry =
  | { kind: 'item'; item: NavItem }
  | { kind: 'group'; id: string; label: string };

export const ALL_NAV_ITEMS: NavItem[] = [...MAIN_NAV, APP_SETTINGS_NAV];

export function findNavItem(key: PageKey): NavItem {
  return ALL_NAV_ITEMS.find((item) => item.key === key) ?? ALL_NAV_ITEMS[0];
}

/**
 * 展开成渲染用的扁平序列（分组标题与导航项混排）。
 * 专家模式关闭时隐藏专家设置页（对齐 LogManager.is_expert_mode()），
 * 分组标题跟着所属页面走。
 */
export function navEntries(expertMode: boolean): NavEntry[] {
  const entries: NavEntry[] = [];
  for (const item of MAIN_NAV) {
    if (item.key === 'expert-settings' && !expertMode) continue;
    const group = GROUP_BEFORE[item.key];
    if (group) entries.push({ kind: 'group', id: `group-${item.key}`, label: group });
    entries.push({ kind: 'item', item });
  }
  return entries;
}
