"""翻译批次大小的自适应推导。

引擎默认按「每批 20 行」切分，换来的是每批固定的提示词与格式开销：一次
2744 条的实测里，输入 token 有九成花在这些固定内容上。接口能提供更大的
输出预算时，把每批行数放大到接近预算上限可以显著摊薄这部分开销。

放大必须保守：批次越大，一次格式错/漏行作废的代价越高，重试也要按半衰减
回落。所以这里只做「按输出预算能给多少就给多少，但不超过安全上限」，
用户显式配置的行数永远作为下限。
"""

from __future__ import annotations

# 实测（20 行/批、低思考等级）约 56 个输出 token/行，含思考与 JSON 结构。
OUTPUT_TOKENS_PER_LINE_ESTIMATE: int = 56
# 只用到输出预算的 75%，给思考内容和格式波动留余量。
OUTPUT_BUDGET_USAGE_RATIO: float = 0.75
# 单批行数上限：更大的批次收益递减，且一次失败的回滚代价成倍上升。
MAX_ADAPTIVE_BATCH_LINES: int = 48


def adaptive_batch_lines(
    configured_lines: int,
    output_token_limit: int,
) -> int:
    """返回首批应使用的行数；永远不小于用户配置的行数。"""

    configured = max(1, int(configured_lines or 1))
    budget = int(output_token_limit or 0)
    if budget <= 0:
        return configured
    affordable = int(
        budget * OUTPUT_BUDGET_USAGE_RATIO / OUTPUT_TOKENS_PER_LINE_ESTIMATE
    )
    return max(configured, min(MAX_ADAPTIVE_BATCH_LINES, affordable))
