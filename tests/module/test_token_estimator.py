from types import SimpleNamespace

from base.Base import Base
from base.BaseLanguage import BaseLanguage
from frontend.TranslationPage import TranslationPage
from module.Cache.CacheItem import CacheItem
from module.Cache.CacheManager import CacheManager
from module.Config import Config
from module.Engine.Engine import Engine
from module.TokenEstimator import TokenEstimator


def _config(input_folder, output_folder) -> Config:
    return Config(
        cache_use_sqlite = False,
        input_folder = str(input_folder),
        output_folder = str(output_folder),
        source_language = BaseLanguage.Enum.EN,
        target_language = BaseLanguage.Enum.ZH,
        token_threshold = 4,
    )


def test_translation_page_estimate_reads_input_before_cache_exists(
    tmp_path,
    monkeypatch,
) -> None:
    input_folder = tmp_path / "input"
    input_folder.mkdir()
    (input_folder / "story.txt").write_text("Hello world", encoding = "utf-8")
    config = _config(input_folder, tmp_path / "output")

    runtime_manager = CacheManager(service = False)
    runtime_manager.set_items([CacheItem(src = "stale project item")])
    monkeypatch.setattr(
        Engine.get(),
        "translator",
        SimpleNamespace(
            cache_manager = runtime_manager,
            _active_cache_output_folder = "",
            _last_runtime_output_folder = str(tmp_path / "other-output"),
        ),
        raising = False,
    )
    page = TranslationPage.__new__(TranslationPage)

    items = page._load_items_for_token_estimate(config)

    assert [item.get_src() for item in items] == ["Hello world"]


def test_estimator_includes_project_worldbook_prompt(tmp_path) -> None:
    item = CacheItem(
        src = "Alice enters the observatory.",
        status = Base.TranslationStatus.UNTRANSLATED,
    )
    platform = {"input_price_per_million": 1, "output_price_per_million": 1}

    plain = _config(tmp_path / "plain-input", tmp_path / "plain-output")
    plain_result = TokenEstimator(plain, platform, [item]).estimate()

    enriched = _config(tmp_path / "asset-input", tmp_path / "asset-output")
    enriched.renpy_workbench_worldbook_enable = True
    enriched.renpy_workbench_worldbook_data = {
        "setting_summary": "A lunar city built inside a vast glass observatory.",
        "world_rules": ["Moonlight powers every machine."],
    }
    enriched_result = TokenEstimator(enriched, platform, [item]).estimate()

    assert plain_result.untranslated_count == 1
    assert plain_result.batch_count == 1
    assert enriched_result.estimated_input_tokens > plain_result.estimated_input_tokens


def test_estimator_uses_byte_fallback_when_tiktoken_is_unavailable(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        TokenEstimator,
        "_get_encoder",
        staticmethod(lambda: None),
    )
    config = _config(tmp_path / "input", tmp_path / "output")
    result = TokenEstimator(
        config,
        {},
        [CacheItem(src = "无法载入编码器时仍可估算")],
    ).estimate()

    assert result.total_source_tokens > 0
    assert result.estimated_input_tokens > result.total_source_tokens


def test_estimator_preceding_rules_match_cache_manager_punctuation(tmp_path) -> None:
    previous = CacheItem(src = "上一句（旁白）", file_path = "story.rpy")
    current = CacheItem(src = "Current line.", file_path = "story.rpy")
    config = _config(tmp_path / "input", tmp_path / "output")
    config.preceding_lines_threshold = 1

    estimator = TokenEstimator(config, {}, [previous, current])

    assert estimator._estimate_preceding_items([current]) == [previous]


def test_estimator_independent_source_budget_can_fill_long_text_batches(monkeypatch):
    # 40 source tokens per item keeps the assertion independent from a
    # particular encoder version.
    items = [CacheItem(src="word " * 40, file_path="story.rpy") for _ in range(1000)]
    monkeypatch.setattr(TokenEstimator, "_count_tokens", lambda _self, text: len(text.split()))
    monkeypatch.setattr(TokenEstimator, "_estimate_batch_prompt_tokens", lambda _self, batches: 0)
    legacy = Config(token_threshold=10, max_batch_source_tokens=0)
    balanced = Config(token_threshold=20, max_batch_source_tokens=0)

    assert TokenEstimator(legacy, {}, items).estimate().batch_count == 100
    assert TokenEstimator(balanced, {}, items).estimate().batch_count == 50


def test_estimator_keeps_file_boundaries_and_oversized_items(monkeypatch):
    items = [
        CacheItem(src="x " * 40, file_path="a.rpy"),
        CacheItem(src="x " * 40, file_path="b.rpy"),
        CacheItem(src="x " * 2000, file_path="b.rpy"),
        CacheItem(src="x " * 40, file_path="b.rpy"),
    ]
    monkeypatch.setattr(TokenEstimator, "_count_tokens", lambda _self, text: len(text.split()))
    monkeypatch.setattr(TokenEstimator, "_estimate_batch_prompt_tokens", lambda _self, batches: 0)
    config = Config(token_threshold=20, max_batch_source_tokens=1024)

    result = TokenEstimator(config, {}, items).estimate()

    assert result.batch_count == 4
    assert result.untranslated_count == 4
