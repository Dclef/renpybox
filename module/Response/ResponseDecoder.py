from __future__ import annotations

import dataclasses
import re
from typing import Any

import json_repair as repair

from base.Base import Base


@dataclasses.dataclass(frozen = True)
class DecodedTranslation:
    """A decoded translation tied to its request-local index."""

    request_index: int
    text: str


@dataclasses.dataclass(frozen = True)
class ResponseDecodeResult:
    """Canonical result of decoding a model response."""

    translations: tuple[DecodedTranslation, ...]
    method: str
    new_glossary: tuple[dict[str, Any], ...] = ()

    @property
    def indexed_records(self) -> tuple[DecodedTranslation, ...]:
        """Migration-friendly alias for callers adopting indexed results."""
        return self.translations

    @property
    def dsts(self) -> list[str]:
        """Compatibility view for callers that still consume aligned text."""
        return [record.text for record in self.translations]

    @property
    def glossarys(self) -> list[dict[str, Any]]:
        """Compatibility view for the legacy, misspelled glossary attribute."""
        return [dict(candidate) for candidate in self.new_glossary]


class ResponseDecoder(Base):
    """Decode model output into strictly validated, indexed translations."""

    RE_MARKDOWN_FENCE = re.compile(
        r"\A\s*```(?:json|jsonline)?[ \t]*\r?\n(?P<body>.*?)(?:\r?\n)?```[ \t]*\s*\Z",
        flags = re.DOTALL | re.IGNORECASE,
    )
    TRANSLATION_KEYS = frozenset(("request_index", "text"))
    STRUCTURED_KEYS = frozenset(("translations", "new_glossary"))

    def __init__(self) -> None:
        super().__init__()

    def decode(
        self,
        response: str,
        expected_count: int = 0,
        allow_plain_text_single: bool = False,
        structured: bool = False,
    ) -> tuple[list[str], list[dict[str, Any]]]:
        """Return legacy positional views while ``decode_result`` is migrated."""
        result = self.decode_result(
            response,
            expected_count = expected_count,
            allow_plain_text_single = allow_plain_text_single,
            structured = structured,
        )
        return result.dsts, result.glossarys

    def decode_result(
        self,
        response: str,
        expected_count: int = 0,
        allow_plain_text_single: bool = False,
        structured: bool = False,
    ) -> ResponseDecodeResult:
        """Decode one explicitly selected response protocol.

        Batch protocols must contain every request index from zero through
        ``expected_count - 1`` exactly once. JSON repair may fix syntax, but
        schema and index validation always run against the repaired value.
        """
        if type(expected_count) is not int or expected_count < 1:
            self.warning(f"[DECODE] expected_count 必须是正整数: {expected_count!r}")
            return self._make_result((), "FAIL")

        if not isinstance(response, str) or response.strip() == "":
            self.warning(f"[DECODE] 响应为空或类型错误: type={type(response)}")
            return self._make_result((), "FAIL")

        payload, fenced = self._unwrap_markdown_fence(response)

        if structured:
            parsed = self._parse_structured(payload)
            if parsed is not None:
                records, new_glossary = parsed
                aligned = self._align_records(records, expected_count)
                if aligned is not None:
                    self.debug(f"[DECODE] STRUCTURED 解析成功: {len(aligned)}/{expected_count} 行")
                    return self._make_result(aligned, "STRUCTURED", new_glossary)

            self.warning("[DECODE] 结构化响应未通过 schema 或索引校验")
            return self._make_result((), "JSON_FAIL")

        records = self._parse_jsonline(payload)
        if records is not None:
            aligned = self._align_records(records, expected_count)
            if aligned is not None:
                method = "MARKDOWN_JSONLINE" if fenced else "JSONLINE"
                self.debug(f"[DECODE] {method} 解析成功: {len(aligned)}/{expected_count} 行")
                return self._make_result(aligned, method)

        if fenced or self._looks_like_json(response):
            self.warning("[DECODE] JSONLINE 响应未通过 schema 或索引校验")
            return self._make_result((), "JSON_FAIL")

        if expected_count == 1 and allow_plain_text_single is True:
            plain_text = self._parse_single_plain_text(response)
            if plain_text is not None:
                return self._make_result((DecodedTranslation(0, plain_text),), "PLAIN_TEXT")

        preview = response[:200].replace("\n", "\\n")
        self.warning(f"[DECODE] 响应不符合启用的输出协议: {preview}")
        return self._make_result((), "FAIL")

    @staticmethod
    def _make_result(
        translations: tuple[DecodedTranslation, ...],
        method: str,
        new_glossary: tuple[dict[str, Any], ...] = (),
    ) -> ResponseDecodeResult:
        return ResponseDecodeResult(
            translations = translations,
            method = method,
            new_glossary = new_glossary,
        )

    def _parse_structured(
        self,
        text: str,
    ) -> tuple[list[DecodedTranslation], tuple[dict[str, Any], ...]] | None:
        data = self._load_json_object(text)
        if data is None or "translations" not in data or not set(data).issubset(self.STRUCTURED_KEYS):
            return None

        translations = data.get("translations")
        if not isinstance(translations, list):
            return None

        records: list[DecodedTranslation] = []
        for item in translations:
            record = self._parse_translation_record(item)
            if record is None:
                return None
            records.append(record)

        raw_glossary = data.get("new_glossary", [])
        if not isinstance(raw_glossary, list) or not all(isinstance(item, dict) for item in raw_glossary):
            return None

        new_glossary = tuple(dict(item) for item in raw_glossary)
        return records, new_glossary

    def _parse_jsonline(self, text: str) -> list[DecodedTranslation] | None:
        lines = [line.strip() for line in text.splitlines() if line.strip() != ""]
        if lines == []:
            return None

        records: list[DecodedTranslation] = []
        for line in lines:
            data = self._load_json_object(line)
            record = self._parse_translation_record(data)
            if record is None:
                return None
            records.append(record)
        return records

    @classmethod
    def _parse_translation_record(cls, value: object) -> DecodedTranslation | None:
        if not isinstance(value, dict) or set(value) != cls.TRANSLATION_KEYS:
            return None

        request_index = value.get("request_index")
        text = value.get("text")
        if type(request_index) is not int or not isinstance(text, str):
            return None

        return DecodedTranslation(request_index = request_index, text = text)

    @staticmethod
    def _align_records(
        records: list[DecodedTranslation],
        expected_count: int,
    ) -> tuple[DecodedTranslation, ...] | None:
        indices = [record.request_index for record in records]
        if len(indices) != len(set(indices)):
            return None

        if set(indices) != set(range(expected_count)):
            return None

        return tuple(sorted(records, key = lambda record: record.request_index))

    @classmethod
    def _unwrap_markdown_fence(cls, text: str) -> tuple[str, bool]:
        match = cls.RE_MARKDOWN_FENCE.fullmatch(text)
        if match is None:
            return text.strip(), False
        return match.group("body").strip(), True

    @staticmethod
    def _load_json_object(text: str) -> dict[str, Any] | None:
        candidate = text.strip()
        if not ResponseDecoder._has_single_object_envelope(candidate):
            return None

        try:
            data = repair.loads(candidate)
        except Exception:
            return None
        return data if isinstance(data, dict) else None

    @staticmethod
    def _has_single_object_envelope(candidate: str) -> bool:
        """Reject surrounding data while allowing repair inside one object."""
        if not candidate.startswith("{"):
            return False

        depth = 0
        quote: str | None = None
        escaped = False
        for position, character in enumerate(candidate):
            if quote is not None:
                if escaped:
                    escaped = False
                elif character == "\\":
                    escaped = True
                elif character == quote:
                    quote = None
                continue

            if character in ('"', "'"):
                quote = character
            elif character == "{":
                depth += 1
            elif character == "}":
                depth -= 1
                if depth < 0:
                    return False
                if depth == 0 and candidate[position + 1:].strip() != "":
                    return False

        # A missing closing brace is repairable; an early close is not.
        return depth >= 0

    @staticmethod
    def _looks_like_json(text: str) -> bool:
        candidate = text.strip()
        if candidate.startswith("```") or "```json" in candidate.lower():
            return True
        if candidate.startswith("{"):
            return ":" in candidate
        if candidate.startswith("["):
            inner = candidate[1:].lstrip().lower()
            return inner.startswith(("{", "[", '"', "'", "]", "-", "true", "false", "null")) or bool(
                re.match(r"\d", inner)
            )
        return False

    @classmethod
    def _parse_single_plain_text(cls, text: str) -> str | None:
        candidate = text.strip()
        if candidate == "" or len(candidate.splitlines()) != 1:
            return None
        if cls._looks_like_json(candidate):
            return None
        return candidate
