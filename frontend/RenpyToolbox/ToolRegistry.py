from dataclasses import dataclass

from qfluentwidgets import FluentIconBase

from frontend.RenpyToolbox.ToolIcon import ToolIcon


FLOW = "flow"
TRANSLATE = "translate"
ASSET = "asset"
ENGINEER = "engineer"

GROUP_TITLES = {
    FLOW: "推荐流程",
    TRANSLATE: "翻译方式",
    ASSET: "资源与词表",
    ENGINEER: "工程与修复",
}


@dataclass(frozen=True)
class ToolSpec:
    """工具箱入口的声明式配置。"""

    key: str
    title: str
    description: str
    group: str
    page_cls: type | None = None
    object_name: str = ""
    icon: FluentIconBase | None = None
    requires_project: bool = False
    keywords: tuple[str, ...] = ()
    handler: str = ""
    lazy_import: str = ""


TOOL_SPECS = (
    ToolSpec(
        "continue_translation",
        "继续翻译",
        "检测到上次未完成的翻译任务",
        FLOW,
        icon=ToolIcon.CONTINUE,
        keywords=("恢复", "未完成", "进度", "resume"),
        handler="_open_continue_translation",
    ),
    ToolSpec(
        "one_key_translate",
        "一键翻译",
        "选择游戏目录，自动完成抽取和翻译",
        FLOW,
        object_name="yi-jian-fanyi",
        icon=ToolIcon.ONE_KEY,
        keywords=("自动", "全流程", "游戏目录", "workflow", "translate"),
        handler="_open_one_key_translate",
        lazy_import="frontend.RenpyToolbox.OneKeyTranslatePage:YiJianFanyiPage",
    ),
    ToolSpec(
        "proofreading",
        "检查与润色",
        "查看质量报告、校对或润色译文并导出",
        FLOW,
        object_name="proofreading_page",
        icon=ToolIcon.PROOFREAD,
        requires_project=True,
        keywords=("校对", "润色", "质检", "质量报告", "proofread", "polish"),
        lazy_import="frontend.Proofreading.ProofreadingPage:ProofreadingPage",
    ),
    ToolSpec(
        "apply_translation",
        "应用翻译到游戏",
        "将翻译结果写入游戏的 TL 目录",
        FLOW,
        icon=ToolIcon.APPLY,
        requires_project=True,
        keywords=("写入", "导入", "应用译文", "tl", "install"),
        handler="_open_apply_translation",
    ),
    ToolSpec(
        "font_replace",
        "字体注入",
        "注入预置字体包及对应的界面适配脚本",
        FLOW,
        object_name="font-replace",
        icon=ToolIcon.FONT,
        requires_project=True,
        keywords=("ttf", "otf", "字库", "乱码", "font"),
        lazy_import="frontend.RenpyToolbox.FontReplacePage:FontReplacePage",
    ),
    ToolSpec(
        "add_language",
        "添加语言入口",
        "向游戏添加语言切换功能",
        FLOW,
        object_name="add-language",
        icon=ToolIcon.ADD_LANGUAGE,
        requires_project=True,
        keywords=("语言切换", "语言菜单", "language", "hook"),
        lazy_import="frontend.RenpyToolbox.AddLanguageEntrancePage:AddLanguageEntrancePage",
    ),
    ToolSpec(
        "set_default_language",
        "设置默认语言",
        "设置游戏启动时的默认语言",
        FLOW,
        object_name="set-default-language",
        icon=ToolIcon.DEFAULT_LANGUAGE,
        requires_project=True,
        keywords=("启动语言", "默认语言", "language", "locale"),
        lazy_import="frontend.RenpyToolbox.SetDefaultLanguagePage:SetDefaultLanguagePage",
    ),
    ToolSpec(
        "extract_to_tl",
        "翻译抽取到 TL",
        "使用官方抽取、运行时抽取等高级抽取方式",
        TRANSLATE,
        icon=ToolIcon.EXTRACT_TL,
        keywords=("tl", "抽取", "extract", "官方抽取", "运行时抽取"),
        lazy_import="frontend.RenpyTranslationPage:RenpyTranslationPage",
    ),
    ToolSpec(
        "direct_rpy_translate",
        "直接翻译 RPY",
        "直接翻译 tl/*.rpy 文件",
        TRANSLATE,
        object_name="direct-rpy-translate",
        icon=ToolIcon.DIRECT_RPY,
        keywords=("rpy", "tl", "脚本", "translate"),
        lazy_import="frontend.RenpyToolbox.DirectRpyTranslatePage:DirectRpyTranslatePage",
    ),
    ToolSpec(
        "hook_translate",
        "HOOK 翻译",
        "运行游戏并抽取文本后直接翻译",
        TRANSLATE,
        object_name="hook-translate",
        icon=ToolIcon.HOOK,
        requires_project=True,
        keywords=("hook", "钩子", "运行时", "抽取"),
        lazy_import="frontend.RenpyToolbox.HookTranslatePage:HookTranslatePage",
    ),
    ToolSpec(
        "source_translate",
        "源码翻译",
        "直接翻译 game/*.rpy 源码",
        TRANSLATE,
        object_name="source-translate",
        icon=ToolIcon.SOURCE,
        requires_project=True,
        keywords=("rpy", "源码", "game", "脚本", "source"),
        lazy_import="frontend.RenpyToolbox.SourceTranslatePage:SourceTranslatePage",
    ),
    ToolSpec(
        "hook_supplement",
        "补全翻译",
        "扫描漏提文本并生成补全脚本",
        TRANSLATE,
        object_name="hook-supplement",
        icon=ToolIcon.SUPPLEMENT,
        requires_project=True,
        keywords=("hook", "补丁", "漏翻", "漏提", "supplement"),
        lazy_import="frontend.RenpyToolbox.HookSupplementPage:HookSupplementPage",
    ),
    ToolSpec(
        "extract_json",
        "文本提取 JSON",
        "导出 JSON 供人工翻译，再导入并应用到 TL",
        TRANSLATE,
        object_name="extract-json",
        icon=ToolIcon.JSON,
        keywords=("json", "导出", "导入", "人工翻译", "excel"),
        lazy_import="frontend.RenpyToolbox.ExtractTab:ExtractTab",
    ),
    ToolSpec(
        "local_glossary",
        "本地词库",
        "管理术语表，统一专有名词翻译",
        ASSET,
        object_name="local-glossary",
        icon=ToolIcon.GLOSSARY,
        keywords=("术语", "词表", "glossary", "csv", "excel"),
        lazy_import="frontend.RenpyToolbox.LocalGlossaryPage:LocalGlossaryPage",
    ),
    ToolSpec(
        "text_preserve",
        "禁翻表",
        "管理不需要翻译的变量和代码",
        ASSET,
        object_name="text-preserve",
        icon=ToolIcon.PRESERVE,
        keywords=("禁翻", "保留", "变量", "正则", "placeholder"),
        lazy_import="frontend.RenpyToolbox.TextPreservePage:TextPreservePage",
    ),
    ToolSpec(
        "honorific_placeholder",
        "称呼桥接",
        "处理称呼和变量组合文本",
        ASSET,
        object_name="honorific-placeholder",
        icon=ToolIcon.HONORIFIC,
        keywords=("称呼", "变量", "占位符", "placeholder"),
        lazy_import="frontend.RenpyToolbox.HonorificPlaceholderPage:HonorificPlaceholderPage",
    ),
    ToolSpec(
        "ma_suite",
        "终极结构导出",
        "导出 Excel 和结构化翻译脚本",
        ASSET,
        object_name="ma-suite",
        icon=ToolIcon.STRUCTURE,
        keywords=("excel", "导出", "结构化", "ma", "脚本"),
        lazy_import="frontend.RenpyToolbox.MaSuitePage:MaSuitePage",
    ),
    ToolSpec(
        "batch_correction",
        "批量修正",
        "通过 Excel 批量修正质检报告中的译文",
        ASSET,
        object_name="batch-correction",
        icon=ToolIcon.BATCH,
        keywords=("excel", "批量", "修正", "质检", "replace"),
        lazy_import="frontend.RenpyToolbox.BatchCorrectionPage:BatchCorrectionPage",
    ),
    ToolSpec(
        "name_extraction",
        "姓名提取",
        "扫描脚本与 JSON，生成角色名清单",
        ASSET,
        object_name="name-extraction",
        icon=ToolIcon.NAME,
        requires_project=True,
        keywords=("姓名", "角色名", "人名", "json", "rpy", "name"),
        lazy_import="frontend.RenpyToolbox.NameExtractionPage:NameExtractionPage",
    ),
    ToolSpec(
        "pack_unpack",
        "解包/打包",
        "解包 RPA 文件或打包游戏资源",
        ENGINEER,
        object_name="pack-unpack",
        icon=ToolIcon.PACK,
        keywords=("rpa", "rpyc", "反编译", "解压", "unrpyc", "unren", "archive"),
        lazy_import="frontend.RenpyToolbox.PackUnpackPage:PackUnpackPage",
    ),
    ToolSpec(
        "error_repair",
        "错误修复",
        "扫描并修复常见脚本错误",
        ENGINEER,
        object_name="error-repair",
        icon=ToolIcon.REPAIR,
        keywords=("修复", "报错", "rpy", "script", "repair"),
        lazy_import="frontend.RenpyToolbox.ErrorRepairPage:ErrorRepairPage",
    ),
    ToolSpec(
        "translation_reuse",
        "更新翻译复用",
        "按原文将旧译文安全填入新版本的空条目",
        ENGINEER,
        object_name="translation-reuse",
        icon=ToolIcon.REUSE,
        requires_project=True,
        keywords=("更新", "复用", "旧译文", "哈希", "reuse", "migrate"),
        lazy_import="frontend.RenpyToolbox.TranslationReusePage:TranslationReusePage",
    ),
    ToolSpec(
        "formatter",
        "代码格式化",
        "格式化 .rpy 文件",
        ENGINEER,
        object_name="formatter",
        icon=ToolIcon.FORMAT,
        keywords=("格式化", "rpy", "代码", "format", "lint"),
        lazy_import="frontend.RenpyToolbox.FormatterPage:FormatterPage",
    ),
    ToolSpec(
        "android_build",
        "安卓打包",
        "安装 SDK、生成签名并构建 APK",
        ENGINEER,
        object_name="android-build",
        icon=ToolIcon.ANDROID,
        requires_project=True,
        keywords=("apk", "sdk", "签名", "rapt", "android", "gradle"),
        lazy_import="frontend.RenpyToolbox.AndroidBuildPage:AndroidBuildPage",
    ),
    ToolSpec(
        "html_import",
        "HTML 导入",
        "在 HTML、TXT 与 Excel 之间转换翻译文本",
        ENGINEER,
        object_name="html-import",
        icon=ToolIcon.HTML,
        keywords=("html", "txt", "excel", "导入", "导出", "convert"),
        lazy_import="frontend.RenpyToolbox.HtmlImportPage:HtmlImportPage",
    ),
    ToolSpec(
        "game_mod",
        "游戏模组注入",
        "注入修改器、自定义按钮栏等通用模组",
        ENGINEER,
        object_name="game-mod",
        icon=ToolIcon.MOD,
        keywords=("模组", "mod", "修改器", "urm", "按钮栏", "注入"),
        lazy_import="frontend.RenpyToolbox.GameModPage:GameModPage",
    ),
)
