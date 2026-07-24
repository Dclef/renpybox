from __future__ import annotations

import dataclasses
import re
from collections import Counter
from collections.abc import Iterable, Mapping
from typing import Any

from module.Cache.CacheItem import CacheItem


TRANSLATION_RETRY_METADATA_KEY = CacheItem.TRANSLATION_RETRY_KEY
TRANSLATION_RETRY_SCHEMA_VERSION = 1

_REASON_CODE = re.compile(r"^[A-Z][A-Z0-9_:-]{0,63}$")
_ALIGNMENT_ERRORS = frozenset({
    "FAIL_LINE_COUNT",
    "INDEX_ALIGNMENT",
    "STRICT_INDEX_ALIGNMENT",
})


def _non_negative_int(value: object) -> int:
    if type(value) is not int or value < 0:
        return 0
    return value


def _normalize_reason_code(value: object) -> str:
    if not isinstance(value, str):
        return ""
    code = value.strip().upper()
    return code if _REASON_CODE.fullmatch(code) is not None else ""


def _normalize_line_indices(value: object) -> tuple[int, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(sorted({index for index in value if type(index) is int and index >= 0}))


def read_translation_retry_reasons(item: CacheItem) -> tuple[dict[str, Any], ...]:
    """Return normalized, JSON-safe retry reasons from one cache item."""
    metadata = item.get_metadata()
    payload = metadata.get(TRANSLATION_RETRY_METADATA_KEY)
    if not isinstance(payload, Mapping):
        return ()

    raw_reasons = payload.get("reasons", ())
    if isinstance(raw_reasons, (str, Mapping)):
        raw_reasons = (raw_reasons,)
    if not isinstance(raw_reasons, (list, tuple)):
        return ()

    reasons: list[dict[str, Any]] = []
    for raw_reason in raw_reasons:
        if isinstance(raw_reason, str):
            code = _normalize_reason_code(raw_reason)
            line_indices: tuple[int, ...] = ()
        elif isinstance(raw_reason, Mapping):
            code = _normalize_reason_code(
                raw_reason.get("code", raw_reason.get("error", raw_reason.get("type")))
            )
            line_indices = _normalize_line_indices(raw_reason.get("line_indices", ()))
        else:
            continue

        if code == "":
            continue
        reasons.append({
            "code": code,
            "line_indices": list(line_indices),
        })

    return tuple(reasons)


@dataclasses.dataclass(frozen = True)
class TranslationQualityItemReference:
    item_index: int
    reference: str
    file_path: str
    row: int
    source_preview: str
    status: str
    retry_count: int
    error_types: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "item_index": self.item_index,
            "reference": self.reference,
            "file_path": self.file_path,
            "row": self.row,
            "source_preview": self.source_preview,
            "status": self.status,
            "retry_count": self.retry_count,
            "error_types": list(self.error_types),
        }


@dataclasses.dataclass(frozen = True)
class TranslationQualityReport:
    """Serializable translation quality summary built without mutating cache state."""

    failed_count: int
    fallback_count: int
    line_mismatch_count: int
    error_type_counts: dict[str, int]
    item_references: tuple[TranslationQualityItemReference, ...]
    schema_version: int = 1

    @property
    def failed_line_count(self) -> int:
        return self.failed_count

    @property
    def fallback_line_count(self) -> int:
        return self.fallback_count

    @property
    def line_count_mismatch_count(self) -> int:
        return self.line_mismatch_count

    @property
    def item_refs(self) -> tuple[TranslationQualityItemReference, ...]:
        return self.item_references

    @classmethod
    def from_items(
        cls,
        items: Iterable[CacheItem],
        progress: Mapping[str, object] | None = None,
    ) -> TranslationQualityReport:
        progress = progress if isinstance(progress, Mapping) else {}
        error_counts: Counter[str] = Counter()
        item_references: list[TranslationQualityItemReference] = []
        derived_failed_count = 0
        derived_line_mismatch_count = 0

        for item_index, item in enumerate(items):
            if not isinstance(item, CacheItem):
                continue

            reasons = read_translation_retry_reasons(item)
            if reasons == ():
                continue

            codes = tuple(sorted({reason["code"] for reason in reasons}))
            failed_lines: set[int] = set()
            alignment_lines: set[int] = set()
            has_unscoped_failure = False
            has_unscoped_alignment = False

            for reason in reasons:
                code = reason["code"]
                line_indices = tuple(reason["line_indices"])
                error_counts[code] += max(1, len(line_indices))
                if line_indices:
                    failed_lines.update(line_indices)
                else:
                    has_unscoped_failure = True
                if code in _ALIGNMENT_ERRORS:
                    if line_indices:
                        alignment_lines.update(line_indices)
                    else:
                        has_unscoped_alignment = True

            derived_failed_count += len(failed_lines) or int(has_unscoped_failure)
            derived_line_mismatch_count += len(alignment_lines) or int(has_unscoped_alignment)

            file_path = item.get_file_path() or ""
            row = item.get_row()
            reference = f"{file_path}:{row}" if file_path != "" else f"item:{item_index}"
            source_preview = (item.get_src() or "").replace("\r", " ").replace("\n", " ").strip()
            if len(source_preview) > 160:
                source_preview = source_preview[:157] + "..."

            item_references.append(TranslationQualityItemReference(
                item_index = item_index,
                reference = reference,
                file_path = file_path,
                row = row,
                source_preview = source_preview,
                status = item.get_status().value,
                retry_count = _non_negative_int(item.get_retry_count()),
                error_types = codes,
            ))

        progress_error_counts = progress.get("error_type_counts", {})
        if isinstance(progress_error_counts, Mapping):
            for raw_code, raw_count in progress_error_counts.items():
                code = _normalize_reason_code(raw_code)
                count = _non_negative_int(raw_count)
                if code != "":
                    error_counts[code] = max(error_counts[code], count)

        failed_count = max(
            derived_failed_count,
            _non_negative_int(progress.get("failed_line_count", 0)),
        )
        line_mismatch_count = max(
            derived_line_mismatch_count,
            _non_negative_int(progress.get("line_count_mismatch_count", 0)),
        )

        return cls(
            failed_count = failed_count,
            fallback_count = _non_negative_int(progress.get("fallback_line_count", 0)),
            line_mismatch_count = line_mismatch_count,
            error_type_counts = dict(sorted(error_counts.items())),
            item_references = tuple(item_references),
        )

    build = from_items

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "failed_count": self.failed_count,
            "fallback_count": self.fallback_count,
            "line_mismatch_count": self.line_mismatch_count,
            "error_type_counts": dict(self.error_type_counts),
            "item_references": [reference.as_dict() for reference in self.item_references],
        }


def build_translation_quality_report(
    items: Iterable[CacheItem],
    progress: Mapping[str, object] | None = None,
) -> TranslationQualityReport:
    return TranslationQualityReport.from_items(items, progress)


__all__ = (
    "TRANSLATION_RETRY_METADATA_KEY",
    "TRANSLATION_RETRY_SCHEMA_VERSION",
    "TranslationQualityItemReference",
    "TranslationQualityReport",
    "build_translation_quality_report",
    "read_translation_retry_reasons",
)
