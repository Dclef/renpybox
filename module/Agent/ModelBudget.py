"""按模型容量推导 Agent 的上下文与批次预算。

对齐 ``neavo/LinguaGacha`` 的实际做法（cursor 核对了它的源码）：

- 它**没有**「模型名 → 容量」硬编码表，容量来自依赖包 ``@earendil-works/pi-ai``
  的运行时模型目录；产品层只做档位裁切。
- 自动输出 = ``min(目录 maxTokens, 32000 或 64000)``，阈值是窗口 ≥ 500k 取大档。
- 用户显式非 0 值优先，但仍不能超过 ``窗口 - 32000``（压缩预留）。
- 窗口小到留不出 32000 时，整组退回自动值，不硬凑负数。
- 规格缺失时兜底 256k / 32k；**明确不按模型名猜**。

RenpyBox 没有那样的模型目录，所以这里用三级解析：

1. 平台配置里显式的 ``context_window`` / ``max_output_tokens``（0 或不填 = 自动）；
2. 内置知名模型表（子串匹配，最长命中优先）——这是本地的「目录替身」；
3. 兜底 256k / 32k。

字符预算与消息条数是 **RenpyBox 独有的本地策略**（LinguaGacha 用 token 级压缩，
没有这两个量），因为它们的历史是简单 list，需要一个可裁剪的边界。
"""

from __future__ import annotations

from typing import Any, Mapping


# 与 LinguaGacha 的 FALLBACK_AGENT_LIMITS 对齐：规格未知时按这个跑。
FALLBACK_CONTEXT_WINDOW = 256_000
FALLBACK_MAX_OUTPUT_TOKENS = 32_000

# 产品档位：窗口 ≥ 500k 视为大上下文，输出上限抬到 64k，否则 32k。
LARGE_CONTEXT_WINDOW_THRESHOLD = 500_000
SMALL_AUTOMATIC_OUTPUT_LIMIT = 32_000
LARGE_AUTOMATIC_OUTPUT_LIMIT = 64_000

# 压缩预留：保证上下文里永远留得出一份摘要的位置。
COMPACTION_RESERVE_TOKENS = 32_000
# 压缩后保留的尾部预算（LinguaGacha 的 AGENT_KEEP_RECENT_TOKENS）。
KEEP_RECENT_TOKENS = 32_000

# 字符→token 的保守换算。中英混排的 Ren'Py 文本大约 1 token ≈ 1.5 字符，
# 取小值换安全：宁可少装一点，也不要让请求在供应商侧溢出。
CHARS_PER_TOKEN = 1.5

# 上下文与消息条数的硬上限，避免 1M 窗口的模型把内存和耗时拖垮。
MAX_CONTEXT_CHARS_CEILING = 2_000_000
MAX_MESSAGES_CEILING = 2_000
MIN_CONTEXT_CHARS = 16_000
MIN_MESSAGES = 40

# 单条译文的输出 token 预留（含 id 与 JSON 结构开销）。
AVG_OUTPUT_TOKENS_PER_ENTRY = 60
# 单批条目数的绝对上下限（RenpyBox 本地策略）。
MIN_BATCH_ENTRIES = 8
MAX_BATCH_ENTRIES_CEILING = 400
MAX_BATCH_CHARS_CEILING = 200_000
MIN_BATCH_CHARS = 2_000

# 本地「目录替身」：模型 id 片段 → (context_window, catalog maxTokens)。
# 数字取自 pi-ai@1.3.0 的原厂目录（cursor 逐条核对），供没有目录时兜底用。
# 顺序无关，命中多个时取最长片段，避免 gpt-4 抢走 gpt-4.1。
MODEL_CAPABILITIES: tuple[tuple[str, int, int], ...] = (
    ("gpt-4.1", 1_047_576, 32_768),
    ("gpt-4o", 128_000, 16_384),
    ("gpt-4-turbo", 128_000, 4_096),
    ("gpt-4", 8_192, 8_192),
    ("gpt-5.4-pro", 1_050_000, 128_000),
    ("gpt-5.5-pro", 1_050_000, 128_000),
    ("gpt-5.4", 272_000, 128_000),
    ("gpt-5.5", 272_000, 128_000),
    ("gpt-5", 400_000, 128_000),
    ("o1", 200_000, 100_000),
    ("o3", 200_000, 100_000),
    ("o4", 200_000, 100_000),
    ("claude-opus-4-6", 1_000_000, 128_000),
    ("claude-sonnet-4-6", 1_000_000, 128_000),
    ("claude", 200_000, 64_000),
    ("gemini-2.5", 1_048_576, 65_536),
    ("gemma", 262_144, 32_768),
    ("grok-4.3", 1_000_000, 30_000),
    ("grok-4", 500_000, 500_000),
    ("deepseek-v4", 1_000_000, 384_000),
    ("deepseek", 128_000, 8_192),
    ("kimi-k3", 1_048_576, 1_048_576),
    ("kimi", 262_144, 262_144),
    ("glm-5.3", 1_000_000, 131_072),
    ("glm-5.2", 1_000_000, 131_072),
    ("glm-5", 1_000_000, 131_072),
    ("glm", 200_000, 131_072),
    ("qwen", 128_000, 8_192),
    ("sakura", 32_768, 4_096),
)


def _positive_int(value: Any) -> int:
    """只接受正整数；0、负数、布尔与脏值一律当作「未设置」。"""

    if isinstance(value, bool):
        return 0
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 0
    return number if number > 0 else 0


def _lookup_model(model: Any) -> tuple[int, int]:
    """按最长片段匹配内置模型表，返回 (context_window, maxTokens)。"""

    name = str(model or "").strip().casefold()
    if not name:
        return 0, 0
    best: tuple[int, int, int] | None = None
    for fragment, context_window, max_tokens in MODEL_CAPABILITIES:
        if fragment.casefold() in name:
            length = len(fragment)
            if best is None or length > best[0]:
                best = (length, context_window, max_tokens)
    return (best[1], best[2]) if best is not None else (0, 0)


def resolve_capability(platform: Mapping[str, Any] | None) -> tuple[int, int]:
    """返回本轮实际生效的 (context_window, max_output_tokens)。"""

    config = platform if isinstance(platform, Mapping) else {}
    spec_context, spec_output = _lookup_model(config.get("model"))

    auto_context = spec_context or FALLBACK_CONTEXT_WINDOW
    auto_output = spec_output or FALLBACK_MAX_OUTPUT_TOKENS
    if spec_context and spec_output:
        cap = (
            SMALL_AUTOMATIC_OUTPUT_LIMIT
            if spec_context < LARGE_CONTEXT_WINDOW_THRESHOLD
            else LARGE_AUTOMATIC_OUTPUT_LIMIT
        )
        auto_output = min(spec_output, cap)

    context_window = _positive_int(config.get("context_window")) or auto_context
    max_output = _positive_int(config.get("max_output_tokens")) or auto_output

    available = context_window - COMPACTION_RESERVE_TOKENS
    if available <= 0:
        # 窗口小到留不出压缩预留：整组退回自动值，而不是硬凑一个负数。
        return auto_context, auto_output
    return context_window, min(max_output, available)


def agent_context_budget(platform: Mapping[str, Any] | None) -> dict[str, int]:
    """按模型容量给出本地裁剪参数。"""

    context_window, max_output = resolve_capability(platform)
    usable = context_window - max_output - COMPACTION_RESERVE_TOKENS
    if usable <= 0:
        usable = max(4_096, context_window // 2)

    context_chars = int(usable * CHARS_PER_TOKEN)
    context_chars = max(MIN_CONTEXT_CHARS, min(context_chars, MAX_CONTEXT_CHARS_CEILING))

    # 本地补充：消息条数同时受窗口约束，避免 4096 窗口的模型被塞几百条。
    max_messages = max(MIN_MESSAGES, min(usable // 250, MAX_MESSAGES_CEILING))

    return {
        "context_window": context_window,
        "max_output_tokens": max_output,
        "usable_tokens": usable,
        "max_context_chars": context_chars,
        "max_messages": max_messages,
        "keep_recent_tokens": KEEP_RECENT_TOKENS,
    }


def batch_capacity(platform: Mapping[str, Any] | None) -> dict[str, int]:
    """单批条目数与字符预算。

    条目数由**输出**预算反推：一批 N 条就要在一次回复里吐 N 条译文，
    给太多只会在半路被 max_tokens 截断；字符预算取输入余量的四分之一，
    给历史消息和模型自己的推理留空间。
    """

    budget = agent_context_budget(platform)
    usable = int(budget["usable_tokens"])
    max_output = int(budget["max_output_tokens"])

    entries = int(max_output * 0.5 // AVG_OUTPUT_TOKENS_PER_ENTRY)
    entries = max(MIN_BATCH_ENTRIES, min(entries, MAX_BATCH_ENTRIES_CEILING))

    chars = int(usable * CHARS_PER_TOKEN) // 4
    chars = max(MIN_BATCH_CHARS, min(chars, MAX_BATCH_CHARS_CEILING))

    return {
        "max_entries": entries,
        "max_chars": chars,
        "max_output_tokens": max_output,
        "context_window": int(budget["context_window"]),
    }


__all__ = [
    "agent_context_budget",
    "batch_capacity",
    "resolve_capability",
    "FALLBACK_CONTEXT_WINDOW",
    "FALLBACK_MAX_OUTPUT_TOKENS",
    "COMPACTION_RESERVE_TOKENS",
    "LARGE_CONTEXT_WINDOW_THRESHOLD",
    "SMALL_AUTOMATIC_OUTPUT_LIMIT",
    "LARGE_AUTOMATIC_OUTPUT_LIMIT",
]
