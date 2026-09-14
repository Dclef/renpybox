from types import SimpleNamespace

import pytest

from base.Base import Base
from module.Cache.CacheItem import CacheItem
from module.Engine.TaskRequester import TaskRequester, ThinkingLevel


def requester(api_format=Base.APIFormat.OPENAI, model="test-model", output=0):
    config = SimpleNamespace(token_threshold=10, max_output_tokens=output)
    platform = {"api_format": api_format, "model": model, "api_url": "https://example.invalid", "thinking": False}
    return TaskRequester(config, platform, 0)


@pytest.mark.parametrize("api_format,method", [
    (Base.APIFormat.OPENAI, "generate_openai_args"),
    (Base.APIFormat.SAKURALLM, "generate_sakura_args"),
    (Base.APIFormat.ANTHROPIC, "generate_anthropic_args"),
])
def test_explicit_output_budget_is_independent_of_batch_lines(api_format, method):
    task = requester(api_format, output=2048)
    task.config.token_threshold = 9999
    args = getattr(task, method)([{"role": "user", "content": "hello"}], ThinkingLevel.OFF, {})
    assert args["max_tokens"] == 2048


def test_official_openai_parameter_uses_independent_output_budget():
    task = requester(output=8192)
    task.platform["api_url"] = "https://api.openai.com/v1"
    args = task.generate_openai_args([], ThinkingLevel.OFF, {})
    assert args["max_completion_tokens"] == 8192
    assert "max_tokens" not in args


@pytest.mark.parametrize("model,output,expected", [
    ("gemini-2.5-flash", 0, 16384),
    ("gemini-2.5-flash", 2048, 2048),
    ("gemini-test", 0, 4096),
    ("gemini-test", 8192, 8192),
])
def test_google_defaults_and_explicit_output_budget(model, output, expected):
    task = requester(Base.APIFormat.GOOGLE, model, output)
    args = task.generate_google_args([], ThinkingLevel.OFF, {})
    assert args["config"].max_output_tokens == expected


def test_output_budget_respects_declared_provider_limit():
    task = requester(output=16384)
    task.platform["max_output_tokens"] = 4096
    assert task._output_token_limit() == 4096


def test_oversized_complete_prompt_does_not_enter_network_retry(monkeypatch):
    task = requester(output=512)
    task.platform["context_window_tokens"] = 1024
    calls = []
    monkeypatch.setattr(task, "request_openai", lambda *args, **kwargs: calls.append(True))
    monkeypatch.setattr(task, "warning", lambda *args: None)
    # A short source alone fits; the complete prompt with assets exceeds the limit.
    messages = [
        {"role": "system", "content": "world " * 1000},
        {"role": "user", "content": "Hello"},
    ]
    assert sum(CacheItem(src=m["content"]).get_token_count() for m in messages) > 512
    assert task.request(messages)[0] is True
    assert "BATCH_EXCEEDS_CONTEXT_WINDOW" in task.last_error_message
    assert calls == []


def test_fitting_complete_prompt_uses_existing_request_path(monkeypatch):
    task = requester(output=512)
    task.platform["context_window_tokens"] = 1024
    calls = []
    monkeypatch.setattr(TaskRequester, "is_cancel_requested", classmethod(lambda cls: False))
    monkeypatch.setattr(task, "request_openai", lambda *args, **kwargs: calls.append(True) or (False, "", "translated", 8, 8))
    assert task.request([{"role": "user", "content": "Hello"}])[2] == "translated"
    assert calls == [True]


def test_initialization_preflight_uses_resumed_output_budget(monkeypatch):
    from module.Config import Config
    from module.Engine.Translator.Translator import Translator
    from module.Engine.Translator.TranslationTaskContext import TranslationTaskContext

    old_config = Config(
        max_output_tokens=8192,
        platforms=[{"id": 0, "api_format": Base.APIFormat.OPENAI, "model": "test-model", "context_window_tokens": 4096}],
        activate_platform=0,
    )
    context = TranslationTaskContext.from_config(old_config)
    translator = Translator.__new__(Translator)
    # This runs before self.config/self.platform are assigned by initialization.
    monkeypatch.setattr("module.Engine.Translator.Translator.PromptBuilder", lambda context: SimpleNamespace(
        build_main=lambda: "Translate the following text.", build_worldbook_context=lambda: "",
    ))
    translator._run_asset_preflight(context, {"preflight_confirmed": True}, Config(max_output_tokens=1024))
    with pytest.raises(ValueError, match="FIXED_PROMPT_EXCEEDS_CONTEXT_WINDOW"):
        translator._run_asset_preflight(context, {"preflight_confirmed": True}, old_config)
