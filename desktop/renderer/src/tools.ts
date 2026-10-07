/**
 * 工具箱注册表 —— 与 frontend/RenpyToolbox/ToolRegistry.py 的 TOOL_SPECS 对齐。
 *
 * 27 个工具、四组划分、标题与描述全部取自 module/Localizer/LocalizerZH.py
 * 的真实文案（LocalizerZH.py:2242-2299）。requires_project 对应 Python 侧的
 * 同名字段：这些工具在没有项目时入口是禁用的。
 */

import archive from './icons/toolbox/archive.svg?raw';
import bookOpenText from './icons/toolbox/book-open-text.svg?raw';
import braces from './icons/toolbox/braces.svg?raw';
import clipboardCheck from './icons/toolbox/clipboard-check.svg?raw';
import fileCode from './icons/toolbox/file-code.svg?raw';
import fileDown from './icons/toolbox/file-down.svg?raw';
import fileInput from './icons/toolbox/file-input.svg?raw';
import filePenLine from './icons/toolbox/file-pen-line.svg?raw';
import filePlus from './icons/toolbox/file-plus.svg?raw';
import folderInput from './icons/toolbox/folder-input.svg?raw';
import globe from './icons/toolbox/globe.svg?raw';
import languages from './icons/toolbox/languages.svg?raw';
import listChecks from './icons/toolbox/list-checks.svg?raw';
import puzzle from './icons/toolbox/puzzle.svg?raw';
import rotateCcw from './icons/toolbox/rotate-ccw.svg?raw';
import shieldBan from './icons/toolbox/shield-ban.svg?raw';
import smartphone from './icons/toolbox/smartphone.svg?raw';
import table2 from './icons/toolbox/table-2.svg?raw';
import textAlignStart from './icons/toolbox/text-align-start.svg?raw';
import typeSvg from './icons/toolbox/type.svg?raw';
import usersRound from './icons/toolbox/users-round.svg?raw';
import variable from './icons/toolbox/variable.svg?raw';
import wandSparkles from './icons/toolbox/wand-sparkles.svg?raw';
import webhook from './icons/toolbox/webhook.svg?raw';
import wrench from './icons/toolbox/wrench.svg?raw';

/**
 * 工具图标：直接用项目自带的 resource/icons/toolbox/*.svg（Lucide），
 * 与 frontend/RenpyToolbox/ToolIcon.py 的映射逐项对应，不另画一套。
 */
export const TOOL_ICONS = {
  CONTINUE: rotateCcw,
  ONE_KEY: wandSparkles,
  PROOFREAD: clipboardCheck,
  APPLY: folderInput,
  FONT: typeSvg,
  ADD_LANGUAGE: languages,
  DEFAULT_LANGUAGE: globe,
  EXTRACT_TL: fileDown,
  DIRECT_RPY: filePenLine,
  HOOK: webhook,
  SOURCE: fileCode,
  SUPPLEMENT: filePlus,
  JSON: braces,
  GLOSSARY: bookOpenText,
  PRESERVE: shieldBan,
  HONORIFIC: variable,
  STRUCTURE: table2,
  BATCH: listChecks,
  NAME: usersRound,
  PACK: archive,
  REPAIR: wrench,
  REUSE: clipboardCheck,
  FORMAT: textAlignStart,
  ANDROID: smartphone,
  HTML: fileInput,
  MOD: puzzle,
};

export type ToolIconName = keyof typeof TOOL_ICONS;

export type ToolGroup = 'flow' | 'translate' | 'asset' | 'engineer';

export interface ToolSpec {
  key: string;
  title: string;
  description: string;
  group: ToolGroup;
  /** 需要先选好项目，否则工具无从下手 */
  requiresProject: boolean;
  icon: ToolIconName;
  /** 推荐流程里的执行序号，0 表示不显示（对齐 ItemCard 的 step） */
  step: number;
  /** 搜索关键词，含 Python 侧的 keywords */
  keywords: string[];
}

export const TOOL_GROUP_TITLES: Record<ToolGroup, string> = {
  flow: '推荐流程',
  translate: '翻译方式',
  asset: '资源与词表',
  engineer: '工程与修复',
};

/** 与 Python 侧 GROUP_TITLE_KEYS 的顺序一致：推荐流程排最前 */
export const TOOL_GROUP_ORDER: ToolGroup[] = ['flow', 'translate', 'asset', 'engineer'];

export const TOOL_SPECS: ToolSpec[] = [
  // ---------- 推荐流程 ----------
  {
    key: 'continue_translation',
    title: '继续翻译',
    description: '检测到上次未完成的翻译任务',
    group: 'flow',
    requiresProject: false,
    icon: 'CONTINUE',
    step: 0,
    keywords: ['恢复', '未完成', '进度', 'resume'],
  },
  {
    key: 'one_key_translate',
    title: '一键翻译',
    description: '选择游戏目录，自动完成抽取和翻译',
    group: 'flow',
    requiresProject: false,
    icon: 'ONE_KEY',
    step: 1,
    keywords: ['自动', '全流程', '游戏目录', 'workflow', 'translate'],
  },
  {
    key: 'proofreading',
    title: '检查与润色',
    description: '查看质量报告、校对或润色译文并导出',
    group: 'flow',
    requiresProject: true,
    icon: 'PROOFREAD',
    step: 2,
    keywords: ['校对', '润色', '质检', '质量报告', 'proofread', 'polish'],
  },
  {
    key: 'apply_translation',
    title: '应用翻译到游戏',
    description: '将翻译结果写入游戏的 TL 目录',
    group: 'flow',
    requiresProject: true,
    icon: 'APPLY',
    step: 3,
    keywords: ['写入', '导入', '应用译文', 'tl', 'install'],
  },
  {
    key: 'font_replace',
    title: '字体注入',
    description: '注入预置字体包及对应的界面适配脚本',
    group: 'flow',
    requiresProject: true,
    icon: 'FONT',
    step: 4,
    keywords: ['ttf', 'otf', '字库', '乱码', 'font'],
  },
  {
    key: 'add_language',
    title: '添加语言入口',
    description: '向游戏添加语言切换功能',
    group: 'flow',
    requiresProject: true,
    icon: 'ADD_LANGUAGE',
    step: 5,
    keywords: ['语言切换', '语言菜单', 'language', 'hook'],
  },
  {
    key: 'set_default_language',
    title: '设置默认语言',
    description: '设置游戏启动时的默认语言',
    group: 'flow',
    requiresProject: true,
    icon: 'DEFAULT_LANGUAGE',
    step: 6,
    keywords: ['启动语言', '默认语言', 'language', 'locale'],
  },

  // ---------- 翻译方式 ----------
  {
    key: 'rpy_extraction_settings',
    title: 'RPY 抽取设置',
    description: '分类管理源码和 TL 的内置抽取、自定义正则及使用方案',
    group: 'translate',
    requiresProject: false,
    icon: 'EXTRACT_TL',
    step: 0,
    keywords: ['rpy', '抽取', '正则', '规则', 'regex'],
  },
  {
    key: 'extract_to_tl',
    title: '翻译抽取到 TL',
    description: '使用官方抽取、运行时抽取等高级抽取方式',
    group: 'translate',
    requiresProject: false,
    icon: 'EXTRACT_TL',
    step: 0,
    keywords: ['tl', '抽取', 'extract', '官方抽取', '运行时抽取'],
  },
  {
    key: 'direct_rpy_translate',
    title: '直接翻译 RPY',
    description: '直接翻译 tl/*.rpy 文件',
    group: 'translate',
    requiresProject: false,
    icon: 'DIRECT_RPY',
    step: 0,
    keywords: ['rpy', 'tl', '脚本', 'translate'],
  },
  {
    key: 'hook_translate',
    title: 'HOOK 翻译',
    description: '运行游戏并抽取文本后直接翻译',
    group: 'translate',
    requiresProject: true,
    icon: 'HOOK',
    step: 0,
    keywords: ['hook', '钩子', '运行时', '抽取'],
  },
  {
    key: 'source_translate',
    title: '源码翻译',
    description: '直接翻译 game/*.rpy 源码',
    group: 'translate',
    requiresProject: true,
    icon: 'SOURCE',
    step: 0,
    keywords: ['rpy', '源码', 'game', '脚本', 'source'],
  },
  {
    key: 'hook_supplement',
    title: '补全翻译',
    description: '扫描漏提文本并生成补全脚本',
    group: 'translate',
    requiresProject: true,
    icon: 'SUPPLEMENT',
    step: 0,
    keywords: ['hook', '补丁', '漏翻', '漏提', 'supplement'],
  },
  {
    key: 'extract_json',
    title: '文本提取 JSON',
    description: '导出 JSON 供人工翻译，再导入并应用到 TL',
    group: 'translate',
    requiresProject: false,
    icon: 'JSON',
    step: 0,
    keywords: ['json', '导出', '导入', '人工翻译', 'excel'],
  },

  // ---------- 资源与词表 ----------
  {
    key: 'local_glossary',
    title: '本地词库',
    description: '管理术语表，统一专有名词翻译',
    group: 'asset',
    requiresProject: false,
    icon: 'GLOSSARY',
    step: 0,
    keywords: ['术语', '词表', 'glossary', 'csv', 'excel'],
  },
  {
    key: 'text_preserve',
    title: '禁翻表',
    description: '管理不需要翻译的变量和代码',
    group: 'asset',
    requiresProject: false,
    icon: 'PRESERVE',
    step: 0,
    keywords: ['禁翻', '保留', '变量', '正则', 'placeholder'],
  },
  {
    key: 'honorific_placeholder',
    title: '称呼桥接',
    description: '处理称呼和变量组合文本',
    group: 'asset',
    requiresProject: false,
    icon: 'HONORIFIC',
    step: 0,
    keywords: ['称呼', '变量', '占位符', 'placeholder'],
  },
  {
    key: 'ma_suite',
    title: '终极结构导出',
    description: '导出 Excel 和结构化翻译脚本',
    group: 'asset',
    requiresProject: false,
    icon: 'STRUCTURE',
    step: 0,
    keywords: ['excel', '导出', '结构化', 'ma', '脚本'],
  },
  {
    key: 'batch_correction',
    title: '批量修正',
    description: '通过 Excel 批量修正质检报告中的译文',
    group: 'asset',
    requiresProject: false,
    icon: 'BATCH',
    step: 0,
    keywords: ['excel', '批量', '修正', '质检', 'replace'],
  },
  {
    key: 'name_extraction',
    title: '姓名提取',
    description: '扫描脚本与 JSON，生成角色名清单',
    group: 'asset',
    requiresProject: true,
    icon: 'NAME',
    step: 0,
    keywords: ['姓名', '角色名', '人名', 'json', 'rpy', 'name'],
  },

  // ---------- 工程与修复 ----------
  {
    key: 'pack_unpack',
    title: '解包/打包',
    description: '解包 RPA 文件或打包游戏资源',
    group: 'engineer',
    requiresProject: false,
    icon: 'PACK',
    step: 0,
    keywords: ['rpa', 'rpyc', '反编译', '解压', 'unrpyc', 'unren', 'archive'],
  },
  {
    key: 'error_repair',
    title: '错误修复',
    description: '扫描并修复翻译目录中生成的 .rpy 错误',
    group: 'engineer',
    requiresProject: false,
    icon: 'REPAIR',
    step: 0,
    keywords: ['修复', '报错', 'rpy', 'script', 'repair'],
  },
  {
    key: 'translation_reuse',
    title: '更新翻译复用',
    description: '按原文将旧译文安全填入新版本的空条目',
    group: 'engineer',
    requiresProject: true,
    icon: 'REUSE',
    step: 0,
    keywords: ['更新', '复用', '旧译文', '哈希', 'reuse', 'migrate'],
  },
  {
    key: 'formatter',
    title: '代码格式化',
    description: '格式化 .rpy 文件',
    group: 'engineer',
    requiresProject: false,
    icon: 'FORMAT',
    step: 0,
    keywords: ['格式化', 'rpy', '代码', 'format', 'lint'],
  },
  {
    key: 'android_build',
    title: '安卓打包',
    description: '安装 SDK、生成签名并构建 APK',
    group: 'engineer',
    requiresProject: true,
    icon: 'ANDROID',
    step: 0,
    keywords: ['apk', 'sdk', '签名', 'rapt', 'android', 'gradle'],
  },
  {
    key: 'html_import',
    title: '网页 / AI 翻译向导',
    description: '把 TL 目录变成 TXT，交给 AI 或网页翻译，再一键回填',
    group: 'engineer',
    requiresProject: false,
    icon: 'HTML',
    step: 0,
    keywords: ['html', 'txt', 'excel', '翻译', '向导', '网页', 'AI', 'wizard'],
  },
  {
    key: 'game_mod',
    title: '游戏模组注入',
    description: '注入画廊解锁、修改器等通用模组',
    group: 'engineer',
    requiresProject: false,
    icon: 'MOD',
    step: 0,
    keywords: ['模组', 'mod', '修改器', 'urm', '画廊', '注入'],
  },
];

export function toolsByGroup(): { group: ToolGroup; title: string; tools: ToolSpec[] }[] {
  return TOOL_GROUP_ORDER.map((group) => ({
    group,
    title: TOOL_GROUP_TITLES[group],
    tools: TOOL_SPECS.filter((tool) => tool.group === group),
  }));
}

export function findTool(key: string): ToolSpec | undefined {
  return TOOL_SPECS.find((tool) => tool.key === key);
}

/** 搜索：标题、描述与 Python 侧关键词一起参与匹配。 */
export function searchTools(query: string): ToolSpec[] {
  const needle = query.trim().toLowerCase();
  if (!needle) return TOOL_SPECS;
  return TOOL_SPECS.filter((tool) => {
    const haystack = [tool.title, tool.description, tool.key, ...tool.keywords]
      .join(' ')
      .toLowerCase();
    return haystack.includes(needle);
  });
}
