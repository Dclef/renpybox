from __future__ import annotations

import dataclasses
import json
import threading
import re
from functools import lru_cache

from base.Base import Base
from base.BaseLanguage import BaseLanguage
from base.PathHelper import get_resource_path
from module.Cache.CacheItem import CacheItem
from module.Config import Config
from module.Engine.Translator.TranslationTaskContext import TranslationTaskContext
from module.Workbench.WorkbenchData import normalize_character_cards, normalize_text, normalize_text_list, normalize_worldbook


@dataclasses.dataclass(frozen = True)
class DynamicAssetEntry:
    kind: str
    source: str
    record_id: str
    priority: int
    content: str


@dataclasses.dataclass(frozen = True)
class TranslationPromptConfigView:
    """Read-only PromptBuilder adapter backed by a task snapshot."""

    context: TranslationTaskContext

    @staticmethod
    def _language(value: object, fallback: BaseLanguage.Enum) -> BaseLanguage.Enum:
        if isinstance(value, BaseLanguage.Enum):
            return value
        try:
            return BaseLanguage.Enum(str(value).strip().upper())
        except ValueError:
            return fallback

    @property
    def source_language(self) -> BaseLanguage.Enum:
        return self._language(self.context.source_language, BaseLanguage.Enum.EN)

    @property
    def target_language(self) -> BaseLanguage.Enum:
        return self._language(self.context.target_language, BaseLanguage.Enum.ZH)

    @property
    def translation_prompt_mode(self) -> str:
        return str(self.context.prompt.get("mode", Config.PROMPT_MODE_COMMON))

    @property
    def translation_resolved_base(self) -> str:
        return str(self.context.prompt.get("resolved_base", "") or "")

    @property
    def translation_custom_prompts(self) -> dict[str, str]:
        value = self.translation_resolved_base
        return {self.target_language.value: value} if value != "" else {}

    @property
    def translation_style_id(self) -> str:
        return str(self.context.prompt.get("style_id", Config.STYLE_NONE))

    @property
    def translation_resolved_style(self) -> str:
        return str(self.context.prompt.get("resolved_style", "") or "")

    @property
    def translation_custom_style(self) -> str:
        return self.translation_resolved_style

    @property
    def translation_output_protocol(self) -> str:
        return str(self.context.prompt.get("protocol", Config.OUTPUT_PROTOCOL_STRUCTURED))

    @property
    def structured_output_enable(self) -> bool:
        return self.translation_output_protocol.upper() == Config.OUTPUT_PROTOCOL_STRUCTURED

    @property
    def asset_regex_enable(self) -> bool:
        return bool(self.context.processing.get("asset_regex_enable", False))

    @property
    def asset_prompt_token_budget(self) -> int:
        return int(self.context.processing.get("asset_prompt_token_budget", 2048))

    @property
    def asset_prompt_max_items(self) -> int:
        return int(self.context.processing.get("asset_prompt_max_items", 64))

    @property
    def enable_preceding_on_local(self) -> bool:
        return bool(self.context.processing.get("enable_preceding_on_local", False))

    @property
    def glossary_enable(self) -> bool:
        return self.context.assets.glossary_enabled

    @property
    def glossary_data(self) -> tuple[dict[str, object], ...]:
        return tuple({
            "src": item.source,
            "dst": item.target,
            "info": item.note,
            "record_id": item.record_id,
            "origin": item.origin,
            "enabled": item.enabled,
            "regex": item.regex,
        } for item in self.context.assets.glossary)

    @property
    def renpy_workbench_worldbook_enable(self) -> bool:
        return self.context.assets.worldbook_enabled

    @property
    def renpy_workbench_worldbook_data(self) -> dict[str, object]:
        return self.context.assets.worldbook.to_dict()

    @property
    def renpy_workbench_character_cards_enable(self) -> bool:
        return self.context.assets.character_cards_enabled

    @property
    def renpy_workbench_character_cards(self) -> list[dict[str, object]]:
        return [card.to_dict() for card in self.context.assets.character_cards]

    @property
    def do_not_translate_enable(self) -> bool:
        return self.context.assets.do_not_translate_enabled

    @property
    def do_not_translate_data(self) -> tuple[dict[str, object], ...]:
        return tuple({
            "src": item.source,
            "info": item.note,
            "record_id": item.record_id,
            "origin": item.origin,
            "enabled": item.enabled,
            "regex": item.regex,
        } for item in self.context.assets.do_not_translate)

class PromptBuilder(Base):

    # 类线程锁
    LOCK: threading.Lock = threading.Lock()
    RE_GLOSSARY_IGNORE_SEGMENTS = re.compile(r"\[[^\]]*]|\{[^}]*}")
    RE_LATIN_ONLY = re.compile(r"^[A-Za-z\s'\-]+$")
    RE_STRUCTURED_PLACEHOLDER = re.compile(r"<\s*n\s*(\d+)\s*/?\s*>", flags = re.IGNORECASE)
    MODE_FILES: dict[str, str] = {
        Config.PROMPT_MODE_COMMON: "base.txt",
        Config.PROMPT_MODE_COT: "cot.txt",
        Config.PROMPT_MODE_THINK: "think.txt",
        Config.PROMPT_MODE_LOCAL: "local.txt",
    }
    STYLE_FILES: dict[str, str] = {
        Config.STYLE_LITERARY: "style_literary.txt",
        Config.STYLE_CLASSICAL: "style_classical.txt",
        Config.STYLE_R18: "style_r18.txt",
    }
    PROTOCOL_FILES: dict[str, str] = {
        Config.OUTPUT_PROTOCOL_STRUCTURED: "output_structured.txt",
        Config.OUTPUT_PROTOCOL_JSONLINE: "output_jsonline.txt",
        Config.OUTPUT_PROTOCOL_SINGLE_TEXT: "output_single_text.txt",
    }

    def __init__(self, config: Config | TranslationTaskContext) -> None:
        super().__init__()

        self.task_context = config if isinstance(config, TranslationTaskContext) else None
        self.config: Config | TranslationPromptConfigView = (
            TranslationPromptConfigView(config)
            if isinstance(config, TranslationTaskContext)
            else config
        )

    @classmethod
    def reset(cls) -> None:
        cls.get_base.cache_clear()
        cls.get_mode_base.cache_clear()
        cls.get_engineering.cache_clear()
        cls.get_output_protocol.cache_clear()
        cls.get_style.cache_clear()
        cls.get_prefix.cache_clear()
        cls.get_suffix.cache_clear()
        cls.get_suffix_glossary.cache_clear()

    @classmethod
    def _read_prompt_resource(cls, language: BaseLanguage.Enum, filename: str) -> str:
        with open(
            get_resource_path("resource", "prompt", language.lower(), filename),
            "r",
            encoding = "utf-8-sig",
        ) as reader:
            return reader.read().strip()

    @classmethod
    @lru_cache(maxsize = None)
    def get_base(cls, language: BaseLanguage.Enum) -> str:
        """Return the COMMON base prompt for legacy callers."""
        return cls._read_prompt_resource(language, "base.txt")

    @classmethod
    @lru_cache(maxsize = None)
    def get_mode_base(cls, language: BaseLanguage.Enum, mode: str) -> str:
        if mode == Config.PROMPT_MODE_COMMON:
            return cls.get_base(language)
        filename = cls.MODE_FILES.get(mode, cls.MODE_FILES[Config.PROMPT_MODE_COMMON])
        return cls._read_prompt_resource(language, filename)

    @classmethod
    @lru_cache(maxsize = None)
    def get_engineering(cls, language: BaseLanguage.Enum) -> str:
        return cls._read_prompt_resource(language, "engineering.txt")

    @classmethod
    @lru_cache(maxsize = None)
    def get_output_protocol(cls, language: BaseLanguage.Enum, protocol: str) -> str:
        filename = cls.PROTOCOL_FILES.get(protocol, cls.PROTOCOL_FILES[Config.OUTPUT_PROTOCOL_STRUCTURED])
        return cls._read_prompt_resource(language, filename)

    @classmethod
    @lru_cache(maxsize = None)
    def get_style(cls, language: BaseLanguage.Enum, style_id: str) -> str:
        filename = cls.STYLE_FILES.get(style_id)
        if filename is None:
            return ""
        return cls._read_prompt_resource(language, filename)

    @classmethod
    @lru_cache(maxsize = None)
    def get_prefix(cls, language: BaseLanguage.Enum) -> str:
        return cls._read_prompt_resource(language, "prefix.txt")

    @classmethod
    @lru_cache(maxsize = None)
    def get_suffix(cls, language: BaseLanguage.Enum) -> str:
        return cls._read_prompt_resource(language, "suffix.txt")

    @classmethod
    @lru_cache(maxsize = None)
    def get_suffix_glossary(cls, language: BaseLanguage.Enum) -> str:
        return cls._read_prompt_resource(language, "suffix_glossary.txt")

    @staticmethod
    def _join_sections(*sections: str) -> str:
        return "\n\n".join(
            section.strip()
            for section in sections
            if isinstance(section, str) and section.strip() != ""
        )

    def _normalize_prompt_mode(self) -> str:
        mode = str(getattr(self.config, "translation_prompt_mode", Config.PROMPT_MODE_COMMON)).upper()
        valid = set(__class__.MODE_FILES) | {Config.PROMPT_MODE_CUSTOM}
        return mode if mode in valid else Config.PROMPT_MODE_COMMON

    def _normalize_style_id(self) -> str:
        style_id = str(getattr(self.config, "translation_style_id", Config.STYLE_NONE)).upper()
        valid = set(__class__.STYLE_FILES) | {Config.STYLE_NONE, Config.STYLE_CUSTOM}
        return style_id if style_id in valid else Config.STYLE_NONE

    def _normalize_output_protocol(self) -> str:
        protocol = str(
            getattr(
                self.config,
                "translation_output_protocol",
                Config.OUTPUT_PROTOCOL_STRUCTURED,
            )
        ).upper()
        return protocol if protocol in __class__.PROTOCOL_FILES else Config.OUTPUT_PROTOCOL_STRUCTURED

    def resolve_base_prompt(self, prompt_language: BaseLanguage.Enum) -> str:
        """Resolve one mutually exclusive base mode."""
        mode = self._normalize_prompt_mode()
        resolved = getattr(self.config, "translation_resolved_base", "")
        if isinstance(resolved, str) and resolved.strip() != "":
            return resolved.strip()
        if mode != Config.PROMPT_MODE_CUSTOM:
            return __class__.get_mode_base(prompt_language, mode)

        is_enabled_for = getattr(self.config, "is_custom_prompt_enabled_for", None)
        if callable(is_enabled_for) and not is_enabled_for(prompt_language):
            return __class__.get_mode_base(prompt_language, Config.PROMPT_MODE_COMMON)

        prompts = getattr(self.config, "translation_custom_prompts", {})
        if not isinstance(prompts, dict):
            return ""

        language_keys = (
            prompt_language.value,
            prompt_language.value.lower(),
            prompt_language.name,
            prompt_language.name.lower(),
        )
        for key in language_keys:
            value = prompts.get(key)
            if isinstance(value, str):
                return value.strip()
        return ""

    def build_writing_style(self, prompt_language: BaseLanguage.Enum) -> str:
        """Resolve the independent, fully appended writing-style layer."""
        style_id = self._normalize_style_id()
        if style_id == Config.STYLE_NONE:
            return ""
        resolved = getattr(self.config, "translation_resolved_style", "")
        if isinstance(resolved, str) and resolved.strip() != "":
            return resolved.strip()
        if style_id == Config.STYLE_CUSTOM:
            value = getattr(self.config, "translation_custom_style", "")
            return value.strip() if isinstance(value, str) else ""
        return __class__.get_style(prompt_language, style_id)

    @staticmethod
    def _replace_language_placeholders(
        text: str,
        source_language: str,
        target_language: str,
    ) -> str:
        return (
            text.replace("{source_language}", source_language)
            .replace("{target_language}", target_language)
        )

    def _build_main_for_protocol(self, protocol: str) -> str:
        prompt_language, source_language, target_language = self.get_prompt_language_and_names()
        with __class__.LOCK:
            base = self.resolve_base_prompt(prompt_language)
            engineering = __class__.get_engineering(prompt_language)
            output = __class__.get_output_protocol(prompt_language, protocol)
            style = self.build_writing_style(prompt_language)

        full_prompt = __class__._join_sections(base, engineering, output, style)
        return __class__._replace_language_placeholders(
            full_prompt,
            source_language,
            target_language,
        )

    # 获取主提示词
    def build_main(self) -> str:
        return self._build_main_for_protocol(self._normalize_output_protocol())

    def build_static_prompt_sections(self) -> dict[str, str]:
        """按当前配置返回可预览的静态提示词。"""
        prompt_language, source_language, target_language = self.get_prompt_language_and_names()
        with __class__.LOCK:
            sections = {
                "base": self.resolve_base_prompt(prompt_language),
                "style": self.build_writing_style(prompt_language),
                "fixed": __class__._join_sections(
                    __class__.get_engineering(prompt_language),
                    __class__.get_output_protocol(
                        prompt_language,
                        self._normalize_output_protocol(),
                    ),
                ),
            }

        return {
            key: __class__._replace_language_placeholders(
                value,
                source_language,
                target_language,
            )
            for key, value in sections.items()
        }

    def build_task_prompt_snapshot(self) -> dict[str, object]:
        """Resolve prompt resources before persisting a task context."""
        prompt_language, source_language, target_language = self.get_prompt_language_and_names()
        resolved_base = __class__._replace_language_placeholders(
            self.resolve_base_prompt(prompt_language),
            source_language,
            target_language,
        )
        resolved_style = __class__._replace_language_placeholders(
            self.build_writing_style(prompt_language),
            source_language,
            target_language,
        )
        return {
            "mode": self._normalize_prompt_mode(),
            "resolved_base": resolved_base,
            "style_id": self._normalize_style_id(),
            "resolved_style": resolved_style,
            "protocol": self._normalize_output_protocol(),
            "protocol_version": 1,
        }

    def get_prompt_language_and_names(self) -> tuple[BaseLanguage.Enum, str, str]:
        """获取提示词语言，以及原文/译文语言名称。"""
        if self.config.target_language == BaseLanguage.Enum.ZH:
            return (
                BaseLanguage.Enum.ZH,
                BaseLanguage.get_name_zh(self.config.source_language),
                BaseLanguage.get_name_zh(self.config.target_language),
            )

        return (
            BaseLanguage.Enum.EN,
            BaseLanguage.get_name_en(self.config.source_language),
            BaseLanguage.get_name_en(self.config.target_language),
        )

    def build_worldbook_context(self) -> str:
        """构建世界观上下文。"""
        if getattr(self.config, "renpy_workbench_worldbook_enable", False) is not True:
            return ""

        raw_worldbook = getattr(self.config, "renpy_workbench_worldbook_data", {})
        raw_worldbook = raw_worldbook if isinstance(raw_worldbook, dict) else {}
        worldbook = normalize_worldbook(raw_worldbook)
        extra_worldbook: list[tuple[str, str]] = []
        for key in sorted(set(raw_worldbook) - set(worldbook), key = lambda value: str(value).casefold()):
            value = raw_worldbook.get(key)
            if isinstance(value, (dict, list, tuple)):
                text = json.dumps(value, ensure_ascii = False, sort_keys = True)
            else:
                text = normalize_text(value)
            if text not in ("", "{}", "[]"):
                extra_worldbook.append((str(key), text))

        if not any(worldbook.values()) and extra_worldbook == []:
            return ""

        if self.config.target_language == BaseLanguage.Enum.ZH:
            lines = [
                "世界观设定：",
                f"项目名：{worldbook.get('project_name', '') or '未指定'}",
                f"类型：{worldbook.get('genre', '') or '未指定'}",
                f"背景摘要：{worldbook.get('setting_summary', '') or '未指定'}",
                f"时代与环境：{worldbook.get('era_background', '') or '未指定'}",
                f"整体语气：{worldbook.get('tone_style', '') or '未指定'}",
                f"叙事规则：{worldbook.get('narrative_rules', '') or '未指定'}",
                f"格式规则：{worldbook.get('format_rules', '') or '未指定'}",
            ]
            spoiler_notes = worldbook.get("spoiler_notes", "")
            if spoiler_notes:
                lines.append(f"剧透备注（仅供译者把握身份/关系，不要外显）：{spoiler_notes}")
            reference_notes = worldbook.get("reference_notes", "")
            if reference_notes:
                lines.append(f"补充参考资料：{reference_notes}")
            lines.extend(f"扩展设定 {key}：{value}" for key, value in extra_worldbook)
            return "\n".join(lines)

        lines = [
            "Worldbook Context:",
            f"Project: {worldbook.get('project_name', '') or 'Unknown'}",
            f"Genre: {worldbook.get('genre', '') or 'Unknown'}",
            f"Setting Summary: {worldbook.get('setting_summary', '') or 'Unknown'}",
            f"Era and Environment: {worldbook.get('era_background', '') or 'Unknown'}",
            f"Tone Style: {worldbook.get('tone_style', '') or 'Unknown'}",
            f"Narrative Rules: {worldbook.get('narrative_rules', '') or 'Unknown'}",
            f"Formatting Rules: {worldbook.get('format_rules', '') or 'Unknown'}",
        ]
        spoiler_notes = worldbook.get("spoiler_notes", "")
        if spoiler_notes:
            lines.append(f"Spoiler Notes (translator-only): {spoiler_notes}")
        reference_notes = worldbook.get("reference_notes", "")
        if reference_notes:
            lines.append(f"Additional Reference Notes: {reference_notes}")
        lines.extend(f"Additional Setting {key}: {value}" for key, value in extra_worldbook)
        return "\n".join(lines)

    def _text_contains_term(self, haystack: str, term: str) -> bool:
        """判断文本中是否命中候选词。"""
        full = normalize_text(haystack)
        needle = normalize_text(term)
        if full == "" or needle == "":
            return False

        if re.fullmatch(r"[A-Za-z0-9_ .'’-]+", needle):
            pattern = rf"(?<![A-Za-z0-9_]){re.escape(needle)}(?![A-Za-z0-9_])"
            return re.search(pattern, full, flags = re.IGNORECASE) is not None
        return needle.casefold() in full.casefold()

    @staticmethod
    def _asset_token_cost(text: str) -> int:
        # A deterministic tokenizer-independent upper estimate. The budget is a
        # guardrail for dynamic context, not provider billing.
        return max(1, (len(text.encode("utf-8")) + 3) // 4)

    @staticmethod
    def _asset_priority(kind: str, origin: object = "") -> int:
        if kind == "do_not_translate":
            return 0
        normalized_origin = str(origin or "LOCAL").strip().upper()
        return {
            "LOCAL": 1,
            "CHARACTER": 2,
            "ANALYSIS": 3,
        }.get(normalized_origin, 3)

    def _matches_glossary_asset(self, item: dict, full: str, full_clean: str) -> bool:
        source = normalize_text(item.get("src", item.get("source", "")))
        if source == "" or item.get("enabled", True) is not True:
            return False
        target_full = full if any(character in source for character in "[]{}") else full_clean
        case_sensitive = item.get("case_sensitive", False) is True
        if item.get("regex", False) is True and getattr(self.config, "asset_regex_enable", False) is True:
            try:
                return re.search(source, target_full, 0 if case_sensitive else re.IGNORECASE) is not None
            except re.error:
                return False
        if bool(__class__.RE_LATIN_ONLY.fullmatch(source)) and len(source) <= 20:
            return re.search(
                r"\b" + re.escape(source) + r"\b",
                target_full,
                0 if case_sensitive else re.IGNORECASE,
            ) is not None
        if case_sensitive:
            return source in target_full
        return source.casefold() in target_full.casefold()

    def _collect_glossary_asset_entries(self, srcs: list[str]) -> list[DynamicAssetEntry]:
        if getattr(self.config, "glossary_enable", False) is not True:
            return []
        full = "\n".join(srcs)
        full_clean = __class__.RE_GLOSSARY_IGNORE_SEGMENTS.sub("", full)
        result: list[DynamicAssetEntry] = []
        for raw in getattr(self.config, "glossary_data", ()):
            if not isinstance(raw, dict) or not self._matches_glossary_asset(raw, full, full_clean):
                continue
            source = normalize_text(raw.get("src", raw.get("source", "")))
            target = normalize_text(raw.get("dst", raw.get("target", "")))
            if target == "":
                continue
            note = normalize_text(raw.get("info", raw.get("note", "")))
            origin = normalize_text(raw.get("origin", "LOCAL")).upper() or "LOCAL"
            record_id = normalize_text(raw.get("record_id", raw.get("id", "")))
            if record_id == "":
                record_id = f"term:{origin}:{source.casefold()}"
            content = f"{source} -> {target}" + (f" #{note}" if note else "")
            result.append(DynamicAssetEntry(
                kind = "glossary",
                source = source,
                record_id = record_id,
                priority = self._asset_priority("glossary", origin),
                content = content,
            ))
        return result

    def _collect_do_not_translate_asset_entries(self, srcs: list[str]) -> list[DynamicAssetEntry]:
        if getattr(self.config, "do_not_translate_enable", False) is not True:
            return []
        merged_text = "\n".join(normalize_text_list(srcs, unique = False))
        result: list[DynamicAssetEntry] = []
        for raw in getattr(self.config, "do_not_translate_data", ()):
            if not isinstance(raw, dict) or raw.get("enabled", True) is not True:
                continue
            source = normalize_text(raw.get("source", raw.get("src", raw.get("marker", ""))))
            if source == "":
                continue
            if raw.get("regex", False) is True and getattr(self.config, "asset_regex_enable", False) is True:
                try:
                    matched = re.search(source, merged_text) is not None
                except re.error:
                    matched = False
            else:
                matched = self._text_contains_term(merged_text, source)
            if not matched:
                continue
            note = normalize_text(raw.get("note", raw.get("info", "")))
            record_id = normalize_text(raw.get("record_id", raw.get("id", "")))
            if record_id == "":
                record_id = f"dnt:{source.casefold()}"
            result.append(DynamicAssetEntry(
                kind = "do_not_translate",
                source = source,
                record_id = record_id,
                priority = self._asset_priority("do_not_translate"),
                content = f"- {source}" + (f" #{note}" if note else ""),
            ))
        return result

    def _render_character_card(self, card: dict) -> str:
        name = normalize_text(card.get("name", ""))
        translation = normalize_text(card.get("name_translation", ""))
        aliases = normalize_text_list(card.get("aliases", []))
        relation = normalize_text(card.get("relationship_notes", ""))
        prompt_notes = normalize_text(card.get("prompt_notes", ""))
        sample_lines = normalize_text_list(card.get("sample_lines", []))[:4]

        if self.config.target_language == BaseLanguage.Enum.ZH:
            lines = [f"角色：{name}"]
            if translation:
                lines.append(f"推荐译名：{translation}")
            if aliases:
                lines.append(f"别名：{'、'.join(aliases)}")
            lines.extend((
                f"身份：{normalize_text(card.get('identity', '')) or '未指定'}",
                f"性格：{normalize_text(card.get('personality', '')) or '未指定'}",
                f"说话风格：{normalize_text(card.get('speech_style', '')) or '未指定'}",
            ))
            if relation:
                lines.append(f"关系备注：{relation}")
            if prompt_notes:
                lines.append(f"翻译提示：{prompt_notes}")
            if sample_lines:
                lines.append("代表台词：")
                lines.extend(f"- {line}" for line in sample_lines)
            return "\n".join(lines)

        lines = [
            f"Character: {name}",
            f"Identity: {normalize_text(card.get('identity', '')) or 'Unknown'}",
            f"Personality: {normalize_text(card.get('personality', '')) or 'Unknown'}",
            f"Speech Style: {normalize_text(card.get('speech_style', '')) or 'Unknown'}",
        ]
        if translation:
            lines.append(f"Preferred Translation: {translation}")
        if aliases:
            lines.append(f"Aliases: {', '.join(aliases)}")
        if relation:
            lines.append(f"Relationship Notes: {relation}")
        if prompt_notes:
            lines.append(f"Prompt Notes: {prompt_notes}")
        if sample_lines:
            lines.append("Representative Lines:")
            lines.extend(f"- {line}" for line in sample_lines)
        return "\n".join(lines)

    def _collect_character_asset_entries(
        self,
        srcs: list[str],
        items: list[CacheItem] | None,
    ) -> list[DynamicAssetEntry]:
        result: list[DynamicAssetEntry] = []
        for card in self.match_character_cards(srcs, items):
            source = normalize_text(card.get("name", ""))
            if source == "":
                continue
            record_id = normalize_text(card.get("id", card.get("record_id", "")))
            if record_id == "":
                record_id = f"character:{source.casefold()}"
            result.append(DynamicAssetEntry(
                kind = "character",
                source = source,
                record_id = record_id,
                priority = self._asset_priority("character", "CHARACTER"),
                content = self._render_character_card(card),
            ))
        return result

    def build_dynamic_asset_contexts(
        self,
        srcs: list[str],
        items: list[CacheItem] | None,
    ) -> tuple[str, str, str]:
        candidates = (
            self._collect_glossary_asset_entries(srcs)
            + self._collect_do_not_translate_asset_entries(srcs)
            + self._collect_character_asset_entries(srcs, items)
        )

        winners: dict[str, DynamicAssetEntry] = {}
        for candidate in candidates:
            key = normalize_text(candidate.source).casefold()
            current = winners.get(key)
            candidate_key = (
                candidate.priority,
                -len(candidate.source),
                candidate.source.casefold(),
                candidate.record_id,
            )
            if current is None or candidate_key < (
                current.priority,
                -len(current.source),
                current.source.casefold(),
                current.record_id,
            ):
                winners[key] = candidate

        ordered = sorted(
            winners.values(),
            key = lambda entry: (
                entry.priority,
                -len(entry.source),
                entry.source.casefold(),
                entry.record_id,
            ),
        )
        max_items = max(1, int(getattr(self.config, "asset_prompt_max_items", 64) or 64))
        token_budget = max(1, int(getattr(self.config, "asset_prompt_token_budget", 2048) or 2048))
        selected: list[DynamicAssetEntry] = []
        used_tokens = 0
        for entry in ordered:
            if len(selected) >= max_items:
                break
            cost = self._asset_token_cost(entry.content)
            if used_tokens + cost > token_budget:
                # 单条资产过大时跳过它，继续尝试后续较小资产，避免一个超长备注
                # 阻断同一批次中仍可安全注入的术语、禁翻项或角色卡。
                continue
            selected.append(entry)
            used_tokens += cost

        grouped = {
            "glossary": [entry.content for entry in selected if entry.kind == "glossary"],
            "do_not_translate": [entry.content for entry in selected if entry.kind == "do_not_translate"],
            "character": [entry.content for entry in selected if entry.kind == "character"],
        }
        if self.config.target_language == BaseLanguage.Enum.ZH:
            glossary_header = "术语表 <术语原文> -> <术语译文> #<术语信息>:"
            dnt_header = "禁翻项（在译文中逐字符原样保留）："
            character_header = "命中角色卡："
        else:
            glossary_header = "Glossary <Original Term> -> <Translated Term> #<Term Information>:"
            dnt_header = "Do Not Translate (preserve byte-for-byte in translations):"
            character_header = "Matched Character Cards:"

        return tuple(
            header + "\n" + "\n\n".join(grouped[kind]) if grouped[kind] else ""
            for kind, header in (
                ("glossary", glossary_header),
                ("do_not_translate", dnt_header),
                ("character", character_header),
            )
        )

    def match_character_cards(
        self,
        srcs: list[str],
        items: list[CacheItem] | None,
    ) -> list[dict]:
        """匹配当前批次命中的角色卡。"""
        if getattr(self.config, "renpy_workbench_character_cards_enable", False) is not True:
            return []

        cards = [
            card
            for card in normalize_character_cards(getattr(self.config, "renpy_workbench_character_cards", []))
            if card.get("enabled", True)
        ]
        if cards == []:
            return []

        items = items or []
        speaker_names = {
            normalize_text(item.get_first_name_src()).casefold()
            for item in items
            if normalize_text(item.get_first_name_src()) != ""
        }
        merged_text = "\n".join(normalize_text_list(srcs, unique = False))

        matched: list[dict] = []
        for card in cards:
            name = normalize_text(card.get("name", ""))
            aliases = normalize_text_list(card.get("aliases", []))
            keywords = normalize_text_list(card.get("match_keywords", []))

            name_hits = {name.casefold()} if name else set()
            name_hits.update(alias.casefold() for alias in aliases)
            if speaker_names & name_hits:
                matched.append(card)
                continue

            tokens = normalize_text_list([name] + aliases + keywords)
            if any(self._text_contains_term(merged_text, token) for token in tokens):
                matched.append(card)

        matched.sort(
            key = lambda card: (
                0 if card.get("is_primary", False) else 1,
                normalize_text(card.get("name", "")).casefold(),
            )
        )
        return matched

    def build_character_context(
        self,
        srcs: list[str],
        items: list[CacheItem] | None,
    ) -> str:
        """构建命中角色卡上下文。"""
        matched = self.match_character_cards(srcs, items)
        if matched == []:
            return ""

        if self.config.target_language == BaseLanguage.Enum.ZH:
            blocks = ["命中角色卡："]
            for card in matched:
                lines = [
                    f"角色：{normalize_text(card.get('name', ''))}",
                ]
                translation = normalize_text(card.get("name_translation", ""))
                if translation:
                    lines.append(f"推荐译名：{translation}")
                aliases = normalize_text_list(card.get("aliases", []))
                if aliases:
                    lines.append(f"别名：{'、'.join(aliases)}")
                lines.append(f"身份：{normalize_text(card.get('identity', '')) or '未指定'}")
                lines.append(f"性格：{normalize_text(card.get('personality', '')) or '未指定'}")
                lines.append(f"说话风格：{normalize_text(card.get('speech_style', '')) or '未指定'}")
                relation = normalize_text(card.get("relationship_notes", ""))
                if relation:
                    lines.append(f"关系备注：{relation}")
                prompt_notes = normalize_text(card.get("prompt_notes", ""))
                if prompt_notes:
                    lines.append(f"翻译提示：{prompt_notes}")
                sample_lines = normalize_text_list(card.get("sample_lines", []))
                if sample_lines:
                    lines.append("代表台词：")
                    lines.extend(f"- {line}" for line in sample_lines[:4])
                blocks.append("\n".join(lines))
            return "\n\n".join(blocks)

        blocks = ["Matched Character Cards:"]
        for card in matched:
            lines = [
                f"Character: {normalize_text(card.get('name', ''))}",
                f"Identity: {normalize_text(card.get('identity', '')) or 'Unknown'}",
                f"Personality: {normalize_text(card.get('personality', '')) or 'Unknown'}",
                f"Speech Style: {normalize_text(card.get('speech_style', '')) or 'Unknown'}",
            ]
            translation = normalize_text(card.get("name_translation", ""))
            if translation:
                lines.append(f"Preferred Translation: {translation}")
            aliases = normalize_text_list(card.get("aliases", []))
            if aliases:
                lines.append(f"Aliases: {', '.join(aliases)}")
            relation = normalize_text(card.get("relationship_notes", ""))
            if relation:
                lines.append(f"Relationship Notes: {relation}")
            prompt_notes = normalize_text(card.get("prompt_notes", ""))
            if prompt_notes:
                lines.append(f"Prompt Notes: {prompt_notes}")
            sample_lines = normalize_text_list(card.get("sample_lines", []))
            if sample_lines:
                lines.append("Representative Lines:")
                lines.extend(f"- {line}" for line in sample_lines[:4])
            blocks.append("\n".join(lines))
        return "\n\n".join(blocks)

    # 构造参考上文
    def build_preceding(self, precedings: list[CacheItem]) -> str:
        if len(precedings) == 0:
            return ""

        lines = []
        for item in precedings:
            src = item.get_src().strip().replace("\n", "\\n")
            dst = (item.get_dst() or "").strip().replace("\n", "\\n")
            if dst and dst != src:
                lines.append(f"{src} -> {dst}")
            else:
                lines.append(src)

        if self.config.target_language == BaseLanguage.Enum.ZH:
            return "参考上文（原文 -> 译文）：\n" + "\n".join(lines)
        else:
            return "Preceding Context (Source -> Translation):\n" + "\n".join(lines)

    # 构造术语表
    def build_glossary(self, srcs: list[str]) -> str:
        full = "\n".join(srcs)
        # 术语匹配时忽略占位/标签段，避免 [jane_rlt2] 命中术语 "jane"。
        full_clean = __class__.RE_GLOSSARY_IGNORE_SEGMENTS.sub("", full)
        full_lower = full_clean.lower()
        full_raw_lower = full.lower()
        glossary: list[dict[str, str]] = []
        for v in self.config.glossary_data:
            if v.get("enabled", True) is not True:
                continue
            src = v.get("src", "")
            if src == "":
                continue
            # 若术语本身带占位字符，按原文匹配；普通术语按清洗后文本匹配。
            target_full = full if any(ch in src for ch in "[]{}") else full_clean
            is_case_sensitive = v.get("case_sensitive", False)
            # 纯拉丁术语使用词边界匹配，避免 "an" 匹配 "Another"
            use_word_boundary = bool(__class__.RE_LATIN_ONLY.match(src)) and len(src) <= 20
            if v.get("regex", False) is True and getattr(self.config, "asset_regex_enable", False) is True:
                flags = 0 if is_case_sensitive else re.IGNORECASE
                try:
                    if re.search(src, target_full, flags):
                        glossary.append(v)
                except re.error:
                    continue
            elif use_word_boundary:
                flags = 0 if is_case_sensitive else re.IGNORECASE
                if re.search(r"\b" + re.escape(src) + r"\b", target_full, flags):
                    glossary.append(v)
            elif is_case_sensitive:
                if src in target_full:
                    glossary.append(v)
            else:
                target_lower = full_raw_lower if any(ch in src for ch in "[]{}") else full_lower
                if src.lower() in target_lower:
                    glossary.append(v)

        # 构建文本
        result = []
        for item in glossary:
            src = item.get("src", "")
            dst = item.get("dst", "")
            info = item.get("info", "")

            if info == "":
                result.append(f"{src} -> {dst}")
            else:
                result.append(f"{src} -> {dst} #{info}")

        # 返回结果
        if result == []:
            return ""
        elif self.config.target_language == BaseLanguage.Enum.ZH:
            return (
                "术语表 <术语原文> -> <术语译文> #<术语信息>:"
                + "\n" + "\n".join(result)
            )
        else:
            return (
                "Glossary <Original Term> -> <Translated Term> #<Term Information>:"
                + "\n" + "\n".join(result)
            )

    def build_do_not_translate_context(self, srcs: list[str]) -> str:
        """Build the batch-matched do-not-translate asset layer."""
        if getattr(self.config, "do_not_translate_enable", False) is not True:
            return ""

        merged_text = "\n".join(normalize_text_list(srcs, unique = False))
        matched: list[tuple[str, str]] = []
        seen: set[str] = set()
        for item in getattr(self.config, "do_not_translate_data", ()):
            if not isinstance(item, dict) or item.get("enabled", True) is not True:
                continue
            source = normalize_text(item.get("source", item.get("src", item.get("marker", ""))))
            if source == "":
                continue

            is_match = False
            if item.get("regex", False) is True and getattr(self.config, "asset_regex_enable", False) is True:
                try:
                    is_match = re.search(source, merged_text) is not None
                except re.error:
                    continue
            else:
                is_match = self._text_contains_term(merged_text, source)

            key = source.casefold()
            if is_match and key not in seen:
                seen.add(key)
                matched.append((source, normalize_text(item.get("note", item.get("info", "")))))

        if matched == []:
            return ""
        matched.sort(key = lambda item: item[0].casefold())

        if self.config.target_language == BaseLanguage.Enum.ZH:
            lines = ["禁翻项（在译文中逐字符原样保留）："]
        else:
            lines = ["Do Not Translate (preserve byte-for-byte in translations):"]
        for source, note in matched:
            lines.append(f"- {source}" + (f" #{note}" if note else ""))
        return "\n".join(lines)

    # 构造术语表
    def build_glossary_sakura(self, srcs: list[str]) -> str:
        full = "\n".join(srcs)
        full_clean = __class__.RE_GLOSSARY_IGNORE_SEGMENTS.sub("", full)
        full_lower = full_clean.lower()
        full_raw_lower = full.lower()
        glossary: list[dict[str, str]] = []
        for v in self.config.glossary_data:
            if v.get("enabled", True) is not True:
                continue
            src = v.get("src", "")
            if src == "":
                continue
            target_full = full if any(ch in src for ch in "[]{}") else full_clean
            is_case_sensitive = v.get("case_sensitive", False)
            use_word_boundary = bool(__class__.RE_LATIN_ONLY.match(src)) and len(src) <= 20
            if v.get("regex", False) is True and getattr(self.config, "asset_regex_enable", False) is True:
                flags = 0 if is_case_sensitive else re.IGNORECASE
                try:
                    if re.search(src, target_full, flags):
                        glossary.append(v)
                except re.error:
                    continue
            elif use_word_boundary:
                flags = 0 if is_case_sensitive else re.IGNORECASE
                if re.search(r"\b" + re.escape(src) + r"\b", target_full, flags):
                    glossary.append(v)
            elif is_case_sensitive:
                if src in target_full:
                    glossary.append(v)
            else:
                target_lower = full_raw_lower if any(ch in src for ch in "[]{}") else full_lower
                if src.lower() in target_lower:
                    glossary.append(v)

        # 构建文本
        result = []
        for item in glossary:
            src = item.get("src", "")
            dst = item.get("dst", "")
            info = item.get("info", "")

            if info == "":
                result.append(f"{src}->{dst}")
            else:
                result.append(f"{src}->{dst} #{info}")

        # 返回结果
        if result == []:
            return ""
        else:
            return "\n".join(result)

    # 构建控制字符示例
    def build_control_characters_samples(self, main: str, samples: list[str]) -> str:
        samples = sorted({v.strip() for v in samples if isinstance(v, str) and v.strip() != ""})

        if len(samples) == 0:
            return ""

        # 判断提示词语言
        if self.config.target_language == BaseLanguage.Enum.ZH:
            prefix: str = "控制字符示例："
        else:
            prefix: str = "Control Characters Samples:"

        return prefix + "\n" + ", ".join(samples)

    # 构建输入
    def build_inputs(self, srcs: list[str], protocol: str | None = None) -> str:
        """Build a request batch whose indices match the response contract."""
        protocol = protocol or self._normalize_output_protocol()
        records = [
            {"request_index": index, "text": text}
            for index, text in enumerate(srcs)
        ]

        if protocol == Config.OUTPUT_PROTOCOL_SINGLE_TEXT:
            if len(srcs) != 1:
                raise ValueError("SINGLE_TEXT protocol requires exactly one source line")
            return self.build_single_line_input(srcs[0])

        if protocol == Config.OUTPUT_PROTOCOL_STRUCTURED:
            payload = json.dumps({"inputs": records}, ensure_ascii = False, indent = 2)
            title = "当前索引批次：" if self.config.target_language == BaseLanguage.Enum.ZH else "Current Indexed Batch:"
            return title + "\n```json\n" + payload + "\n```"

        if protocol != Config.OUTPUT_PROTOCOL_JSONLINE:
            raise ValueError(f"Unsupported translation output protocol: {protocol}")

        payload = "\n".join(
            json.dumps(record, ensure_ascii = False)
            for record in records
        )
        title = "当前索引批次：" if self.config.target_language == BaseLanguage.Enum.ZH else "Current Indexed Batch:"
        return title + "\n```jsonline\n" + payload + "\n```"

    def build_single_line_instruction(self) -> str:
        """Return the non-overridable engineering and SINGLE_TEXT protocol."""
        prompt_language, source_language, target_language = self.get_prompt_language_and_names()
        prompt = __class__._join_sections(
            __class__.get_engineering(prompt_language),
            __class__.get_output_protocol(prompt_language, Config.OUTPUT_PROTOCOL_SINGLE_TEXT),
        )
        return __class__._replace_language_placeholders(prompt, source_language, target_language)

    def build_single_line_input(self, src: str) -> str:
        prompt_language, _, _ = self.get_prompt_language_and_names()
        if prompt_language == BaseLanguage.Enum.ZH:
            return "原文：\n```text\n" + src + "\n```"

        return "Source:\n```text\n" + src + "\n```"

    def build_single_line_control_samples(self, samples: list[str]) -> str:
        samples = sorted({v.strip() for v in samples if isinstance(v, str) and v.strip() != ""})
        if len(samples) == 0:
            return ""

        prompt_language, _, _ = self.get_prompt_language_and_names()
        if prompt_language == BaseLanguage.Enum.ZH:
            return "需要原样保留的控制字符示例：\n" + ", ".join(samples)

        return "Control character examples that must be preserved:\n" + ", ".join(samples)

    def build_structured_placeholder_context(self, srcs: list[str]) -> str:
        """构建结构化占位符上下文，避免把临时 token 当自然语言翻译。"""
        tokens: dict[int, str] = {}
        for src in srcs:
            if not isinstance(src, str):
                continue
            for match in __class__.RE_STRUCTURED_PLACEHOLDER.finditer(src):
                index = int(match.group(1))
                tokens[index] = f"<n{index}/>"

        if tokens == {}:
            return ""

        token_text = ", ".join(tokens[index] for index in sorted(tokens))
        if self.config.target_language == BaseLanguage.Enum.ZH:
            return (
                "结构化占位符协议："
                + token_text
                + " 是程序临时变量占位符，不是自然语言。翻译时可按目标语语序移动它们，但输出时必须逐字符原样保留，禁止翻译、音译、改写、加空格或补闭合标签。"
            )

        return (
            "Structured Placeholder Protocol: "
            + token_text
            + " are temporary program placeholders, not natural language. You may move them to fit target-language word order, but must output each token byte-for-byte unchanged; do not translate, transliterate, rewrite, add spaces, or add closing tags."
        )

    def generate_single_line_prompt(
        self,
        src: str,
        samples: list[str],
        precedings: list[CacheItem],
        local_flag: bool,
        item: CacheItem | None = None,
    ) -> tuple[list[dict], list[str]]:
        """生成单行翻译提示词：单请求单原文，允许模型直接输出纯文本。"""
        extra_log: list[str] = []
        items = [item] if item is not None else None
        system_sections = [
            self._build_main_for_protocol(Config.OUTPUT_PROTOCOL_SINGLE_TEXT),
        ]

        result = self.build_worldbook_context()
        if result != "":
            system_sections.append(result)
            extra_log.append(result)

        for result in self.build_dynamic_asset_contexts([src], items):
            if result != "":
                system_sections.append(result)
                extra_log.append(result)

        result = self.build_single_line_control_samples(samples)
        if result != "":
            system_sections.append(result)
            extra_log.append(result)

        result = self.build_structured_placeholder_context([src])
        if result != "":
            system_sections.append(result)
            extra_log.append(result)

        user_sections: list[str] = []
        result = self.build_retry_hint(items)
        if result != "":
            user_sections.append(result)
            extra_log.append(result)

        if local_flag is False or self.config.enable_preceding_on_local is True:
            result = self.build_preceding(precedings)
            if result != "":
                user_sections.append(result)
                extra_log.append(result)

        user_sections.append(self.build_single_line_input(src))
        messages = [
            {"role": "system", "content": __class__._join_sections(*system_sections)},
            {"role": "user", "content": __class__._join_sections(*user_sections)},
        ]

        return messages, extra_log

    @staticmethod
    def _read_retry_reason_codes(items: list[CacheItem] | None) -> frozenset[str]:
        codes: set[str] = set()
        for item in items or []:
            if item is None:
                continue
            payload = item.get_metadata().get("translation_retry")
            if not isinstance(payload, dict):
                continue
            reasons = payload.get("reasons", payload.get("reason", ()))
            if isinstance(reasons, (str, dict)):
                reasons = (reasons,)
            if not isinstance(reasons, (list, tuple)):
                continue

            for reason in reasons:
                if isinstance(reason, str):
                    code = reason
                elif isinstance(reason, dict):
                    code = reason.get("code", reason.get("error", reason.get("type", "")))
                else:
                    continue
                if isinstance(code, str) and code.strip() != "":
                    codes.add(code.strip().upper())
        return frozenset(codes)

    def build_retry_hint(self, items: list[CacheItem] | None) -> str:
        """Build short, deterministic corrections for the last known failure types."""
        codes = self._read_retry_reason_codes(items)
        if codes == frozenset():
            return ""

        groups: tuple[tuple[frozenset[str], str, str], ...] = (
            (
                frozenset({"INDEX_ALIGNMENT", "FAIL_LINE_COUNT", "STRICT_INDEX_ALIGNMENT"}),
                "严格按请求中的 0-based request_index 输出；每个索引恰好出现一次，不得缺失、重复或新增。",
                "Follow the requested 0-based request_index values exactly; emit every index once with no missing, duplicate, or extra index.",
            ),
            (
                frozenset({"RESPONSE_FORMAT", "FAIL_DATA"}),
                "只输出当前指定的响应协议，译文不得为空，也不要添加协议外文本。",
                "Return only the selected response protocol, with non-empty translations and no text outside it.",
            ),
            (
                frozenset({"PLACEHOLDER_MISMATCH", "TEXT_PRESERVE", "LINE_ERROR_FAKE_REPLY"}),
                "逐字保留原文中的变量、标签和占位符；拼写与出现次数必须一致。",
                "Preserve every variable, tag, and placeholder verbatim, with identical spelling and occurrence counts.",
            ),
            (
                frozenset({"LINE_ERROR_KANA", "LINE_ERROR_HANGEUL", "LINE_ERROR_MIXED_LANGUAGE", "RESIDUAL_LANGUAGE"}),
                "完整翻译可翻译的源语言内容，不得残留日文、韩文或夹杂的源语言片段。",
                "Fully translate translatable source-language content; do not leave Japanese, Korean, or mixed source-language fragments.",
            ),
            (
                frozenset({"GLOSSARY", "TERMINOLOGY", "TERM_MISMATCH"}),
                "严格使用本批提示中已命中的术语译法。",
                "Use the matched glossary translations supplied for this batch exactly.",
            ),
            (
                frozenset({"LINE_ERROR_EMPTY_LINE", "EMPTY_TRANSLATION"}),
                "每个请求都必须返回非空译文。",
                "Return a non-empty translation for every request.",
            ),
            (
                frozenset({"LINE_ERROR_SIMILARITY", "SOURCE_COPY"}),
                "不要照抄或仅轻微改写自然语言原文；请完整翻译。",
                "Do not copy or lightly paraphrase natural-language source text; translate it fully.",
            ),
            (
                frozenset({"LINE_ERROR_DEGRADATION", "DEGRADED_OUTPUT"}),
                "避免重复字符、词语或句段，输出完整且不退化的译文。",
                "Avoid repeated characters, words, or passages; return a complete, non-degraded translation.",
            ),
            (
                frozenset({"TRANSLATION_ERROR_MARKER", "INVALID_RESPONSE"}),
                "直接给出有效译文，不要输出失败标记或拒绝说明。",
                "Return a valid translation directly, without failure markers or refusal text.",
            ),
        )

        use_chinese = self.config.target_language == BaseLanguage.Enum.ZH
        hints = [zh if use_chinese else en for group, zh, en in groups if not codes.isdisjoint(group)]
        if hints == []:
            return ""
        heading = "重试修正：" if use_chinese else "Retry corrections:"
        return heading + "\n" + "\n".join(f"- {hint}" for hint in hints)

    # 生成提示词
    def generate_prompt(
        self,
        srcs: list[str],
        samples: list[str],
        precedings: list[CacheItem],
        local_flag: bool,
        items: list[CacheItem] | None = None,
    ) -> tuple[list[dict], list[str]]:
        protocol = self._normalize_output_protocol()
        if protocol == Config.OUTPUT_PROTOCOL_SINGLE_TEXT:
            raise ValueError("SINGLE_TEXT must use generate_single_line_prompt")

        extra_log: list[str] = []
        system_sections = [self._build_main_for_protocol(protocol)]

        result = self.build_worldbook_context()
        if result != "":
            system_sections.append(result)
            extra_log.append(result)

        for result in self.build_dynamic_asset_contexts(srcs, items):
            if result != "":
                system_sections.append(result)
                extra_log.append(result)

        result = self.build_control_characters_samples(system_sections[0], samples)
        if result != "":
            system_sections.append(result)
            extra_log.append(result)

        result = self.build_structured_placeholder_context(srcs)
        if result != "":
            system_sections.append(result)
            extra_log.append(result)

        user_sections: list[str] = []

        result = self.build_retry_hint(items)
        if result != "":
            user_sections.append(result)
            extra_log.append(result)

        if local_flag is False or self.config.enable_preceding_on_local is True:
            result = self.build_preceding(precedings)
            if result != "":
                user_sections.append(result)
                extra_log.append(result)

        user_sections.append(self.build_inputs(srcs, protocol = protocol))
        messages = [
            {"role": "system", "content": __class__._join_sections(*system_sections)},
            {"role": "user", "content": __class__._join_sections(*user_sections)},
        ]

        return messages, extra_log

    # 生成提示词 - Sakura
    def generate_prompt_sakura(
        self,
        srcs: list[str],
        items: list[CacheItem] | None = None,
    ) -> tuple[list[dict], list[str]]:
        extra_log: list[str] = []
        protocol = Config.OUTPUT_PROTOCOL_JSONLINE
        system_sections = [self._build_main_for_protocol(protocol)]

        result = self.build_worldbook_context()
        if result != "":
            system_sections.append(result)
            extra_log.append(result)

        for result in self.build_dynamic_asset_contexts(srcs, items):
            if result != "":
                system_sections.append(result)
                extra_log.append(result)

        result = self.build_structured_placeholder_context(srcs)
        if result != "":
            system_sections.append(result)
            extra_log.append(result)

        user_sections: list[str] = []
        result = self.build_retry_hint(items)
        if result != "":
            user_sections.append(result)
            extra_log.append(result)
        user_sections.append(self.build_inputs(srcs, protocol = protocol))

        messages = [
            {"role": "system", "content": __class__._join_sections(*system_sections)},
            {"role": "user", "content": __class__._join_sections(*user_sections)},
        ]

        return messages, extra_log

    # 生成提示词 - Sakura 格式化重试
    def generate_prompt_sakura_format_retry(self, srcs: list[str], raw_reply: str) -> tuple[list[dict], list[str]]:
        extra_log: list[str] = []
        protocol = Config.OUTPUT_PROTOCOL_JSONLINE
        prompt_language, source_language, target_language = self.get_prompt_language_and_names()
        output_protocol = __class__._replace_language_placeholders(
            __class__.get_output_protocol(prompt_language, protocol),
            source_language,
            target_language,
        )
        system_content = __class__._join_sections(
            "你是翻译结果的格式整理助手。只整理已有译文，不翻译、不改写、不补造内容。",
            output_protocol,
        )

        content_lines = [
            "把“模型回复内容”整理成 JSONLINE 输出。",
            "每行必须是 {\"request_index\":0,\"text\":\"译文\"} 结构，索引从 0 开始。",
            "只保留能够从模型回复中明确对应到请求索引的译文；不得猜测索引，不得为空缺索引编造或补空。",
            "如果出现中英双语，优先中文行，忽略英文行。",
            "保留控制字符/标签/变量（如 {w}、{...}、[...]）原样输出。",
            self.build_inputs(srcs, protocol = protocol),
            "模型回复内容：",
            raw_reply,
        ]
        content = "\n".join(content_lines)

        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": content},
        ]

        return messages, extra_log
