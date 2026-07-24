import json

from base.Base import Base
from base.BaseLanguage import BaseLanguage
from module.Cache.CacheItem import CacheItem
from module.Config import Config
from module.Engine.Quality.TranslationQualityReport import TranslationQualityReport
from module.Engine.TaskRequester import TaskRequester
from module.Engine.Translator.TranslatorTask import TranslatorTask
from module.PromptBuilder import PromptBuilder
from module.Response.ResponseChecker import ResponseChecker


def _platform() -> dict:
    return {
        "api_url": "https://example.invalid/v1",
        "api_format": Base.APIFormat.OPENAI,
        "model": "test-model",
    }


def _task(item: CacheItem, config: Config | None = None) -> TranslatorTask:
    return TranslatorTask(
        config or Config(
            source_language = BaseLanguage.Enum.EN,
            target_language = BaseLanguage.Enum.ZH,
            translation_output_protocol = Config.OUTPUT_PROTOCOL_STRUCTURED,
        ),
        _platform(),
        False,
        [item],
        [],
    )


def test_retry_reasons_are_serializable_and_hints_are_failure_specific() -> None:
    item = CacheItem(src = "Hello <v0/>\nかな", metadata = {"trace_id": "kept"})
    TranslatorTask.set_retry_metadata(
        item,
        [
            ResponseChecker.Error.LINE_ERROR_FAKE_REPLY,
            ResponseChecker.Error.LINE_ERROR_KANA,
        ],
        ["Hello <v0/>", "かな"],
        ["你好", "かな"],
        1,
    )

    payload = item.get_metadata()[TranslatorTask.RETRY_METADATA_KEY]
    assert json.loads(json.dumps(payload, ensure_ascii = False)) == payload
    assert payload == {
        "schema_version": 1,
        "attempt": 1,
        "reasons": [
            {"code": "PLACEHOLDER_MISMATCH", "line_indices": [0]},
            {"code": "LINE_ERROR_KANA", "line_indices": [1]},
        ],
    }

    hint = PromptBuilder(Config(target_language = BaseLanguage.Enum.ZH)).build_retry_hint([item])
    assert "变量、标签和占位符" in hint
    assert "不得残留日文" in hint
    assert "request_index" not in hint
    assert "术语译法" not in hint
    assert "照抄" not in hint


def test_retry_hint_uses_metadata_not_retry_count_and_has_fixed_order() -> None:
    legacy_item = CacheItem(src = "legacy", retry_count = 3)
    assert PromptBuilder(Config()).build_retry_hint([legacy_item]) == ""

    item = CacheItem(
        src = "source",
        retry_count = 1,
        metadata = {
            "translation_retry": {
                "schema_version": 1,
                "attempt": 1,
                "reasons": [
                    {"code": "GLOSSARY", "line_indices": [0]},
                    {"code": "INDEX_ALIGNMENT", "line_indices": [0]},
                    {"code": "PLACEHOLDER_MISMATCH", "line_indices": [0]},
                ],
            }
        },
    )
    hint = PromptBuilder(Config(target_language = BaseLanguage.Enum.ZH)).build_retry_hint([item])

    assert hint.index("request_index") < hint.index("变量、标签和占位符")
    assert hint.index("变量、标签和占位符") < hint.index("术语译法")


def test_strict_decode_failure_skips_checker_and_never_writes_back(monkeypatch) -> None:
    item = CacheItem(src = "Hello", metadata = {"trace_id": "kept"})
    task = _task(item)
    task.prompt_builder.generate_prompt = lambda *args, **kwargs: ([{"role": "user", "content": "x"}], [])
    task.print_log_table = lambda *args, **kwargs: None

    response = json.dumps({
        "translations": [{"request_index": 1, "text": "错误索引"}],
        "new_glossary": [],
    })
    monkeypatch.setattr(
        TaskRequester,
        "request",
        lambda self, messages: (False, "", response, 3, 2),
    )

    def fail_if_checked(*args, **kwargs):
        raise AssertionError("strict decode failures must not enter ResponseChecker")

    task.response_checker.check = fail_if_checked
    result = task.request(task.items, task.processors, [], False, 0)

    assert result["row_count"] == 0
    assert result["failed_line_count"] == 1
    assert item.get_dst() == ""
    assert item.get_status() == Base.TranslationStatus.UNTRANSLATED
    assert item.get_retry_count() == 1
    assert item.get_metadata()["trace_id"] == "kept"
    assert item.get_metadata()["translation_retry"]["reasons"] == [
        {"code": "INDEX_ALIGNMENT", "line_indices": [0]}
    ]


def test_successful_write_clears_only_temporary_retry_metadata(monkeypatch) -> None:
    item = CacheItem(
        src = "Hello",
        retry_count = 1,
        metadata = {
            "trace_id": "kept",
            "translation_retry": {
                "schema_version": 1,
                "attempt": 1,
                "reasons": [{"code": "INDEX_ALIGNMENT", "line_indices": [0]}],
            },
        },
    )
    task = _task(item)
    task.prompt_builder.generate_prompt = lambda *args, **kwargs: ([{"role": "user", "content": "x"}], [])
    task.print_log_table = lambda *args, **kwargs: None
    response = json.dumps({
        "translations": [{"request_index": 0, "text": "你好"}],
        "new_glossary": [],
    }, ensure_ascii = False)
    monkeypatch.setattr(
        TaskRequester,
        "request",
        lambda self, messages: (False, "", response, 3, 2),
    )

    result = task.request(task.items, task.processors, [], False, 0)

    assert result["row_count"] == 1
    assert item.get_dst() == "你好"
    assert item.get_status() == Base.TranslationStatus.TRANSLATED
    assert item.get_metadata() == {"trace_id": "kept"}


def test_quality_report_combines_item_reasons_with_progress_counts() -> None:
    first = CacheItem(
        src = "source one",
        file_path = "game/script.rpy",
        row = 12,
        retry_count = 2,
        metadata = {
            "translation_retry": {
                "schema_version": 1,
                "attempt": 2,
                "reasons": [
                    {"code": "PLACEHOLDER_MISMATCH", "line_indices": [0]},
                    {"code": "LINE_ERROR_KANA", "line_indices": [1]},
                ],
            }
        },
    )
    second = CacheItem(
        src = "source two",
        row = 4,
        retry_count = 1,
        metadata = {
            "translation_retry": {
                "schema_version": 1,
                "attempt": 1,
                "reasons": [{"code": "INDEX_ALIGNMENT", "line_indices": [0]}],
            }
        },
    )
    report = TranslationQualityReport.from_items(
        [first, second],
        {
            "failed_line_count": 5,
            "fallback_line_count": 2,
            "line_count_mismatch_count": 1,
            "error_type_counts": {"GLOSSARY": 3},
        },
    )

    assert report.failed_count == report.failed_line_count == 5
    assert report.fallback_count == report.fallback_line_count == 2
    assert report.line_mismatch_count == report.line_count_mismatch_count == 1
    assert report.error_type_counts == {
        "GLOSSARY": 3,
        "INDEX_ALIGNMENT": 1,
        "LINE_ERROR_KANA": 1,
        "PLACEHOLDER_MISMATCH": 1,
    }
    assert [reference.reference for reference in report.item_references] == [
        "game/script.rpy:12",
        "item:1",
    ]
    serialized = json.loads(json.dumps(report.as_dict(), ensure_ascii = False))
    assert serialized["item_references"][0]["error_types"] == [
        "LINE_ERROR_KANA",
        "PLACEHOLDER_MISMATCH",
    ]
    assert "rollback" not in serialized
