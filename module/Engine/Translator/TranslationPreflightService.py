from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from typing import Any

from module.Engine.Translator.TranslationTaskContext import ProjectAssets


@dataclasses.dataclass(frozen = True)
class TranslationPreflightResult:
    assets: ProjectAssets
    effective_sections: tuple[str, ...]
    fixed_prompt_tokens: int = 0
    context_window_tokens: int = 0
    errors: tuple[str, ...] = ()

    @property
    def has_effective_assets(self) -> bool:
        return bool(self.effective_sections)

    @property
    def should_prompt_for_missing_assets(self) -> bool:
        return self.has_effective_assets is False

    @property
    def can_start(self) -> bool:
        return self.errors == ()


class TranslationPreflightService:
    """Shared, UI-independent validation for all translation entry points."""

    @classmethod
    def check(
        cls,
        assets: ProjectAssets | Mapping[str, Any] | None,
        *,
        fixed_prompt: str = "",
        provider: Mapping[str, Any] | None = None,
        reserved_output_tokens: int = 0,
    ) -> TranslationPreflightResult:
        normalized = ProjectAssets.from_dict(assets)
        sections: list[str] = []

        if normalized.worldbook_enabled and cls._has_content(normalized.worldbook):
            sections.append("worldbook")
        if normalized.character_cards_enabled and any(
            cls._is_effective_character(card)
            for card in normalized.character_cards
        ):
            sections.append("character_cards")
        if normalized.glossary_enabled and any(
            item.enabled and item.source != "" and item.target != ""
            for item in normalized.glossary
        ):
            sections.append("glossary")
        if normalized.do_not_translate_enabled and any(
            item.enabled and item.source != ""
            for item in normalized.do_not_translate
        ):
            sections.append("do_not_translate")

        fixed_prompt_tokens = cls.estimate_tokens(fixed_prompt)
        context_window_tokens = cls._context_window(provider)
        errors: list[str] = []
        if context_window_tokens > 0:
            available = max(0, context_window_tokens - max(0, int(reserved_output_tokens)))
            if fixed_prompt_tokens >= available:
                errors.append(
                    "FIXED_PROMPT_EXCEEDS_CONTEXT_WINDOW:"
                    f"{fixed_prompt_tokens}>={available}"
                )

        return TranslationPreflightResult(
            assets = normalized,
            effective_sections = tuple(sections),
            fixed_prompt_tokens = fixed_prompt_tokens,
            context_window_tokens = context_window_tokens,
            errors = tuple(errors),
        )

    @classmethod
    def has_effective_assets(cls, assets: ProjectAssets | Mapping[str, Any] | None) -> bool:
        return cls.check(assets).has_effective_assets

    @staticmethod
    def estimate_tokens(text: Any) -> int:
        if not isinstance(text, str) or text == "":
            return 0
        return max(1, (len(text.encode("utf-8")) + 3) // 4)

    @staticmethod
    def _context_window(provider: Mapping[str, Any] | None) -> int:
        if not isinstance(provider, Mapping):
            return 0
        for key in (
            "context_window_tokens",
            "context_window",
            "context_length",
            "max_context_tokens",
        ):
            value = provider.get(key)
            if isinstance(value, int) and not isinstance(value, bool) and value > 0:
                return value
        return 0

    @classmethod
    def evaluate(cls, assets: ProjectAssets | Mapping[str, Any] | None) -> TranslationPreflightResult:
        return cls.check(assets)

    @classmethod
    def _has_content(cls, value: Any) -> bool:
        if value is None:
            return False
        if isinstance(value, str):
            return value.strip() != ""
        if isinstance(value, Mapping):
            return any(cls._has_content(item) for item in value.values())
        if isinstance(value, (list, tuple, set, frozenset)):
            return any(cls._has_content(item) for item in value)
        if isinstance(value, bool):
            return value
        return True

    @classmethod
    def _is_effective_character(cls, card: Mapping[str, Any]) -> bool:
        if bool(card.get("enabled", True)) is False:
            return False
        if str(card.get("name", "")).strip() == "":
            return False

        injectable_fields = (
            "name",
            "name_translation",
            "aliases",
            "match_keywords",
            "identity",
            "personality",
            "speech_style",
            "relationship_notes",
            "prompt_notes",
            "sample_lines",
        )
        return any(cls._has_content(card.get(field)) for field in injectable_fields)
