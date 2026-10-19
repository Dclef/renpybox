"""Slow requests must emit status before returning and stop observers on exit."""
from __future__ import annotations

import threading
from functools import partial
from types import SimpleNamespace

import pytest

from module.Engine.RequestProgress import request_progress
from module.Extract import GlossaryCandidateService as glossary_module
from module.Workbench import AnalysisService as analysis_module


@pytest.mark.parametrize("kind", ["glossary", "worldbook"])
def test_slow_request_reports_waiting_before_response(monkeypatch, kind):
    waiting = threading.Event()
    records = []

    def report(message):
        records.append(message)
        if "等待模型响应中" in message:
            waiting.set()

    class FakeRequester:
        def __init__(self, *args, **kwargs):
            pass

        def request(self, messages, response_shape="none"):
            # The status must be emitted while this request is still blocked.
            assert waiting.wait(2), "No in-flight progress was reported"
            return False, "测试思考摘要", '{"src":"East Square","dst":"","type":"地名"}', 80, 20

    module = glossary_module if kind == "glossary" else analysis_module
    monkeypatch.setattr(module, "TaskRequester", FakeRequester)
    monkeypatch.setattr(module, "request_progress", partial(request_progress, interval=0.01))
    if kind == "glossary":
        service = module.GlossaryCandidateService(config=SimpleNamespace(), target_path=".", platform={"api_format":"OpenAI"})
        monkeypatch.setattr(service, "info", report)
        success, entries = service._extract_chunk_with_llm(["We met at East Square."], 0)
        assert success and entries[0]["src"] == "East Square"
    else:
        service = module.WorkbenchAnalysisService()
        monkeypatch.setattr(service, "info", report)
        assert service.request_json_text(SimpleNamespace(), {}, "Test prompt")
    assert any("思考" in message for message in records)
    assert not [thread for thread in threading.enumerate() if thread.name == "model-progress"]


def test_progress_observer_stops_when_request_raises():
    observed = threading.Event()
    observers = []

    def report(message):
        observers.append(threading.current_thread())
        observed.set()

    with pytest.raises(RuntimeError, match="request failed"):
        with request_progress(report, "测试请求", interval=0.01):
            assert observed.wait(2)
            raise RuntimeError("request failed")
    assert observers and all(not thread.is_alive() for thread in observers)
