from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from base.Base import Base
from module.Cache.CacheItem import CacheItem
from module.Config import Config
from module.Engine.Translator.TranslationTaskContext import TranslationTaskContext
from module.Response.ResponseDecoder import ResponseDecoder

from ._common import (
    BaseQualityTask,
    QualityItemSnapshot,
    QualityPromptBuilderProtocol,
    QualityRequester,
    QualityTaskFailure,
    QualityTaskResult,
    QualityValidator,
)


class PolisherTask(BaseQualityTask):
    """通过严格的索引协议批量润色 TRANSLATED 状态的条目。"""

    def __init__(
        self,
        context: TranslationTaskContext,
        *,
        requester: QualityRequester | Callable[[list[dict[str, str]]], Any] | None = None,
        requester_factory: Callable[[Config, dict[str, Any], int], QualityRequester] | None = None,
        prompt_builder: QualityPromptBuilderProtocol | None = None,
        validator: QualityValidator | None = None,
        decoder: ResponseDecoder | None = None,
    ) -> None:
        if not isinstance(context, TranslationTaskContext):
            raise TypeError("Quality tasks require TranslationTaskContext")
        requested_protocol = str(
            context.prompt.get("protocol", Config.OUTPUT_PROTOCOL_JSONLINE)
        ).strip().upper()
        protocol = (
            requested_protocol
            if requested_protocol in {
                Config.OUTPUT_PROTOCOL_STRUCTURED,
                Config.OUTPUT_PROTOCOL_JSONLINE,
            }
            else Config.OUTPUT_PROTOCOL_JSONLINE
        )
        super().__init__(
            context,
            protocol = protocol,
            requester = requester,
            requester_factory = requester_factory,
            prompt_builder = prompt_builder,
            validator = validator,
        )
        self.protocol = protocol
        self.decoder = decoder or ResponseDecoder()

    def run(
        self,
        items: Sequence[CacheItem],
        *,
        precedings: Sequence[CacheItem] = (),
    ) -> QualityTaskResult:
        indexed_items = list(enumerate(items))
        eligible: list[tuple[int, CacheItem, QualityItemSnapshot]] = []
        failures: list[QualityTaskFailure] = []

        for item_index, item in indexed_items:
            if not Base.is_item_polishable(item.get_status()):
                continue
            snapshot = QualityItemSnapshot.from_item(
                item,
                request_index = len(eligible),
                item_index = item_index,
            )
            if snapshot.current_translation.strip() == "":
                failures.append(QualityTaskFailure(item_index, "EMPTY_CURRENT_TRANSLATION"))
                continue
            eligible.append((item_index, item, snapshot))

        eligible_count = len(eligible) + len(failures)
        skipped_count = len(indexed_items) - eligible_count
        if not eligible:
            return QualityTaskResult(
                total_count = len(indexed_items),
                eligible_count = eligible_count,
                skipped_count = skipped_count,
                failed_count = len(failures),
                failures = tuple(failures),
            )

        snapshots = [entry[2] for entry in eligible]
        try:
            messages = self.prompt_builder.build_polisher_prompt(
                snapshots,
                protocol = self.protocol,
                precedings = precedings,
            )
        except Exception as exc:
            reason = f"PROMPT_BUILD_FAILED:{type(exc).__name__}"
            failures.extend(
                QualityTaskFailure(item_index, reason)
                for item_index, _, _ in eligible
            )
            return self._result(
                indexed_items,
                eligible_count,
                skipped_count,
                failures,
            )

        outcome = self._request(messages)
        if not outcome.ok:
            failures.extend(
                QualityTaskFailure(item_index, outcome.error or "REQUEST_FAILED", attempts = 1)
                for item_index, _, _ in eligible
            )
            return self._result(
                indexed_items,
                eligible_count,
                skipped_count,
                failures,
                input_tokens = outcome.input_tokens,
                output_tokens = outcome.output_tokens,
            )

        decoded = self.decoder.decode_result(
            outcome.content,
            expected_count = len(eligible),
            structured = self.protocol == Config.OUTPUT_PROTOCOL_STRUCTURED,
        )
        if len(decoded.translations) != len(eligible):
            failures.extend(
                QualityTaskFailure(item_index, "INDEXED_RESPONSE_INVALID", attempts = 1)
                for item_index, _, _ in eligible
            )
            return self._result(
                indexed_items,
                eligible_count,
                skipped_count,
                failures,
                input_tokens = outcome.input_tokens,
                output_tokens = outcome.output_tokens,
            )

        pending: list[tuple[int, CacheItem, QualityItemSnapshot, str]] = []
        for (item_index, item, snapshot), record in zip(eligible, decoded.translations):
            validation = self.validator.validate(
                item,
                record.text,
                source = snapshot.source,
                current_translation = snapshot.current_translation,
            )
            if not validation.valid:
                failures.append(QualityTaskFailure(
                    item_index,
                    "VALIDATION_FAILED:" + ",".join(validation.errors),
                    attempts = 1,
                ))
                continue
            pending.append((item_index, item, snapshot, record.text.strip()))

        updated_count = 0
        for item_index, item, snapshot, candidate in pending:
            if (
                item.get_status() != Base.TranslationStatus.TRANSLATED
                or item.get_dst() != snapshot.current_translation
            ):
                failures.append(QualityTaskFailure(item_index, "ITEM_CHANGED", attempts = 1))
                continue
            item.set_quality_result(candidate, CacheItem.QualityOrigin.POLISHER)
            updated_count += 1

        return self._result(
            indexed_items,
            eligible_count,
            skipped_count,
            failures,
            updated_count = updated_count,
            input_tokens = outcome.input_tokens,
            output_tokens = outcome.output_tokens,
        )

    @staticmethod
    def _result(
        indexed_items: Sequence[tuple[int, CacheItem]],
        eligible_count: int,
        skipped_count: int,
        failures: Sequence[QualityTaskFailure],
        *,
        updated_count: int = 0,
        input_tokens: int = 0,
        output_tokens: int = 0,
    ) -> QualityTaskResult:
        return QualityTaskResult(
            total_count = len(indexed_items),
            eligible_count = eligible_count,
            updated_count = updated_count,
            skipped_count = skipped_count,
            failed_count = len(failures),
            input_tokens = input_tokens,
            output_tokens = output_tokens,
            failures = tuple(failures),
        )
