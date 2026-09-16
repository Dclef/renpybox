import json

import pytest

from base.Base import Base
from module.Config import Config
from scripts import benchmark_translation_throughput as benchmark


def test_load_corpus_json_deduplicates_before_limit(tmp_path):
    path = tmp_path / "corpus.json"
    path.write_text(json.dumps(["a", "", "b", "a", "c"]), encoding="utf-8")

    audit = benchmark.load_corpus(path, max_items=2)

    assert audit.texts == ("a", "b")
    assert audit.supplied_count == 5
    assert audit.blank_skipped == 1
    assert audit.duplicate_removed == 1
    assert audit.selected_count == 2


def test_load_corpus_jsonl_accepts_text_records_and_rejects_invalid_records(tmp_path):
    path = tmp_path / "corpus.jsonl"
    path.write_text('"first"\n{"text":"second"}\n\n', encoding="utf-8")
    assert benchmark.load_corpus(path).texts == ("first", "second")

    invalid = tmp_path / "invalid.jsonl"
    invalid.write_text('{"text": 42}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="record 1"):
        benchmark.load_corpus(invalid)


@pytest.mark.parametrize(
    ("profile", "expected_chunks"),
    [("legacy10", 100), ("source1024", 100), ("balanced20", 50)],
)
def test_profiles_use_production_source_and_line_budgets(monkeypatch, profile, expected_chunks):
    monkeypatch.setattr("module.Cache.CacheItem.CacheItem.get_token_count", lambda self: 40)
    texts = [f"line-{index}" for index in range(1000)]

    result = benchmark.run_profile(texts, profile)

    assert result["chunk_count"] == expected_chunks
    assert result["task_count"] == 0
    assert result["quality"]["available"] is False


def test_dry_run_does_not_construct_translation_tasks(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("dry run constructed a translation task")

    monkeypatch.setattr(benchmark, "TranslatorTask", fail)
    result = benchmark.run_profile(["one", "two"], "legacy10")
    assert result["chunk_count"] == 1


def test_execute_counts_quality_passed_unique_sources(monkeypatch):
    class FakeTask:
        def __init__(self, config, platform, local_flag, items, precedings, **kwargs):
            self.items = items
            self.print_log_table = None

        def start(self, current_round):
            for item in self.items:
                if item.get_src() == "good":
                    item.set_dst("translated")
                    item.set_status(Base.TranslationStatus.TRANSLATED)
                elif item.get_src() == "same":
                    item.set_dst(item.get_src())
                    item.set_status(Base.TranslationStatus.TRANSLATED)
            return {
                "row_count": len(self.items),
                "input_tokens": 10,
                "output_tokens": 5,
                "request_metrics": {
                    "logical_request_ms": 4,
                    "logical_request_ms_samples": [4, 5],
                    "secret": "must not escape",
                },
                "api_key": "must not escape",
            }

    monkeypatch.setattr(benchmark, "TranslatorTask", FakeTask)
    config = Config(token_threshold=10, max_batch_source_tokens=0, rpm_threshold=0)
    platform = {"api_url": "https://example.invalid", "model": "test", "api_format": Base.APIFormat.OPENAI}

    result = benchmark.run_profile(
        ["good", "good", "same", "failed"],
        "legacy10",
        config=config,
        execute=True,
        concurrency=2,
        platform=platform,
    )

    assert result["task_count"] == 1
    assert result["row_count"] == 4
    assert result["quality"]["effective_unique"] == 1
    assert result["quality"]["quality_failed_unique"] == 2
    assert result["request_metrics"]["logical_request_ms"] == 4
    assert "api_key" not in result
    assert "secret" not in result["request_metrics"]
