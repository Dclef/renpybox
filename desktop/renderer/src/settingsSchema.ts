/**
 * 设置项描述表 —— 驱动基础设置 / 专家设置 / 应用设置三个页面。
 *
 * 标题与说明逐字取自 module/Localizer/LocalizerZH.py，字段名与顺序与
 * frontend/Setting/BasicSettingsPage.py、ExpertSettingsPage.py、
 * frontend/AppSettingsPage.py 一致，键就是 Config 的 120 个字段之一。
 * PATCH 未知字段会 400，所以这里的 key 必须真实存在。
 */

export type FieldKind = 'switch' | 'spin' | 'text' | 'password' | 'select' | 'multiline';

export interface FieldSpec {
  key: string;
  title: string;
  description: string;
  kind: FieldKind;
  min?: number;
  max?: number;
  options?: { value: string; label: string }[];
  /** 值为空字符串或 null 时不写入，避免把"未设置"变成"清空" */
  allowEmpty?: boolean;
}

/** 语言下拉：值沿用 base/BaseLanguage.py 的 BaseLanguage.Enum，与 Config 的 str 字段一致。 */
export const LANGUAGE_OPTIONS = [
  { value: 'ZH', label: '中文' },
  { value: 'EN', label: '英文' },
  { value: 'JA', label: '日文' },
  { value: 'KO', label: '韩文' },
  { value: 'RU', label: '俄文' },
  { value: 'AR', label: '阿拉伯文' },
  { value: 'DE', label: '德文' },
  { value: 'FR', label: '法文' },
  { value: 'PL', label: '波兰文' },
  { value: 'ES', label: '西班牙' },
  { value: 'IT', label: '意大利文' },
  { value: 'PT', label: '葡萄牙文' },
  { value: 'HU', label: '匈牙利文' },
  { value: 'TR', label: '土耳其文' },
  { value: 'TH', label: '泰文' },
  { value: 'ID', label: '印尼文' },
  { value: 'VI', label: '越南文' },
];

export const OUTPUT_PROTOCOL_OPTIONS = [
  { value: 'STRUCTURED', label: '结构化 JSON（STRUCTURED）' },
  { value: 'JSONLINE', label: '逐行 JSON（JSONLINE）' },
  { value: 'SINGLE_TEXT', label: '单条纯文本（SINGLE_TEXT）' },
];

/** 应用设置里的语言下拉用的是 app_language（界面语言，不是翻译语言）。 */
export const APP_LANGUAGE_OPTIONS = [
  { value: 'ZH', label: '简体中文' },
  { value: 'EN', label: 'English' },
];

export const BASIC_FIELDS: FieldSpec[] = [
  {
    key: 'max_workers',
    title: '并发任务阈值',
    // 换行照 LocalizerZH.py:742-748 的 <br>：原壳这两张卡的说明是两行，
    // 卡高因此是 82 而不是 66。行内 <b>/<font> 是配色，渲染端只保留加粗。
    description:
      '同时执行的任务数量的最大值\n默认 16；合理设置可以显著加快任务的完成速度，请参考 API 平台的文档进行设置，0 = 自动',
    kind: 'spin',
    min: 0,
    max: 9999999,
  },
  {
    key: 'rpm_threshold',
    title: '每分钟任务数量阈值',
    description:
      '每分钟执行的任务总数量的最大值，即 <b>RPM</b> 阈值\n部分平台会对网络请求的速率进行限制，请参考 API 平台的文档进行设置，0 = 无限制',
    kind: 'spin',
    min: 0,
    max: 9999999,
  },
  {
    key: 'token_threshold',
    title: '任务行数阈值',
    description: '每个任务所包含的文本最大行数；默认 20 行，降低可提升稳定性，提高可减少请求数',
    kind: 'spin',
    min: 0,
    max: 9999999,
  },
  {
    key: 'max_batch_source_tokens',
    title: '每批原文 Token 上限',
    description: '每批原文的 Token 预算，不含提示词和参考上文；0 表示仅按行数切分。单条超长文本独立提交',
    kind: 'spin',
    min: 0,
    max: 9999999,
  },
  {
    key: 'max_output_tokens',
    title: '每次请求输出 Token 上限',
    description: '模型回复的 Token 预算；0 使用接口默认值，重试时保持此预算',
    kind: 'spin',
    min: 0,
    max: 9999999,
  },
  {
    key: 'request_timeout',
    title: '超时时间阈值',
    description: '发起请求时等待模型回复的最长时间（秒）；默认 60 秒，超时后释放并发槽并进入失败重试',
    kind: 'spin',
    min: 0,
    max: 9999999,
  },
  {
    key: 'max_round',
    title: '任务轮次阈值',
    description: '当完成一轮任务后，将在新的轮次中对失败的任务进行重试，直到全部完成或达到轮次阈值',
    kind: 'spin',
    min: 0,
    max: 9999999,
  },
];

/** 「均衡吞吐」按钮要一起改的三个字段，与 BasicSettingsPage._apply_balanced_throughput 一致。 */
export const BALANCED_THROUGHPUT: { values: Record<string, number>; label: string; tooltip: string } = {
  values: { token_threshold: 20, max_batch_source_tokens: 0, max_output_tokens: 0 },
  label: '恢复推荐吞吐配置：20 行 / 原文自动 / 输出自动',
  tooltip:
    '把批行数、原文 Token 预算和输出预算恢复为推荐值；原文自动表示只按行数切分，并发、超时和质量检查保持当前设置',
};

export const EXPERT_FIELDS: FieldSpec[] = [
  {
    key: 'preceding_lines_threshold',
    title: '参考上文行数阈值',
    description: '每个翻译任务最多可携带的参考上文的行数，默认禁用',
    kind: 'spin',
    min: 0,
    max: 9999999,
  },
  {
    key: 'enable_preceding_on_local',
    title: '本地接口启用参考上文',
    description: '本地模型性能较差，参考上文功能大部分时候是负面效果，默认禁用',
    kind: 'switch',
  },
  {
    key: 'single_line_translation_enable',
    title: '单行翻译模式',
    description:
      '启用后，每次请求只提交一行原文，并允许模型直接返回纯文本译文；适合腾讯 hy1.5 等速度快但批量 JSONLINE 格式容易错位的小模型，会增加请求次数但可显著降低行数不一致',
    kind: 'switch',
  },
  {
    key: 'translation_output_protocol',
    title: '翻译输出协议',
    description: 'SINGLE_TEXT 只允许单条任务，选择后会自动启用单行翻译模式',
    kind: 'select',
    options: OUTPUT_PROTOCOL_OPTIONS,
  },
  {
    key: 'asset_regex_enable',
    title: '项目资产正则匹配',
    description: '启用后，明确标记为正则的术语与禁翻项会按正则表达式匹配',
    kind: 'switch',
  },
  {
    key: 'asset_prompt_token_budget',
    title: '项目资产 Token 预算',
    description: '每个任务可注入的动态项目资产 Token 上限',
    kind: 'spin',
    min: 1,
    max: 9999999,
  },
  {
    key: 'asset_prompt_max_items',
    title: '项目资产条目上限',
    description: '每个任务可注入的动态项目资产最大条目数',
    kind: 'spin',
    min: 1,
    max: 9999999,
  },
  {
    key: 'clean_ruby',
    title: '清理原文中的注音文本',
    description:
      '移除注音上标中的注音部分，仅保留正文部分，默认启用；支持的注音格式包括 (漢字/かんじ)、[漢字/かんじ]、\\r[漢字,かんじ]、[ruby text=かんじ] 等',
    kind: 'switch',
  },
  {
    key: 'deduplication_in_trans',
    title: 'T++ 项目文件中对重复文本去重',
    description: '在 T++ 项目文件（即 .trans 文件）中，如有重复文本是否去重，默认启用',
    kind: 'switch',
  },
  {
    key: 'deduplication_in_bilingual',
    title: '双语输出文件中原文与译文一致的文本只输出一次',
    description: '在字幕与电子书中，如目标文本的原文与译文一致是否只输出一次，默认启用',
    kind: 'switch',
  },
  {
    key: 'write_translated_name_fields_to_file',
    title: '将姓名字段译文写入输出文件',
    description:
      '部分 GalGame 中，姓名字段数据与立绘、配音等资源文件绑定，翻译后会报错，此时可以关闭该功能，默认启用；支持 RenPy 导出的 .rpy 与 VNTextPatch/SExtractor 导出的带 name 字段 .json',
    kind: 'switch',
  },
  {
    key: 'auto_process_prefix_suffix_preserved_text',
    title: '自动处理前后缀的保护文本段',
    description:
      '启用后，头尾命中保护规则的文本段将被移除，翻译完成后再拼接回去；禁用后会把完整文本条目发送给模型，语义更完整但文本保护效果下降',
    kind: 'switch',
  },
  {
    key: 'honorific_placeholder_bridge_enable',
    title: '称呼变量智能桥接',
    description:
      '自动处理称呼 + 变量场景（如 Mr.[xx]），避免模型丢失变量并修正中文语序，默认启用；译前临时替换为结构化占位符，译后自动还原',
    kind: 'switch',
  },
  {
    key: 'sakura_jsonline_retry_enable',
    title: 'Sakura JSONLINE 解析失败时格式化重试',
    description: '当 SakuraLLM 回复不是 JSONLINE 时，自动发起一次格式化重试，提高通过率',
    kind: 'switch',
  },
  {
    key: 'result_checker_retry_count_threshold',
    title: '结果检查 - 重试次数达到阈值',
    description:
      '是否在结果检查报告里面输出「重试次数达到阈值」的条目列表；重试达阈值后会放宽部分检查，但原文照抄、空译文等明显异常仍不会直接通过',
    kind: 'switch',
  },
  {
    key: 'mixed_language_cleanup_enable',
    title: '混合翻译清理',
    description: '清理译文里残留的原文片段（需要同时配置 mixed_language_replacements 规则）',
    kind: 'switch',
  },
  {
    key: 'auto_glossary_enable',
    title: '自动补全术语表（不支持 SakuraLLM 模型）',
    description:
      '翻译的同时尝试自动补全术语表中缺失的专有名词条目，只有在启用术语表功能时才生效；可能产生不合适的条目，建议仅在 DeepSeek V3/R1 级别的强力模型使用',
    kind: 'switch',
  },
  {
    key: 'mtool_optimizer_enable',
    title: 'MTool 优化器',
    description:
      '在对 MTool 文本进行翻译时，至多可减少 40% 的翻译时间与 Token 消耗；可能导致原文残留或语句不连贯，请自行判断，并且只应在翻译 MTool 文本时启用',
    kind: 'switch',
  },
];

/** 全局缩放倍率：值就是 Qt 侧存的文本（`config.scale_factor`），空串 = 自动。 */
export const SCALE_FACTOR_OPTIONS = [
  { value: '', label: '自动' },
  ...Object.keys({ '125%': '1.25', '150%': '1.50', '175%': '1.75', '200%': '2.00' }).map((key) => ({
    value: key,
    label: key,
  })),
];

/**
 * 应用设置页字段，顺序照 `renpybox/frontend/AppSettingsPage.py:89-95`：
 * 应用语言 → 关于与更新（GroupCard，不在本表）→ 启动音效 → 专家模式
 * → 字体优化 → 全局缩放倍率 → 网络代理。
 *
 * 注意：`startup_sound_path` / `startup_sound_volume` / `cache_use_sqlite` 都是
 * 真实存在的 Config 字段，但**原壳应用设置页没有给它们任何控件**（实测页面上
 * 只有 7 张卡），所以这里也不放，避免又造出原版没有的界面。
 */
export const APP_FIELDS: FieldSpec[] = [
  {
    key: 'app_language',
    title: '应用语言',
    description: '选择应用界面语言，更改将在重启应用后生效',
    kind: 'select',
    options: APP_LANGUAGE_OPTIONS,
  },
  {
    key: 'startup_sound_enable',
    title: '启动音效',
    description: '启用后，应用启动时会播放提示音（默认关闭）',
    kind: 'switch',
  },
  {
    key: 'expert_mode',
    title: '专家模式',
    description: '启用此功能后，将显示更多日志信息并提供更多高级设置选项（将在应用重启后生效）',
    kind: 'switch',
  },
  {
    key: 'font_hinting',
    title: '字体优化',
    description: '启用此功能后，应用内 UI 字体的边缘渲染将更加圆润（将在应用重启后生效）',
    kind: 'switch',
  },
  {
    key: 'scale_factor',
    title: '全局缩放比例',
    description: '启用此功能后，应用界面将按照所选比例进行缩放（将在应用重启后生效）',
    kind: 'select',
    options: SCALE_FACTOR_OPTIONS,
    allowEmpty: true,
  },
];

/** 代理卡：文字取自 `app_settings_page_proxy_url*`，输入框 placeholder 用 `app_settings_page_proxy_url`。 */
export const PROXY_FIELD: FieldSpec = {
  key: 'proxy_url',
  title: '网络代理',
  description: '启用此功能后，将使用设置的代理地址发送网络请求（将在应用重启后生效）',
  kind: 'text',
  allowEmpty: true,
};

export const PROJECT_FIELDS: FieldSpec[] = [
  {
    key: 'source_language',
    title: '原文语言',
    description: '设置当前项目中输入文本的语言',
    kind: 'select',
    options: LANGUAGE_OPTIONS,
  },
  {
    key: 'target_language',
    title: '译文语言',
    description: '设置当前项目中输出文本的语言',
    kind: 'select',
    options: LANGUAGE_OPTIONS,
  },
  {
    key: 'output_folder_open_on_finish',
    title: '任务完成时打开输出文件夹',
    description: '启用此功能后，将在任务完成时自动打开输出文件夹',
    kind: 'switch',
  },
  {
    key: 'traditional_chinese_enable',
    title: '使用繁体输出中文',
    description: '启用此功能后，在译文语言设置为中文时，将使用繁体字形输出中文文本',
    kind: 'switch',
  },
];
