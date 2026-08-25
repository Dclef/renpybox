from base.Base import Base
from module.Cache.CacheItem import CacheItem
from module.Config import Config
from module.Engine.Translator.TranslationTaskContext import TranslationTaskContext
from module.Engine.Translator.TranslatorTask import TranslatorTask


def _platform() -> dict:
    return {
        "id": 7,
        "api_url": "https://example.invalid/v1",
        "api_format": Base.APIFormat.OPENAI,
        "model": "test-model",
        "api_key": ["current-secret"],
    }


def test_task_uses_an_isolated_runtime_config_from_context() -> None:
    current = Config(
        token_threshold = 64,
        platforms = [_platform()],
        activate_platform = 7,
    )
    context = TranslationTaskContext.from_config(current)

    task = TranslatorTask(
        context,
        _platform(),
        False,
        [CacheItem(src = "source")],
        [],
        runtime_config = current,
    )
    task.config.token_threshold = 1
    task.config.glossary_data.append({"src": "changed", "dst": "changed"})

    assert current.token_threshold == 64
    assert current.glossary_data == []
    assert context.processing["token_threshold"] == 64
    assert task.task_context is context


def test_runtime_glossary_is_forwarded_as_candidates_only() -> None:
    current = Config(
        auto_glossary_enable = True,
        glossary_enable = True,
        glossary_data = [{"src": "Alice", "dst": "爱丽丝"}],
        platforms = [_platform()],
        activate_platform = 7,
    )
    context = TranslationTaskContext.from_config(current)
    received: list[list[dict[str, str]]] = []
    task = TranslatorTask(
        context,
        _platform(),
        False,
        [CacheItem(src = "source")],
        [],
        runtime_config = current,
        candidate_sink = received.append,
    )

    task.merge_glossary(
        [
            {"source": "Bob", "target": "鲍勃", "note": "character"},
            {"src": "Bob", "dst": "鲍勃", "info": "duplicate"},
            {"source": "same", "target": "same"},
        ],
        0,
    )

    assert received == [[{
        "source": "Bob",
        "target": "鲍勃",
        "note": "character",
    }]]
    assert current.glossary_data == [{"src": "Alice", "dst": "爱丽丝"}]
    assert [term.source for term in context.assets.glossary] == ["Alice"]


def test_task_keeps_runtime_request_policy_over_snapshot() -> None:
    snapshot_config = Config(
        max_workers = 4,
        rpm_threshold = 30,
        platforms = [_platform()],
        activate_platform = 7,
    )
    context = TranslationTaskContext.from_config(snapshot_config)
    runtime_config = Config(
        max_workers = 16,
        rpm_threshold = 90,
        platforms = [_platform()],
        activate_platform = 7,
    )

    task = TranslatorTask(
        context,
        _platform(),
        False,
        [CacheItem(src = "source")],
        [],
        runtime_config = runtime_config,
    )

    assert task.config.max_workers == 16
    assert task.config.rpm_threshold == 90
