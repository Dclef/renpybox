"""术语扫描 / 工作台分析请求的思考档位封顶。"""

from __future__ import annotations

import copy
from types import SimpleNamespace

import pytest

import module.Extract.GlossaryCandidateService as glossary_module
import module.Workbench.AnalysisService as analysis_module
from module.Extract.GlossaryCandidateService import GlossaryCandidateService
from module.Workbench.AnalysisRequestPolicy import build_analysis_platform
from module.Workbench.AnalysisService import WorkbenchAnalysisService


def make_platform(thinking):
    return {
        "api_format": "OpenAI",
        "api_url": "http://localhost",
        "api_key": ["secret-key"],
        "model": "deepseek-ai/DeepSeek-V4.1-Flash",
        "thinking": thinking,
        "extra_body": {"nested": {"keep": 1}},
    }


@pytest.mark.parametrize("level", ["MEDIUM", "HIGH", "MAX", "max"])
def test_high_levels_capped_to_low_on_copy(level):
    platform = make_platform({"level": level, "budget": 99})
    original = copy.deepcopy(platform)
    logs: list[str] = []

    capped = build_analysis_platform(platform, logs.append)

    assert capped is not platform
    assert capped["thinking"] == {"level": "LOW", "budget": 99}
    assert platform == original
    assert capped["thinking"] is not platform["thinking"]
    assert capped["extra_body"] == original["extra_body"]
    assert capped["extra_body"] is not platform["extra_body"]
    assert {key: value for key, value in capped.items() if key != "thinking"} == {
        key: value for key, value in original.items() if key != "thinking"
    }
    assert logs == [f"分析请求思考档位：{level.upper()} → LOW"]
    assert "secret-key" not in logs[0]


@pytest.mark.parametrize("thinking", [{"level": "OFF"}, {"level": "LOW"}, False, None])
def test_off_and_low_preserved(thinking):
    platform = make_platform(thinking)
    logs: list[str] = []

    result = build_analysis_platform(platform, logs.append)

    assert result is not platform
    assert result == platform
    assert logs == []


def test_legacy_bool_true_capped_to_low():
    platform = make_platform(True)

    capped = build_analysis_platform(platform)

    assert capped["thinking"] == {"level": "LOW"}
    assert platform["thinking"] is True


def test_non_dict_platform_passthrough():
    assert build_analysis_platform(None) is None


def test_glossary_chunk_passes_capped_copy_to_requester(monkeypatch):
    platform = make_platform({"level": "MAX"})
    original = copy.deepcopy(platform)
    captured: dict[str, object] = {}

    class FakeRequester:
        def __init__(self, config, platform, index):
            captured["platform"] = platform

        def request(self, messages, response_shape = "none"):
            return False, "", '{"src": "Leo", "dst": "", "type": "角色"}', 1, 1

    monkeypatch.setattr(glossary_module, "TaskRequester", FakeRequester)
    service = GlossaryCandidateService(config = SimpleNamespace(), target_path = ".", platform = platform)
    lines: list[str] = []
    service.info = lines.append

    success, _ = service._extract_chunk_with_llm(["Leo waved."], 0)

    assert success is True
    assert captured["platform"]["thinking"] == {"level": "LOW"}
    assert captured["platform"] is not platform
    assert service.platform == original
    assert any("MAX → LOW" in line for line in lines)


def test_workbench_request_passes_capped_copy_to_requester(monkeypatch):
    platform = make_platform({"level": "HIGH"})
    original = copy.deepcopy(platform)
    captured: dict[str, object] = {}

    class FakeRequester:
        def __init__(self, config, platform, index):
            captured["platform"] = platform

        def request(self, messages, response_shape = "none"):
            return False, "", "{}", 1, 1

    monkeypatch.setattr(analysis_module, "TaskRequester", FakeRequester)
    service = WorkbenchAnalysisService()
    lines: list[str] = []
    service.info = lines.append

    raw = service.request_json_text(SimpleNamespace(), platform, "prompt", label = "世界观草稿")

    assert raw == "{}"
    assert captured["platform"]["thinking"] == {"level": "LOW"}
    assert captured["platform"] is not platform
    assert platform == original
    assert any("HIGH → LOW" in line for line in lines)
