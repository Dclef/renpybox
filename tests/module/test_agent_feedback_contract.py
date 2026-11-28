"""A contract regressions: fake requesters only, every game corpus lives in tmp_path."""
from __future__ import annotations

import copy
import json
import threading
import time
from types import SimpleNamespace

import pytest
import module.Extract.GlossaryCandidateService as module
from module.Extract.GlossaryCandidateService import ExtractionProgress, GlossaryCandidateService


PLATFORM = {"api_format": "OpenAI", "model": "fake", "reasoning_effort": "high"}


@pytest.fixture(autouse=True)
def _isolated_extraction_checkpoints(tmp_path_factory, monkeypatch):
    root = tmp_path_factory.mktemp('extraction-checkpoints')
    monkeypatch.setattr('module.Extract.ExtractionCheckpoint.default_checkpoint_root', lambda: root)


def service(**kwargs):
    return GlossaryCandidateService(config=SimpleNamespace(), target_path=kwargs.pop("target_path", "."),
                                    platform=copy.deepcopy(PLATFORM), **kwargs)


def item(index, text=None, **kwargs):
    return {"id": index, "text": text or f"Name{index} spoke.", "source": "story/chapter.rpy", "line": index + 11, **kwargs}


def response(text="[]"):
    return SimpleNamespace(success=True, text=text, error_code="", error_message="")


def payload(messages):
    return [json.loads(line) for line in messages[0]["content"].split("输入：\n", 1)[1].splitlines()]


class Requester:
    def __init__(self, config, platform, **kwargs):
        self.platform = platform

    def request_text(self, messages, **_kwargs):
        return response()

    def cancel(self):
        pass

    def close(self):
        pass


@pytest.fixture(autouse=True)
def no_real_requests(monkeypatch):
    # Keep real application log I/O out of millisecond fake deadline tests.
    monkeypatch.setattr(GlossaryCandidateService, 'info', lambda *args, **kwargs: None)
    monkeypatch.setattr(module, "AgentRequester", Requester)


def fake_corpus(monkeypatch, count):
    monkeypatch.setattr(GlossaryCandidateService, "_collect_corpus",
                        lambda self: ([item(i) for i in range(count)], []))
    monkeypatch.setattr(GlossaryCandidateService, "CHUNK_MAX_ITEMS", 1)


@pytest.mark.parametrize("basename", ["common.rpy", "common_box.rpy", "screens_box.rpy", "style_box.rpy"])
def test_user_template_like_basenames_keep_story(tmp_path, basename):
    game = tmp_path / "game"
    (game / "story").mkdir(parents=True)
    (game / "story" / basename).write_text('define h = Character("History")\nh "Help saved Mouse."', encoding="utf-8")
    rows, warnings = service(target_path=game)._collect_corpus()
    assert not warnings
    assert [row["line"] for row in rows] == [1, 2]
    assert all(row["source"] == "story/" + basename for row in rows)
    assert any("Help saved Mouse" in row["text"] for row in rows)


def test_each_dialogue_request_has_transitive_cross_file_definitions(tmp_path):
    game = tmp_path / "game"
    game.mkdir()
    (game / "names.rpy").write_text('init python:\n    HERO = "Luma"\ndefault hero_name = HERO\ndefine e = Character(hero_name)\n', encoding="utf-8")
    (game / "chapter.rpy").write_text("\n".join(f'e "[hero_name] spoke at gate {i}."' for i in range(24)), encoding="utf-8")
    svc = service(target_path=game)
    svc.CHUNK_MAX_ITEMS = 8
    svc.CHUNK_MAX_CHARS = 600
    rows, warnings = svc._collect_corpus()
    chunks = svc._build_chunks(rows)
    assert not warnings
    assert len(chunks) > 3
    assert {row["id"] for chunk in chunks for row in chunk} == {row["id"] for row in rows}
    expected = {'HERO = "Luma"', 'default hero_name = HERO', 'define e = Character(hero_name)'}
    for chunk in chunks:
        assert len(chunk) <= 8
        assert sum(len(row["text"]) for row in chunk) <= 600
        if any(row.get("speaker") == "e" for row in chunk):
            assert expected <= {row["text"] for row in chunk}
            assert {row["line"] for row in chunk if row["source"] == "names.rpy"} >= {2, 3, 4}
        decoded = payload(svc._build_prompt(chunk))
        assert decoded == chunk
    assert svc._context_limited_count == 0


def test_multiline_character_definition_keeps_real_name_line(tmp_path):
    game = tmp_path / "game"
    game.mkdir()
    (game / "names.rpy").write_text('define h = Character(\n    "History",\n    color="#fff"\n)\n', encoding="utf-8")
    (game / "chapter.rpy").write_text('h "I remember."', encoding="utf-8")
    svc = service(target_path=game)
    rows, _ = svc._collect_corpus()
    chunk = next(chunk for chunk in svc._build_chunks(rows) if any(row.get("speaker") == "h" for row in chunk))
    name_row = next(row for row in chunk if '"History"' in row["text"])
    assert name_row["source"] == "names.rpy" and name_row["line"] == 2
    assert name_row["kind"] == "character-definition"
    assert any("Character(" in row["text"] for row in chunk)
    requester = Requester(None, PLATFORM)
    requester.request_text = lambda *_args, **_kwargs: response(json.dumps({"src": "History", "type": "角色", "line": name_row["id"]}))
    success, grounded = svc._request_chunk(0, chunk, requester)
    assert success and grounded[0]["line"] == 2 and grounded[0]["source"] == "names.rpy"


def test_ui_usage_and_same_word_character_are_distinct(tmp_path):
    game = tmp_path / "game"
    game.mkdir()
    (game / "screens.rpy").write_text('textbutton "History" action ShowMenu("history")', encoding="utf-8")
    (game / "story.rpy").write_text('define h = Character("History")\nh "Hello, Mouse."', encoding="utf-8")
    svc = service(target_path=game)
    rows, _ = svc._collect_corpus()
    ui = next(row for row in rows if row["kind"] == "ui")
    assert "textbutton" in ui["statement"] and "ShowMenu" in ui["statement"]
    prompt = svc._build_prompt(rows)[0]["content"]
    assert "不按单词拼写设黑名单" in prompt
    assert "History 是角色，应提取" in prompt
    assert "赋值里的字符串并非都指人物" in prompt
    definition = next(row for row in rows if row["kind"] == "character-definition")
    requester = Requester(None, PLATFORM)
    requester.request_text = lambda *_args, **_kwargs: response(json.dumps({"src": "History", "type": "角色", "line": definition["id"]}))
    success, grounded = svc._request_chunk(0, rows, requester)
    assert success and grounded[0]["src"] == "History"


@pytest.mark.parametrize("name", ["[Archivist]", "Mouse", "Help", "History", "田中"])
def test_real_character_spelling_is_not_blacklisted_or_stripped(name):
    row = item(0, f'define narrator = Character("{name}")', kind="character-definition")
    requester = Requester(None, PLATFORM)
    requester.request_text = lambda *_args, **_kwargs: response(json.dumps({"src": name, "type": "角色", "line": 0}, ensure_ascii=False))
    success, grounded = service()._request_chunk(0, [row], requester)
    assert success and grounded[0]["src"] == name


def test_preview_uses_checked_quote_and_resolved_source_not_model_hint():
    svc = service()
    rows = [item(9, "Nothing here.", source="ui.rpy", line=2),
            item(17, "Luma waved at History.", source="chapter/real.rpy", line=87)]
    requester = Requester(None, PLATFORM)
    requester.request_text = lambda *_args, **_kwargs: response(json.dumps({"src": "History", "type": "角色", "line": 9,
                                                           "source": "forged.rpy", "evidence": "secret invented reasoning"}))
    success, grounded = svc._request_chunk(0, rows, requester)
    assert success
    assert grounded[0]["source"] == "chapter/real.rpy" and grounded[0]["line"] == 87
    assert grounded[0]["evidence"] in rows[1]["text"]
    assert "History" in grounded[0]["evidence"]
    assert "invented" not in grounded[0]["evidence"]
    requester.request_text = lambda *_args, **_kwargs: response(json.dumps({"src": "History", "type": "角色", "line": 17,
                                                           "evidence": "waved at History."}))
    assert svc._request_chunk(0, rows, requester)[1][0]["evidence"] == "waved at History."


def test_progress_conservation_dedupe_cap_and_closed_state():
    progress = ExtractionProgress()
    progress.set_chunks([[item(i)] for i in range(7)])
    progress.chunk_started(0)
    progress.chunk_started(1)
    progress.chunk_finished(0, True)
    progress.chunk_finished(0, False)
    progress.see_candidates([{"src": f"Name{i}", "type": "角色", "evidence": "x" * 100, "prompt": "SECRET"} for i in range(40)])
    progress.see_candidates([{"src": "name0", "type": "角色"}])
    snapshot = progress.snapshot()
    assert snapshot["completed_chunks"] + len(snapshot["active_chunks"]) + snapshot["pending_chunks"] == 7
    assert snapshot["completed_chunks"] == snapshot["successful_chunks"] == 1
    assert snapshot["candidate_count"] == 40 and len(snapshot["candidates"]) == 20
    assert all(len(row["evidence"]) <= 40 and "prompt" not in row for row in snapshot["candidates"])
    progress.close()
    progress.chunk_started(4)
    progress.chunk_finished(1, True)
    progress.see_candidates([{"src": "Late", "type": "角色"}])
    assert progress.snapshot()["candidate_count"] == 40
    assert progress.snapshot()["completed_chunks"] == 1
    assert not progress.should_emit(force=True)


def test_healthy_slot_runs_far_beyond_first_timeout_and_discards_late(monkeypatch):
    fake_corpus(monkeypatch, 18)
    release = threading.Event()
    closed = threading.Event()
    calls = []
    class Mixed(Requester):
        def request_text(self, messages, **_kwargs):
            index = payload(messages)[0]["id"]
            self.index = index
            calls.append(index)
            if index == 0:
                release.wait(3)
                return response('{"src":"Name0","type":"角色","line":0}')
            time.sleep(0.04)
            return response()
        def close(self):
            if self.index == 0:
                closed.set()
    monkeypatch.setattr(module, "AgentRequester", Mixed)
    events, legacy = [], []
    svc = service(event_callback=events.append, progress_callback=lambda *args: legacy.append(args))
    svc.CHUNK_CONCURRENCY = 2
    svc.CHUNK_TIMEOUT_SECONDS = 0.15
    svc.CLOSE_TIMEOUT_SECONDS = 0.04
    try:
        started = time.monotonic()
        result = svc.run()
        elapsed = time.monotonic() - started
        frozen, event_count, report_count = copy.deepcopy(result), len(events), len(legacy)
        assert elapsed > 0.6, "健康槽必须继续处理超过首次超时宽限的后续队列"
        assert sorted(calls) == list(range(18))
        assert result["llm_chunks_success"] == 17 and result["llm_chunks_failed"] == 1
        assert result["llm_chunks_pending"] == 0 and result["llm_chunks_started"] == 18
        assert result["status"] == "partial" and result["coverage_percent"] < 100
        assert legacy[-1][1] < 100
        assert events[-1]["candidate_count"] == 0
    finally:
        release.set()
        assert closed.wait(2)
    assert result == frozen and len(events) == event_count and len(legacy) == report_count
    assert svc.progress.snapshot()["candidate_count"] == 0


def test_all_slots_request_and_cancel_block_but_return_is_bounded(monkeypatch):
    fake_corpus(monkeypatch, 12)
    release = threading.Event()
    instances = []
    class Stuck(Requester):
        def __init__(self, config, platform, **kwargs):
            super().__init__(config, platform)
            instances.append(self)
        def request_text(self, messages, **_kwargs):
            release.wait(3)
            return response()
        def cancel(self):
            release.wait(3)
        def close(self):
            release.wait(3)
    monkeypatch.setattr(module, "AgentRequester", Stuck)
    events = []
    svc = service(event_callback=events.append)
    svc.CHUNK_CONCURRENCY = 3
    svc.CHUNK_TIMEOUT_SECONDS = 0.06
    svc.CLOSE_TIMEOUT_SECONDS = 0.04
    try:
        started = time.monotonic()
        result = svc.run()
        assert time.monotonic() - started < 1
        assert len(instances) == 3
        assert result["llm_chunks_failed"] == 3 and result["llm_chunks_pending"] == 9
        assert result["llm_chunks_started"] == 3
        assert len(result["warnings"]) == 12
        last = events[-1]
        assert last["completed_chunks"] == 3 and last["pending_chunks"] == 9 and last["active_chunks"] == []
    finally:
        release.set()


def test_blocking_close_keeps_occupied_slots_and_valid_results(monkeypatch):
    fake_corpus(monkeypatch, 6)
    release = threading.Event()
    calls = []
    class SlowClose(Requester):
        def request_text(self, messages, **_kwargs):
            calls.append(payload(messages)[0]["id"])
            return response()
        def close(self):
            release.wait(3)
    monkeypatch.setattr(module, "AgentRequester", SlowClose)
    svc = service()
    svc.CHUNK_CONCURRENCY = 2
    svc.CLOSE_TIMEOUT_SECONDS = 0.05
    try:
        started = time.monotonic()
        result = svc.run()
        assert time.monotonic() - started < 1
        assert len(calls) == 2 and result["llm_chunks_success"] == 2
        assert result["llm_chunks_pending"] == 4
        assert result["status"] == "partial"
    finally:
        release.set()


def test_constructor_and_cleanup_exceptions_do_not_kill_worker(monkeypatch):
    fake_corpus(monkeypatch, 4)
    instances = []
    class Failure(Requester):
        def __init__(self, config, platform, **kwargs):
            instances.append(self)
            if len(instances) == 1:
                raise RuntimeError("bad setup")
        def close(self):
            raise RuntimeError("bad cleanup")
    monkeypatch.setattr(module, "AgentRequester", Failure)
    svc = service()
    svc.CHUNK_CONCURRENCY = 1
    result = svc.run()
    assert len(instances) == 4
    assert result["llm_chunks_success"] == 3 and result["llm_chunks_failed"] == 1
    assert result["llm_chunks_pending"] == 0


def test_user_cancel_freezes_events_results_and_legacy_callbacks(monkeypatch):
    fake_corpus(monkeypatch, 7)
    release, cancelled = threading.Event(), threading.Event()
    closes = []
    class Slow(Requester):
        def request_text(self, messages, **_kwargs):
            self.index = payload(messages)[0]["id"]
            release.wait(3)
            return response(json.dumps({"src": f"Name{self.index}", "type": "角色", "line": self.index}))
        def close(self):
            closes.append(self.index)
    monkeypatch.setattr(module, "AgentRequester", Slow)
    events, legacy = [], []
    def event(snapshot):
        events.append(snapshot)
        if len(snapshot["active_chunks"]) == 2:
            cancelled.set()
    svc = service(event_callback=event, cancel_callback=cancelled.is_set,
                  progress_callback=lambda *args: legacy.append(args))
    svc.CHUNK_CONCURRENCY = 2
    svc.CLOSE_TIMEOUT_SECONDS = 0.05
    try:
        with pytest.raises(InterruptedError):
            svc.run()
        count, reports = len(events), len(legacy)
        assert svc.progress.closed
        assert svc.progress.snapshot()["candidate_count"] == 0
    finally:
        release.set()
    deadline = time.monotonic() + 2
    while len(closes) < 2 and time.monotonic() < deadline:
        time.sleep(0.01)
    assert len(closes) == 2
    assert len(events) == count and len(legacy) == reports
    assert svc.progress.snapshot()["candidate_count"] == 0


def test_events_cover_start_finish_heartbeat_and_use_one_publisher(monkeypatch):
    fake_corpus(monkeypatch, 1)
    owner = threading.get_ident()
    times, events, publishers = [], [], []
    class Heartbeat(Requester):
        def request_text(self, messages, **_kwargs):
            time.sleep(1.15)
            return response('{"src":"Name0","type":"角色","line":0,"evidence":"Name0 spoke."}')
    monkeypatch.setattr(module, "AgentRequester", Heartbeat)
    def emit(snapshot):
        events.append(snapshot)
        times.append(time.monotonic())
        publishers.append(threading.get_ident())
    result = service(event_callback=emit).run()
    assert set(publishers) == {owner}
    active = [snapshot for snapshot in events if snapshot["active_chunks"]]
    assert active and active[0]["active_chunks"][0]["sources"] == ["story/chapter.rpy"]
    assert any(snapshot["active_chunks"][0]["elapsed_seconds"] >= 0.8 for snapshot in active)
    assert len(events) <= 9, "心跳不能每50ms轰炸"
    assert events[-1]["candidates"] == [{"src":"Name0", "type":"角色", "evidence":"Name0 spoke.", "source":"story/chapter.rpy", "line":11}]
    assert "evidence" not in result["entries"][0]
    for snapshot in events:
        assert snapshot["completed_chunks"] + len(snapshot["active_chunks"]) + snapshot["pending_chunks"] == snapshot["total_chunks"]
        assert snapshot["successful_chunks"] + snapshot["failed_chunks"] == snapshot["completed_chunks"]


def test_chunk_cap_keeps_unsent_work_visible(monkeypatch):
    fake_corpus(monkeypatch, 8)
    events = []
    svc = service(event_callback=events.append)
    svc.MAX_LLM_CHUNKS = 2
    result = svc.run()
    assert result["llm_chunks_total"] == 2
    assert result["llm_chunks_planned"] == 8 and result["llm_chunks_pending"] == 6
    assert result["coverage_percent"] == 25 and not result["coverage_complete"]
    assert events[-1]["total_chunks"] == 8 and events[-1]["pending_chunks"] == 6


def test_context_overflow_is_reported_without_dropping_source(tmp_path):
    game = tmp_path / "game"
    game.mkdir()
    (game / "story.rpy").write_text('default hero_name = "Luma"\ndefine e = Character(hero_name)\ne "[hero_name] spoke."', encoding="utf-8")
    svc = service(target_path=game)
    svc.CHUNK_MAX_ITEMS = 1
    rows, _ = svc._collect_corpus()
    chunks = svc._build_chunks(rows)
    assert {row["id"] for chunk in chunks for row in chunk} == {row["id"] for row in rows}
    result = svc.run()
    assert result["status"] == "partial" and not result["coverage_complete"]
    assert result["coverage_percent"] < 100, "incomplete context is not complete coverage"
    assert any("语境" in warning or "context" in warning for warning in result["warnings"])


def test_character_preview_filters_only_agent_category(monkeypatch):
    fake_corpus(monkeypatch, 1)
    class Entities(Requester):
        def request_text(self, messages, **_kwargs):
            return response('{"src":"Name0","type":"物品","line":0}')
    monkeypatch.setattr(module, "AgentRequester", Entities)
    events = []
    svc = service(character_only=True, event_callback=events.append)
    original_platform = copy.deepcopy(svc.platform)
    result = svc.run()
    assert result["entries"] == [] and events[-1]["candidate_count"] == 0
    assert svc.platform == original_platform == PLATFORM


def test_response_after_deadline_before_next_poll_is_rejected(monkeypatch):
    fake_corpus(monkeypatch, 1)
    class JustLate(Requester):
        def request_text(self, messages, **_kwargs):
            time.sleep(0.075)
            return response('{"src":"Name0","type":"角色","line":0}')
    monkeypatch.setattr(module, "AgentRequester", JustLate)
    events = []
    svc = service(event_callback=events.append)
    svc.CHUNK_TIMEOUT_SECONDS = 0.06
    svc.CLOSE_TIMEOUT_SECONDS = 0.04
    result = svc.run()
    assert result["status"] == "failed"
    assert result["entries"] == [] and events[-1]["candidate_count"] == 0
    assert result["llm_chunks_failed"] == 1


def test_unicode_speaker_attributes_and_renpy_say_keep_definitions(tmp_path):
    game = tmp_path / "game"
    game.mkdir()
    (game / "defs.rpy").write_text('default 姓名 = "田中"\ndefine 人物 = Character(姓名)', encoding="utf-8")
    (game / "story.rpy").write_text('人物 happy "你好。"\n$ renpy.say(人物, "你好，朋友。")', encoding="utf-8")
    svc = service(target_path=game)
    rows, _ = svc._collect_corpus()
    spoken = next(row for row in rows if row["source"] == "story.rpy" and row["line"] == 1)
    assert spoken["speaker"] == "人物"
    svc.CHUNK_MAX_ITEMS = 4
    for chunk in svc._build_chunks(rows):
        if any(row["source"] == "story.rpy" for row in chunk):
            assert {'default 姓名 = "田中"', 'define 人物 = Character(姓名)'} <= {row["text"] for row in chunk}


def test_serialized_prompt_budget_includes_metadata_and_context(monkeypatch):
    svc = service()
    base = len(json.dumps(svc._build_prompt([]), ensure_ascii=False).encode("utf-8"))
    limit = base + 1600
    monkeypatch.setattr(svc, "_input_byte_limit", lambda: limit)
    rows = [item(i, "田中" * 90, source="story/" + "chapter" * 20 + ".rpy") for i in range(12)]
    chunks = svc._build_chunks(rows)
    assert len(chunks) > 1
    assert {row["id"] for chunk in chunks for row in chunk} == set(range(12))
    for chunk in chunks:
        assert len(json.dumps(svc._build_prompt(chunk), ensure_ascii=False).encode("utf-8")) <= limit
    assert svc.platform == PLATFORM


def test_over_budget_request_is_not_sent_or_silently_accepted(monkeypatch):
    svc = service()
    monkeypatch.setattr(svc, "_input_byte_limit", lambda: 1)
    requester = Requester(None, PLATFORM)
    def forbidden(_):
        pytest.fail("over-budget request must not be sent")
    requester.request_text = forbidden
    success, warning = svc._request_chunk(0, [item(0)], requester)
    assert not success and ("预算" in warning or "budget" in warning)


def test_large_ui_literal_is_segmented_without_repeating_full_statement(tmp_path):
    game = tmp_path / "game"
    game.mkdir()
    (game / "screen.rpy").write_text('textbutton "' + " ".join(f"Sentence {i}." for i in range(1000)) + '" action ShowMenu("history")', encoding="utf-8")
    svc = service(target_path=game)
    rows, _ = svc._collect_corpus()
    assert len(rows) > 10
    assert all(len(row.get("statement", "")) < 100 for row in rows)
    for chunk in svc._build_chunks(rows):
        assert sum(len(row["text"]) + len(row.get("statement", "")) for row in chunk) <= svc.CHUNK_MAX_CHARS
        assert all(row["line"] == 1 and row["source"] == "screen.rpy" for row in chunk)

