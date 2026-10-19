"""术语候选扫描：规则通道判定、LLM 分块提示词与思考日志。"""

from __future__ import annotations

from types import SimpleNamespace

import module.Extract.GlossaryCandidateService as service_module
from module.Extract.GlossaryCandidateService import GlossaryCandidateService


def make_service(**kwargs) -> GlossaryCandidateService:
    options = {
        "config": SimpleNamespace(),
        "target_path": ".",
        "platform": {"api_format": "OpenAI", "api_url": "http://localhost", "model": "test"},
    }
    options.update(kwargs)
    return GlossaryCandidateService(**options)


def test_prompt_chunks_respect_size_and_char_limits():
    service = make_service()
    texts = [f"line-{index}" for index in range(100)]

    chunks = service._build_prompt_chunks(texts)

    assert sum(len(chunk) for chunk in chunks) == 100
    for chunk in chunks:
        assert len(chunk) <= service.MAX_LLM_CHUNK_ITEMS
        assert sum(len(text) for text in chunk) <= service.MAX_LLM_CHUNK_CHARS or len(chunk) == 1


def test_prompt_chunks_truncate_long_lines():
    service = make_service()
    long_line = "A" * (service.MAX_LLM_LINE_CHARS + 500)

    chunks = service._build_prompt_chunks([long_line])

    assert len(chunks) == 1
    assert len(chunks[0][0]) == service.MAX_LLM_LINE_CHARS


def test_candidate_prompt_includes_known_terms_hint():
    service = make_service()

    prompt = service._build_candidate_prompt(["Leo went to the market."], ["Leo", "Alice"])[0]["content"]

    assert "参考：本地规则" in prompt
    assert "Leo" in prompt
    assert "Alice" in prompt


def test_candidate_prompt_skips_empty_known_terms():
    service = make_service()

    prompt = service._build_candidate_prompt(["Leo went home."], ["", "  "])[0]["content"]

    assert "参考：本地规则" not in prompt


def test_candidate_prompt_requires_proper_noun_judgement():
    service = make_service()

    prompt = service._build_candidate_prompt(["Something happened."])[0]["content"]

    # 提示词必须明确排除日常词汇/按钮/变量，否则模型会把句首大写词也报上来。
    for token in ("特定的名字", "按钮", "变量", "纯数字", "JSONLINE"):
        assert token in prompt


def test_llm_exchange_logs_thinking_and_usage(monkeypatch):
    service = make_service()
    lines: list[str] = []
    service.info = lambda message: lines.append(message)

    service._log_llm_exchange(0, 12, "weigh  which nouns are proper…", 321, 45, 2.5)

    assert any("思考片段" in line for line in lines)
    assert any("tokens 321/45" in line for line in lines)
    assert any("耗时 2.5s" in line for line in lines)


def test_llm_exchange_logs_without_thinking(monkeypatch):
    service = make_service()
    lines: list[str] = []
    service.info = lambda message: lines.append(message)

    service._log_llm_exchange(3, 5, "", 10, 20, 1.0)

    assert not any("思考片段" in line for line in lines)
    assert any("tokens 10/20" in line for line in lines)


def test_extract_chunk_uses_known_terms_and_reports_tokens(monkeypatch):
    service = make_service()
    captured: dict[str, object] = {}

    class FakeRequester:
        def __init__(self, config, platform, index):
            captured["index"] = index

        def request(self, messages, response_shape="none"):
            captured["prompt"] = messages[0]["content"]
            return False, "thinking text", '{"src": "Leo", "dst": "", "type": "角色"}', 100, 20

    monkeypatch.setattr(service_module, "TaskRequester", FakeRequester)
    lines: list[str] = []
    service.info = lambda message: lines.append(message)

    success, payload = service._extract_chunk_with_llm(["Leo waved."], 0, known_terms = ["Alice"])

    assert success is True
    assert payload[0]["src"] == "Leo"
    assert payload[0]["origin"] == "llm"
    assert "Alice" in str(captured["prompt"])
    assert any("tokens 100/20" in line for line in lines)


def test_extract_chunk_reports_empty_response(monkeypatch):
    service = make_service()

    class FakeRequester:
        def __init__(self, *args, **kwargs):
            pass

        def request(self, messages, response_shape="none"):
            return False, "", "", 0, 0

    monkeypatch.setattr(service_module, "TaskRequester", FakeRequester)

    success, payload = service._extract_chunk_with_llm(["text"], 2)

    assert success is False
    assert "第 3 个分块" in str(payload)


def test_candidate_prompt_requests_empty_array_when_no_terms():
    service = make_service()

    prompt = service._build_candidate_prompt(["Something happened."])[0]["content"]

    assert "只输出 []" in prompt


def _fake_requester_returning(text):
    class FakeRequester:
        def __init__(self, *args, **kwargs):
            pass

        def request(self, messages, response_shape="none"):
            return False, "", text, 1, 1

    return FakeRequester


def test_extract_chunk_accepts_valid_empty_array(monkeypatch):
    for text in ("[]", "  [ ]\n", "```json\n[]\n```"):
        service = make_service()
        monkeypatch.setattr(service_module, "TaskRequester", _fake_requester_returning(text))

        assert service._extract_chunk_with_llm(["text"], 0) == (True, [])


def test_extract_chunk_still_rejects_malformed_output(monkeypatch):
    for text in ("[oops", "no terms here", "[]\n extra"):
        service = make_service()
        monkeypatch.setattr(service_module, "TaskRequester", _fake_requester_returning(text))

        success, payload = service._extract_chunk_with_llm(["text"], 1)

        assert success is False, text
        assert "第 2 个分块" in str(payload)


def test_empty_array_chunk_counts_as_success_without_warning(monkeypatch):
    service = make_service()
    monkeypatch.setattr(service_module, "TaskRequester", _fake_requester_returning("[]"))

    succeeded, payloads, warnings = service._run_llm_chunks([["a"], ["b"]], [])

    assert succeeded == 2
    assert payloads == [[], []]
    assert warnings == []


def test_rule_channel_prefers_speaking_characters(monkeypatch):
    service = make_service()
    from module.Extract import ProperNounDetector as detector_module

    class FakeScanner:
        def __init__(self):
            pass

        def scan_project(self, project_root, progress=None):
            return SimpleNamespace(
                names = {"Leo", "Soldier"},
                speaker_counts = {"Leo": 12},
            )

    monkeypatch.setattr(service_module, "CharacterScanner", FakeScanner)
    monkeypatch.setattr(
        detector_module.ProperNounDetector,
        "detect",
        lambda self, evidence: ["Alice"],
    )

    evidence = SimpleNamespace(words = {}, phrases = {})
    candidates = service._collect_rule_candidates(["Leo: hi", "Alice smiled."], "." , evidence)

    sources = {item["src"]: item for item in candidates}
    assert "Leo" in sources
    assert sources["Leo"]["type"] == "角色"
    assert "Alice" in sources
    assert sources["Alice"]["origin"] == "rule_phrase"


def test_looks_like_code_line_filters_script_statements():
    service = make_service()

    assert service._looks_like_code_line("wait_event('e1', 'e2') and delta_day('d1')") is True
    assert service._looks_like_code_line("show screen calendar with dissolve") is True
    assert service._looks_like_code_line("images/bg room.png") is True
    assert service._looks_like_code_line("Leo went to the market.") is False
    assert service._looks_like_code_line("{b}Notice Board{/b}") is False


def test_select_llm_texts_skips_known_and_stopwords():
    from module.Extract.ProperNounDetector import CorpusEvidence

    service = make_service()
    texts = [
        "Leo waved at Alice.",
        "Leo went to the East Square.",
        "The queen waved at Leo.",
    ]
    evidence = CorpusEvidence(texts)

    selected = service._select_llm_texts(texts, evidence, ["Leo", "Alice"])

    # 只含已知名的行没必要再问模型；queen 是停用词也不驱动选样；
    # 只有东广场（未被规则通道收录）才值得问。
    assert "Leo waved at Alice." not in selected
    assert "The queen waved at Leo." not in selected
    assert "Leo went to the East Square." in selected


def test_pick_coverage_lines_prefers_readable_context():
    from module.Extract.ProperNounDetector import CorpusEvidence

    service = make_service()
    texts = [
        "Zyx",
        "She whispered that Zyx would return before dawn broke over the hills.",
    ]
    evidence = CorpusEvidence(texts)

    selected = service._pick_coverage_lines(texts, {"zyx"}, evidence, 1)

    assert len(selected) == 1
    assert "whispered" in selected[0]


def test_run_llm_chunks_runs_in_parallel(monkeypatch):
    import threading

    service = make_service()
    barrier = threading.Barrier(3, timeout = 5)
    seen_threads: set[str] = set()

    def fake_extract(chunk, index, *, known_terms = ()):
        seen_threads.add(threading.current_thread().name)
        barrier.wait()
        return True, [{"src": f"Term{index}", "dst": "", "type": "术语"}]

    monkeypatch.setattr(service, "_extract_chunk_with_llm", fake_extract)

    success, payloads, warnings = service._run_llm_chunks([["a"], ["b"], ["c"]], [])

    assert success == 3
    assert len(payloads) == 3
    assert warnings == []
    assert len(seen_threads) == 3


def test_llm_only_candidates_require_corpus_proper_name_evidence():
    from module.Extract.ProperNounDetector import CorpusEvidence

    service = make_service()
    evidence = CorpusEvidence([
        "We drove to the Castle.",
        "The castle is old.",
        "I visited the East Square.",
        "I returned to the East Square.",
        "The bar is called Sisterhood.",
        "{b}Red Pearl{/b}",
        "Yeah, it's like mount Fuji, you just get to see it once.",
        "Sasha waved from the station.",
        "Open Inventory with the Button.",
        'I heard about "The Organize" yesterday.',
    ])
    candidates = [
        {"src": "Castle", "origins": {"llm"}},
        {"src": "East Square", "origins": {"llm"}},
        {"src": "Sisterhood", "origins": {"llm"}},
        {"src": "Red Pearl", "origins": {"llm"}},
        {"src": "Sasha", "origins": {"llm"}},
        {"src": "Mount Fuji", "type": "地名", "origins": {"llm"}},
        {"src": "Inventory", "origins": {"llm"}},
        {"src": "Button", "origins": {"llm"}},
        {"src": "The Organize", "origins": {"llm"}},
        {"src": "Castle", "origins": {"rule_phrase"}},
    ]

    filtered, rejected = service._filter_unsupported_llm_candidates(candidates, evidence)

    assert rejected == 3
    assert {item["src"] for item in filtered} == {
        "East Square", "Sisterhood", "Red Pearl", "Sasha", "Mount Fuji", "The Organize", "Castle"
    }
    assert any(item["origins"] == {"rule_phrase"} for item in filtered if item["src"] == "Castle")


def test_evidence_keeps_named_and_lowercase_game_terms():
    from module.Extract.ProperNounDetector import CorpusEvidence

    service = make_service()
    lines = [
        "We called it... The Cemetery of the living dead!",
        "She called me ‘The skeleton flogger.’ Do you know anything about that?",
        "The book I read was {i}Devil May Die{/i}.",
        "The mysterious HPL virus continues to spread.",
        "I have to bring the Mana potion to her.",
        "Make her drink this Mana potion.",
        "Group corruption magic is a work in progress.",
        "Group corruption magic was really strong.",
        "I have to complete the awakening ritual.",
        "The awakening ritual ends before summer.",
        "Destroy the cult's artifact: the cursed trapezohedron.",
        "The amulet resonated with the Trapezohedron.",
    ]
    types = {
        "Cemetery of the living dead": "地名",
        "The skeleton flogger": "角色",
        "Devil May Die": "物品",
        "Hpl virus": "术语",
        "Mana potion": "物品",
        "group corruption magic": "术语",
        "awakening ritual": "术语",
        "cursed trapezohedron": "物品",
        "Trapezohedron": "物品",
    }
    entries = [{"src": src, "type": kind, "origins": {"llm"}} for src, kind in types.items()]

    filtered, rejected = service._filter_unsupported_llm_candidates(entries, CorpusEvidence(lines))

    assert rejected == 0
    assert {item["src"] for item in filtered} == set(types)


def test_evidence_rejects_hallucinations_and_ordinary_lowercase_phrases():
    from module.Extract.ProperNounDetector import CorpusEvidence

    service = make_service()
    lines = [
        "Buy a {b}chamomile tea{/b} for her.",
        "We returned to the castle.",
        "He brought chamomile tea again.",
        "She called me silly.",
    ]
    entries = [
        {"src": src, "type": kind, "origins": {"llm"}}
        for src, kind in [
            ("Chamomile tea", "物品"), ("Castle", "地名"),
            ("Nottingham", "地名"), ("Silly", "角色"),
            ("Invented Magic", "术语"),
        ]
    ]

    filtered, rejected = service._filter_unsupported_llm_candidates(entries, CorpusEvidence(lines))

    assert filtered == []
    assert rejected == len(entries)


def test_short_names_are_selected_for_ai_and_pass_grounding():
    from module.Extract.ProperNounDetector import CorpusEvidence

    service = make_service()
    texts = ["Her name was Ann.", "We met Lee by the river.", "The boy is named Jo."]
    evidence = CorpusEvidence(texts)

    assert set(service._select_llm_texts(texts, evidence, [])) == set(texts)
    candidates = [{"src": name, "type": "角色", "origins": {"llm"}} for name in ("Ann", "Lee", "Jo")]
    filtered, rejected = service._filter_unsupported_llm_candidates(candidates, evidence)
    assert rejected == 0
    assert len(filtered) == 3


def test_coverage_selection_checks_cancellation():
    import pytest
    from module.Extract.ProperNounDetector import CorpusEvidence

    checks = 0

    def cancelled():
        nonlocal checks
        checks += 1
        return checks >= 3

    service = make_service(cancel_callback=cancelled)
    texts = [f"We met Zyx near the station on day {index}." for index in range(400)]
    with pytest.raises(InterruptedError, match="已停止"):
        service._pick_coverage_lines(texts, {"zyx"}, CorpusEvidence(texts), 1)
    assert checks == 3


def test_run_warns_when_character_budget_truncates_selected_contexts(monkeypatch):
    service = make_service()
    service.MAX_LLM_CHUNKS = 2
    service.MAX_LLM_CHUNK_CHARS = 100
    texts = [f"We met Zyx outside the old palace and waited by the western gate, number {index}." for index in range(5)]
    monkeypatch.setattr(service_module, "collect_glossary_candidate_texts", lambda *args, **kwargs: texts)
    monkeypatch.setattr(service, "_collect_rule_candidates", lambda *args: [])
    monkeypatch.setattr(service, "_select_llm_texts", lambda *args: texts)
    sent = []

    def fake_run(chunks, known_terms):
        sent.extend(chunks)
        return len(chunks), [], []

    monkeypatch.setattr(service, "_run_llm_chunks", fake_run)
    result = service.run()

    assert len(sent) == 2
    assert result["llm_chunks_total"] == 2
    assert any("2/5" in warning and "低频专名" in warning for warning in result["warnings"])
