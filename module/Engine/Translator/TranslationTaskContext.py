from __future__ import annotations

import dataclasses
import hashlib
import json
import math
from collections.abc import Iterator, Mapping
from copy import deepcopy
from datetime import datetime, timezone
from enum import Enum
from typing import Any


SNAPSHOT_SCHEMA_VERSION = 1
PROJECT_ASSETS_SCHEMA_VERSION = 1

_CREDENTIAL_KEYS = {
    "access_key",
    "access_token",
    "api_key",
    "apikey",
    "authorization",
    "auth_token",
    "cookie",
    "cookies",
    "credential",
    "credentials",
    "key",
    "password",
    "proxy_authorization",
    "secret",
    "secret_key",
    "token",
}
_CREDENTIAL_SUFFIXES = (
    "_api_key",
    "_password",
    "_secret",
    "_token",
)
_TERM_ORIGINS = {"LOCAL", "ANALYSIS", "CHARACTER"}

_CHARACTER_TEXT_FIELDS = (
    "name",
    "name_translation",
    "identity",
    "personality",
    "speech_style",
    "relationship_notes",
    "prompt_notes",
)
_CHARACTER_LIST_FIELDS = (
    "aliases",
    "match_keywords",
    "sample_lines",
)


class TranslationSnapshotError(ValueError):
    """Raised when a persisted translation snapshot is invalid."""


class FrozenDict(Mapping[str, Any]):
    """Small recursively-freezable mapping used by task contexts."""

    __slots__ = ("_items",)

    def __init__(self, values: Mapping[str, Any] | None = None) -> None:
        source = values if isinstance(values, Mapping) else {}
        object.__setattr__(
            self,
            "_items",
            tuple((str(key), _freeze(value)) for key, value in source.items()),
        )

    def __getitem__(self, key: str) -> Any:
        for current_key, value in self._items:
            if current_key == key:
                return value
        raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        return (key for key, _ in self._items)

    def __len__(self) -> int:
        return len(self._items)

    def __repr__(self) -> str:
        return f"FrozenDict({_thaw(self)!r})"

    def __hash__(self) -> int:
        return hash(self._items)

    def __setattr__(self, name: str, value: Any) -> None:
        raise TypeError("FrozenDict is immutable")

    def to_dict(self) -> dict[str, Any]:
        return _thaw(self)


def _freeze(value: Any) -> Any:
    if isinstance(value, FrozenDict):
        return value
    if dataclasses.is_dataclass(value):
        return _freeze(dataclasses.asdict(value))
    if isinstance(value, Mapping):
        return FrozenDict(value)
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        normalized = [_freeze(item) for item in value]
        return tuple(sorted(normalized, key = lambda item: _canonical_json(_thaw(item))))
    if isinstance(value, Enum):
        return _freeze(value.value)
    if isinstance(value, float) and math.isfinite(value) is False:
        return None
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    return str(value)


def _thaw(value: Any) -> Any:
    if isinstance(value, FrozenDict):
        return {key: _thaw(item) for key, item in value._items}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    if dataclasses.is_dataclass(value):
        return _thaw(dataclasses.asdict(value))
    return deepcopy(value)


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii = False,
        allow_nan = False,
        separators = (",", ":"),
        sort_keys = True,
    )


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, Enum):
        value = value.value
    return str(value).strip()


def _normalize_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized in {"", "0", "false", "no", "off"}:
            return False
        if normalized in {"1", "true", "yes", "on"}:
            return True
    return bool(value)


def _normalize_int(value: Any, default: int = 0, minimum: int = 0) -> int:
    try:
        return max(minimum, int(value))
    except (TypeError, ValueError):
        return default


def _normalize_text_list(value: Any) -> tuple[str, ...]:
    values = value if isinstance(value, (list, tuple, set, frozenset)) else [value]
    result: list[str] = []
    seen: set[str] = set()
    for item in values:
        text = _normalize_text(item)
        key = text.casefold()
        if text == "" or key in seen:
            continue
        seen.add(key)
        result.append(text)
    return tuple(result)


def _normalize_data(value: Any) -> Any:
    """Normalize arbitrary project data into deterministic JSON-compatible data."""
    if isinstance(value, Enum):
        return _normalize_data(value.value)
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        entries = sorted(value.items(), key = lambda item: str(item[0]).casefold())
        for raw_key, raw_value in entries:
            key = str(raw_key)
            normalized = _normalize_data(raw_value)
            if _has_content(normalized):
                result[key] = normalized
        return result
    if isinstance(value, (list, tuple, set, frozenset)):
        result = [_normalize_data(item) for item in value]
        return [item for item in result if _has_content(item)]
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, float) and math.isfinite(value) is False:
        return None
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value).strip()


def _has_content(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() != ""
    if isinstance(value, Mapping):
        return any(_has_content(item) for item in value.values())
    if isinstance(value, (list, tuple, set, frozenset)):
        return any(_has_content(item) for item in value)
    if isinstance(value, bool):
        return value
    return True


_URL_CREDENTIALS_KEY = "__url_credentials__"


def is_credential_key(key: Any) -> bool:
    normalized = str(key).strip().casefold().replace("-", "_")
    return (
        normalized in _CREDENTIAL_KEYS
        or normalized.endswith(_CREDENTIAL_SUFFIXES)
        or normalized.endswith("_credential")
        or normalized.endswith("_credentials")
        or normalized.endswith("_cookie")
        or normalized.endswith("_key")
    )


def _is_url_key(key: Any) -> bool:
    normalized = str(key).strip().casefold().replace("-", "_")
    return normalized == "url" or normalized.endswith("_url")


def _split_url_credentials(value: str) -> tuple[str, str]:
    from urllib.parse import urlsplit, urlunsplit

    try:
        parts = urlsplit(value)
    except ValueError:
        return value, ""
    if parts.scheme == "" or "@" not in parts.netloc:
        return value, ""
    userinfo, host = parts.netloc.rsplit("@", 1)
    if userinfo == "" or host == "":
        return value, ""
    return urlunsplit((parts.scheme, host, parts.path, parts.query, parts.fragment)), userinfo


def split_provider_config(value: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    """Split provider semantics from runtime-only credentials."""
    if not isinstance(value, Mapping):
        return {}, {}
    value = _thaw(value)

    semantic: dict[str, Any] = {}
    credentials: dict[str, Any] = {}
    url_credentials: dict[str, str] = {}
    for raw_key, item in value.items():
        key = str(raw_key)
        if is_credential_key(key):
            credentials[key] = deepcopy(item)
            continue
        if isinstance(item, Mapping):
            nested_semantic, nested_credentials = split_provider_config(item)
            semantic[key] = nested_semantic
            if nested_credentials:
                credentials[key] = nested_credentials
            continue
        if isinstance(item, str) and _is_url_key(key):
            clean_url, userinfo = _split_url_credentials(item)
            semantic[key] = clean_url
            if userinfo:
                url_credentials[key] = userinfo
            continue
        semantic[key] = deepcopy(item)

    if url_credentials:
        credentials[_URL_CREDENTIALS_KEY] = url_credentials
    return semantic, credentials


def _merge_mapping(base: Any, overlay: Any) -> dict[str, Any]:
    result = deepcopy(dict(base)) if isinstance(base, Mapping) else {}
    if not isinstance(overlay, Mapping):
        return result
    for raw_key, value in overlay.items():
        key = str(raw_key)
        if key == _URL_CREDENTIALS_KEY:
            continue
        if isinstance(value, Mapping) and isinstance(result.get(key), Mapping):
            result[key] = _merge_mapping(result[key], value)
        else:
            result[key] = deepcopy(value)

    url_credentials = overlay.get(_URL_CREDENTIALS_KEY)
    if isinstance(url_credentials, Mapping):
        from urllib.parse import urlsplit, urlunsplit

        for raw_key, raw_userinfo in url_credentials.items():
            key = str(raw_key)
            clean_url = result.get(key)
            userinfo = str(raw_userinfo or "")
            if not isinstance(clean_url, str) or userinfo == "":
                continue
            try:
                parts = urlsplit(clean_url)
            except ValueError:
                continue
            if parts.scheme == "" or parts.netloc == "":
                continue
            result[key] = urlunsplit((
                parts.scheme,
                f"{userinfo}@{parts.netloc.rsplit('@', 1)[-1]}",
                parts.path,
                parts.query,
                parts.fragment,
            ))
    return result


def merge_provider_credentials(
    semantic_provider: Any,
    current_provider: Any,
) -> dict[str, Any]:
    """Attach only current credentials to persisted provider semantics."""
    semantic, _ = split_provider_config(semantic_provider)
    _, credentials = split_provider_config(current_provider)
    return _merge_mapping(semantic, credentials)


def strip_credentials(value: Any) -> Any:
    """Return a deep JSON-compatible copy without credential-bearing fields."""
    value = _thaw(_freeze(value))
    if isinstance(value, dict):
        return {
            str(key): strip_credentials(item)
            for key, item in value.items()
            if is_credential_key(key) is False
        }
    if isinstance(value, list):
        return [strip_credentials(item) for item in value]
    return value


def sanitize_request_policy(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    policy = _thaw(value)
    provider = policy.get("provider")
    if isinstance(provider, Mapping):
        policy["provider"] = split_provider_config(provider)[0]
    return strip_credentials(policy)


def sanitize_translation_snapshot(value: Any) -> dict[str, Any]:
    """Remove runtime credentials without altering semantic prompt/asset data."""
    if not isinstance(value, Mapping):
        return {}
    snapshot = _thaw(_freeze(value))
    snapshot.pop("runtime_provider", None)
    for key in tuple(snapshot):
        if is_credential_key(key):
            snapshot.pop(key, None)
        elif key == "request_policy":
            snapshot[key] = sanitize_request_policy(snapshot[key])
        elif key not in {"prompt", "assets", "processing", "checking"}:
            snapshot[key] = strip_credentials(snapshot[key])
    return snapshot


def _object_to_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return deepcopy(dict(value))
    if dataclasses.is_dataclass(value):
        return {
            field.name: deepcopy(getattr(value, field.name))
            for field in dataclasses.fields(value)
            if field.init
        }
    try:
        return {
            str(key): deepcopy(item)
            for key, item in vars(value).items()
            if str(key).startswith("_") is False and callable(item) is False
        }
    except TypeError:
        return {}


@dataclasses.dataclass(frozen = True)
class TermAsset:
    record_id: str
    origin: str
    source: str
    target: str = ""
    enabled: bool = True
    regex: bool = False
    note: str = ""

    @staticmethod
    def build_record_id(origin: str, source: str, regex: bool = False) -> str:
        identity = _canonical_json({
            "origin": _normalize_text(origin).upper() or "LOCAL",
            "regex": bool(regex),
            "source": _normalize_text(source).casefold(),
        })
        digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
        return f"term_{digest}"

    @classmethod
    def from_value(
        cls,
        value: Any,
        *,
        default_origin: str = "LOCAL",
        require_target: bool = False,
    ) -> TermAsset | None:
        if isinstance(value, cls):
            data = value.to_dict()
        elif isinstance(value, Mapping):
            data = dict(value)
        elif isinstance(value, (list, tuple)) and len(value) >= 1:
            data = {
                "source": value[0],
                "target": value[1] if len(value) >= 2 else "",
            }
        else:
            data = {"source": value}

        source = _normalize_text(
            data.get("source", data.get("src", data.get("original", "")))
        )
        target = _normalize_text(
            data.get("target", data.get("dst", data.get("translation", "")))
        )
        if source == "" or (require_target and target == ""):
            return None

        origin = _normalize_text(data.get("origin", default_origin)).upper()
        if origin not in _TERM_ORIGINS:
            origin = _normalize_text(default_origin).upper()
        if origin not in _TERM_ORIGINS:
            origin = "LOCAL"

        regex = _normalize_bool(data.get("regex", False))
        record_id = _normalize_text(data.get("record_id", data.get("id", "")))
        if record_id == "":
            record_id = cls.build_record_id(origin, source, regex)

        return cls(
            record_id = record_id,
            origin = origin,
            source = source,
            target = target,
            enabled = _normalize_bool(data.get("enabled", True), default = True),
            regex = regex,
            note = _normalize_text(data.get("note", data.get("info", ""))),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "origin": self.origin,
            "source": self.source,
            "target": self.target,
            "enabled": self.enabled,
            "regex": self.regex,
            "note": self.note,
        }


def _normalize_terms(
    values: Any,
    *,
    default_origin: str,
    require_target: bool,
) -> tuple[TermAsset, ...]:
    if not isinstance(values, (list, tuple)):
        return ()

    candidates: list[TermAsset] = []
    for value in values:
        term = TermAsset.from_value(
            value,
            default_origin = default_origin,
            require_target = require_target,
        )
        if term is None:
            continue
        candidates.append(term)

    origin_priority = {"LOCAL": 0, "CHARACTER": 1, "ANALYSIS": 2}
    candidates.sort(key = lambda item: (
        item.source.casefold(),
        origin_priority.get(item.origin, 99),
        item.record_id,
        item.target.casefold(),
        item.note.casefold(),
    ))
    result: list[TermAsset] = []
    seen_ids: set[str] = set()
    for term in candidates:
        if term.record_id in seen_ids:
            continue
        seen_ids.add(term.record_id)
        result.append(term)
    return tuple(result)


def _build_character_id(name: str) -> str:
    digest = hashlib.sha256(_normalize_text(name).casefold().encode("utf-8")).hexdigest()[:16]
    return f"character_{digest}"


def _normalize_character_card(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    name = _normalize_text(value.get("name", ""))
    if name == "":
        return None

    card: dict[str, Any] = {
        "id": _normalize_text(value.get("id", value.get("record_id", ""))) or _build_character_id(name),
        "name": name,
    }
    for field in _CHARACTER_TEXT_FIELDS[1:]:
        card[field] = _normalize_text(value.get(field, ""))
    for field in _CHARACTER_LIST_FIELDS:
        card[field] = list(_normalize_text_list(value.get(field, [])))
    if name.casefold() not in {item.casefold() for item in card["match_keywords"]}:
        card["match_keywords"].insert(0, name)
    card["enabled"] = _normalize_bool(value.get("enabled", True), default = True)
    card["is_primary"] = _normalize_bool(value.get("is_primary", False))
    return card


def _normalize_character_cards(values: Any) -> tuple[FrozenDict, ...]:
    if not isinstance(values, (list, tuple)):
        return ()
    candidates: list[dict[str, Any]] = []
    for value in values:
        card = _normalize_character_card(value)
        if card is None:
            continue
        candidates.append(card)
    candidates.sort(key = lambda card: (
        card["name"].casefold(),
        card["id"],
        _canonical_json(card),
    ))
    cards: list[dict[str, Any]] = []
    seen: set[str] = set()
    for card in candidates:
        if card["id"] in seen:
            continue
        seen.add(card["id"])
        cards.append(card)
    return tuple(FrozenDict(card) for card in cards)


def _section(data: Mapping[str, Any], key: str, value_key: str) -> tuple[bool, Any]:
    raw = data.get(key, {})
    if isinstance(raw, Mapping) and ("enabled" in raw or value_key in raw):
        return _normalize_bool(raw.get("enabled", False)), raw.get(value_key, {} if value_key == "data" else [])
    return _normalize_bool(data.get(f"{key}_enabled", False)), raw


@dataclasses.dataclass(frozen = True)
class ProjectAssets:
    schema_version: int = PROJECT_ASSETS_SCHEMA_VERSION
    revision: int = 0
    updated_at: str = ""
    worldbook_enabled: bool = False
    worldbook: FrozenDict = dataclasses.field(default_factory = FrozenDict)
    character_cards_enabled: bool = False
    character_cards: tuple[FrozenDict, ...] = ()
    glossary_enabled: bool = False
    glossary: tuple[TermAsset, ...] = ()
    do_not_translate_enabled: bool = False
    do_not_translate: tuple[TermAsset, ...] = ()

    @classmethod
    def from_dict(cls, value: Any) -> ProjectAssets:
        if isinstance(value, cls):
            return value
        data = dict(value) if isinstance(value, Mapping) else {}
        schema_version = _normalize_int(
            data.get("schema_version", PROJECT_ASSETS_SCHEMA_VERSION),
            default = 0,
        )
        if schema_version != PROJECT_ASSETS_SCHEMA_VERSION:
            raise TranslationSnapshotError(
                f"Unsupported project assets schema: {schema_version}"
            )

        worldbook_enabled, worldbook_data = _section(data, "worldbook", "data")
        characters_enabled, character_items = _section(data, "character_cards", "items")
        glossary_enabled, glossary_items = _section(data, "glossary", "items")
        excluded_enabled, excluded_items = _section(data, "do_not_translate", "items")

        normalized_worldbook = _normalize_data(worldbook_data)
        if not isinstance(normalized_worldbook, dict):
            normalized_worldbook = {}

        return cls(
            schema_version = PROJECT_ASSETS_SCHEMA_VERSION,
            revision = _normalize_int(data.get("revision", 0)),
            updated_at = _normalize_text(data.get("updated_at", "")),
            worldbook_enabled = worldbook_enabled,
            worldbook = FrozenDict(normalized_worldbook),
            character_cards_enabled = characters_enabled,
            character_cards = _normalize_character_cards(character_items),
            glossary_enabled = glossary_enabled,
            glossary = _normalize_terms(
                glossary_items,
                default_origin = "LOCAL",
                require_target = True,
            ),
            do_not_translate_enabled = excluded_enabled,
            do_not_translate = _normalize_terms(
                excluded_items,
                default_origin = "LOCAL",
                require_target = False,
            ),
        )

    @classmethod
    def from_config(cls, config: Any) -> ProjectAssets:
        """Build the initial project asset set from legacy global settings."""
        data = _object_to_dict(config)
        return cls.from_dict({
            "worldbook": {
                "enabled": data.get("renpy_workbench_worldbook_enable", False),
                "data": data.get("renpy_workbench_worldbook_data", {}),
            },
            "character_cards": {
                "enabled": data.get("renpy_workbench_character_cards_enable", False),
                "items": data.get("renpy_workbench_character_cards", []),
            },
            "glossary": {
                "enabled": data.get("glossary_enable", False),
                "items": data.get("glossary_data", []),
            },
            "do_not_translate": {
                "enabled": data.get("do_not_translate_enable", False),
                "items": data.get("do_not_translate_data", []),
            },
        })

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": PROJECT_ASSETS_SCHEMA_VERSION,
            "revision": self.revision,
            "updated_at": self.updated_at,
            "worldbook": {
                "enabled": self.worldbook_enabled,
                "data": self.worldbook.to_dict(),
            },
            "character_cards": {
                "enabled": self.character_cards_enabled,
                "items": [card.to_dict() for card in self.character_cards],
            },
            "glossary": {
                "enabled": self.glossary_enabled,
                "items": [item.to_dict() for item in self.glossary],
            },
            "do_not_translate": {
                "enabled": self.do_not_translate_enabled,
                "items": [item.to_dict() for item in self.do_not_translate],
            },
        }

    def character_terms(self) -> tuple[TermAsset, ...]:
        if self.character_cards_enabled is False:
            return ()
        result: list[TermAsset] = []
        for card in self.character_cards:
            if not card.get("enabled", True):
                continue
            source = _normalize_text(card.get("name", ""))
            target = _normalize_text(card.get("name_translation", ""))
            if source == "" or target == "":
                continue
            card_id = _normalize_text(card.get("id", "")) or _build_character_id(source)
            digest = hashlib.sha256(card_id.encode("utf-8")).hexdigest()[:16]
            result.append(TermAsset(
                record_id = f"term_character_{digest}",
                origin = "CHARACTER",
                source = source,
                target = target,
                enabled = True,
            ))
        return tuple(result)


_PROCESSING_FIELDS = (
    "asset_prompt_max_items",
    "asset_prompt_token_budget",
    "asset_regex_enable",
    "auto_process_prefix_suffix_preserved_text",
    "auto_glossary_enable",
    "clean_ruby",
    "deduplication_in_bilingual",
    "deduplication_in_trans",
    "enable_preceding_on_local",
    "honorific_placeholder_bridge_enable",
    "honorific_placeholder_titles",
    "mixed_language_cleanup_enable",
    "mixed_language_replacements",
    "mixed_language_sentence_overrides",
    "mtool_optimizer_enable",
    "post_translation_replacement_data",
    "post_translation_replacement_enable",
    "pre_translation_replacement_data",
    "pre_translation_replacement_enable",
    "preceding_lines_threshold",
    "single_line_translation_enable",
    "text_preserve_data",
    "text_preserve_enable",
    "token_estimation_output_ratio",
    "token_threshold",
    "traditional_chinese_enable",
    "write_translated_name_fields_to_file",
)
_CHECKING_FIELDS = (
    "result_checker_retry_count_threshold",
    "sakura_jsonline_retry_enable",
)
_REQUEST_POLICY_FIELDS = (
    "max_round",
    "max_workers",
    "request_timeout",
    "rpm_threshold",
)


def _pick(data: Mapping[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    return {key: deepcopy(data[key]) for key in keys if key in data}


def _resolve_provider(data: Mapping[str, Any]) -> dict[str, Any]:
    platforms = data.get("platforms", [])
    if not isinstance(platforms, (list, tuple)):
        return {}
    active = data.get("activate_platform", 0)
    for platform in platforms:
        if isinstance(platform, Mapping) and platform.get("id", 0) == active:
            return deepcopy(dict(platform))
    return {}


def _default_prompt(data: Mapping[str, Any]) -> dict[str, Any]:
    mode = _normalize_text(data.get("translation_prompt_mode", "COMMON")).upper() or "COMMON"
    style_id = _normalize_text(data.get("translation_style_id", "NONE")).upper() or "NONE"
    protocol = _normalize_text(data.get("translation_output_protocol", "")).upper()
    if protocol == "":
        protocol = "STRUCTURED" if _normalize_bool(data.get("structured_output_enable", True)) else "JSONLINE"

    resolved_base = _normalize_text(data.get("translation_resolved_base", ""))
    if mode == "CUSTOM" and resolved_base == "":
        custom_prompts = data.get("translation_custom_prompts", {})
        if isinstance(custom_prompts, Mapping):
            target = _normalize_text(data.get("target_language", ""))
            for key in (target, target.upper(), target.lower()):
                if key in custom_prompts:
                    resolved_base = _normalize_text(custom_prompts[key])
                    break
            if resolved_base == "":
                values = [
                    _normalize_text(value)
                    for _, value in sorted(custom_prompts.items(), key = lambda item: str(item[0]))
                    if _normalize_text(value) != ""
                ]
                resolved_base = values[0] if values else ""
        if resolved_base == "":
            resolved_base = _normalize_text(
                data.get("translation_custom_prompt", data.get("custom_prompt_zh_data", ""))
            )

    return {
        "mode": mode,
        "resolved_base": resolved_base,
        "style_id": style_id,
        "resolved_style": _normalize_text(
            data.get("translation_resolved_style", data.get("translation_custom_style", ""))
        ),
        "protocol": protocol,
        "protocol_version": _normalize_int(data.get("translation_protocol_version", 1), default = 1, minimum = 1),
    }


@dataclasses.dataclass(frozen = True)
class TranslationTaskContext:
    source_language: str
    target_language: str
    prompt: FrozenDict
    assets: ProjectAssets
    processing: FrozenDict
    checking: FrozenDict
    request_policy: FrozenDict
    runtime_provider: FrozenDict = dataclasses.field(default_factory = FrozenDict, repr = False, compare = False)
    schema_version: int = SNAPSHOT_SCHEMA_VERSION
    created_at: str = ""
    legacy_bootstrap: bool = False
    snapshot_id: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != SNAPSHOT_SCHEMA_VERSION:
            raise TranslationSnapshotError(
                f"Unsupported translation snapshot schema: {self.schema_version}"
            )

        object.__setattr__(self, "source_language", _normalize_text(self.source_language))
        object.__setattr__(self, "target_language", _normalize_text(self.target_language))
        object.__setattr__(self, "prompt", FrozenDict(_thaw(self.prompt)))
        object.__setattr__(self, "assets", ProjectAssets.from_dict(self.assets))
        object.__setattr__(self, "processing", FrozenDict(_thaw(self.processing)))
        object.__setattr__(self, "checking", FrozenDict(_thaw(self.checking)))
        object.__setattr__(self, "request_policy", FrozenDict(sanitize_request_policy(self.request_policy)))
        object.__setattr__(self, "runtime_provider", FrozenDict(_thaw(self.runtime_provider)))

        created_at = _normalize_text(self.created_at)
        if created_at == "":
            created_at = datetime.now(timezone.utc).isoformat()
        object.__setattr__(self, "created_at", created_at)

        expected_id = self._calculate_snapshot_id()
        supplied_id = _normalize_text(self.snapshot_id)
        if supplied_id != "" and supplied_id != expected_id:
            raise TranslationSnapshotError("Translation snapshot content hash does not match snapshot_id")
        object.__setattr__(self, "snapshot_id", expected_id)

    @classmethod
    def from_config(
        cls,
        config: Any,
        project_assets: ProjectAssets | Mapping[str, Any] | None = None,
        *,
        prompt: Mapping[str, Any] | None = None,
        processing: Mapping[str, Any] | None = None,
        checking: Mapping[str, Any] | None = None,
        request_policy: Mapping[str, Any] | None = None,
        overrides: Mapping[str, Any] | None = None,
        created_at: str = "",
        legacy_bootstrap: bool = False,
    ) -> TranslationTaskContext:
        data = _object_to_dict(config)
        if isinstance(overrides, Mapping):
            data.update(deepcopy(dict(overrides)))

        resolved_assets = (
            ProjectAssets.from_config(data)
            if project_assets is None
            else ProjectAssets.from_dict(project_assets)
        )
        provider = _resolve_provider(data)

        resolved_prompt = dict(prompt) if isinstance(prompt, Mapping) else _default_prompt(data)
        resolved_processing = (
            dict(processing)
            if isinstance(processing, Mapping)
            else dict(data.get("processing", {}))
            if isinstance(data.get("processing"), Mapping)
            else _pick(data, _PROCESSING_FIELDS)
        )
        resolved_checking = (
            dict(checking)
            if isinstance(checking, Mapping)
            else dict(data.get("checking", {}))
            if isinstance(data.get("checking"), Mapping)
            else _pick(data, _CHECKING_FIELDS)
        )
        resolved_request_policy = (
            dict(request_policy)
            if isinstance(request_policy, Mapping)
            else dict(data.get("request_policy", {}))
            if isinstance(data.get("request_policy"), Mapping)
            else _pick(data, _REQUEST_POLICY_FIELDS)
        )
        if provider:
            resolved_request_policy.setdefault("provider", split_provider_config(provider)[0])
        resolved_request_policy = sanitize_request_policy(resolved_request_policy)

        return cls(
            source_language = _normalize_text(data.get("source_language", "")),
            target_language = _normalize_text(data.get("target_language", "")),
            prompt = FrozenDict(deepcopy(resolved_prompt)),
            assets = resolved_assets,
            processing = FrozenDict(deepcopy(resolved_processing)),
            checking = FrozenDict(deepcopy(resolved_checking)),
            request_policy = FrozenDict(resolved_request_policy),
            runtime_provider = FrozenDict(deepcopy(provider)),
            created_at = created_at,
            legacy_bootstrap = bool(legacy_bootstrap),
        )

    @classmethod
    def from_snapshot(
        cls,
        snapshot: Mapping[str, Any] | str,
        *,
        runtime_provider: Mapping[str, Any] | None = None,
    ) -> TranslationTaskContext:
        if isinstance(snapshot, str):
            try:
                snapshot = json.loads(snapshot)
            except json.JSONDecodeError as exc:
                raise TranslationSnapshotError("Translation snapshot is not valid JSON") from exc
        if not isinstance(snapshot, Mapping):
            raise TranslationSnapshotError("Translation snapshot must be an object")

        data = sanitize_translation_snapshot(snapshot)
        schema_version = _normalize_int(data.get("schema_version", 0), default = 0)
        if schema_version != SNAPSHOT_SCHEMA_VERSION:
            raise TranslationSnapshotError(
                f"Unsupported translation snapshot schema: {schema_version}"
            )

        for section in ("prompt", "assets", "processing", "checking", "request_policy"):
            if not isinstance(data.get(section), Mapping):
                raise TranslationSnapshotError(
                    f"Translation snapshot section '{section}' must be an object"
                )

        assets = ProjectAssets.from_dict(data["assets"])
        declared_revision = _normalize_int(data.get("project_asset_revision", 0))
        if declared_revision != assets.revision:
            raise TranslationSnapshotError(
                "Translation snapshot project_asset_revision does not match assets.revision"
            )

        return cls(
            schema_version = schema_version,
            snapshot_id = _normalize_text(data.get("snapshot_id", "")),
            created_at = _normalize_text(data.get("created_at", "")),
            source_language = data.get("source_language", ""),
            target_language = data.get("target_language", ""),
            prompt = FrozenDict(data.get("prompt", {})),
            assets = assets,
            processing = FrozenDict(data.get("processing", {})),
            checking = FrozenDict(data.get("checking", {})),
            request_policy = FrozenDict(data.get("request_policy", {})),
            runtime_provider = FrozenDict(deepcopy(runtime_provider or {})),
            legacy_bootstrap = _normalize_bool(data.get("legacy_bootstrap", False)),
        )

    @property
    def project_asset_revision(self) -> int:
        return self.assets.revision

    def _content_payload(self) -> dict[str, Any]:
        return {
            "schema_version": SNAPSHOT_SCHEMA_VERSION,
            "project_asset_revision": self.project_asset_revision,
            "source_language": self.source_language,
            "target_language": self.target_language,
            "prompt": self.prompt.to_dict(),
            "assets": self.assets.to_dict(),
            "processing": self.processing.to_dict(),
            "checking": self.checking.to_dict(),
            "request_policy": self.request_policy.to_dict(),
            "legacy_bootstrap": self.legacy_bootstrap,
        }

    def _calculate_snapshot_id(self) -> str:
        digest = hashlib.sha256(_canonical_json(self._content_payload()).encode("utf-8")).hexdigest()
        return f"sha256:{digest}"

    def to_snapshot(self) -> dict[str, Any]:
        snapshot = self._content_payload()
        snapshot["snapshot_id"] = self.snapshot_id
        snapshot["created_at"] = self.created_at
        return sanitize_translation_snapshot(snapshot)

    def to_json(self) -> str:
        return _canonical_json(self.to_snapshot())

    def to_dict(self) -> dict[str, Any]:
        return self.to_snapshot()

    def to_runtime_config(self, current_config: Any | None = None) -> Any:
        """
        Project this immutable context into an isolated legacy ``Config``.

        The projection exists only while legacy translator components still read
        Config attributes. Callers may mutate it for adaptive runtime behavior,
        but must never save it. Snapshot-owned values always override values from
        ``current_config``; current provider credentials are used only when the
        context has no runtime provider attached.
        """
        from base.BaseLanguage import BaseLanguage
        from module.Config import Config

        runtime = Config()
        if current_config is not None:
            current_data = _object_to_dict(current_config)
            for field in dataclasses.fields(runtime):
                if field.init and field.name in current_data:
                    setattr(runtime, field.name, deepcopy(current_data[field.name]))
        else:
            current_data = {}

        try:
            runtime.source_language = BaseLanguage.Enum(self.source_language)
        except ValueError:
            runtime.source_language = self.source_language
        try:
            runtime.target_language = BaseLanguage.Enum(self.target_language)
        except ValueError:
            runtime.target_language = self.target_language

        for section in (self.processing, self.checking, self.request_policy):
            for key, value in section.items():
                if key != "provider" and hasattr(runtime, key):
                    setattr(runtime, key, _thaw(value))

        mode = _normalize_text(self.prompt.get("mode", "COMMON")).upper() or "COMMON"
        resolved_base = _normalize_text(self.prompt.get("resolved_base", ""))
        if resolved_base != "":
            runtime.translation_prompt_mode = Config.PROMPT_MODE_CUSTOM
            runtime.translation_custom_prompts = {
                BaseLanguage.Enum.ZH.value: resolved_base,
                BaseLanguage.Enum.EN.value: resolved_base,
            }
        else:
            runtime.translation_prompt_mode = mode

        style_id = _normalize_text(self.prompt.get("style_id", "NONE")).upper() or "NONE"
        resolved_style = _normalize_text(self.prompt.get("resolved_style", ""))
        if resolved_style != "":
            runtime.translation_style_id = Config.STYLE_CUSTOM
            runtime.translation_custom_style = resolved_style
        else:
            runtime.translation_style_id = style_id
            runtime.translation_custom_style = ""
        runtime.translation_output_protocol = _normalize_text(
            self.prompt.get("protocol", Config.OUTPUT_PROTOCOL_STRUCTURED)
        ).upper()

        runtime.glossary_enable = self.assets.glossary_enabled
        runtime.glossary_data = [
            {
                "src": term.source,
                "dst": term.target,
                "info": term.note,
                "record_id": term.record_id,
                "origin": term.origin,
                "regex": term.regex,
                "enabled": term.enabled,
            }
            for term in self.assets.glossary
        ]
        runtime.renpy_workbench_worldbook_enable = self.assets.worldbook_enabled
        runtime.renpy_workbench_worldbook_data = self.assets.worldbook.to_dict()
        runtime.renpy_workbench_character_cards_enable = self.assets.character_cards_enabled
        runtime.renpy_workbench_character_cards = [
            card.to_dict() for card in self.assets.character_cards
        ]

        provider = self.runtime_provider.to_dict()
        if not provider:
            provider = _resolve_provider(current_data)
        if provider:
            provider.setdefault("id", 0)
            runtime.platforms = [provider]
            runtime.activate_platform = provider["id"]

        return runtime

    def with_runtime_provider(self, provider: Mapping[str, Any] | None) -> TranslationTaskContext:
        """Attach current credentials without changing persisted snapshot content."""
        return dataclasses.replace(
            self,
            runtime_provider = FrozenDict(deepcopy(provider or {})),
        )
