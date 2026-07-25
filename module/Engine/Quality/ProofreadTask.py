from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from base.Base import Base
from module.Cache.CacheItem import CacheItem
from module.Config import Config
from module.Engine.Translator.TranslationTaskContext import TranslationTaskContext
from module.ResultChecker import ResultChecker

from ._common import (
    BaseQualityTask,
    QualityItemSnapshot,
    QualityPromptBuilderProtocol,
    QualityRequester,
    QualityTaskFailure,
    QualityTaskResult,
    QualityValidator,
    normalize_error_types,
)


class ProofreadTask(BaseQualityTask):
    """逐条校对可校对条目，每个任务最多尝试两次。"""

    MAX_ATTEMPTS = 2

    def __init__(
        self,
        context: TranslationTaskContext,
        *,
        requester: QualityRequester | Callable[[list[dict[str, str]]], Any] | None = None,
        requester_factory: Callable[[Config, dict[str, Any], int], QualityRequester] | None = None,
        prompt_builder: QualityPromptBuilderProtocol | None = None,
        validator: QualityValidator | None = None,
    ) -> None:
        super().__init__(
            context,
            protocol = Config.OUTPUT_PROTOCOL_SINGLE_TEXT,
            requester = requester,
            requester_factory = requester_factory,
            prompt_builder = prompt_builder,
            validator = validator,
        )

    def run(
        self,
        items: Sequence[CacheItem],
        *,
        warning_map: Mapping[int, Sequence[Any]] | None = None,
        precedings: Sequence[CacheItem] | Mapping[int, Sequence[CacheItem]] = (),
    ) -> QualityTaskResult:
        indexed_items = list(enumerate(items))
        failures: list[QualityTaskFailure] = []
        eligible_count = 0
        updated_count = 0
        input_tokens = 0
        output_tokens = 0

        for item_index, item in indexed_items:
            if not Base.is_item_proofreadable(item.get_status()):
                continue
            eligible_count += 1
            snapshot = QualityItemSnapshot.from_item(
                item,
                request_index = 0,
                item_index = item_index,
            )
            if snapshot.current_translation.strip() == "":
                failures.append(QualityTaskFailure(item_index, "EMPTY_CURRENT_TRANSLATION"))
                continue

            error_types = self._resolve_error_types(item, item_index, warning_map)
            item_precedings = self._resolve_precedings(item, item_index, precedings)
            retry_reason = ""
            success = False
            attempts = 0

            for attempt in range(1, self.MAX_ATTEMPTS + 1):
                attempts = attempt
                if (
                    item.get_status() != snapshot.status
                    or item.get_dst() != snapshot.current_translation
                ):
                    retry_reason = "ITEM_CHANGED"
                    break

                try:
                    messages = self.prompt_builder.build_proofread_prompt(
                        snapshot,
                        error_types = error_types,
                        precedings = item_precedings,
                        attempt = attempt,
                        retry_reason = retry_reason,
                    )
                except Exception as exc:
                    retry_reason = f"PROMPT_BUILD_FAILED:{type(exc).__name__}"
                    break

                outcome = self._request(messages)
                input_tokens += outcome.input_tokens
                output_tokens += outcome.output_tokens
                if not outcome.ok:
                    retry_reason = outcome.error or "REQUEST_FAILED"
                    continue

                candidate = self._decode_single_text(outcome.content)
                if candidate is None:
                    retry_reason = "SINGLE_TEXT_RESPONSE_INVALID"
                    continue

                validation = self.validator.validate(
                    item,
                    candidate,
                    source = snapshot.source,
                    current_translation = snapshot.current_translation,
                )
                if not validation.valid:
                    retry_reason = "VALIDATION_FAILED:" + ",".join(validation.errors)
                    continue

                if (
                    item.get_status() != snapshot.status
                    or item.get_dst() != snapshot.current_translation
                ):
                    retry_reason = "ITEM_CHANGED"
                    break
                item.set_quality_result(candidate, CacheItem.QualityOrigin.PROOFREADER)
                updated_count += 1
                success = True
                break

            if not success:
                failures.append(QualityTaskFailure(
                    item_index,
                    retry_reason or "PROOFREAD_FAILED",
                    attempts = attempts,
                ))

        return QualityTaskResult(
            total_count = len(indexed_items),
            eligible_count = eligible_count,
            updated_count = updated_count,
            skipped_count = len(indexed_items) - eligible_count,
            failed_count = len(failures),
            input_tokens = input_tokens,
            output_tokens = output_tokens,
            failures = tuple(failures),
        )

    def _resolve_error_types(
        self,
        item: CacheItem,
        item_index: int,
        warning_map: Mapping[int, Sequence[Any]] | None,
    ) -> tuple[str, ...]:
        values: Sequence[Any] | None = None
        if warning_map is not None:
            if id(item) in warning_map:
                values = warning_map[id(item)]
            elif item_index in warning_map:
                values = warning_map[item_index]
        normalized = normalize_error_types(values)
        if normalized:
            return normalized

        warnings = ResultChecker(self.runtime_config, [item]).check_single_item(item)
        normalized = normalize_error_types(warnings)
        return normalized or ("USER_SELECTED",)

    @staticmethod
    def _resolve_precedings(
        item: CacheItem,
        item_index: int,
        precedings: Sequence[CacheItem] | Mapping[int, Sequence[CacheItem]],
    ) -> tuple[CacheItem, ...]:
        if isinstance(precedings, Mapping):
            values = precedings.get(id(item), precedings.get(item_index, ()))
            return tuple(values)
        return tuple(precedings)

    @staticmethod
    def _decode_single_text(response: str) -> str | None:
        if not isinstance(response, str):
            return None
        candidate = response.strip()
        if candidate == "" or candidate.startswith("```"):
            return None
        try:
            structured = json.loads(candidate)
        except (TypeError, ValueError, json.JSONDecodeError):
            structured = None
        if isinstance(structured, (dict, list)):
            return None
        return candidate
