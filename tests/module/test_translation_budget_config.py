import json

import pytest

from module.Config import Config
from module.Engine.Translator.TranslationTaskContext import TranslationTaskContext


def test_new_config_uses_source_budget_but_old_config_keeps_legacy_batching(tmp_path):
    assert Config().max_batch_source_tokens == 1024
    assert Config().max_output_tokens == 0
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"config_version": 2, "token_threshold": 10}), encoding="utf-8")

    loaded = Config().load(str(path))

    assert loaded.token_threshold == 10
    assert loaded.max_batch_source_tokens == 0
    assert loaded.max_output_tokens == 0
    loaded.max_batch_source_tokens = 2048
    loaded.max_output_tokens = 8192
    loaded.save(str(path), strict=True)
    saved = Config().load(str(path))
    assert (saved.max_batch_source_tokens, saved.max_output_tokens) == (2048, 8192)


@pytest.mark.parametrize("value", [-1, True, "1024", None])
def test_invalid_budget_values_use_legacy_or_provider_defaults(value):
    migrated = Config.migrate_dict({"max_batch_source_tokens": value, "max_output_tokens": value})
    assert migrated["max_batch_source_tokens"] == 0
    assert migrated["max_output_tokens"] == 0


def test_budget_snapshot_is_stable_and_resumed_run_uses_current_budgets():
    original = Config(token_threshold=10, max_batch_source_tokens=1024, max_output_tokens=8192)
    context = TranslationTaskContext.from_config(original)
    snapshot = context.to_snapshot()
    restored = TranslationTaskContext.from_snapshot(snapshot)
    baseline = restored.to_runtime_config()
    assert (baseline.max_batch_source_tokens, baseline.max_output_tokens) == (1024, 8192)

    current = Config(token_threshold=20, max_batch_source_tokens=2048, max_output_tokens=0)
    resumed = restored.to_runtime_config(current)

    assert (resumed.token_threshold, resumed.max_batch_source_tokens, resumed.max_output_tokens) == (20, 2048, 0)
    assert restored.to_snapshot() == snapshot
