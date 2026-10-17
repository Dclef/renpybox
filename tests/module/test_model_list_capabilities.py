"""`/models` 目录解析：从供应商返回里读出上下文窗口与最大输出。"""

from __future__ import annotations

import io
import json
import urllib.request

import pytest

from module.Engine.API import ModelList


class _FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.close()
        return False


def _patch_payload(monkeypatch, payload) -> None:
    body = json.dumps(payload).encode("utf-8")

    def fake_urlopen(request, timeout = 0):
        return _FakeResponse(body)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)


def test_openrouter_style_catalog_is_parsed(monkeypatch) -> None:
    _patch_payload(monkeypatch, {
        "data": [
            {
                "id": "openai/gpt-x",
                "context_length": 400_000,
                "top_provider": {"max_completion_tokens": 128_000},
            },
            {"id": "only-id-model"},
            {"id": "alt-fields", "context_window": 200_000, "max_output_tokens": 32_000},
        ]
    })

    catalog = ModelList.list_model_capabilities("https://example.test/v1", "k", "OpenAI")

    assert catalog["openai/gpt-x"] == (400_000, 128_000)
    assert catalog["alt-fields"] == (200_000, 32_000)
    # 只有 id 的条目不进目录，交给兜底
    assert "only-id-model" not in catalog


def test_plain_list_payload_is_accepted(monkeypatch) -> None:
    _patch_payload(monkeypatch, [
        {"id": "m1", "context_length": 128_000, "max_tokens": 8_192},
    ])

    catalog = ModelList.list_model_capabilities("https://example.test/v1", "", "OpenAI")

    assert catalog == {"m1": (128_000, 8_192)}


def test_network_failure_returns_empty(monkeypatch) -> None:
    def boom(_request, timeout = 0):
        raise OSError("offline")

    monkeypatch.setattr(urllib.request, "urlopen", boom)

    assert ModelList.list_model_capabilities("https://example.test/v1", "k", "OpenAI") == {}


def test_machine_and_anthropic_formats_skip_lookup() -> None:
    assert ModelList.list_model_capabilities("", "", "Anthropic") == {}
