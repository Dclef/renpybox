import copy
import dataclasses
import json
import os
import threading
from typing import Any
from typing import ClassVar
from typing import Optional
from base.compat import Self

from base.BaseLanguage import BaseLanguage
from base.LogManager import LogManager
from base.PathHelper import get_app_path, get_resource_path
from module.Localizer.Localizer import Localizer

@dataclasses.dataclass
class Config():

    CURRENT_CONFIG_VERSION: ClassVar[int] = 1
    PROJECT_SCOPED_WORKBENCH_DEFAULTS: ClassVar[dict[str, Any]] = {
        "renpy_workbench_worldbook_enable": False,
        "renpy_workbench_worldbook_data": {},
        "renpy_workbench_character_cards_enable": False,
        "renpy_workbench_character_cards": [],
        "renpy_workbench_generated_worldbook_draft": {},
        "renpy_workbench_generated_character_drafts": [],
    }

    PROMPT_MODE_COMMON: ClassVar[str] = "COMMON"
    PROMPT_MODE_COT: ClassVar[str] = "COT"
    PROMPT_MODE_THINK: ClassVar[str] = "THINK"
    PROMPT_MODE_LOCAL: ClassVar[str] = "LOCAL"
    PROMPT_MODE_CUSTOM: ClassVar[str] = "CUSTOM"

    STYLE_NONE: ClassVar[str] = "NONE"
    STYLE_LITERARY: ClassVar[str] = "LITERARY"
    STYLE_CLASSICAL: ClassVar[str] = "CLASSICAL"
    STYLE_R18: ClassVar[str] = "R18"
    STYLE_CUSTOM: ClassVar[str] = "CUSTOM"

    OUTPUT_PROTOCOL_STRUCTURED: ClassVar[str] = "STRUCTURED"
    OUTPUT_PROTOCOL_JSONLINE: ClassVar[str] = "JSONLINE"
    OUTPUT_PROTOCOL_SINGLE_TEXT: ClassVar[str] = "SINGLE_TEXT"

    PROMPT_MODES: ClassVar[frozenset[str]] = frozenset({
        PROMPT_MODE_COMMON,
        PROMPT_MODE_COT,
        PROMPT_MODE_THINK,
        PROMPT_MODE_LOCAL,
        PROMPT_MODE_CUSTOM,
    })
    STYLE_IDS: ClassVar[frozenset[str]] = frozenset({
        STYLE_NONE,
        STYLE_LITERARY,
        STYLE_CLASSICAL,
        STYLE_R18,
        STYLE_CUSTOM,
    })
    OUTPUT_PROTOCOLS: ClassVar[frozenset[str]] = frozenset({
        OUTPUT_PROTOCOL_STRUCTURED,
        OUTPUT_PROTOCOL_JSONLINE,
        OUTPUT_PROTOCOL_SINGLE_TEXT,
    })

    DEFAULT_ASSET_PROMPT_TOKEN_BUDGET: ClassVar[int] = 2048
    DEFAULT_ASSET_PROMPT_MAX_ITEMS: ClassVar[int] = 64

    # 主题枚举
    THEME_DARK = "DARK"
    THEME_LIGHT = "LIGHT"

    # Config schema
    config_version: int = CURRENT_CONFIG_VERSION

    # Application
    theme: str = THEME_LIGHT
    app_language: BaseLanguage.Enum = BaseLanguage.Enum.ZH
    startup_sound_enable: bool = False
    startup_sound_path: str = "resource/Ciallo.mp3"
    startup_sound_volume: int = 80
    cache_use_sqlite: bool = True
    last_seen_version: str = ""

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
    single_line_translation_enable: bool = False
    clean_ruby: bool = True
    deduplication_in_trans: bool = True
    deduplication_in_bilingual: bool = True
    write_translated_name_fields_to_file: bool = True
    result_checker_retry_count_threshold: bool = False
    auto_process_prefix_suffix_preserved_text: bool = False
    sakura_jsonline_retry_enable: bool = True
    token_estimation_output_ratio: float = 1.2
    honorific_placeholder_bridge_enable: bool = True
    honorific_placeholder_titles: list[str] = dataclasses.field(default_factory = lambda: [
        "mr",
        "mrs",
        "ms",
        "miss",
        "dr",
        "doctor",
        "prof",
        "professor",
        "sir",
        "madam",
        "lady",
        "master",
    ])
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

    # Translation pipeline
    translation_prompt_mode: str = PROMPT_MODE_COMMON
    translation_custom_prompts: dict[str, str] = dataclasses.field(default_factory = dict)
    # None means the current CUSTOM mode applies to every prompt language. A list
    # is only needed to preserve the independent legacy ZH/EN enable switches.
    translation_custom_prompt_enabled_languages: Optional[list[str]] = None
    translation_style_id: str = STYLE_NONE
    translation_custom_style: str = ""
    translation_output_protocol: str = OUTPUT_PROTOCOL_STRUCTURED
    asset_regex_enable: bool = False
    asset_prompt_token_budget: int = DEFAULT_ASSET_PROMPT_TOKEN_BUDGET
    asset_prompt_max_items: int = DEFAULT_ASSET_PROMPT_MAX_ITEMS

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
    # 源码翻译：引擎读取 .rpy 源码
    renpy_source_translate: bool = False
    renpy_hook_translate: bool = False  # replace_text 补全模式
    renpy_auto_detect_encoding: bool = True
    renpy_default_encoding: str = "utf-8"
    # 删除与 translate 块重复的 strings 项，避免双份：保留块翻译，移除 old/new
    renpy_remove_string_duplicates: bool = True
    # strings 内重复 old 的处置方式：comment 保留审计记录，delete 兼容旧行为
    renpy_duplicate_string_action: str = "comment"
    # 过滤疑似被误提取的布尔表达式（例如 "foo == True"、"bar = false"），并备份到 tl/<lang>/_filtered_suspicious
    renpy_filter_suspicious_bool_expr: bool = True
    # 增量抽取时，把 old/new 中未翻译（new==old 或 new==""）的条目也纳入“待翻译新增包”。
    # 解决：tl 目录存在但某些文件没翻译过/只抽到占位时，增量抽取输出过少的问题。
    renpy_incremental_include_untranslated: bool = True
    # 增量抽取后自动合并并清理重复（把 tl/<lang>_new 合并回 tl/<lang>）
    renpy_incremental_auto_merge_cleanup: bool = True

    # 一键翻译选项
    onekey_inject_base_box: bool = False
    # 一键翻译完成后，是否自动执行 replace_text 补全漏翻
    onekey_auto_hook_supplement: bool = False

    # 角色 / 世界观工作台
    renpy_workbench_worldbook_enable: bool = False
    renpy_workbench_worldbook_data: dict[str, Any] = dataclasses.field(default_factory = dict)
    renpy_workbench_character_cards_enable: bool = False
    renpy_workbench_character_cards: list[dict[str, Any]] = dataclasses.field(default_factory = list)
    renpy_workbench_last_analysis_scope: str = "current"
    renpy_workbench_generated_worldbook_draft: dict[str, Any] = dataclasses.field(default_factory = dict)
    renpy_workbench_generated_character_drafts: list[dict[str, Any]] = dataclasses.field(default_factory = list)

    # AndroidBuildPage
    renpy_sdk_path: str = ""
    android_app_name: str = ""
    android_package_name: str = ""
    android_version: str = ""
    android_archive_source_dir: str = ""
    android_shell_backup_enable: bool = True
    android_shell_remove_dirs: str = "images,image,audio,video,videos,movies,script"
    android_dname: str = ""
    android_update_always: bool = True
    android_update_icons: bool = True

    # RenpyToolboxPage
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
    # 用户配置固定到应用目录，避免从快捷方式、终端或其他工作目录启动时
    # 读写到不同的 ``./config.json``。
    CONFIG_PATH: ClassVar[str] = get_app_path("config.json")
    CONFIG_LOCK: ClassVar[threading.Lock] = threading.Lock()

    @classmethod
    def migrate_dict(cls, raw: dict[str, Any] | None) -> dict[str, Any]:
        config = copy.deepcopy(raw) if isinstance(raw, dict) else {}
        version_value = config.get("config_version", 0)
        version = (
            version_value
            if isinstance(version_value, int)
            and not isinstance(version_value, bool)
            and version_value >= 0
            else 0
        )

        while version < cls.CURRENT_CONFIG_VERSION:
            if version == 0:
                cls._migrate_v0_to_v1(config)
            else:
                raise ValueError(f"Unsupported config migration version: {version}")

            version += 1
            config["config_version"] = version

        cls._apply_current_defaults(config)
        return config

    @classmethod
    def _migrate_v0_to_v1(cls, config: dict[str, Any]) -> None:
        prompts_value = config.get("translation_custom_prompts")
        prompts = dict(prompts_value) if isinstance(prompts_value, dict) else {}

        legacy_prompts = (
            (BaseLanguage.Enum.ZH.value, "custom_prompt_zh_data"),
            (BaseLanguage.Enum.EN.value, "custom_prompt_en_data"),
        )
        for language, legacy_key in legacy_prompts:
            legacy_value = config.get(legacy_key)
            if language not in prompts and isinstance(legacy_value, str):
                prompts[language] = legacy_value

        config["translation_custom_prompts"] = prompts
        enabled_languages = []
        if config.get("custom_prompt_zh_enable") is True:
            enabled_languages.append(BaseLanguage.Enum.ZH.value)
        if config.get("custom_prompt_en_enable") is True:
            enabled_languages.append(BaseLanguage.Enum.EN.value)
        if enabled_languages:
            config.setdefault(
                "translation_custom_prompt_enabled_languages",
                enabled_languages,
            )
        config.setdefault(
            "translation_prompt_mode",
            cls.PROMPT_MODE_CUSTOM
            if enabled_languages
            else cls.PROMPT_MODE_COMMON,
        )
        config.setdefault(
            "translation_output_protocol",
            cls.OUTPUT_PROTOCOL_STRUCTURED
            if config.get("structured_output_enable", True) is True
            else cls.OUTPUT_PROTOCOL_JSONLINE,
        )

    @classmethod
    def _apply_current_defaults(cls, config: dict[str, Any]) -> None:
        config.setdefault("config_version", cls.CURRENT_CONFIG_VERSION)
        config.setdefault("translation_prompt_mode", cls.PROMPT_MODE_COMMON)
        config.setdefault("translation_custom_prompts", {})
        config.setdefault("translation_custom_prompt_enabled_languages", None)
        config.setdefault("translation_style_id", cls.STYLE_NONE)
        config.setdefault("translation_custom_style", "")
        config.setdefault("translation_output_protocol", cls.OUTPUT_PROTOCOL_STRUCTURED)
        config.setdefault("asset_regex_enable", False)
        config.setdefault("last_seen_version", "")

        if not isinstance(config.get("last_seen_version"), str):
            config["last_seen_version"] = ""

        config["translation_prompt_mode"] = cls._normalize_choice(
            config.get("translation_prompt_mode"),
            cls.PROMPT_MODES,
            cls.PROMPT_MODE_COMMON,
        )
        config["translation_style_id"] = cls._normalize_choice(
            config.get("translation_style_id"),
            cls.STYLE_IDS,
            cls.STYLE_NONE,
        )
        config["translation_output_protocol"] = cls._normalize_choice(
            config.get("translation_output_protocol"),
            cls.OUTPUT_PROTOCOLS,
            cls.OUTPUT_PROTOCOL_STRUCTURED,
        )

        prompts = config.get("translation_custom_prompts")
        if not isinstance(prompts, dict):
            config["translation_custom_prompts"] = {}

        scope = config.get("translation_custom_prompt_enabled_languages")
        if scope is not None:
            if not isinstance(scope, (list, tuple, set, frozenset)):
                scope = []
            allowed_languages = (
                BaseLanguage.Enum.ZH.value,
                BaseLanguage.Enum.EN.value,
            )
            config["translation_custom_prompt_enabled_languages"] = [
                language
                for language in allowed_languages
                if language in {
                    str(value).strip().upper()
                    for value in scope
                }
            ]

        token_budget = config.get("asset_prompt_token_budget")
        if (
            not isinstance(token_budget, int)
            or isinstance(token_budget, bool)
            or token_budget <= 0
        ):
            config["asset_prompt_token_budget"] = cls.DEFAULT_ASSET_PROMPT_TOKEN_BUDGET

        max_items = config.get("asset_prompt_max_items")
        if not isinstance(max_items, int) or isinstance(max_items, bool) or max_items <= 0:
            config["asset_prompt_max_items"] = cls.DEFAULT_ASSET_PROMPT_MAX_ITEMS

    @staticmethod
    def _normalize_choice(value: Any, allowed: frozenset[str], default: str) -> str:
        normalized = str(value).strip().upper() if isinstance(value, str) else ""
        return normalized if normalized in allowed else default

    def is_custom_prompt_enabled_for(self, language: BaseLanguage.Enum | str) -> bool:
        if self.translation_prompt_mode != self.PROMPT_MODE_CUSTOM:
            return False
        scope = self.translation_custom_prompt_enabled_languages
        if scope is None:
            return True
        language_value = language.value if isinstance(language, BaseLanguage.Enum) else str(language)
        return language_value.strip().upper() in {
            str(value).strip().upper()
            for value in scope
        }

    @property
    def custom_prompt_zh_enable(self) -> bool:
        return self.is_custom_prompt_enabled_for(BaseLanguage.Enum.ZH)

    @custom_prompt_zh_enable.setter
    def custom_prompt_zh_enable(self, value: bool) -> None:
        self._set_legacy_custom_prompt_enabled(BaseLanguage.Enum.ZH, value)

    @property
    def custom_prompt_en_enable(self) -> bool:
        return self.is_custom_prompt_enabled_for(BaseLanguage.Enum.EN)

    @custom_prompt_en_enable.setter
    def custom_prompt_en_enable(self, value: bool) -> None:
        self._set_legacy_custom_prompt_enabled(BaseLanguage.Enum.EN, value)

    def _set_legacy_custom_prompt_enabled(
        self,
        language: BaseLanguage.Enum,
        value: bool,
    ) -> None:
        supported = {
            BaseLanguage.Enum.ZH.value,
            BaseLanguage.Enum.EN.value,
        }
        if self.translation_custom_prompt_enabled_languages is None:
            enabled = supported if self.translation_prompt_mode == self.PROMPT_MODE_CUSTOM else set()
        else:
            enabled = {
                str(item).strip().upper()
                for item in self.translation_custom_prompt_enabled_languages
                if str(item).strip().upper() in supported
            }

        if value:
            enabled.add(language.value)
        else:
            enabled.discard(language.value)

        self.translation_custom_prompt_enabled_languages = sorted(enabled)
        self.translation_prompt_mode = (
            self.PROMPT_MODE_CUSTOM if enabled else self.PROMPT_MODE_COMMON
        )

    def _get_legacy_custom_prompt(self, language: BaseLanguage.Enum) -> Optional[str]:
        if not isinstance(self.translation_custom_prompts, dict):
            return None
        return self.translation_custom_prompts.get(language.value)

    def _set_legacy_custom_prompt(
        self,
        language: BaseLanguage.Enum,
        value: Optional[str],
    ) -> None:
        prompts = (
            dict(self.translation_custom_prompts)
            if isinstance(self.translation_custom_prompts, dict)
            else {}
        )
        if value is None:
            prompts.pop(language.value, None)
        else:
            prompts[language.value] = value
        self.translation_custom_prompts = prompts

    @property
    def custom_prompt_zh_data(self) -> Optional[str]:
        return self._get_legacy_custom_prompt(BaseLanguage.Enum.ZH)

    @custom_prompt_zh_data.setter
    def custom_prompt_zh_data(self, value: Optional[str]) -> None:
        self._set_legacy_custom_prompt(BaseLanguage.Enum.ZH, value)

    @property
    def custom_prompt_en_data(self) -> Optional[str]:
        return self._get_legacy_custom_prompt(BaseLanguage.Enum.EN)

    @custom_prompt_en_data.setter
    def custom_prompt_en_data(self, value: Optional[str]) -> None:
        self._set_legacy_custom_prompt(BaseLanguage.Enum.EN, value)

    @property
    def structured_output_enable(self) -> bool:
        return self.translation_output_protocol == self.OUTPUT_PROTOCOL_STRUCTURED

    @structured_output_enable.setter
    def structured_output_enable(self, value: bool) -> None:
        self.translation_output_protocol = (
            self.OUTPUT_PROTOCOL_STRUCTURED
            if value
            else self.OUTPUT_PROTOCOL_JSONLINE
        )

    def load(self, path: str = None) -> Self:
        if path is None:
            user_path = __class__.CONFIG_PATH
            path = user_path if os.path.isfile(user_path) else get_resource_path("resource", "config.json")

        with __class__.CONFIG_LOCK:
            try:
                if os.path.isfile(path):
                    with open(path, "r", encoding = "utf-8-sig") as reader:
                        config = __class__.migrate_dict(json.load(reader))
                        field_names = {field.name for field in dataclasses.fields(self)}
                        for k, v in config.items():
                            if k in field_names:
                                setattr(self, k, v)
            except Exception as e:
                LogManager.get().error(f"{Localizer.get().log_read_file_fail}", e)

        return self

    def save(self, path: str = None) -> Self:
        if path is None:
            path = __class__.CONFIG_PATH

        with __class__.CONFIG_LOCK:
            try:
                parent = os.path.dirname(os.path.abspath(path))
                os.makedirs(parent, exist_ok = True)
                payload = dataclasses.asdict(self)
                # 工作台资产由项目缓存持久化，不能写回全局配置后污染下一个项目。
                for key, value in __class__.PROJECT_SCOPED_WORKBENCH_DEFAULTS.items():
                    payload[key] = copy.deepcopy(value)
                with open(path, "w", encoding = "utf-8") as writer:
                    json.dump(payload, writer, indent = 4, ensure_ascii = False)
            except Exception as e:
                LogManager.get().error(f"{Localizer.get().log_write_file_fail}", e)

        return self

    # 重置专家模式
    def reset_expert_settings(self) -> None:
        # ExpertSettingsPage
        self.preceding_lines_threshold: int = 0
        self.enable_preceding_on_local: bool = False
        self.single_line_translation_enable: bool = False
        self.clean_ruby: bool = True
        self.deduplication_in_trans: bool = True
        self.deduplication_in_bilingual: bool = True
        self.write_translated_name_fields_to_file: bool = True
        self.result_checker_retry_count_threshold: bool = False
        self.auto_process_prefix_suffix_preserved_text: bool = False
        self.sakura_jsonline_retry_enable: bool = True
        self.honorific_placeholder_bridge_enable: bool = True
        self.honorific_placeholder_titles: list[str] = [
            "mr",
            "mrs",
            "ms",
            "miss",
            "dr",
            "doctor",
            "prof",
            "professor",
            "sir",
            "madam",
            "lady",
            "master",
        ]
        # TextPreservePage
        self.text_preserve_enable: bool = False
        self.text_preserve_data: list[Any] = []

    # 获取平台配置
    def get_platform(self, id: int) -> Optional[dict[str, Any]]:
        if isinstance(self.platforms, list) is False:
            return None

        item: dict[str, str | bool | int | float | list[str]] = None
        for item in self.platforms:
            if item.get("id", 0) == id:
                return item
        return None

    # 更新平台配置
    def set_platform(self, platform: dict[str, Any]) -> None:
        if isinstance(self.platforms, list) is False:
            self.platforms = []
        for i, item in enumerate(self.platforms):
            if item.get("id", 0) == platform.get("id", 0):
                self.platforms[i] = platform
                break
