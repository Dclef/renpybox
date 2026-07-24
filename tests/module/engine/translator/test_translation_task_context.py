import json

import pytest

from module.Engine.Translator.TranslationPreflightService import TranslationPreflightService
from module.Engine.Translator.TranslationTaskContext import (
    ProjectAssets,
    TermAsset,
    TranslationSnapshotError,
    TranslationTaskContext,
)


def _assets() -> ProjectAssets:
    return ProjectAssets.from_dict({
        "revision": 7,
        "updated_at": " 2026-07-24T10:00:00+08:00 ",
        "worldbook": {
            "enabled": True,
            "data": {
                "setting_summary": "  A floating city  ",
                "secret": "The prince is alive",
                "key": "The brass key opens the observatory",
                "empty": "  ",
            },
        },
        "character_cards": {
            "enabled": True,
            "items": [{
                "name": " Alice ",
                "name_translation": " 爱丽丝 ",
                "aliases": [" Al ", "Al"],
            }],
        },
        "glossary": {
            "enabled": True,
            "items": [
                {"src": " Sword ", "dst": " 剑 ", "origin": "local"},
                {"source": "", "target": "invalid"},
            ],
        },
        "do_not_translate": {
            "enabled": True,
            "items": [{"source": " Ren'Py "}],
        },
    })


def test_term_asset_normalizes_and_generates_stable_id() -> None:
    first = TermAsset.from_value({"source": " Alice ", "target": "爱丽丝"})
    changed_translation = TermAsset.from_value({"source": "Alice", "target": "艾丽丝"})

    assert first is not None
    assert changed_translation is not None
    assert first.source == "Alice"
    assert first.record_id.startswith("term_")
    assert first.record_id == changed_translation.record_id


def test_project_assets_are_normalized_and_character_ids_are_stable() -> None:
    assets = _assets()
    serialized = assets.to_dict()

    assert assets.revision == 7
    assert assets.worldbook["setting_summary"] == "A floating city"
    assert "empty" not in assets.worldbook
    assert len(assets.glossary) == 1
    assert assets.character_cards[0]["id"].startswith("character_")
    assert assets.character_cards[0]["aliases"] == ("Al",)
    assert ProjectAssets.from_dict(serialized) == assets
    assert assets.character_terms()[0].record_id.startswith("term_character_")


def test_task_context_is_deep_copied_immutable_and_snapshot_safe() -> None:
    config = {
        "source_language": "JA",
        "target_language": "ZH",
        "activate_platform": 5,
        "platforms": [{
            "id": 5,
            "model": "test-model",
            "api_url": "https://old-user:old-pass@example.invalid/v1",
            "api_key": ["top-secret"],
            "auth": {
                "token": "nested-token",
                "refresh_token": "refresh-secret",
                "Authorization": "Bearer authorization-secret",
                "password": "nested-password",
                "region": "local",
            },
        }],
        "processing": {"rules": {"preserve": ["[name]"]}},
        "checking": {"placeholder_check": True},
        "request_policy": {
            "max_tokens": 4096,
            "credentials": {"secret": "request-secret"},
        },
    }
    assets_data = _assets().to_dict()
    context = TranslationTaskContext.from_config(
        config,
        assets_data,
        created_at = "2026-07-24T02:05:00+00:00",
    )

    config["processing"]["rules"]["preserve"].append("mutated")
    config["platforms"][0]["api_key"][0] = "changed"
    assets_data["worldbook"]["data"]["setting_summary"] = "changed"

    assert context.processing["rules"]["preserve"] == ("[name]",)
    assert context.runtime_provider["api_key"] == ("top-secret",)
    assert context.assets.worldbook["setting_summary"] == "A floating city"
    with pytest.raises(TypeError):
        context.processing["rules"]["new"] = True

    snapshot = context.to_snapshot()
    serialized = json.dumps(snapshot, ensure_ascii = False)
    for credential in (
        "api_key",
        "top-secret",
        "nested-token",
        "refresh-secret",
        "authorization-secret",
        "nested-password",
        "request-secret",
    ):
        assert credential not in serialized
    assert snapshot["request_policy"]["max_tokens"] == 4096
    assert "credentials" not in snapshot["request_policy"]
    assert snapshot["assets"]["worldbook"]["data"]["secret"] == "The prince is alive"
    assert snapshot["assets"]["worldbook"]["data"]["key"] == "The brass key opens the observatory"
    assert snapshot["request_policy"]["provider"]["api_url"] == "https://example.invalid/v1"

    restored = TranslationTaskContext.from_snapshot(
        json.loads(serialized),
        runtime_provider = {"api_key": ["current-key"]},
    )
    assert restored == context
    assert restored.to_snapshot() == snapshot
    assert restored.runtime_provider["api_key"] == ("current-key",)


def test_snapshot_rejects_unsupported_schema_and_content_tampering() -> None:
    context = TranslationTaskContext.from_config(
        {"source_language": "JA", "target_language": "ZH"},
        _assets(),
        created_at = "2026-07-24T02:05:00+00:00",
    )
    snapshot = context.to_snapshot()

    unsupported = dict(snapshot)
    unsupported["schema_version"] = 999
    with pytest.raises(TranslationSnapshotError):
        TranslationTaskContext.from_snapshot(unsupported)

    tampered = json.loads(json.dumps(snapshot))
    tampered["target_language"] = "EN"
    with pytest.raises(TranslationSnapshotError):
        TranslationTaskContext.from_snapshot(tampered)


def test_runtime_config_projection_is_isolated_and_uses_runtime_credentials() -> None:
    context = TranslationTaskContext.from_config(
        {
            "source_language": "JA",
            "target_language": "ZH",
            "processing": {"token_threshold": 24},
        },
        _assets(),
        prompt = {
            "mode": "COMMON",
            "resolved_base": "frozen base",
            "style_id": "LITERARY",
            "resolved_style": "frozen style",
            "protocol": "JSONLINE",
            "protocol_version": 1,
        },
        created_at = "2026-07-24T02:05:00+00:00",
    )
    snapshot = context.to_snapshot()
    resumed = TranslationTaskContext.from_snapshot(
        snapshot,
        runtime_provider = {"id": 8, "api_key": ["current-secret"], "model": "runtime-model"},
    )

    runtime = resumed.to_runtime_config()
    runtime.token_threshold = 1
    runtime.glossary_data[0]["dst"] = "changed"

    assert runtime.get_platform(8)["api_key"] == ["current-secret"]
    assert runtime.translation_prompt_mode == runtime.PROMPT_MODE_CUSTOM
    assert runtime.translation_custom_prompts["ZH"] == "frozen base"
    assert runtime.translation_style_id == runtime.STYLE_CUSTOM
    assert runtime.translation_custom_style == "frozen style"
    assert runtime.translation_output_protocol == runtime.OUTPUT_PROTOCOL_JSONLINE
    assert context.processing["token_threshold"] == 24
    assert context.assets.glossary[0].target == "剑"


def test_preflight_checks_normalized_content_not_switches_alone() -> None:
    empty = TranslationPreflightService.check({
        "worldbook": {"enabled": True, "data": {"setting": "  "}},
        "glossary": {"enabled": True, "items": [{"source": "x", "target": ""}]},
        "character_cards": {"enabled": False, "items": [{"name": "Alice"}]},
    })
    effective = TranslationPreflightService.check(_assets())

    assert empty.has_effective_assets is False
    assert empty.should_prompt_for_missing_assets is True
    assert effective.effective_sections == (
        "worldbook",
        "character_cards",
        "glossary",
        "do_not_translate",
    )


def test_preflight_rejects_fixed_layers_that_leave_no_context_for_output() -> None:
    result = TranslationPreflightService.check(
        _assets(),
        fixed_prompt = "fixed prompt " * 100,
        provider = {"context_window_tokens": 128},
        reserved_output_tokens = 32,
    )

    assert result.can_start is False
    assert result.context_window_tokens == 128
    assert result.fixed_prompt_tokens >= 96
    assert result.errors[0].startswith("FIXED_PROMPT_EXCEEDS_CONTEXT_WINDOW:")


def test_preflight_ignores_unknown_provider_context_window() -> None:
    result = TranslationPreflightService.check(
        _assets(),
        fixed_prompt = "fixed prompt",
        provider = {"model": "unknown"},
        reserved_output_tokens = 4096,
    )

    assert result.can_start is True
    assert result.context_window_tokens == 0
