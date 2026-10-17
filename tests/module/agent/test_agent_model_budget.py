"""模型容量推导：上下文预算、消息上限与批次容量。"""

from __future__ import annotations

import pytest

from module.Agent.ModelBudget import (
    COMPACTION_RESERVE_TOKENS,
    FALLBACK_CONTEXT_WINDOW,
    FALLBACK_MAX_OUTPUT_TOKENS,
    agent_context_budget,
    batch_capacity,
    resolve_capability,
)


def test_unknown_model_uses_safe_fallback() -> None:
    assert resolve_capability({"model": "some-unknown-model"}) == (
        FALLBACK_CONTEXT_WINDOW,
        FALLBACK_MAX_OUTPUT_TOKENS,
    )
    # 平台配置缺失时同样走兜底，不按名字猜
    assert resolve_capability(None) == (
        FALLBACK_CONTEXT_WINDOW,
        FALLBACK_MAX_OUTPUT_TOKENS,
    )


@pytest.mark.parametrize(
    "model,expected",
    [
        ("deepseek-chat", (128_000, 8_192)),
        ("claude-3-7-sonnet", (200_000, 32_000)),
        # 大窗口模型：输出按产品档位封顶到 64k
        ("gemini-2.5-pro", (1_048_576, 64_000)),
        # 目录 maxTokens 比产品档小，取目录值
        ("gpt-4.1-mini", (1_047_576, 32_768)),
        ("gpt-4o-mini", (128_000, 16_384)),
        ("Qwen2.5-72B-Instruct", (128_000, 8_192)),
        ("deepseek-v4-pro", (1_000_000, 64_000)),
    ],
)
def test_known_models_are_recognised(model: str, expected: tuple[int, int]) -> None:
    assert resolve_capability({"model": model}) == expected


def test_longest_model_fragment_wins() -> None:
    # gpt-4.1 不能被更短的 gpt-4 抢走
    assert resolve_capability({"model": "gpt-4.1-mini"})[0] == 1_047_576
    assert resolve_capability({"model": "gpt-4"})[0] == 8_192


def test_tiny_window_falls_back_instead_of_going_negative() -> None:
    context_window, max_output = resolve_capability({
        "model": "sakura-7b",
        "context_window": 20_000,
        "max_output_tokens": 8_000,
    })

    # 20000 - 32000 <= 0：整组退回自动值，不硬凑负数
    assert context_window == 32_768
    assert max_output == 4_096


def test_explicit_platform_fields_win() -> None:
    capability = resolve_capability({
        "model": "deepseek-chat",
        "context_window": 64_000,
        "max_output_tokens": 4_000,
    })

    assert capability == (64_000, 4_000)


def test_output_tokens_never_exceed_available_context() -> None:
    context_window, max_output = resolve_capability({
        "context_window": 40_000,
        "max_output_tokens": 100_000,
    })

    assert context_window == 40_000
    assert max_output == 40_000 - COMPACTION_RESERVE_TOKENS


def test_context_budget_follows_model_window() -> None:
    small = agent_context_budget({"model": "deepseek-chat"})
    large = agent_context_budget({"model": "gemini-2.5-pro"})

    # 128k 窗口的模型不能按 1M 的预算塞，否则请求会在供应商侧溢出
    assert small["max_context_chars"] < large["max_context_chars"]
    assert small["max_context_chars"] < 300_000
    assert large["max_context_chars"] > small["max_context_chars"]
    # 消息条数上限随窗口一起变化
    assert small["max_messages"] < large["max_messages"]


def test_batch_capacity_is_driven_by_output_budget() -> None:
    small = batch_capacity({"model": "deepseek-chat"})
    large = batch_capacity({"model": "gemini-2.5-pro"})

    # 输出 8k 的模型一批给不了几百条，否则它会在半路截断
    assert small["max_entries"] < large["max_entries"]
    assert small["max_entries"] >= 20
    assert large["max_entries"] <= 400
    assert small["max_chars"] < large["max_chars"]


def test_batch_capacity_respects_ceiling() -> None:
    huge = batch_capacity({"context_window": 4_000_000, "max_output_tokens": 200_000})

    assert huge["max_entries"] == 400
    assert huge["max_chars"] <= 200_000


def test_runtime_catalog_beats_builtin_table() -> None:
    """目录是现取的，新模型不必等我加表。"""

    catalog = {"brand-new-model-2027": (500_000, 128_000)}

    assert resolve_capability({"model": "brand-new-model-2027"}, catalog) == (500_000, 64_000)
    # 目录里没有这个模型时，退回内置离线表
    assert resolve_capability({"model": "gpt-4o"}, catalog) == (128_000, 16_384)


def test_explicit_config_beats_runtime_catalog() -> None:
    catalog = {"some-model": (1_000_000, 128_000)}

    capability = resolve_capability(
        {"model": "some-model", "context_window": 64_000, "max_output_tokens": 8_000},
        catalog,
    )

    assert capability == (64_000, 8_000)


def test_catalog_lookup_is_case_insensitive() -> None:
    catalog = {"MiniMax-M2-New": (200_000, 64_000)}

    assert resolve_capability({"model": "minimax-m2-new"}, catalog) == (200_000, 32_000)
