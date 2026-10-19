from types import SimpleNamespace

from base.Base import Base
from module.Agent.AgentRequester import AgentRequester
from module.Config import Config


def _requester(api_format: str = Base.APIFormat.OPENAI) -> AgentRequester:
    config = Config()
    platform = {
        "api_key": ["test-key"],
        "api_url": "https://example.invalid/v1",
        "api_format": api_format,
        "model": "test-model",
    }
    return AgentRequester(config, platform)


def test_usage_extracts_nested_openai_cache_hit_tokens() -> None:
    usage = SimpleNamespace(
        prompt_tokens=1000,
        completion_tokens=200,
        prompt_tokens_details=SimpleNamespace(cached_tokens=768),
    )

    result = AgentRequester._usage(
        usage,
        ("prompt_tokens", "input_tokens"),
        ("completion_tokens", "output_tokens"),
        ("prompt_tokens_details.cached_tokens", "prompt_cache_hit_tokens"),
    )

    assert result == {"input_tokens": 1000, "output_tokens": 200, "cached_tokens": 768}


def test_usage_falls_back_to_deepseek_flat_cache_field() -> None:
    # DeepSeek 直连接口把命中量平铺在 usage 顶层，没有 details 子对象。
    usage = {"prompt_tokens": 500, "completion_tokens": 100, "prompt_cache_hit_tokens": 400}

    result = AgentRequester._usage(
        usage,
        ("prompt_tokens",),
        ("completion_tokens",),
        ("prompt_tokens_details.cached_tokens", "prompt_cache_hit_tokens"),
    )

    assert result["cached_tokens"] == 400


def test_usage_omits_cache_field_when_provider_reports_none() -> None:
    usage = {"prompt_tokens": 500, "completion_tokens": 100}

    result = AgentRequester._usage(
        usage,
        ("prompt_tokens",),
        ("completion_tokens",),
        ("prompt_tokens_details.cached_tokens", "prompt_cache_hit_tokens"),
    )

    assert "cached_tokens" not in result
    assert result["input_tokens"] == 500


def test_nested_value_returns_default_for_missing_path() -> None:
    usage = {"prompt_tokens": 1}

    assert AgentRequester._nested_value(usage, "prompt_tokens_details.cached_tokens", None) is None
    assert AgentRequester._nested_value(None, "prompt_tokens", 7) == 7
