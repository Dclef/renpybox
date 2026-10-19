"""Regression checks for issues found during real-game verification."""
from __future__ import annotations
import os
import threading
from types import SimpleNamespace
import pytest
from module.Engine.TaskRequester import TaskRequester
from module.Extract.GlossaryCandidateService import GlossaryCandidateService
from module.Workbench.AnalysisService import WorkbenchAnalysisService
from module.Workbench.CharacterScanner import CharacterScanner


def make_service(**kwargs):
    return GlossaryCandidateService(config=SimpleNamespace(), target_path=".", platform=None, **kwargs)


def test_glossary_workers_inherit_caller_cancellation(monkeypatch):
    service = make_service()
    event = threading.Event()
    def fake_extract(chunk, index, *, known_terms=()):
        assert getattr(TaskRequester.RUN_CANCEL_CONTEXT, "event", None) is event
        return True, [{"src": "East Square", "type": "地名"}]
    monkeypatch.setattr(service, "_extract_chunk_with_llm", fake_extract)
    TaskRequester.bind_run_cancel_event(event)
    try:
        success, payloads, warnings = service._run_llm_chunks([["East Square"]], [])
    finally:
        TaskRequester.unbind_run_cancel_event()
    assert success == 1 and len(payloads) == 1 and warnings == []


def test_glossary_payloads_keep_input_order_when_second_finishes_first(monkeypatch):
    reported = threading.Event()
    service = make_service(progress_callback=lambda message, percent: reported.set())
    def fake_extract(chunk, index, *, known_terms=()):
        if index == 0:
            assert reported.wait(3)
            return True, [{"src": "ARIA", "type": "地名", "origin": "llm"}]
        return True, [{"src": "Aria", "type": "角色", "origin": "llm"}]
    monkeypatch.setattr(service, "_extract_chunk_with_llm", fake_extract)
    _, payloads, _ = service._run_llm_chunks([["a"], ["b"]], [])
    assert [payload[0]["src"] for payload in payloads] == ["ARIA", "Aria"]


@pytest.mark.parametrize("owner", [WorkbenchAnalysisService, CharacterScanner])
def test_source_cache_detects_same_size_edit_before_latest_mtime(tmp_path, owner):
    game = tmp_path / "game"
    game.mkdir()
    old = game / "characters.rpy"
    newest = game / "script.rpy"
    old.write_text('define e = Character("Alice")', encoding="utf-8")
    newest.write_text('e "Hello there."', encoding="utf-8")
    os.utime(old, ns=(1_000_000_000, 1_000_000_000))
    os.utime(newest, ns=(9_000_000_000, 9_000_000_000))
    def fingerprint():
        if owner is WorkbenchAnalysisService:
            return owner._source_fingerprint(game)
        return owner._fingerprint(sorted(game.glob("*.rpy")))
    first = fingerprint()
    old.write_text('define e = Character("Betty")', encoding="utf-8")
    os.utime(old, ns=(2_000_000_000, 2_000_000_000))
    assert fingerprint() != first


@pytest.mark.parametrize("owner", [WorkbenchAnalysisService, CharacterScanner])
def test_source_cache_detects_rename(tmp_path, owner):
    game = tmp_path / "game"
    game.mkdir()
    (game / "a.rpy").write_text('e "Hello there."', encoding="utf-8")
    (game / "b.rpy").write_text('e "Second one."', encoding="utf-8")
    def fingerprint():
        if owner is WorkbenchAnalysisService:
            return owner._source_fingerprint(game)
        return owner._fingerprint(sorted(game.glob("*.rpy")))
    first = fingerprint()
    os.rename(game / "a.rpy", game / "c.rpy")
    second = fingerprint()
    assert second[0] == first[0] == 2
    assert second != first


def test_glossary_cancel_skips_queued_chunks(monkeypatch):
    service = make_service()
    service.LLM_CHUNK_CONCURRENCY = 1
    event = threading.Event()
    called = []
    def fake_extract(chunk, index, *, known_terms=()):
        called.append(index)
        event.set()
        return True, [{"src": f"Term{index}", "type": "术语"}]
    monkeypatch.setattr(service, "_extract_chunk_with_llm", fake_extract)
    TaskRequester.bind_run_cancel_event(event)
    try:
        with pytest.raises(InterruptedError):
            service._run_llm_chunks([["a"], ["b"], ["c"]], [])
    finally:
        TaskRequester.unbind_run_cancel_event()
    assert called == [0]


def test_glossary_cancel_waits_for_running_chunk(monkeypatch):
    import time
    cancelled = threading.Event()
    service = make_service(cancel_callback=cancelled.is_set)
    started = threading.Event()
    finished = threading.Event()
    def fake_extract(chunk, index, *, known_terms=()):
        if index == 0:
            assert started.wait(3)
            cancelled.set()
            return True, [{"src": "Alpha", "type": "术语"}]
        started.set()
        time.sleep(0.3)
        finished.set()
        return True, [{"src": "Beta", "type": "术语"}]
    monkeypatch.setattr(service, "_extract_chunk_with_llm", fake_extract)
    with pytest.raises(InterruptedError):
        service._run_llm_chunks([["a"], ["b"]], [])
    assert finished.is_set()


def test_source_fingerprint_ignores_ancestor_directory_names(tmp_path):
    game = tmp_path / "cache" / "tl" / "project" / "game"
    game.mkdir(parents=True)
    (game / "script.rpy").write_text('e "Hello."', encoding="utf-8")
    assert WorkbenchAnalysisService._source_fingerprint(game)[0] == 1


def test_character_scan_ignores_ancestor_directory_names(tmp_path):
    game = tmp_path / "cache" / "tl" / "project" / "game"
    game.mkdir(parents=True)
    (game / "script.rpy").write_text('define a = Character("Alice")\nlabel start:\n    a "Hello there, friend."\n', encoding="utf-8")
    assert CharacterScanner().scan_project(game.parent).names == {"Alice"}


def test_cancelled_source_parse_is_not_cached(tmp_path, monkeypatch):
    from module.Cache.CacheItem import CacheItem
    from module.Workbench import AnalysisService as service_module
    game = tmp_path / "project" / "game"
    game.mkdir(parents=True)
    (game / "script.rpy").write_text('e "Hello there."', encoding="utf-8")
    event = threading.Event()
    calls = []
    class FakeManager:
        def __init__(self, config):
            pass
        def read_from_path(self):
            calls.append(1)
            if len(calls) == 1:
                event.set()
                return object(), []
            item = CacheItem()
            item.set_src("Hello there.")
            return object(), [item]
    monkeypatch.setattr(service_module, "FileManager", FakeManager)
    config = SimpleNamespace(input_folder=str(game), output_folder=str(tmp_path / "output"), project_dir=str(game.parent))
    service = WorkbenchAnalysisService()
    TaskRequester.bind_run_cancel_event(event)
    try:
        service.load_full_project_items(config)
    finally:
        TaskRequester.unbind_run_cancel_event()
    assert len(service.load_full_project_items(config)) == 1
    assert len(calls) == 2
