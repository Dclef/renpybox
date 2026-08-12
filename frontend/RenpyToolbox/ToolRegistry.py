from dataclasses import dataclass

from qfluentwidgets import FluentIconBase

from frontend.RenpyToolbox.ToolIcon import ToolIcon
from module.Localizer.Localizer import Localizer
from module.Localizer.LocalizerEN import LocalizerEN
from module.Localizer.LocalizerZH import LocalizerZH


FLOW = "flow"
TRANSLATE = "translate"
ASSET = "asset"
ENGINEER = "engineer"

GROUP_TITLE_KEYS = {
    FLOW: "toolbox_group_flow",
    TRANSLATE: "toolbox_group_translate",
    ASSET: "toolbox_group_asset",
    ENGINEER: "toolbox_group_engineer",
}

GROUP_TITLES = {
    group: getattr(LocalizerZH, resource_key)
    for group, resource_key in GROUP_TITLE_KEYS.items()
}

GROUP_TITLES_EN = {
    group: getattr(LocalizerEN, resource_key)
    for group, resource_key in GROUP_TITLE_KEYS.items()
}


def get_group_title(group: str) -> str:
    return getattr(Localizer.get(), GROUP_TITLE_KEYS[group])


@dataclass(frozen=True)
class ToolSpec:
    """工具箱入口的声明式配置。"""

    key: str
    title_key: str
    description_key: str
    group: str
    page_cls: type | None = None
    object_name: str = ""
    icon: FluentIconBase | None = None
    requires_project: bool = False
    keywords: tuple[str, ...] = ()
    handler: str = ""
    lazy_import: str = ""

    @property
    def title(self) -> str:
        return getattr(LocalizerZH, self.title_key)

    @property
    def description(self) -> str:
        return getattr(LocalizerZH, self.description_key)

    @property
    def title_en(self) -> str:
        return getattr(LocalizerEN, self.title_key)

    @property
    def description_en(self) -> str:
        return getattr(LocalizerEN, self.description_key)

    def localized_title(self) -> str:
        return getattr(Localizer.get(), self.title_key)

    def localized_description(self) -> str:
        return getattr(Localizer.get(), self.description_key)


TOOL_SPECS = (
    ToolSpec(
        "continue_translation",
        'toolbox_tool_continue_translation_title',
        'toolbox_tool_continue_translation_description',
        FLOW,
        icon=ToolIcon.CONTINUE,
        keywords=("恢复", "未完成", "进度", "resume"),
        handler="_open_continue_translation",
    ),
    ToolSpec(
        "one_key_translate",
        'toolbox_tool_one_key_translate_title',
        'toolbox_tool_one_key_translate_description',
        FLOW,
        object_name="yi-jian-fanyi",
        icon=ToolIcon.ONE_KEY,
        keywords=("自动", "全流程", "游戏目录", "workflow", "translate"),
        handler="_open_one_key_translate",
        lazy_import="frontend.RenpyToolbox.OneKeyTranslatePage:YiJianFanyiPage",
    ),
    ToolSpec(
        "proofreading",
        'toolbox_tool_proofreading_title',
        'toolbox_tool_proofreading_description',
        FLOW,
        object_name="proofreading_page",
        icon=ToolIcon.PROOFREAD,
        requires_project=True,
        keywords=("校对", "润色", "质检", "质量报告", "proofread", "polish"),
        lazy_import="frontend.Proofreading.ProofreadingPage:ProofreadingPage",
    ),
    ToolSpec(
        "apply_translation",
        'toolbox_tool_apply_translation_title',
        'toolbox_tool_apply_translation_description',
        FLOW,
        icon=ToolIcon.APPLY,
        requires_project=True,
        keywords=("写入", "导入", "应用译文", "tl", "install"),
        handler="_open_apply_translation",
    ),
    ToolSpec(
        "font_replace",
        'toolbox_tool_font_replace_title',
        'toolbox_tool_font_replace_description',
        FLOW,
        object_name="font-replace",
        icon=ToolIcon.FONT,
        requires_project=True,
        keywords=("ttf", "otf", "字库", "乱码", "font"),
        lazy_import="frontend.RenpyToolbox.FontReplacePage:FontReplacePage",
    ),
    ToolSpec(
        "add_language",
        'toolbox_tool_add_language_title',
        'toolbox_tool_add_language_description',
        FLOW,
        object_name="add-language",
        icon=ToolIcon.ADD_LANGUAGE,
        requires_project=True,
        keywords=("语言切换", "语言菜单", "language", "hook"),
        lazy_import="frontend.RenpyToolbox.AddLanguageEntrancePage:AddLanguageEntrancePage",
    ),
    ToolSpec(
        "set_default_language",
        'toolbox_tool_set_default_language_title',
        'toolbox_tool_set_default_language_description',
        FLOW,
        object_name="set-default-language",
        icon=ToolIcon.DEFAULT_LANGUAGE,
        requires_project=True,
        keywords=("启动语言", "默认语言", "language", "locale"),
        lazy_import="frontend.RenpyToolbox.SetDefaultLanguagePage:SetDefaultLanguagePage",
    ),
    ToolSpec(
        "extract_to_tl",
        'toolbox_tool_extract_to_tl_title',
        'toolbox_tool_extract_to_tl_description',
        TRANSLATE,
        icon=ToolIcon.EXTRACT_TL,
        keywords=("tl", "抽取", "extract", "官方抽取", "运行时抽取"),
        lazy_import="frontend.RenpyTranslationPage:RenpyTranslationPage",
    ),
    ToolSpec(
        "direct_rpy_translate",
        'toolbox_tool_direct_rpy_translate_title',
        'toolbox_tool_direct_rpy_translate_description',
        TRANSLATE,
        object_name="direct-rpy-translate",
        icon=ToolIcon.DIRECT_RPY,
        keywords=("rpy", "tl", "脚本", "translate"),
        lazy_import="frontend.RenpyToolbox.DirectRpyTranslatePage:DirectRpyTranslatePage",
    ),
    ToolSpec(
        "hook_translate",
        'toolbox_tool_hook_translate_title',
        'toolbox_tool_hook_translate_description',
        TRANSLATE,
        object_name="hook-translate",
        icon=ToolIcon.HOOK,
        requires_project=True,
        keywords=("hook", "钩子", "运行时", "抽取"),
        lazy_import="frontend.RenpyToolbox.HookTranslatePage:HookTranslatePage",
    ),
    ToolSpec(
        "source_translate",
        'toolbox_tool_source_translate_title',
        'toolbox_tool_source_translate_description',
        TRANSLATE,
        object_name="source-translate",
        icon=ToolIcon.SOURCE,
        requires_project=True,
        keywords=("rpy", "源码", "game", "脚本", "source"),
        lazy_import="frontend.RenpyToolbox.SourceTranslatePage:SourceTranslatePage",
    ),
    ToolSpec(
        "hook_supplement",
        'toolbox_tool_hook_supplement_title',
        'toolbox_tool_hook_supplement_description',
        TRANSLATE,
        object_name="hook-supplement",
        icon=ToolIcon.SUPPLEMENT,
        requires_project=True,
        keywords=("hook", "补丁", "漏翻", "漏提", "supplement"),
        lazy_import="frontend.RenpyToolbox.HookSupplementPage:HookSupplementPage",
    ),
    ToolSpec(
        "extract_json",
        'toolbox_tool_extract_json_title',
        'toolbox_tool_extract_json_description',
        TRANSLATE,
        object_name="extract-json",
        icon=ToolIcon.JSON,
        keywords=("json", "导出", "导入", "人工翻译", "excel"),
        lazy_import="frontend.RenpyToolbox.ExtractTab:ExtractTab",
    ),
    ToolSpec(
        "local_glossary",
        'toolbox_tool_local_glossary_title',
        'toolbox_tool_local_glossary_description',
        ASSET,
        object_name="local-glossary",
        icon=ToolIcon.GLOSSARY,
        keywords=("术语", "词表", "glossary", "csv", "excel"),
        lazy_import="frontend.RenpyToolbox.LocalGlossaryPage:LocalGlossaryPage",
    ),
    ToolSpec(
        "text_preserve",
        'toolbox_tool_text_preserve_title',
        'toolbox_tool_text_preserve_description',
        ASSET,
        object_name="text-preserve",
        icon=ToolIcon.PRESERVE,
        keywords=("禁翻", "保留", "变量", "正则", "placeholder"),
        lazy_import="frontend.RenpyToolbox.TextPreservePage:TextPreservePage",
    ),
    ToolSpec(
        "honorific_placeholder",
        'toolbox_tool_honorific_placeholder_title',
        'toolbox_tool_honorific_placeholder_description',
        ASSET,
        object_name="honorific-placeholder",
        icon=ToolIcon.HONORIFIC,
        keywords=("称呼", "变量", "占位符", "placeholder"),
        lazy_import="frontend.RenpyToolbox.HonorificPlaceholderPage:HonorificPlaceholderPage",
    ),
    ToolSpec(
        "ma_suite",
        'toolbox_tool_ma_suite_title',
        'toolbox_tool_ma_suite_description',
        ASSET,
        object_name="ma-suite",
        icon=ToolIcon.STRUCTURE,
        keywords=("excel", "导出", "结构化", "ma", "脚本"),
        lazy_import="frontend.RenpyToolbox.MaSuitePage:MaSuitePage",
    ),
    ToolSpec(
        "batch_correction",
        'toolbox_tool_batch_correction_title',
        'toolbox_tool_batch_correction_description',
        ASSET,
        object_name="batch-correction",
        icon=ToolIcon.BATCH,
        keywords=("excel", "批量", "修正", "质检", "replace"),
        lazy_import="frontend.RenpyToolbox.BatchCorrectionPage:BatchCorrectionPage",
    ),
    ToolSpec(
        "name_extraction",
        'toolbox_tool_name_extraction_title',
        'toolbox_tool_name_extraction_description',
        ASSET,
        object_name="name-extraction",
        icon=ToolIcon.NAME,
        requires_project=True,
        keywords=("姓名", "角色名", "人名", "json", "rpy", "name"),
        lazy_import="frontend.RenpyToolbox.NameExtractionPage:NameExtractionPage",
    ),
    ToolSpec(
        "pack_unpack",
        'toolbox_tool_pack_unpack_title',
        'toolbox_tool_pack_unpack_description',
        ENGINEER,
        object_name="pack-unpack",
        icon=ToolIcon.PACK,
        keywords=("rpa", "rpyc", "反编译", "解压", "unrpyc", "unren", "archive"),
        lazy_import="frontend.RenpyToolbox.PackUnpackPage:PackUnpackPage",
    ),
    ToolSpec(
        "error_repair",
        'toolbox_tool_error_repair_title',
        'toolbox_tool_error_repair_description',
        ENGINEER,
        object_name="error-repair",
        icon=ToolIcon.REPAIR,
        keywords=("修复", "报错", "rpy", "script", "repair"),
        lazy_import="frontend.RenpyToolbox.ErrorRepairPage:ErrorRepairPage",
    ),
    ToolSpec(
        "translation_reuse",
        'toolbox_tool_translation_reuse_title',
        'toolbox_tool_translation_reuse_description',
        ENGINEER,
        object_name="translation-reuse",
        icon=ToolIcon.REUSE,
        requires_project=True,
        keywords=("更新", "复用", "旧译文", "哈希", "reuse", "migrate"),
        lazy_import="frontend.RenpyToolbox.TranslationReusePage:TranslationReusePage",
    ),
    ToolSpec(
        "formatter",
        'toolbox_tool_formatter_title',
        'toolbox_tool_formatter_description',
        ENGINEER,
        object_name="formatter",
        icon=ToolIcon.FORMAT,
        keywords=("格式化", "rpy", "代码", "format", "lint"),
        lazy_import="frontend.RenpyToolbox.FormatterPage:FormatterPage",
    ),
    ToolSpec(
        "android_build",
        'toolbox_tool_android_build_title',
        'toolbox_tool_android_build_description',
        ENGINEER,
        object_name="android-build",
        icon=ToolIcon.ANDROID,
        requires_project=True,
        keywords=("apk", "sdk", "签名", "rapt", "android", "gradle"),
        lazy_import="frontend.RenpyToolbox.AndroidBuildPage:AndroidBuildPage",
    ),
    ToolSpec(
        "html_import",
        'toolbox_tool_html_import_title',
        'toolbox_tool_html_import_description',
        ENGINEER,
        object_name="html-import",
        icon=ToolIcon.HTML,
        keywords=("html", "txt", "excel", "导入", "导出", "convert"),
        lazy_import="frontend.RenpyToolbox.HtmlImportPage:HtmlImportPage",
    ),
    ToolSpec(
        "game_mod",
        'toolbox_tool_game_mod_title',
        'toolbox_tool_game_mod_description',
        ENGINEER,
        object_name="game-mod",
        icon=ToolIcon.MOD,
        keywords=("模组", "mod", "修改器", "urm", "画廊", "注入"),
        lazy_import="frontend.RenpyToolbox.GameModPage:GameModPage",
    ),
)
