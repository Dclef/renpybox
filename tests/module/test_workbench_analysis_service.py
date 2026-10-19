"""工作台分析服务：进度回调、分批并发与全项目解析缓存。"""

from __future__ import annotations

import threading
from types import SimpleNamespace

import pytest

from module.Workbench.AnalysisService import AnalysisServiceError, WorkbenchAnalysisService
from module.Workbench.CharacterScanner import CharacterCandidate


def make_service(monkeypatch, *, candidates=None):
    service = WorkbenchAnalysisService()
    monkeypatch.setattr(
        WorkbenchAnalysisService,
        "ensure_analysis_ready",
        lambda self, config, **kwargs: {"api_format": "OpenAI", "model": "test-model"},
    )
    monkeypatch.setattr(
        WorkbenchAnalysisService,
        "load_scope_items",
        lambda self, config, scope: ([], "测试语料"),
    )
    monkeypatch.setattr(
        WorkbenchAnalysisService,
        "resolve_project_root",
        lambda self, config: None,
    )
    from module.Workbench import CharacterScanner as scanner_module

    monkeypatch.setattr(
        scanner_module.CharacterScanner,
        "build_candidates",
        lambda self, config, items, project_root, progress=None: list(candidates or []),
    )
    return service


def test_progress_callback_accepts_both_signatures():
    service = WorkbenchAnalysisService()
    single: list[str] = []
    service.progress_callback = single.append
    service._report_progress("只有文案")
    assert single == ["只有文案"]

    both: list[tuple[str, object]] = []
    service.progress_callback = lambda message, percent=None: both.append((message, percent))
    service._report_progress("带进度", 42)
    assert both == [("带进度", 42)]


def test_character_drafts_use_concurrent_batches(monkeypatch):
    service = make_service(monkeypatch)
    seen_threads: set[str] = set()
    lock = threading.Lock()
    calls: list[tuple[str, int]] = []
    # 三批必须同时在飞才会通过栅栏；串行实现会在这里超时，直接暴露退化。
    barrier = threading.Barrier(3, timeout = 5)

    def fake_request(self, config, platform, prompt, *, round_index=0, label="AI 分析"):
        with lock:
            seen_threads.add(threading.current_thread().name)
            calls.append((label, round_index))
        barrier.wait()
        # 每批返回两个角色，名字从 prompt 里取，保证能匹配回候选。
        names = [line.split(": ", 1)[1] for line in prompt.splitlines() if line.startswith("角色名: ")]
        import json

        return json.dumps(
            [{"name": name, "aliases": [], "match_keywords": [name]} for name in names],
            ensure_ascii = False,
        )

    monkeypatch.setattr(WorkbenchAnalysisService, "request_json_text", fake_request)

    candidates = [CharacterCandidate(f"角色{index}") for index in range(20)]
    progress: list[tuple[str, object]] = []
    service.progress_callback = lambda message, percent=None: progress.append((message, percent))

    drafts, raws = service.generate_character_drafts(
        config = SimpleNamespace(),
        platform = {},
        scope = "current",
        candidates = candidates,
        worldbook_draft = {},
    )

    assert len(drafts) == 20
    assert len(raws) == 3  # 20 / 8 → 3 批
    assert [index for _, index in calls] == [0, 1, 2]
    # 三批同时穿过栅栏，说明确实是并发而不是串行。
    assert len(seen_threads) == 3
    percents = [percent for _, percent in progress if isinstance(percent, int)]
    assert percents == sorted(percents)
    assert percents[-1] == 100 or percents[-1] >= 96


def test_character_drafts_report_no_candidates(monkeypatch):
    service = make_service(monkeypatch)
    progress: list[tuple[str, object]] = []
    service.progress_callback = lambda message, percent=None: progress.append((message, percent))

    drafts, raws = service.generate_character_drafts(
        config = SimpleNamespace(),
        platform = {},
        scope = "current",
        candidates = [],
        worldbook_draft = {},
    )

    assert drafts == [] and raws == []
    assert progress[-1][1] == 100


def test_worldbook_progress_reports_percent(monkeypatch):
    service = make_service(monkeypatch)

    def fake_request(self, config, platform, prompt, *, round_index=0, label="AI 分析"):
        import json

        return json.dumps({key: "值" for key in (
            "project_name", "genre", "setting_summary", "era_background",
            "tone_style", "narrative_rules", "format_rules", "spoiler_notes",
        )}, ensure_ascii = False)

    monkeypatch.setattr(WorkbenchAnalysisService, "request_json_text", fake_request)
    progress: list[tuple[str, object]] = []
    service.progress_callback = lambda message, percent=None: progress.append((message, percent))

    draft, raw = service.generate_worldbook_draft(
        config = SimpleNamespace(),
        platform = {},
        scope = "current",
        items = [],
        candidates = [],
    )

    assert draft["genre"] == "值"
    assert raw
    percents = [percent for _, percent in progress if isinstance(percent, int)]
    assert percents == [20, 48]


def test_worldbook_empty_response_raises(monkeypatch):
    service = make_service(monkeypatch)

    class FakeRequester:
        def __init__(self, *args, **kwargs):
            pass

        def request(self, messages, response_shape="none"):
            return False, "", "   ", 0, 0

    from module.Workbench import AnalysisService as service_module

    monkeypatch.setattr(service_module, "TaskRequester", FakeRequester)
    with pytest.raises(AnalysisServiceError):
        service.generate_worldbook_draft(
            config = SimpleNamespace(),
            platform = {},
            scope = "current",
            items = [],
            candidates = [],
        )


def test_analyze_all_reports_final_completion(monkeypatch):
    service = make_service(monkeypatch, candidates=[CharacterCandidate("Alice")])
    progress: list[tuple[str, object]] = []

    monkeypatch.setattr(
        WorkbenchAnalysisService,
        "generate_worldbook_draft",
        lambda self, **kwargs: ({"genre": "奇幻"}, "{}"),
    )
    monkeypatch.setattr(
        WorkbenchAnalysisService,
        "generate_character_drafts",
        lambda self, **kwargs: ([{"name": "Alice"}], ["[]"]),
    )
    service.progress_callback = lambda message, percent=None: progress.append((message, percent))

    result = service.analyze_all(SimpleNamespace(), "current")

    assert result.worldbook_draft == {"genre": "奇幻"}
    assert len(result.character_drafts) == 1
    assert progress[-1][1] == 100
    assert "分析完成" in progress[-1][0]


ORIGINAL_SAMPLES = [f"Line number {index} from Alice." for index in range(10)]
# 10 条样本均匀抽 8 条进提示词：跳过第 2、7 条，而不是只取前 8 条。
PROMPT_SAMPLES = [ORIGINAL_SAMPLES[index] for index in (0, 1, 3, 4, 5, 6, 8, 9)]


def make_alice():
    return CharacterCandidate(
        "Alice",
        sample_lines = list(ORIGINAL_SAMPLES),
        sample_count = len(ORIGINAL_SAMPLES),
    )


def described(name, **extra):
    data = {"name": name, "identity": "学生", "personality": "开朗"}
    data.update(extra)
    return data


def test_character_prompt_keeps_source_samples_and_chinese_descriptions():
    prompt = WorkbenchAnalysisService().build_character_prompt("current", [make_alice()], {})

    assert "所有字符串必须使用中文" not in prompt
    assert "原样复制" in prompt and "不得翻译" in prompt
    assert "name、aliases、match_keywords 保留游戏原文拼写" in prompt
    assert ORIGINAL_SAMPLES[9] in prompt  # 均匀抽样覆盖到最后一条
    assert ORIGINAL_SAMPLES[7] not in prompt


def test_character_samples_drop_translated_and_invented_lines():
    service = WorkbenchAnalysisService()
    raw = described(
        "Alice",
        sample_lines = [
            "这是第一句的中文翻译。",
            f"  {ORIGINAL_SAMPLES[3]}  ",
            "Alice says something she never said.",
            ORIGINAL_SAMPLES[7],  # 真实台词，但没有写进提示词
            ORIGINAL_SAMPLES[1],
            ORIGINAL_SAMPLES[3],
        ],
    )

    card = service.normalize_character_drafts_from_response([raw], [make_alice()])[0]

    assert card["sample_lines"] == [ORIGINAL_SAMPLES[3], ORIGINAL_SAMPLES[1]]


def test_character_samples_keep_genuine_selection_limited_to_six():
    service = WorkbenchAnalysisService()
    raw = described("Alice", sample_lines = list(reversed(PROMPT_SAMPLES)))

    card = service.normalize_character_drafts_from_response([raw], [make_alice()])[0]

    assert card["sample_lines"] == list(reversed(PROMPT_SAMPLES))[:6]


@pytest.mark.parametrize("model_samples", [["全是翻译。"], [], None, "Not a sample.", 3])
def test_character_samples_fall_back_to_originals(model_samples):
    service = WorkbenchAnalysisService()
    raw = described("Alice", sample_lines = model_samples)

    card = service.normalize_character_drafts_from_response([raw], [make_alice()])[0]

    # 回退样本同样均匀分布在提示词样本里，而不是只取开头几条。
    assert card["sample_lines"] == [PROMPT_SAMPLES[index] for index in (0, 1, 3, 4, 6, 7)]
    assert card["sample_lines"][-1] == ORIGINAL_SAMPLES[9]


@pytest.mark.parametrize("value", [None, 5, {"x": 1}, "Liddell", ["Liddell", 7, None]])
def test_character_aliases_tolerate_non_list_values(value):
    service = WorkbenchAnalysisService()
    candidate = CharacterCandidate("Alice Liddell", sample_lines = ["I'm Alice Liddell."])
    raw = described("Alice Liddell", aliases = value, match_keywords = value)

    card = service.normalize_character_drafts_from_response([raw], [candidate])[0]

    expected = ["Liddell"] if value in ("Liddell", ["Liddell", 7, None]) else []
    assert card["aliases"] == expected
    # 模型给的 match_keywords 不进触发词，只保留候选自带的称呼。
    assert card["match_keywords"] == ["Alice Liddell"]


def test_missing_and_empty_characters_are_marked_incomplete():
    service = WorkbenchAnalysisService()
    candidates = [
        make_alice(),
        CharacterCandidate("Bob", sample_lines = ["Hi."], low_confidence = True),
        CharacterCandidate("Cara", sample_lines = ["Cara speaks.", "Again.", "More."]),
    ]

    drafts = service.normalize_character_drafts_from_response(
        [described("Alice"), {"name": "Cara", "identity": " ", "aliases": []}],
        candidates,
    )

    by_name = {card["name"]: card for card in drafts}
    assert len(drafts) == 3
    assert "需手动补全" not in by_name["Alice"]["prompt_notes"]
    assert by_name["Bob"]["prompt_notes"].startswith(WorkbenchAnalysisService.NOTE_MISSING_ANALYSIS)
    assert "低置信度候选" in by_name["Bob"]["prompt_notes"]
    assert by_name["Cara"]["prompt_notes"].startswith(WorkbenchAnalysisService.NOTE_EMPTY_ANALYSIS)


def test_duplicate_model_names_keep_first_card_only():
    service = WorkbenchAnalysisService()

    drafts = service.normalize_character_drafts_from_response(
        [described("Alice", identity = "第一份"), described("alice", identity = "第二份")],
        [make_alice()],
    )

    assert len(drafts) == 1
    assert drafts[0]["identity"] == "第一份"
