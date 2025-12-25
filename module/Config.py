import dataclasses
import json
import os
import threading
from typing import Any
from typing import ClassVar
from base.compat import Self

from base.BaseLanguage import BaseLanguage
from base.LogManager import LogManager
from base.PathHelper import get_resource_path
from module.Localizer.Localizer import Localizer

@dataclasses.dataclass
class Config():

    # 主题枚举
    THEME_DARK = "DARK"
    THEME_LIGHT = "LIGHT"

    # Application
    theme: str = THEME_LIGHT
    app_language: BaseLanguage.Enum = BaseLanguage.Enum.ZH
    startup_sound_enable: bool = True
    startup_sound_path: str = "resource/Ciallo.mp3"
    startup_sound_volume: int = 80

    # PlatformPage
    activate_platform: int = 0
    platforms: list[dict[str, Any]] = None

    # AppSettingsPage
    expert_mode: bool = False
    proxy_url: str = ""
    proxy_enable: bool = False
    font_hinting: bool = True
    scale_factor: str = ""

    # BasicSettingsPage
    token_threshold: int = 10
    max_workers: int = 0
    rpm_threshold: int = 0
    request_timeout: int = 120
    max_round: int = 16

    # ExpertSettingsPage
    preceding_lines_threshold: int = 0
    enable_preceding_on_local: bool = False
    clean_ruby: bool = True
    deduplication_in_trans: bool = True
    deduplication_in_bilingual: bool = True
    write_translated_name_fields_to_file: bool = True
    result_checker_retry_count_threshold: bool = False

    # ProjectPage
    # 默认原文语言改为英文，避免误将非日文项目设为日文
    source_language: BaseLanguage.Enum = BaseLanguage.Enum.EN
    target_language: BaseLanguage.Enum = BaseLanguage.Enum.ZH
    input_folder: str = "./input"
    output_folder: str = "./output"
    output_folder_open_on_finish: bool = False
    traditional_chinese_enable: bool = False

    # GlossaryPage
    glossary_enable: bool = True
    glossary_data: list[Any] = dataclasses.field(default_factory = list)
    glossary_auto_scan_cache: dict[str, float] = dataclasses.field(default_factory = dict)

    # TextPreservePage
    text_preserve_enable: bool = False
    text_preserve_data: list[Any] = dataclasses.field(default_factory = list)

    # PreTranslationReplacementPage
    pre_translation_replacement_enable: bool = True
    pre_translation_replacement_data: list[Any] = dataclasses.field(default_factory = list)

    # PostTranslationReplacementPage
    post_translation_replacement_enable: bool = True
    post_translation_replacement_data: list[Any] = dataclasses.field(default_factory = list)

    # Mixed language cleanup helpers
    mixed_language_cleanup_enable: bool = False
    mixed_language_replacements: dict[str, str] = dataclasses.field(default_factory = dict)
    mixed_language_sentence_overrides: dict[str, str] = dataclasses.field(default_factory = dict)

    # CustomPromptZHPage
    custom_prompt_zh_enable: bool = False
    custom_prompt_zh_data: str = None

    # CustomPromptENPage
    custom_prompt_en_enable: bool = False
    custom_prompt_en_data: str = None

    # LaboratoryPage
    auto_glossary_enable: bool = False
    mtool_optimizer_enable: bool = False

    # RenpyProjectPage
    renpy_project_path: str = ""
    renpy_game_folder: str = ""
    renpy_tl_folder: str = ""
    extract_use_official: bool = True
    extract_use_custom: bool = True
    extract_skip_hook_files: bool = True
    extract_export_excel: bool = False
    extract_split_names: bool = True
    renpy_extract_dialogs: bool = True
    renpy_extract_strings: bool = True
    renpy_extract_screens: bool = True
    renpy_backup_original: bool = True
    renpy_auto_detect_encoding: bool = True
    renpy_default_encoding: str = "utf-8"
    # 删除与 translate 块重复的 strings 项，避免双份：保留块翻译，移除 old/new
    renpy_remove_string_duplicates: bool = True
    # 增量抽取时，把 old/new 中未翻译（new==old 或 new==""）的条目也纳入“待翻译新增包”。
    # 解决：tl 目录存在但某些文件没翻译过/只抽到占位时，增量抽取输出过少的问题。
    renpy_incremental_include_untranslated: bool = True

    # RenpyToolkitPage
    renpy_font_replace_enable: bool = False
    renpy_font_original: str = ""
    renpy_font_target: str = ""
    renpy_format_indent: int = 4
    renpy_format_line_width: int = 80
    renpy_format_preserve_comments: bool = True
    renpy_error_check_syntax: bool = True
    renpy_error_check_indent: bool = True
    renpy_error_check_quotes: bool = True

    # 类属性
    # 用户配置（运行时生成，避免写回 resource 打包资源）
    CONFIG_PATH: ClassVar[str] = "./config.json"
    CONFIG_LOCK: ClassVar[threading.Lock] = threading.Lock()

    def load(self, path: str = None) -> Self:
        if path is None:
            user_path = __class__.CONFIG_PATH
            path = user_path if os.path.isfile(user_path) else get_resource_path("resource", "config.json")

        with __class__.CONFIG_LOCK:
            try:
                if os.path.isfile(path):
                    with open(path, "r", encoding = "utf-8-sig") as reader:
                        config: dict = json.load(reader)
                        for k, v in config.items():
                            if hasattr(self, k):
                                setattr(self, k, v)
            except Exception as e:
                LogManager.get().error(f"{Localizer.get().log_read_file_fail}", e)

        return self

    def save(self, path: str = None) -> Self:
        if path is None:
            path = __class__.CONFIG_PATH

        with __class__.CONFIG_LOCK:
            try:
                os.makedirs(os.path.dirname(path), exist_ok = True)
                with open(path, "w", encoding = "utf-8") as writer:
                    json.dump(dataclasses.asdict(self), writer, indent = 4, ensure_ascii = False)
            except Exception as e:
                LogManager.get().error(f"{Localizer.get().log_write_file_fail}", e)

        return self

    # 重置专家模式
    def reset_expert_settings(self) -> None:
        # ExpertSettingsPage
        self.preceding_lines_threshold: int = 0
        self.enable_preceding_on_local: bool = False
        self.clean_ruby: bool = True
        self.deduplication_in_trans: bool = True
        self.deduplication_in_bilingual: bool = True
        self.write_translated_name_fields_to_file: bool = True
        self.result_checker_retry_count_threshold: bool = False

        # TextPreservePage
        self.text_preserve_enable: bool = False
        self.text_preserve_data: list[Any] = []

    # 获取平台配置
    def get_platform(self, id: int) -> dict[str, Any]:
        item: dict[str, str | bool | int | float | list[str]] = None
        for item in self.platforms:
            if item.get("id", 0) == id:
                return item

    # 更新平台配置
    def set_platform(self, platform: dict[str, Any]) -> None:
        for i, item in enumerate(self.platforms):
            if item.get("id", 0) == platform.get("id", 0):
                self.platforms[i] = platform
                break
