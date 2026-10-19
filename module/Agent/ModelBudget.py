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
# 顺序无关，命中多个时取最长片段，避免 gpt-4 抢走 gpt-4.1。
#
# 关于 maxTokens：这是**输出**上限，不是上下文。早期版本按厂商标称值填，
# 结果 kimi-k3 填了 1M、deepseek-v4 填了 384k，而供应商实际只接受 32k/128k，
# 请求在参数校验阶段就被 400 拒掉。国产生效值取自 WorkBuddy 的运行时模型表
# （逐行核对），宁可按实际值填小，也不要拿标称值去撞接口。
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
    # DeepSeek：v4 系列窗口 1M、输出 128k；v3.x 窗口 96k、输出 16k～32k。
    ("deepseek-v4.1", 1_000_000, 128_000),
    ("deepseek-v4", 1_000_000, 128_000),
    ("deepseek-v3-2", 96_000, 32_000),
    ("deepseek-v3-1", 96_000, 32_000),
    ("deepseek-v3-0324", 112_000, 16_000),
    ("deepseek-r1", 96_000, 16_000),
    # 认不出的 deepseek 型号（如官方 deepseek-chat）按保守档：128k 窗口、8k 输出。
    ("deepseek", 128_000, 8_192),
    # Kimi：k3 虽标称 1M 窗口，输出实际只给 32k。
    ("kimi-k3", 1_000_000, 32_000),
    ("kimi-k2.8", 1_000_000, 64_000),
    ("kimi-k2", 256_000, 32_000),
    ("kimi", 256_000, 32_000),
    ("glm-5.3-flash", 1_000_000, 131_072),
    ("glm-5.3", 1_000_000, 64_000),
    ("glm-5.2", 1_000_000, 64_000),
    ("glm-5.1", 200_000, 48_000),
    ("glm-5.0", 200_000, 48_000),
    ("glm-5", 200_000, 48_000),
    ("glm-4.7", 200_000, 48_000),
    ("glm-4.6", 168_000, 32_000),
    ("glm-4", 128_000, 32_000),
    ("glm", 200_000, 32_000),
    ("minimax-m3", 512_000, 128_000),
    ("minimax-m2", 200_000, 48_000),
    ("minimax", 200_000, 48_000),
    ("hunyuan-2.0-thinking", 128_000, 24_000),
    ("hunyuan-2.0", 128_000, 16_000),
    ("hunyuan-chat", 128_000, 8_192),
    ("hunyuan", 128_000, 8_192),
    # 腾讯混元 hy3/hy4 才是 64k 输出档，别被上面的 hunyuan 泛匹配吃掉。
    ("hy4-preview", 1_000_000, 64_000),
    ("hy3", 192_000, 64_000),
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


def _lookup_catalog(model: Any, catalog: Mapping[str, Any] | None) -> tuple[int, int]:
    """在运行时目录里按模型 id 精确匹配（大小写不敏感）。"""

    name = str(model or "").strip().casefold()
    if not name or not isinstance(catalog, Mapping):
        return 0, 0
    for key, value in catalog.items():
        if str(key).strip().casefold() != name:
            continue
        try:
            context_window, max_output = value
        except (TypeError, ValueError):
            return 0, 0
        return int(context_window or 0), int(max_output or 0)
    return 0, 0


def resolve_capability(
    platform: Mapping[str, Any] | None,
    catalog: Mapping[str, Any] | None = None,
) -> tuple[int, int]:
    """返回本轮实际生效的 (context_window, max_output_tokens)。

    优先级：平台显式配置 > 运行时模型目录 > 内置离线兜底表 > 固定兜底。
    目录是现取的，模型换代不必改代码。
    """

    config = platform if isinstance(platform, Mapping) else {}
    spec_context, spec_output = _lookup_catalog(config.get("model"), catalog)
    if not spec_context and not spec_output:
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


def agent_context_budget(
    platform: Mapping[str, Any] | None,
    catalog: Mapping[str, Any] | None = None,
) -> dict[str, int]:
    """按模型容量给出本地裁剪参数。"""

    context_window, max_output = resolve_capability(platform, catalog)
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


def batch_capacity(
    platform: Mapping[str, Any] | None,
    catalog: Mapping[str, Any] | None = None,
) -> dict[str, int]:
    """单批条目数与字符预算。

    条目数由**输出**预算反推：一批 N 条就要在一次回复里吐 N 条译文，
    给太多只会在半路被 max_tokens 截断；字符预算取输入余量的四分之一，
    给历史消息和模型自己的推理留空间。
    """

    budget = agent_context_budget(platform, catalog)
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
