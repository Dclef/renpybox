from __future__ import annotations

import dataclasses
import json
import re
from collections import Counter
from collections.abc import Callable, Sequence
from enum import Enum
from typing import Any, Protocol

from base.Base import Base
from module.Cache.CacheItem import CacheItem
from module.Config import Config
from module.Engine.TaskRequester import TaskRequester
from module.Engine.Translator.TranslationTaskContext import (
    TermAsset,
    TranslationTaskContext,
)
from module.PromptBuilder import PromptBuilder
from module.Response.ResponseChecker import ResponseChecker
from module.TextProcessor import TextProcessor


@dataclasses.dataclass(frozen = True)
class QualityTaskFailure:
    item_index: int
    reason: str
    attempts: int = 0


@dataclasses.dataclass(frozen = True)
class QualityTaskResult:
    total_count: int = 0
    eligible_count: int = 0
    updated_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    failures: tuple[QualityTaskFailure, ...] = ()

    @property
    def success_count(self) -> int:
        return self.updated_count


@dataclasses.dataclass(frozen = True)
class QualityItemSnapshot:
    request_index: int
    item_index: int
    source: str
    current_translation: str
    status: Base.TranslationStatus
    text_type: CacheItem.TextType
    name_source: str | tuple[str, ...] | None = None

    @classmethod
    def from_item(
        cls,
        item: CacheItem,
        *,
        request_index: int,
        item_index: int,
    ) -> QualityItemSnapshot:
        raw_name = item.get_name_src()
        if isinstance(raw_name, list):
            name_source: str | tuple[str, ...] | None = tuple(str(value) for value in raw_name)
        elif isinstance(raw_name, str):
            name_source = raw_name
        else:
            name_source = None

        return cls(
            request_index = request_index,
            item_index = item_index,
            source = item.get_src(),
            current_translation = item.get_dst(),
            status = item.get_status(),
            text_type = item.get_text_type(),
            name_source = name_source,
        )


@dataclasses.dataclass(frozen = True)
class QualityValidationResult:
    valid: bool
    errors: tuple[str, ...] = ()


@dataclasses.dataclass(frozen = True)
class RequestOutcome:
    ok: bool
    content: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    error: str = ""


class QualityRequester(Protocol):
    def request(self, messages: list[dict[str, str]]) -> tuple[bool, str, str, int, int]: ...


class QualityPromptBuilderProtocol(Protocol):
    def build_polisher_prompt(
        self,
        snapshots: Sequence[QualityItemSnapshot],
        *,
        protocol: str,
        precedings: Sequence[CacheItem] = (),
    ) -> list[dict[str, str]]: ...

    def build_proofread_prompt(
        self,
        snapshot: QualityItemSnapshot,
        *,
        error_types: Sequence[str],
        precedings: Sequence[CacheItem] = (),
        attempt: int = 1,
        retry_reason: str = "",
    ) -> list[dict[str, str]]: ...


class QualityPromptBuilder:
    """基于不可变的翻译快照构建质量任务提示词。"""

    MAX_PRECEDING_ITEMS = 3

    def __init__(self, context: TranslationTaskContext) -> None:
        if not isinstance(context, TranslationTaskContext):
            raise TypeError("QualityPromptBuilder requires TranslationTaskContext")
        self.context = context
        self.translation_builder = PromptBuilder(context)

    @staticmethod
    def _join(*sections: str) -> str:
        return "\n\n".join(
            section.strip()
            for section in sections
            if isinstance(section, str) and section.strip() != ""
        )

    def _asset_sections(
        self,
        snapshots: Sequence[QualityItemSnapshot],
        precedings: Sequence[CacheItem],
    ) -> list[str]:
        srcs = [snapshot.source for snapshot in snapshots]
        items = [_snapshot_as_cache_item(snapshot) for snapshot in snapshots]
        prompt_language, _, _ = self.translation_builder.get_prompt_language_and_names()

        dynamic_assets = self.translation_builder.build_dynamic_asset_contexts(srcs, items)
        sections = [
            self.translation_builder.build_writing_style(prompt_language),
            self.translation_builder.build_worldbook_context(),
            *dynamic_assets,
            self.translation_builder.build_structured_placeholder_context(
                srcs + [snapshot.current_translation for snapshot in snapshots]
            ),
        ]
        if precedings:
            sections.append(
                self.translation_builder.build_preceding(
                    list(precedings)[-self.MAX_PRECEDING_ITEMS:]
                )
            )
        return [section for section in sections if section.strip() != ""]

    def build_polisher_prompt(
        self,
        snapshots: Sequence[QualityItemSnapshot],
        *,
        protocol: str,
        precedings: Sequence[CacheItem] = (),
    ) -> list[dict[str, str]]:
        prompt_language, source_language, target_language = (
            self.translation_builder.get_prompt_language_and_names()
        )
        system = self._join(
            (
                "You are a game-localization editor. Improve each current translation "
                "for fluency, consistency, characterization, and style without changing "
                "its meaning. Preserve every placeholder, protected marker, formatting "
                "token, and required term exactly."
            ),
            f"The source language is {source_language}; the target language is {target_language}.",
            PromptBuilder.get_engineering(prompt_language),
            PromptBuilder.get_output_protocol(prompt_language, protocol),
            *self._asset_sections(snapshots, precedings),
        )
        payload = {
            "inputs": [
                {
                    "request_index": snapshot.request_index,
                    "source": snapshot.source,
                    "current_translation": snapshot.current_translation,
                }
                for snapshot in snapshots
            ]
        }
        user = self._join(
            "Polish every indexed current_translation. Return only the selected indexed output protocol.",
            "```json\n" + json.dumps(payload, ensure_ascii = False, indent = 2) + "\n```",
        )
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

    def build_proofread_prompt(
        self,
        snapshot: QualityItemSnapshot,
        *,
        error_types: Sequence[str],
        precedings: Sequence[CacheItem] = (),
        attempt: int = 1,
        retry_reason: str = "",
    ) -> list[dict[str, str]]:
        prompt_language, source_language, target_language = (
            self.translation_builder.get_prompt_language_and_names()
        )
        constraints = collect_constraints(self.context, snapshot.source)
        system = self._join(
            (
                "You are a game-localization proofreader. Correct the supplied current "
                "translation using the source, reported errors, matched project assets, "
                "and nearby context. Preserve all placeholders and protected markers. "
                "Output only the revised translation as plain text, with no label, "
                "explanation, quotation marks, or Markdown fence."
            ),
            f"The source language is {source_language}; the target language is {target_language}.",
            self.translation_builder.build_single_line_instruction(),
            *self._asset_sections((snapshot,), precedings),
        )
        payload = {
            "source": snapshot.source,
            "current_translation": snapshot.current_translation,
            "error_types": list(error_types),
            "required_terms": [
                {"source": source, "target": target}
                for source, target in constraints.required_terms
            ],
            "do_not_translate": list(constraints.do_not_translate),
            "protected_markers": list(
                required_markers(snapshot.source, snapshot.current_translation).elements()
            ),
        }
        retry = ""
        if attempt > 1:
            retry = (
                "The previous revision failed deterministic validation. Correct that "
                f"failure in this final attempt: {retry_reason or 'invalid output'}."
            )
        user = self._join(
            retry,
            "Revise this one item:",
            "```json\n" + json.dumps(payload, ensure_ascii = False, indent = 2) + "\n```",
        )
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]


@dataclasses.dataclass(frozen = True)
class MatchedConstraints:
    required_terms: tuple[tuple[str, str], ...] = ()
    do_not_translate: tuple[str, ...] = ()


class QualityValidator:
    """在回写前以确定性规则验证质量任务候选结果。"""

    def __init__(
        self,
        context: TranslationTaskContext,
        runtime_config: Config,
    ) -> None:
        self.context = context
        self.runtime_config = runtime_config
        self.text_processor = TextProcessor(runtime_config, None)
        self.response_checker = ResponseChecker(runtime_config, [])

    def validate(
        self,
        item: CacheItem,
        candidate: str,
        *,
        source: str,
        current_translation: str,
    ) -> QualityValidationResult:
        if not isinstance(candidate, str) or candidate.strip() == "":
            return QualityValidationResult(False, ("EMPTY_RESPONSE",))

        candidate = candidate.strip()
        errors: list[str] = []
        expected_markers = required_markers(source, current_translation)
        if marker_counter(candidate) != expected_markers:
            errors.append("PROTECTED_MARKER_MISMATCH")

        if not self.text_processor.check(source, candidate, item.get_text_type()):
            errors.append("TEXT_PRESERVE_MISMATCH")

        constraints = collect_constraints(self.context, source)
        for source_term, target_term in constraints.required_terms:
            if not contains_literal(candidate, target_term):
                errors.append(f"MISSING_TERM:{source_term}->{target_term}")
        for protected_text in constraints.do_not_translate:
            if protected_text not in candidate:
                errors.append(f"MISSING_DO_NOT_TRANSLATE:{protected_text}")

        checks = self.response_checker.check(
            [source],
            [candidate],
            item.get_text_type(),
            line_items = [item],
        )
        for check in checks:
            if check == ResponseChecker.Error.NONE:
                continue
            if (
                check == ResponseChecker.Error.LINE_ERROR_SIMILARITY
                and is_fully_do_not_translate(source, constraints.do_not_translate)
            ):
                continue
            errors.append(f"RESPONSE_CHECK:{check}")

        return QualityValidationResult(errors == [], tuple(dict.fromkeys(errors)))


class BaseQualityTask:
    def __init__(
        self,
        context: TranslationTaskContext,
        *,
        protocol: str,
        requester: QualityRequester | Callable[[list[dict[str, str]]], Any] | None = None,
        requester_factory: Callable[[Config, dict[str, Any], int], QualityRequester] | None = None,
        prompt_builder: QualityPromptBuilderProtocol | None = None,
        validator: QualityValidator | None = None,
    ) -> None:
        if not isinstance(context, TranslationTaskContext):
            raise TypeError("Quality tasks require TranslationTaskContext")

        self.context = context
        self.runtime_config = context.to_runtime_config()
        self.runtime_config.translation_output_protocol = protocol
        self.prompt_builder = prompt_builder or QualityPromptBuilder(context)
        self.validator = validator or QualityValidator(context, self.runtime_config)
        self.requester = requester
        self.requester_factory = requester_factory or TaskRequester

    def _get_requester(self) -> QualityRequester | Callable[[list[dict[str, str]]], Any]:
        if self.requester is not None:
            return self.requester

        platform = self.runtime_config.get_platform(self.runtime_config.activate_platform)
        if not isinstance(platform, dict):
            raise ValueError("TranslationTaskContext has no runtime provider for quality requests")
        self.requester = self.requester_factory(self.runtime_config, dict(platform), 0)
        return self.requester

    def _request(self, messages: list[dict[str, str]]) -> RequestOutcome:
        try:
            requester = self._get_requester()
            method = getattr(requester, "request", None)
            if isinstance(requester, TaskRequester) and callable(method):
                response_shape = (
                    "json_object"
                    if self.runtime_config.structured_output_enable
                    else "none"
                )
                raw = method(messages, response_shape = response_shape)
            else:
                raw = method(messages) if callable(method) else requester(messages)
        except Exception as exc:
            return RequestOutcome(False, error = f"REQUEST_EXCEPTION:{type(exc).__name__}")

        if isinstance(raw, str):
            return RequestOutcome(raw.strip() != "", raw)
        if not isinstance(raw, tuple) or len(raw) < 3:
            return RequestOutcome(False, error = "INVALID_REQUEST_RESULT")

        skip = bool(raw[0])
        content = raw[2] if isinstance(raw[2], str) else ""
        input_tokens = _safe_int(raw[3]) if len(raw) > 3 else 0
        output_tokens = _safe_int(raw[4]) if len(raw) > 4 else 0
        if skip or content.strip() == "":
            return RequestOutcome(
                False,
                content,
                input_tokens,
                output_tokens,
                "REQUEST_FAILED" if skip else "EMPTY_RESPONSE",
            )
        return RequestOutcome(True, content, input_tokens, output_tokens)


_MARKER_RE = re.compile(
    r"_RENPYBOX_\d+_\d+_|<\s*[vn]\s*\d+\s*/?\s*>|\[[^\]\n]*\]|\{[^}\n]*\}",
    flags = re.IGNORECASE,
)
_LATIN_TERM_RE = re.compile(r"^[A-Za-z0-9_ .'\u2019\-]+$")
_ASSET_IGNORE_SEGMENTS_RE = re.compile(r"\[[^\]\n]*\]|\{[^}\n]*\}")


def marker_counter(text: str) -> Counter[str]:
    if not isinstance(text, str):
        return Counter()
    return Counter(match.group(0) for match in _MARKER_RE.finditer(text))


def required_markers(source: str, current_translation: str) -> Counter[str]:
    source_markers = marker_counter(source)
    current_markers = marker_counter(current_translation)
    return source_markers | current_markers


def contains_literal(text: str, needle: str) -> bool:
    if not isinstance(text, str) or not isinstance(needle, str):
        return False
    text = text.strip()
    needle = needle.strip()
    if text == "" or needle == "":
        return False
    if _LATIN_TERM_RE.fullmatch(needle):
        pattern = rf"(?<![A-Za-z0-9_]){re.escape(needle)}(?![A-Za-z0-9_])"
        return re.search(pattern, text, flags = re.IGNORECASE) is not None
    return needle.casefold() in text.casefold()


def _regex_enabled(context: TranslationTaskContext) -> bool:
    return bool(
        context.processing.get(
            "asset_regex_enable",
            context.prompt.get("asset_regex_enable", False),
        )
    )


def _term_matches(context: TranslationTaskContext, text: str, term: TermAsset) -> bool:
    if term.enabled is False or term.source == "":
        return False
    target_text = (
        text
        if any(character in term.source for character in "[]{}")
        else _ASSET_IGNORE_SEGMENTS_RE.sub("", text)
    )
    if term.regex and _regex_enabled(context):
        try:
            return re.search(term.source, target_text) is not None
        except re.error:
            return False
    return contains_literal(target_text, term.source)


def _regex_matches(text: str, pattern: str) -> tuple[str, ...]:
    try:
        return tuple(match.group(0) for match in re.finditer(pattern, text) if match.group(0) != "")
    except re.error:
        return ()


def collect_constraints(
    context: TranslationTaskContext,
    source: str,
) -> MatchedConstraints:
    assets = context.assets
    priority = {"LOCAL": 0, "CHARACTER": 1, "ANALYSIS": 2}
    required_by_source: dict[str, TermAsset] = {}
    candidates: list[TermAsset] = []
    if assets.glossary_enabled:
        candidates.extend(assets.glossary)
    if assets.character_cards_enabled:
        candidates.extend(assets.character_terms())
    for term in candidates:
        if term.target == "" or not _term_matches(context, source, term):
            continue
        key = term.source.casefold()
        current = required_by_source.get(key)
        if current is None or priority.get(term.origin, 99) < priority.get(current.origin, 99):
            required_by_source[key] = term

    protected: list[str] = []
    if assets.do_not_translate_enabled:
        for term in assets.do_not_translate:
            if term.enabled is False or term.source == "":
                continue
            if term.regex and _regex_enabled(context):
                protected.extend(_regex_matches(source, term.source))
            elif contains_literal(source, term.source):
                protected.append(term.source)
    do_not_translate = tuple(sorted(dict.fromkeys(protected), key = str.casefold))

    protected_keys = {value.strip().casefold() for value in do_not_translate}
    required_terms = tuple(
        (term.source, term.target)
        for term in sorted(
            required_by_source.values(),
            key = lambda value: (value.source.casefold(), value.record_id),
        )
        if term.source.strip().casefold() not in protected_keys
    )
    return MatchedConstraints(required_terms, do_not_translate)


def is_fully_do_not_translate(source: str, protected: Sequence[str]) -> bool:
    normalized = source.strip().casefold()
    return normalized != "" and any(normalized == value.strip().casefold() for value in protected)


def normalize_error_types(values: Sequence[Any] | None) -> tuple[str, ...]:
    result: list[str] = []
    for value in values or ():
        if isinstance(value, Enum):
            value = value.value
        text = str(value).strip()
        if text != "" and text not in result:
            result.append(text)
    return tuple(result)


def _snapshot_as_cache_item(snapshot: QualityItemSnapshot) -> CacheItem:
    name_source: str | list[str] | None
    if isinstance(snapshot.name_source, tuple):
        name_source = list(snapshot.name_source)
    else:
        name_source = snapshot.name_source
    return CacheItem(
        src = snapshot.source,
        dst = snapshot.current_translation,
        name_src = name_source,
        text_type = snapshot.text_type,
        status = snapshot.status,
    )


def _safe_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0
