"""自适应批次行数：按输出预算放大，但不低于用户配置、不超安全上限。"""

from module.Engine.BatchSizing import (
    MAX_ADAPTIVE_BATCH_LINES,
    OUTPUT_BUDGET_USAGE_RATIO,
    OUTPUT_TOKENS_PER_LINE_ESTIMATE,
    adaptive_batch_lines,
)


def test_default_output_budget_reaches_safe_ceiling() -> None:
    # 4096 token 输出预算下，按 56 token/行、75% 余量可容纳 54 行，被上限截到 48。
    assert adaptive_batch_lines(20, 4096) == MAX_ADAPTIVE_BATCH_LINES


def test_smaller_budget_scales_up_gradually() -> None:
    # 2048 * 0.75 / 56 = 27 行，高于用户配置的 20。
    assert adaptive_batch_lines(20, 2048) == 27


def test_user_configured_lines_is_a_floor() -> None:
    # 用户明确配了 80 行：不要因为自适应又缩回去。
    assert adaptive_batch_lines(80, 4096) == 80
    assert adaptive_batch_lines(5, 2048) == 27


def test_zero_or_missing_budget_keeps_configured_lines() -> None:
    assert adaptive_batch_lines(20, 0) == 20
    assert adaptive_batch_lines(20, -1) == 20


def test_degenerate_config_never_returns_zero() -> None:
    assert adaptive_batch_lines(0, 0) >= 1
    assert adaptive_batch_lines(1, 512) == 6
    assert OUTPUT_BUDGET_USAGE_RATIO < 1
    assert OUTPUT_TOKENS_PER_LINE_ESTIMATE > 0
