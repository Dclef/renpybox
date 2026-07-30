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
    handler: str = ""
    lazy_import: str = ""


TOOL_SPECS = (
    ToolSpec(
        "continue_translation",
        "继续翻译",
        "检测到上次未完成的翻译任务",
        FLOW,
        icon=ToolIcon.CONTINUE,
        handler="_open_continue_translation",
    ),
    ToolSpec(
        "one_key_translate",
        "一键翻译",
        "选择游戏目录，自动完成抽取和翻译",
        FLOW,
        object_name="yi-jian-fanyi",
        icon=ToolIcon.ONE_KEY,
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
        lazy_import="frontend.Proofreading.ProofreadingPage:ProofreadingPage",
    ),
    ToolSpec(
        "apply_translation",
        "应用翻译到游戏",
        "将翻译结果写入游戏的 TL 目录",
        FLOW,
        icon=ToolIcon.APPLY,
        handler="_open_apply_translation",
    ),
    ToolSpec(
        "font_replace",
        "字体注入",
        "注入预置字体包及对应的界面适配脚本",
        FLOW,
        object_name="font-replace",
        icon=ToolIcon.FONT,
        lazy_import="frontend.RenpyToolbox.FontReplacePage:FontReplacePage",
    ),
    ToolSpec(
        "add_language",
        "添加语言入口",
        "向游戏添加语言切换功能",
        FLOW,
        object_name="add-language",
        icon=ToolIcon.ADD_LANGUAGE,
        lazy_import="frontend.RenpyToolbox.AddLanguageEntrancePage:AddLanguageEntrancePage",
    ),
    ToolSpec(
        "set_default_language",
        "设置默认语言",
        "设置游戏启动时的默认语言",
        FLOW,
        object_name="set-default-language",
        icon=ToolIcon.DEFAULT_LANGUAGE,
        lazy_import="frontend.RenpyToolbox.SetDefaultLanguagePage:SetDefaultLanguagePage",
    ),
    ToolSpec(
        "extract_to_tl",
        "翻译抽取到 TL",
        "使用官方抽取、运行时抽取等高级抽取方式",
        TRANSLATE,
        icon=ToolIcon.EXTRACT_TL,
        lazy_import="frontend.RenpyTranslationPage:RenpyTranslationPage",
    ),
    ToolSpec(
        "direct_rpy_translate",
        "直接翻译 RPY",
        "直接翻译 tl/*.rpy 文件",
        TRANSLATE,
        object_name="direct-rpy-translate",
        icon=ToolIcon.DIRECT_RPY,
        lazy_import="frontend.RenpyToolbox.DirectRpyTranslatePage:DirectRpyTranslatePage",
    ),
    ToolSpec(
        "hook_translate",
        "HOOK 翻译",
        "运行游戏并抽取文本后直接翻译",
        TRANSLATE,
        object_name="hook-translate",
        icon=ToolIcon.HOOK,
        lazy_import="frontend.RenpyToolbox.HookTranslatePage:HookTranslatePage",
    ),
    ToolSpec(
        "source_translate",
        "源码翻译",
        "直接翻译 game/*.rpy 源码",
        TRANSLATE,
        object_name="source-translate",
        icon=ToolIcon.SOURCE,
        lazy_import="frontend.RenpyToolbox.SourceTranslatePage:SourceTranslatePage",
    ),
    ToolSpec(
        "hook_supplement",
        "补全翻译",
        "扫描漏提文本并生成补全脚本",
        TRANSLATE,
        object_name="hook-supplement",
        icon=ToolIcon.SUPPLEMENT,
        lazy_import="frontend.RenpyToolbox.HookSupplementPage:HookSupplementPage",
    ),
    ToolSpec(
        "extract_json",
        "文本提取 JSON",
        "导出 JSON 供人工翻译，再导入并应用到 TL",
        TRANSLATE,
        object_name="extract-json",
        icon=ToolIcon.JSON,
        lazy_import="frontend.RenpyToolbox.ExtractTab:ExtractTab",
    ),
    ToolSpec(
        "local_glossary",
        "本地词库",
        "管理术语表，统一专有名词翻译",
        ASSET,
        object_name="local-glossary",
        icon=ToolIcon.GLOSSARY,
        lazy_import="frontend.RenpyToolbox.LocalGlossaryPage:LocalGlossaryPage",
    ),
    ToolSpec(
        "text_preserve",
        "禁翻表",
        "管理不需要翻译的变量和代码",
        ASSET,
        object_name="text-preserve",
        icon=ToolIcon.PRESERVE,
        lazy_import="frontend.RenpyToolbox.TextPreservePage:TextPreservePage",
    ),
    ToolSpec(
        "honorific_placeholder",
        "称呼桥接",
        "处理称呼和变量组合文本",
        ASSET,
        object_name="honorific-placeholder",
        icon=ToolIcon.HONORIFIC,
        lazy_import="frontend.RenpyToolbox.HonorificPlaceholderPage:HonorificPlaceholderPage",
    ),
    ToolSpec(
        "ma_suite",
        "终极结构导出",
        "导出 Excel 和结构化翻译脚本",
        ASSET,
        object_name="ma-suite",
        icon=ToolIcon.STRUCTURE,
        lazy_import="frontend.RenpyToolbox.MaSuitePage:MaSuitePage",
    ),
    ToolSpec(
        "batch_correction",
        "批量修正",
        "通过 Excel 批量修正质检报告中的译文",
        ASSET,
        object_name="batch-correction",
        icon=ToolIcon.BATCH,
        lazy_import="frontend.RenpyToolbox.BatchCorrectionPage:BatchCorrectionPage",
    ),
    ToolSpec(
        "name_extraction",
        "姓名提取",
        "扫描脚本与 JSON，生成角色名清单",
        ASSET,
        object_name="name-extraction",
        icon=ToolIcon.NAME,
        lazy_import="frontend.RenpyToolbox.NameExtractionPage:NameExtractionPage",
    ),
    ToolSpec(
        "pack_unpack",
        "解包/打包",
        "解包 RPA 文件或打包游戏资源",
        ENGINEER,
        object_name="pack-unpack",
        icon=ToolIcon.PACK,
        lazy_import="frontend.RenpyToolbox.PackUnpackPage:PackUnpackPage",
    ),
    ToolSpec(
        "error_repair",
        "错误修复",
        "扫描并修复常见脚本错误",
        ENGINEER,
        object_name="error-repair",
        icon=ToolIcon.REPAIR,
        lazy_import="frontend.RenpyToolbox.ErrorRepairPage:ErrorRepairPage",
    ),
    ToolSpec(
        "formatter",
        "代码格式化",
        "格式化 .rpy 文件",
        ENGINEER,
        object_name="formatter",
        icon=ToolIcon.FORMAT,
        lazy_import="frontend.RenpyToolbox.FormatterPage:FormatterPage",
    ),
    ToolSpec(
        "android_build",
        "安卓打包",
        "安装 SDK、生成签名并构建 APK",
        ENGINEER,
        object_name="android-build",
        icon=ToolIcon.ANDROID,
        lazy_import="frontend.RenpyToolbox.AndroidBuildPage:AndroidBuildPage",
    ),
    ToolSpec(
        "html_import",
        "HTML 导入",
        "在 HTML、TXT 与 Excel 之间转换翻译文本",
        ENGINEER,
        object_name="html-import",
        icon=ToolIcon.HTML,
        lazy_import="frontend.RenpyToolbox.HtmlImportPage:HtmlImportPage",
    ),
)
