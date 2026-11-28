"""Agent 术语候选服务：分块、证据定位、部分失败与取消。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import module.Extract.GlossaryCandidateService as service_module
from module.Extract.GlossaryCandidateService import (
    ExtractionProgress,
    GlossaryCandidateService,
    REASONING_MAX_CHARS,
    extract_character_candidates,
    extract_glossary_candidates,
)

PLATFORM = {"api_format": "OpenAI", "api_url": "http://localhost", "model": "test"}
FENCE = "```"


@pytest.fixture(autouse=True)
def _isolated_extraction_checkpoints(tmp_path_factory, monkeypatch):
    root = tmp_path_factory.mktemp('extraction-checkpoints')
    monkeypatch.setattr('module.Extract.ExtractionCheckpoint.default_checkpoint_root', lambda: root)


def make_service(**kwargs) -> GlossaryCandidateService:
    options = {
        "config": SimpleNamespace(),
        "target_path": ".",
        "platform": dict(PLATFORM),
    }
    options.update(kwargs)
    return GlossaryCandidateService(**options)


def make_item(index: int, text: str) -> dict:
    return {"id": index, "text": text, "source": "script.rpy", "line": index + 1}


class FakeRequester:
    """按脚本返回 Agent 结果；记录每个实例的 close 次数。"""

    responses: list = []
    instances: list = []

    def __init__(self, config, platform, *, thinking_level=None):
        self.config = config
        self.platform = platform
        self.thinking_level = thinking_level
        self.closed = 0
        self.cancelled = 0
        self.prompts: list[str] = []
        FakeRequester.instances.append(self)

    def request_text(self, messages, on_text_delta=None, on_reasoning_delta=None):
        self.prompts.append(messages[0]["content"])
        self.on_reasoning_delta = on_reasoning_delta
        if callable(on_reasoning_delta):
            for delta in getattr(self, "reasoning_deltas", ()) or ():
                on_reasoning_delta(delta)
        response = FakeRequester.responses.pop(0) if FakeRequester.responses else None
        if response is None:
            return SimpleNamespace(success=True, text="[]", error_code="", error_message="")
        if isinstance(response, Exception):
            raise response
        if isinstance(response, SimpleNamespace):
            return response
        return SimpleNamespace(success=True, text=str(response), error_code="", error_message="")

    def cancel(self):
        self.cancelled += 1

    def close(self):
        self.closed += 1


@pytest.fixture(autouse=True)
def reset_fake():
    FakeRequester.responses = []
    FakeRequester.instances = []
    yield
    FakeRequester.responses = []
    FakeRequester.instances = []


def test_chunks_respect_size_and_char_limits():
    service = make_service()
    items = [make_item(index, f"line-{index}") for index in range(100)]

    chunks = service._build_chunks(items)

    assert sum(len(chunk) for chunk in chunks) == 100
    for chunk in chunks:
        assert len(chunk) <= service.CHUNK_MAX_ITEMS
        assert sum(len(item["text"]) for item in chunk) <= service.CHUNK_MAX_CHARS or len(chunk) == 1


def test_long_lines_split_by_sentence_not_truncated():
    service = make_service()
    line = ("Alpha met Beta at the gate. " * 60).strip()
    assert len(line) > service.MAX_ITEM_CHARS

    segments = service._split_long_text(line)

    assert len(segments) > 1
    assert all(len(segment) <= service.MAX_ITEM_CHARS for segment in segments)
    assert "Alpha met Beta at the gate." in segments[0]


def test_prompt_requires_grounded_non_english_extraction():
    service = make_service()

    prompt = service._build_prompt([make_item(0, "LUMA waved at 田中さん.")])[0]["content"]

    for token in ("非英语", "不要依赖大小写", "JSONLINE", "逐字出现的原样片段"):
        assert token in prompt


def test_character_prompt_asks_for_names_only():
    service = make_service(character_only=True)

    prompt = service._build_prompt([make_item(0, "LUMA waved.")])[0]["content"]

    assert "人物名字" in prompt
    assert "非英语人名" in prompt


def test_prompt_payload_carries_source_line_kind_and_speaker():
    service = make_service()
    chunk = [
        {
            "id": 7,
            "text": "LUMA waved.",
            "source": "sub/scripts/chapter1.rpy",
            "line": 42,
            "kind": "dialogue",
            "speaker": "e",
        }
    ]

    prompt = service._build_prompt(chunk)[0]["content"]
    payload_line = [line for line in prompt.splitlines() if line.startswith('{"id"')][0]

    assert '"source": "sub/scripts/chapter1.rpy"' in payload_line
    assert '"line": 42' in payload_line
    assert '"kind": "dialogue"' in payload_line
    assert '"speaker": "e"' in payload_line
    assert "键是行号" not in prompt
    assert "id、source、line、kind、speaker" in prompt


def test_candidates_must_be_locatable_in_input():
    service = make_service()
    chunk = [make_item(0, "LUMA went to the East Square.")]

    assert service._locate_candidate({"src": "East Square", "line": 0}, chunk) == "East Square"
    assert service._locate_candidate({"src": "LUMA", "line": 0}, chunk) == "LUMA"
    assert service._locate_candidate({"src": "Nottingham", "line": 0}, chunk) is None
    assert service._locate_candidate({"src": "LUMA", "line": 99}, chunk) == "LUMA"


def test_ungrounded_response_is_reported_as_failure(monkeypatch):
    service = make_service()
    FakeRequester.responses = ['{"src": "Nottingham", "type": "地名", "line": 0}']

    success, payload = service._request_chunk(
        0, [make_item(0, "LUMA waved.")], FakeRequester(None, PLATFORM)
    )

    assert success is False
    assert "找不到原文" in str(payload)


def test_empty_array_is_success_with_zero_candidates():
    service = make_service()
    FakeRequester.responses = ["[]"]

    success, payload = service._request_chunk(
        0, [make_item(0, "LUMA waved.")], FakeRequester(None, PLATFORM)
    )

    assert success is True
    assert payload == []


def test_fenced_empty_array_is_accepted():
    service = make_service()
    FakeRequester.responses = [FENCE + "json\n[]\n" + FENCE]

    success, payload = service._request_chunk(
        0, [make_item(0, "LUMA waved.")], FakeRequester(None, PLATFORM)
    )

    assert success is True
    assert payload == []


def test_malformed_response_is_a_failure():
    for text in ("[oops", "no terms here"):
        service = make_service()
        FakeRequester.responses = [text]

        success, payload = service._request_chunk(
            1, [make_item(0, "LUMA waved.")], FakeRequester(None, PLATFORM)
        )

        assert success is False, text
        assert "第 2 块" in str(payload)


def test_agent_failure_keeps_code_and_message():
    service = make_service()
    requester = FakeRequester(None, PLATFORM)
    requester.request_text = lambda messages, on_text_delta=None, on_reasoning_delta=None: SimpleNamespace(
        success=False, text="", error_code="RATE_LIMITED", error_message="限流"
    )

    success, payload = service._request_chunk(0, [make_item(0, "LUMA waved.")], requester)

    assert success is False
    assert "限流" in str(payload)


def test_missing_platform_fails_without_rule_fallback(monkeypatch):
    texts = ["LUMA waved.", "Leo went to the East Square."]
    monkeypatch.setattr(
        service_module.GlossaryCandidateService,
        "_collect_corpus",
        lambda self: (
            [make_item(index, text) for index, text in enumerate(texts)],
            [],
        ),
    )
    service = make_service(platform=None)

    result = service.run()

    assert result["status"] == "failed"
    assert result["entries"] == []
    assert result["rule_candidate_count"] == 0
    assert result["used_llm"] is False
    assert result["coverage_complete"] is False


def test_partial_failure_keeps_successful_chunks(monkeypatch):
    texts = ["LUMA waved.", "Leo went to the East Square.", "Third line here."]
    monkeypatch.setattr(
        service_module.GlossaryCandidateService,
        "_collect_corpus",
        lambda self: (
            [make_item(index, text) for index, text in enumerate(texts)],
            [],
        ),
    )
    monkeypatch.setattr(service_module, "AgentRequester", FakeRequester)
    monkeypatch.setattr(
        service_module.GlossaryCandidateService,
        "CHUNK_MAX_ITEMS",
        1,
    )
    FakeRequester.responses = ['{"src": "LUMA", "type": "角色", "line": 0}', "[oops"]

    service = make_service()
    result = service.run()

    assert result["status"] == "partial"
    assert result["llm_chunks_total"] == 3
    assert result["llm_chunks_success"] >= 1
    assert result["coverage_complete"] is False
    assert any(entry["src"] == "LUMA" for entry in result["entries"])


def test_all_chunks_failed_reports_failure(monkeypatch):
    monkeypatch.setattr(
        service_module.GlossaryCandidateService,
        "_collect_corpus",
        lambda self: ([make_item(0, "LUMA waved.")], []),
    )
    monkeypatch.setattr(service_module, "AgentRequester", FakeRequester)
    FakeRequester.responses = ["[oops"]

    result = make_service().run()

    assert result["status"] == "failed"
    assert result["entries"] == []
    assert result["coverage_complete"] is False


def test_requester_closed_after_each_chunk(monkeypatch):
    monkeypatch.setattr(
        service_module.GlossaryCandidateService,
        "_collect_corpus",
        lambda self: ([make_item(0, "LUMA waved.")], []),
    )
    monkeypatch.setattr(service_module, "AgentRequester", FakeRequester)
    FakeRequester.responses = ["[]"]

    make_service().run()

    assert FakeRequester.instances
    assert all(requester.closed == 1 for requester in FakeRequester.instances)


def test_cancel_raises_and_closes_requester(monkeypatch):
    monkeypatch.setattr(
        service_module.GlossaryCandidateService,
        "_collect_corpus",
        lambda self: ([make_item(0, "LUMA waved.")], []),
    )

    class SlowRequester(FakeRequester):
        instances = []

        def __init__(self, config, platform, *, thinking_level=None):
            super().__init__(config, platform, thinking_level=thinking_level)
            SlowRequester.instances.append(self)

        def request_text(self, messages, on_text_delta=None, on_reasoning_delta=None):
            raise InterruptedError("stopped")

    monkeypatch.setattr(service_module, "AgentRequester", SlowRequester)

    with pytest.raises(InterruptedError):
        make_service().run()

    assert all(requester.closed == 1 for requester in SlowRequester.instances)


def test_corpus_keeps_character_definitions_and_later_lines(tmp_path):
    game = tmp_path / "game"
    game.mkdir()
    lines = [
        'define e = Character("LUMA")',
        "label start:",
        '    "Hello there."',
        '    e "LUMA is back."',
    ]
    (game / "script.rpy").write_text("\n".join(lines), encoding="utf-8")
    (game / "tl").mkdir()
    (game / "tl" / "ignored.rpy").write_text('"Not a source line."', encoding="utf-8")

    items, _warnings = make_service(target_path=str(game))._collect_corpus()
    texts = [item["text"] for item in items]
    kinds = {item["text"]: item["kind"] for item in items}

    assert 'define e = Character("LUMA")' in texts
    assert kinds['define e = Character("LUMA")'] == "character-definition"
    assert "Hello there." in texts
    assert "LUMA is back." in texts
    assert "Not a source line." not in texts
    speakers = {item["text"]: item.get("speaker", "") for item in items}
    assert speakers["LUMA is back."] == "e"


def test_corpus_source_is_relative_path(tmp_path):
    game = tmp_path / "game"
    nested = game / "sub"
    nested.mkdir(parents=True)
    (nested / "chapter1.rpy").write_text('e "LUMA is here."', encoding="utf-8")

    items, _warnings = make_service(target_path=str(game))._collect_corpus()

    assert [item["source"] for item in items] == ["sub/chapter1.rpy"]
    assert [item["line"] for item in items] == [1]


def test_same_text_on_different_lines_is_kept_once_per_line(tmp_path):
    game = tmp_path / "game"
    game.mkdir()
    lines = [
        'e "LUMA is here."',
        'r "LUMA is here."',
        'e "LUMA is here."',
    ]
    (game / "script.rpy").write_text("\n".join(lines), encoding="utf-8")

    items, _warnings = make_service(target_path=str(game))._collect_corpus()
    same_text = [item for item in items if item["text"] == "LUMA is here."]

    assert len(same_text) == 3, "同一句在不同行/不同说话人下都要保留"
    assert {item["speaker"] for item in same_text} == {"e", "r"}
    assert len({item["line"] for item in same_text}) == 3


def test_duplicate_literal_within_one_line_is_deduped(tmp_path):
    game = tmp_path / "game"
    game.mkdir()
    (game / "script.rpy").write_text('e "Yes. Yes."', encoding="utf-8")

    items, _warnings = make_service(target_path=str(game))._collect_corpus()
    assert [item["text"] for item in items] == ["Yes. Yes."]


def test_extract_character_candidates_filters_agent_type(monkeypatch):
    texts = ["LUMA waved.", "East Square is far."]
    monkeypatch.setattr(
        service_module.GlossaryCandidateService,
        "_collect_corpus",
        lambda self: (
            [make_item(index, text) for index, text in enumerate(texts)],
            [],
        ),
    )
    monkeypatch.setattr(service_module, "AgentRequester", FakeRequester)
    FakeRequester.responses = [
        '{"src": "LUMA", "type": "角色", "line": 0}\n{"src": "East Square", "type": "地名", "line": 1}'
    ]

    payload = make_service().run()
    assert {entry["src"] for entry in payload["entries"]} == {"LUMA", "East Square"}

    FakeRequester.responses = [
        '{"src": "LUMA", "type": "角色", "line": 0}\n{"src": "East Square", "type": "地名", "line": 1}'
    ]
    character = extract_character_candidates(
        config=SimpleNamespace(), target_path=".", platform=dict(PLATFORM)
    )
    assert character["names"] == ["LUMA"]


def test_corpus_read_failure_marks_partial(monkeypatch):
    texts = ["LUMA waved."]
    monkeypatch.setattr(
        service_module.GlossaryCandidateService,
        "_collect_corpus",
        lambda self: ([make_item(0, texts[0])], ["读取源码文件失败：broken.rpy"]),
    )
    monkeypatch.setattr(service_module, "AgentRequester", FakeRequester)
    FakeRequester.responses = ["[]"]

    result = make_service().run()

    assert result["status"] == "partial", "读失败必须反映为部分覆盖"
    assert result["coverage_complete"] is False
    assert any("broken.rpy" in warning for warning in result["warnings"])


def test_source_listing_failure_marks_partial():
    import pathlib

    service = make_service()

    class BoomError(OSError):
        pass

    def boom(self, pattern):
        raise BoomError("boom")

    original = pathlib.Path.rglob
    pathlib.Path.rglob = boom
    try:
        files, warning = service._source_files(pathlib.Path("."))
    finally:
        pathlib.Path.rglob = original

    assert files == []
    assert warning != ""


def test_cancel_stops_active_requester(monkeypatch):
    import threading
    import time as time_module

    entered = threading.Event()

    class BlockingRequester(FakeRequester):
        instances = []

        def __init__(self, config, platform, *, thinking_level=None):
            super().__init__(config, platform, thinking_level=thinking_level)
            BlockingRequester.instances.append(self)

        def request_text(self, messages, on_text_delta=None, on_reasoning_delta=None):
            entered.set()
            deadline = time_module.monotonic() + 3
            while time_module.monotonic() < deadline:
                if self.cancelled:
                    return SimpleNamespace(success=False, text="", error_code="CANCELLED", error_message="")
                time_module.sleep(0.01)
            return SimpleNamespace(success=True, text="[]", error_code="", error_message="")

        def cancel(self):
            FakeRequester.cancel(self)
            self.cancelled = 1

    monkeypatch.setattr(
        service_module.GlossaryCandidateService,
        "_collect_corpus",
        lambda self: ([make_item(0, "LUMA waved.")], []),
    )
    monkeypatch.setattr(service_module, "AgentRequester", BlockingRequester)
    BlockingRequester.instances = []

    checks = {"count": 0}

    def cancelled():
        checks["count"] += 1
        return entered.is_set() and checks["count"] >= 2

    service = make_service(cancel_callback=cancelled)
    with pytest.raises(InterruptedError):
        service.run()

    assert BlockingRequester.instances, "必须真的发出请求"
    assert any(requester.cancelled for requester in BlockingRequester.instances), \
        "取消必须传播到活跃 requester，不能等网络超时"
    assert all(requester.closed == 1 for requester in BlockingRequester.instances)


def test_slow_chunk_times_out_after_starting(monkeypatch):
    import time as time_module

    class SlowRequester(FakeRequester):
        instances = []

        def __init__(self, config, platform, *, thinking_level=None):
            super().__init__(config, platform, thinking_level=thinking_level)
            SlowRequester.instances.append(self)

        def request_text(self, messages, on_text_delta=None, on_reasoning_delta=None):
            time_module.sleep(1.5)
            return SimpleNamespace(success=True, text="[]", error_code="", error_message="")

    monkeypatch.setattr(
        service_module.GlossaryCandidateService,
        "_collect_corpus",
        lambda self: ([make_item(0, "LUMA waved.")], []),
    )
    monkeypatch.setattr(service_module, "AgentRequester", SlowRequester)
    SlowRequester.instances = []
    monkeypatch.setattr(service_module.GlossaryCandidateService, "CHUNK_TIMEOUT_SECONDS", 0.2)

    result = make_service().run()

    assert result["status"] == "failed", "唯一分块超时即为失败"
    assert any("超时" in warning for warning in result["warnings"])
    assert any(requester.cancelled for requester in SlowRequester.instances)
    assert all(requester.closed == 1 for requester in SlowRequester.instances)


def test_all_chunks_settled_returns_without_waiting_forever(monkeypatch):
    import threading
    import time as time_module

    class StuckRequester(FakeRequester):
        instances = []

        def __init__(self, config, platform, *, thinking_level=None):
            super().__init__(config, platform, thinking_level=thinking_level)
            StuckRequester.instances.append(self)

        def request_text(self, messages, on_text_delta=None, on_reasoning_delta=None):
            threading.Event().wait(30)
            return SimpleNamespace(success=True, text="[]", error_code="", error_message="")

    monkeypatch.setattr(
        service_module.GlossaryCandidateService,
        "_collect_corpus",
        lambda self: ([make_item(0, "LUMA waved.")], []),
    )
    monkeypatch.setattr(service_module, "AgentRequester", StuckRequester)
    monkeypatch.setattr(service_module.GlossaryCandidateService, "CHUNK_TIMEOUT_SECONDS", 0.2)
    monkeypatch.setattr(service_module.GlossaryCandidateService, "CLOSE_TIMEOUT_SECONDS", 0.3)

    started = time_module.monotonic()
    result = make_service().run()
    elapsed = time_module.monotonic() - started

    assert elapsed < 20, "超时后必须有界返回，不能无限等待"
    assert result["status"] == "failed"
    assert StuckRequester.instances


def test_all_workers_stuck_returns_within_deadline_two_chunks(monkeypatch):
    import threading
    import time as time_module

    class StuckRequester(FakeRequester):
        instances = []

        def __init__(self, config, platform, *, thinking_level=None):
            super().__init__(config, platform, thinking_level=thinking_level)
            StuckRequester.instances.append(self)

        def request_text(self, messages, on_text_delta=None, on_reasoning_delta=None):
            threading.Event().wait(60)
            return SimpleNamespace(success=True, text="[]", error_code="", error_message="")

    texts = ["LUMA waved.", "Leo left."]
    monkeypatch.setattr(
        service_module.GlossaryCandidateService,
        "_collect_corpus",
        lambda self: ([make_item(index, text) for index, text in enumerate(texts)], []),
    )
    monkeypatch.setattr(service_module, "AgentRequester", StuckRequester)
    monkeypatch.setattr(service_module.GlossaryCandidateService, "CHUNK_CONCURRENCY", 1)
    monkeypatch.setattr(service_module.GlossaryCandidateService, "CHUNK_TIMEOUT_SECONDS", 0.2)
    monkeypatch.setattr(service_module.GlossaryCandidateService, "CLOSE_TIMEOUT_SECONDS", 0.3)

    started = time_module.monotonic()
    result = make_service().run()
    elapsed = time_module.monotonic() - started

    bound = 0.2 + 0.3 + 1.0
    assert elapsed < bound, f"必须在截止时间内返回，实际 {elapsed:.2f}s"
    assert result["status"] == "failed"
    assert len(StuckRequester.instances) == 1, "不得在阻塞时创建额外线程/请求"
    assert result["llm_chunks_success"] == 0
    assert any("块" in warning for warning in result["warnings"])


def test_all_workers_stuck_returns_within_deadline_five_chunks(monkeypatch):
    import threading
    import time as time_module

    class StuckRequester(FakeRequester):
        instances = []

        def __init__(self, config, platform, *, thinking_level=None):
            super().__init__(config, platform, thinking_level=thinking_level)
            StuckRequester.instances.append(self)

        def request_text(self, messages, on_text_delta=None, on_reasoning_delta=None):
            threading.Event().wait(60)
            return SimpleNamespace(success=True, text="[]", error_code="", error_message="")

    texts = [f"Line {index} here." for index in range(5)]
    monkeypatch.setattr(
        service_module.GlossaryCandidateService,
        "_collect_corpus",
        lambda self: ([make_item(index, text) for index, text in enumerate(texts)], []),
    )
    monkeypatch.setattr(service_module, "AgentRequester", StuckRequester)
    monkeypatch.setattr(service_module.GlossaryCandidateService, "CHUNK_CONCURRENCY", 4)
    monkeypatch.setattr(service_module.GlossaryCandidateService, "CHUNK_MAX_ITEMS", 1)
    monkeypatch.setattr(service_module.GlossaryCandidateService, "CHUNK_TIMEOUT_SECONDS", 0.2)
    monkeypatch.setattr(service_module.GlossaryCandidateService, "CLOSE_TIMEOUT_SECONDS", 0.3)

    started = time_module.monotonic()
    result = make_service().run()
    elapsed = time_module.monotonic() - started

    bound = 0.2 + 0.3 + 1.0
    assert elapsed < bound, f"4 个槽全被占满时也必须在截止时间内返回，实际 {elapsed:.2f}s"
    assert result["status"] == "failed"
    assert result["llm_chunks_total"] == 5
    assert len(StuckRequester.instances) == 4, "不得为排队中的块创建额外请求"
    assert result["llm_chunks_success"] == 0
    assert len(result["warnings"]) >= 5, "每个未完成块都要有警告"


def test_candidate_lowercase_is_restored_to_source_casing():
    service = make_service()
    chunk = [make_item(0, "LUMA waved at the gate.")]

    assert service._locate_candidate({"src": "luma", "line": 0}, chunk) == "LUMA"
    assert service._locate_candidate({"src": "Luma", "line": 0}, chunk) == "LUMA"
    assert service._locate_candidate({"src": "LUMA", "line": 0}, chunk) == "LUMA"
    assert service._locate_candidate({"src": "Nottingham", "line": 0}, chunk) is None


def test_non_english_candidate_returns_source_slice():
    service = make_service()
    chunk = [make_item(0, "田中さんはLUMAを見た。")]

    assert service._locate_candidate({"src": "田中さん", "line": 0}, chunk) == "田中さん"
    assert service._locate_candidate({"src": "LUMA", "line": 0}, chunk) == "LUMA"


def test_casefold_expansion_does_not_misplace_slice():
    service = make_service()

    assert service._match_source_slice("luma", "Stra\u00dfe LUMA") == "LUMA"
    assert service._match_source_slice("STRASSE", "Stra\u00dfe LUMA") == "Stra\u00dfe"
    assert service._match_source_slice("strasse", "Stra\u00dfe LUMA") == "Stra\u00dfe"
    assert service._match_source_slice("Luma", "\u0130stanbul LUMA") == "LUMA"
    assert service._match_source_slice("\u0130stanbul", "\u0130stanbul LUMA") == "\u0130stanbul"
    assert service._match_source_slice("Nottingham", "Stra\u00dfe LUMA") is None


def test_casefold_boundary_through_locate_candidate():
    service = make_service()
    chunk = [make_item(0, "Stra\u00dfe LUMA waved.")]

    assert service._locate_candidate({"src": "luma", "line": 0}, chunk) == "LUMA"
    assert service._locate_candidate({"src": "STRASSE", "line": 0}, chunk) == "Stra\u00dfe"


def test_public_entry_points_keep_signature():
    """旧两参数回调契约保持不变；event_callback 是可选新增，不破坏旧调用。"""
    import inspect

    signature = inspect.signature(extract_glossary_candidates)
    assert {
        "config",
        "target_path",
        "platform",
        "progress_callback",
        "cancel_callback",
    } <= set(signature.parameters)
    assert signature.parameters["event_callback"].default is None
    for name in ("progress_callback", "cancel_callback"):
        assert signature.parameters[name].default is None

    character_signature = inspect.signature(extract_character_candidates)
    assert character_signature.parameters["event_callback"].default is None


def test_prompt_excludes_generic_ui_terms_by_semantics():
    """泛用 UI 词靠语义说明排除，不是事后英文词表过滤。"""
    service = make_service()

    prompt = service._build_prompt([make_item(0, "Help")])[0]["content"]

    for token in ("通用界面词", "通用按键", "引擎与运行时名词", "不属于目标"):
        assert token in prompt
    assert "反例" in prompt, "要给出正反 few-shot，而不是只列禁止词"
    assert "evidence" in prompt, "要求模型给出短依据"


def test_prompt_character_mode_mentions_definition_context():
    service = make_service(character_only=True)

    prompt = service._build_prompt([make_item(0, "LUMA")])[0]["content"]

    assert "definition" in prompt
    assert "变量名只是引用" in prompt


def test_chunk_capacity_covers_regular_pages():
    service = make_service()

    assert service.CHUNK_MAX_ITEMS >= 80
    assert service.CHUNK_MAX_CHARS >= 8000


def test_corpus_keeps_define_and_default_lines(tmp_path):
    game = tmp_path / "game"
    game.mkdir()
    lines = [
        'define e = Character("LUMA")',
        'default moon_blade = "Moon Blade"',
        'define guild = "Silver Guild"',
    ]
    (game / "script.rpy").write_text("\n".join(lines), encoding="utf-8")

    items, _warnings = make_service(target_path=str(game))._collect_corpus()
    kinds = {item["text"]: item["kind"] for item in items}

    assert kinds['define e = Character("LUMA")'] == "character-definition"
    assert kinds['default moon_blade = "Moon Blade"'] == "definition"
    assert kinds['define guild = "Silver Guild"'] == "definition"
    assert all(item["text"] for item in items), "整行语境不能被切成裸字面量"


def test_corpus_orders_character_and_dialogue_before_ui(tmp_path):
    game = tmp_path / "game"
    game.mkdir()
    lines = [
        'text "Help"',
        'e "LUMA is back."',
        'define e = Character("LUMA")',
    ]
    (game / "script.rpy").write_text("\n".join(lines), encoding="utf-8")

    items, _warnings = make_service(target_path=str(game))._collect_corpus()
    kinds = [item["kind"] for item in items]

    assert kinds == sorted(kinds, key=lambda name: {"character-definition": 0, "definition": 1, "dialogue": 2, "ui": 3}[name])
    assert [item["id"] for item in items] == list(range(len(items))), "id 必须重排且连续"
    assert len(items) == 3, "排序不得丢语料"


def test_generated_template_files_are_not_sent(tmp_path):
    """内置/生成模板按文件来源排除，属于结构名单而不是词表。"""
    game = tmp_path / "game"
    game.mkdir()
    (game / "script.rpy").write_text('e "LUMA is here."', encoding="utf-8")
    (game / "base_box").mkdir()
    (game / "base_box" / "screens_box.rpy").write_text('text "Help"', encoding="utf-8")
    (game / "base_box" / "generated.rpy").write_text('text "History"', encoding="utf-8")

    items, _warnings = make_service(target_path=str(game))._collect_corpus()
    texts = [item["text"] for item in items]

    assert "LUMA is here." in texts
    assert "Help" not in texts
    assert "History" not in texts


def test_progress_events_follow_shared_contract(monkeypatch):
    """结构化快照字段与去重上限必须与共享契约一致。"""
    events: list[dict] = []
    texts = ["LUMA waved.", "Leo left."]
    monkeypatch.setattr(
        service_module.GlossaryCandidateService,
        "_collect_corpus",
        lambda self: ([make_item(index, text) for index, text in enumerate(texts)], []),
    )
    monkeypatch.setattr(service_module, "AgentRequester", FakeRequester)
    monkeypatch.setattr(service_module.GlossaryCandidateService, "CHUNK_MAX_ITEMS", 1)
    FakeRequester.responses = [
        '{"src": "LUMA", "type": "角色", "line": 0, "evidence": "角色定义中的显示名"}',
        '{"src": "Leo", "type": "角色", "line": 1}',
    ]

    service = make_service(event_callback=events.append)
    result = service.run()

    assert events, "必须真的发出过事件"
    snapshot = events[-1]
    assert snapshot["phase"] == "completed"
    for field in ("total_chunks", "completed_chunks", "successful_chunks", "failed_chunks", "pending_chunks"):
        assert isinstance(snapshot[field], int) and snapshot[field] >= 0
    assert snapshot["pending_chunks"] == 0
    assert snapshot["successful_chunks"] == result["llm_chunks_total"]
    assert isinstance(snapshot["elapsed_seconds"], (int, float)) and snapshot["elapsed_seconds"] >= 0
    assert snapshot["candidate_count"] >= 1
    assert len(snapshot["candidates"]) <= 20
    assert all("src" in item for item in snapshot["candidates"])
    # 临时候选不得进入最终 entries 之外的落盘结构。
    assert result["entries"] and "evidence" not in result["entries"][0]


def test_event_callback_is_optional(monkeypatch):
    monkeypatch.setattr(
        service_module.GlossaryCandidateService,
        "_collect_corpus",
        lambda self: ([make_item(0, "LUMA waved.")], []),
    )
    monkeypatch.setattr(service_module, "AgentRequester", FakeRequester)
    FakeRequester.responses = ["[]"]

    assert make_service().run()["status"] == "completed"


def test_healthy_chunks_run_after_one_timeout(monkeypatch):
    """单块超时只结算该块，健康工作槽继续消费队列。"""
    import time as time_module

    class MixedRequester(FakeRequester):
        instances = []
        order = 0

        def __init__(self, config, platform, *, thinking_level=None):
            super().__init__(config, platform, thinking_level=thinking_level)
            MixedRequester.instances.append(self)
            self.index = MixedRequester.order
            MixedRequester.order += 1

        def request_text(self, messages, on_text_delta=None, on_reasoning_delta=None):
            if self.index == 0:
                time_module.sleep(1.2)
                return SimpleNamespace(success=True, text="[]", error_code="", error_message="")
            return SimpleNamespace(success=True, text="[]", error_code="", error_message="")

    texts = ["first", "second", "third"]
    monkeypatch.setattr(
        service_module.GlossaryCandidateService,
        "_collect_corpus",
        lambda self: ([make_item(index, text) for index, text in enumerate(texts)], []),
    )
    monkeypatch.setattr(service_module, "AgentRequester", MixedRequester)
    # 两个槽：一个槽被不返回的超时块占住时，另一个槽必须继续消费队列。
    monkeypatch.setattr(service_module.GlossaryCandidateService, "CHUNK_CONCURRENCY", 2)
    monkeypatch.setattr(service_module.GlossaryCandidateService, "CHUNK_MAX_ITEMS", 1)
    monkeypatch.setattr(service_module.GlossaryCandidateService, "CHUNK_TIMEOUT_SECONDS", 0.2)
    monkeypatch.setattr(service_module.GlossaryCandidateService, "CLOSE_TIMEOUT_SECONDS", 0.3)
    MixedRequester.order = 0
    MixedRequester.instances = []

    started = time_module.monotonic()
    result = make_service().run()
    elapsed = time_module.monotonic() - started

    assert result["llm_chunks_total"] == 3
    assert result["llm_chunks_success"] == 2, "超时块之后的健康块必须继续执行"
    assert len(MixedRequester.instances) == 3, "每个块都要有机会启动"
    assert result["status"] == "partial"
    assert elapsed < 10


def test_coverage_limit_marks_result_incomplete(monkeypatch):
    texts = [f"line {index}" for index in range(6)]
    monkeypatch.setattr(
        service_module.GlossaryCandidateService,
        "_collect_corpus",
        lambda self: (
            [make_item(index, text) for index, text in enumerate(texts)],
            [],
        ),
    )
    monkeypatch.setattr(service_module, "AgentRequester", FakeRequester)
    monkeypatch.setattr(service_module.GlossaryCandidateService, "CHUNK_MAX_ITEMS", 1)
    monkeypatch.setattr(service_module.GlossaryCandidateService, "MAX_LLM_CHUNKS", 2)
    FakeRequester.responses = ["[]", "[]"]

    result = make_service().run()

    assert result["llm_chunks_total"] == 2
    assert result["coverage_complete"] is False
    assert any("未分析部分不算完成" in warning for warning in result["warnings"])


def test_definitions_without_display_text_stay_out_of_corpus(tmp_path):
    game = tmp_path / "game"
    game.mkdir()
    lines = [
        "default tall_in = 0",
        "define gui.text_size = 33",
        "init python:",
        "define stats = (",
        "    0",
        ")",
        "define h = Character('History')",
        'default hero_name = "Luma"',
        "define luna = Character(",
        '    "Astrid"',
        ")",
    ]
    (game / "script.rpy").write_text("\n".join(lines), encoding="utf-8")

    items, _warnings = make_service(target_path=str(game))._collect_corpus()
    texts = [item["text"] for item in items]

    assert not any("tall_in" in text or "text_size" in text or "init python" in text for text in texts)
    assert not any(text.strip() in {"0", "define stats = (", ")"} for text in texts)
    assert "define h = Character('History')" in texts
    assert 'default hero_name = "Luma"' in texts
    assert any("Astrid" in text for text in texts)


def test_context_noise_drops_code_tokens_and_keeps_plain_names():
    normalize = GlossaryCandidateService._normalize_context
    for noise in ("my_style", "K_ESCAPE", "mouseup_3", "quick_save", "clarissa_school01_breath1", "breath2"):
        assert normalize(noise) == ""
    for name in ("Astrid", "Park", "Ox", "Luma", "Eastwatch"):
        assert normalize(name) == name
    assert normalize("Park walked home") == "Park walked home"
    assert GlossaryCandidateService._normalize_definition('define h = Character("History")').startswith("define h")


def test_extraction_uses_config_thinking_level(monkeypatch):
    monkeypatch.setattr(
        service_module.GlossaryCandidateService,
        "_collect_corpus",
        lambda self: ([make_item(0, "LUMA waved.")], []),
    )
    monkeypatch.setattr(service_module, "AgentRequester", FakeRequester)
    FakeRequester.responses = ["[]"]
    config = SimpleNamespace(agent_thinking_level="LOW")

    make_service(config=config).run()

    assert FakeRequester.instances
    assert FakeRequester.instances[-1].thinking_level == "LOW"


def test_reasoning_buffer_keeps_the_tail_and_only_active_chunks():
    progress = ExtractionProgress()
    progress.append_reasoning(0, "ab")
    progress.append_reasoning(0, "cd")
    progress.append_reasoning(1, "other")
    progress.chunk_started(0)
    visible = progress.snapshot()["active_chunks"]
    assert len(visible) == 1
    assert visible[0]["reasoning"] == "abcd"
    progress.append_reasoning(0, "x" * (REASONING_MAX_CHARS + 50))
    tail = progress.snapshot()["active_chunks"][0]["reasoning"]
    assert tail == "x" * REASONING_MAX_CHARS
    progress.clear_reasoning(0)
    assert progress.snapshot()["active_chunks"][0]["reasoning"] == ""
    assert 0 not in progress._reasoning


def test_request_chunk_feeds_reasoning_into_the_active_snapshot():
    service = make_service()
    requester = FakeRequester(None, PLATFORM)
    requester.reasoning_deltas = ["think ", "about Luma"]
    FakeRequester.responses = ["[]"]
    service.progress.chunk_started(0)

    success, payload = service._request_chunk(0, [make_item(0, "LUMA waved.")], requester)

    assert success is True and payload == []
    assert requester.on_reasoning_delta is not None
    assert service.progress.snapshot()["active_chunks"][0]["reasoning"] == "think about Luma"


def test_reasoning_is_not_stored_on_entries(monkeypatch):
    monkeypatch.setattr(
        service_module.GlossaryCandidateService,
        "_collect_corpus",
        lambda self: ([make_item(0, "LUMA waved.")], []),
    )
    monkeypatch.setattr(service_module, "AgentRequester", FakeRequester)
    FakeRequester.responses = ['{"src": "LUMA", "type": "角色", "line": 0}']
    original = FakeRequester.request_text

    def request_text(self, messages, on_text_delta=None, on_reasoning_delta=None):
        self.reasoning_deltas = ["hidden thought"]
        return original(self, messages, on_text_delta, on_reasoning_delta)

    monkeypatch.setattr(FakeRequester, "request_text", request_text)
    service = make_service()
    result = service.run()

    assert {entry["src"] for entry in result["entries"]} == {"LUMA"}
    assert all("reasoning" not in entry for entry in result["entries"])
    assert "reasoning" not in result
    assert "extraction_progress" not in result
    assert service.progress._reasoning == {}


def test_agent_failure_message_keeps_reason_and_redacts_key(monkeypatch):
    from base.Base import Base
    from module.Agent.AgentRequester import AgentRequester
    from module.Config import Config

    requester = AgentRequester(
        Config(),
        {
            "api_key": ["test-key"],
            "api_url": "https://example.invalid/v1",
            "api_format": Base.APIFormat.OPENAI,
            "model": "test-model",
        },
    )

    class Boom(RuntimeError):
        status_code = 503

    def raise_boom(*_args, **_kwargs):
        raise Boom("read timeout sk-abcDEF123456\nbody " + ("x" * 400))

    monkeypatch.setattr(requester, "_request_openai", raise_boom)
    result = requester.request_tools([{"role": "user", "content": "hi"}], [])

    assert result.success is False
    assert result.error_code == "REQUEST_FAILED"
    assert "Boom" in result.error_message
    assert "503" in result.error_message
    assert "read timeout" in result.error_message
    assert "sk-abcDEF123456" not in result.error_message
    assert "sk-***" in result.error_message
    assert "\n" not in result.error_message
    assert len(result.error_message) < 220
