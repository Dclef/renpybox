"""Agent 长会话保障用例。

覆盖施工单 `docs/internal/2026-11-03/plan/task-agent-long-session.md` §七：

- 上下文压缩：优先摘要，失败退回删除式裁剪
- 压缩后的结构不变量
- 失败批次自动降级与回升
- 会话恢复（stage / budget / metrics）
"""

from __future__ import annotations

from typing import Any

import pytest

from module.Agent.AgentService import AgentService
from module.Agent.ModelBudget import CHARS_PER_TOKEN, MIN_BATCH_ENTRIES
from module.Agent.types import AgentRequestResult


def _service() -> AgentService:
    service = AgentService(
        config_loader = lambda: None,
        dispatcher = _NullDispatcher(),
        max_iterations = 8,
    )
    return service


class _NullDispatcher:
    """最小 dispatcher：压缩测试不执行真实工具。"""

    tools: dict[str, Any] = {}

    def execute(self, *_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("压缩测试不应执行工具")


class _FakeRequester:
    def __init__(self, *, text: str = "摘要内容", success: bool = True) -> None:
        self.text = text
        self.success = success
        self.calls: list[list[dict[str, Any]]] = []
        self.usage = {"input_tokens": 10, "output_tokens": 5}

    def request_text(self, messages: list[dict[str, Any]], **_kwargs: Any) -> AgentRequestResult:
        self.calls.append(list(messages))
        return AgentRequestResult(
            success = self.success,
            text = self.text if self.success else "",
            usage = dict(self.usage),
        )


def _conversation(rounds: int, *, filler: int = 200) -> list[dict[str, Any]]:
    """造一段多回合对话：每回合一个 user + 一个 assistant。"""

    messages: list[dict[str, Any]] = [{"role": "system", "content": "你是助手"}]
    for index in range(rounds):
        messages.append({"role": "user", "content": f"第 {index} 个请求" + "x" * filler})
        messages.append({"role": "assistant", "content": f"第 {index} 个回复" + "y" * filler})
    return messages


# --- token 口径 ---------------------------------------------------------


def test_token_estimate_uses_chars_per_token() -> None:
    service = _service()
    messages = [{"role": "user", "content": "a" * 1500}]
    expected = int(len("a" * 1500) / CHARS_PER_TOKEN)
    # json 包裹（键名、引号、分隔符）会多出几十个字符，按比例放宽
    assert abs(service._estimate_tokens(messages) - expected) <= expected * 0.05


def test_over_budget_prefers_token_estimate() -> None:
    """token 超了就该算超预算，哪怕字符数还没到 max_context_chars。"""

    service = _service()
    service.context_budget = {"usable_tokens": 10}
    service.max_context_chars = 10 ** 9
    service.max_messages = 0
    service.messages = _conversation(2)

    assert service._over_budget() is True


def test_over_budget_keeps_char_and_message_guards() -> None:
    """字符与消息条数是兜底护栏，不能被 token 口径取代。"""

    service = _service()
    service.context_budget = {"usable_tokens": 10 ** 9}
    service.max_context_chars = 100
    service.max_messages = 0
    service.messages = _conversation(2)

    assert service._over_budget() is True


# --- 压缩 ---------------------------------------------------------------


def test_trim_compacts_instead_of_deleting() -> None:
    """超预算时优先摘要：旧回合被替换成一条摘要消息，而不是整段删掉。"""

    service = _service()
    # 预算设为「摘要 + 剩余内容」放得下、原文放不下」的量：
    # 原文 3 回合各带 200 字填充，摘要只有一句话，压缩后应当回到预算内。
    service.context_budget = {"usable_tokens": 400}
    service.max_context_chars = 10 ** 9
    service.max_messages = 0
    service.messages = _conversation(3)
    requester = _FakeRequester(text = "用户想翻完整个项目")
    service._requester = requester

    service._trim_history()

    # 摘要请求确实发过
    assert requester.calls
    summary = [msg for msg in service.messages if msg.get(AgentService.SUMMARY_FLAG)]
    assert summary, "应当有摘要消息替换掉旧回合"
    assert "用户想翻完整个项目" in summary[0]["content"]


def test_trim_falls_back_to_delete_when_summary_fails() -> None:
    """摘要失败时退回删除式裁剪，会话仍可继续。"""

    service = _service()
    service.context_budget = {"usable_tokens": 50}
    service.max_context_chars = 10 ** 9
    service.max_messages = 0
    service.messages = _conversation(3)
    before = len(service.messages)
    service._requester = _FakeRequester(success = False)

    service._trim_history()

    # 没有摘要消息，但消息确实被裁剪了
    assert not [msg for msg in service.messages if msg.get(AgentService.SUMMARY_FLAG)]
    assert len(service.messages) < before


def test_trim_without_requester_uses_delete_path() -> None:
    """没有请求器（例如离线或构造期）时不能尝试摘要，直接走删除。"""

    service = _service()
    service.context_budget = {"usable_tokens": 50}
    service.max_context_chars = 10 ** 9
    service.max_messages = 0
    service.messages = _conversation(3)
    before = len(service.messages)

    service._trim_history()

    assert len(service.messages) < before


def test_compaction_keeps_structure_invariants() -> None:
    """压缩后：system 在首位、当前回合保留、无孤立 tool 消息。"""

    service = _service()
    service.messages = _conversation(3)[:1] + [
        {"role": "user", "content": "旧请求"},
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "c1", "type": "function", "function": {"name": "x", "arguments": "{}"}},
        ]},
        {"role": "tool", "tool_call_id": "c1", "name": "x", "content": "结果"},
        {"role": "assistant", "content": "旧回复"},
        {"role": "user", "content": "当前请求"},
    ]
    service.context_budget = {"usable_tokens": 20}
    service.max_context_chars = 10 ** 9
    service.max_messages = 0
    service._requester = _FakeRequester(text = "摘要")

    service._trim_history()

    assert service.messages[0]["role"] == "system"
    # 当前（最新）用户请求必须还在
    assert any(
        msg.get("role") == "user" and msg.get("content") == "当前请求"
        for msg in service.messages
    )
    # 不允许出现没有所属 assistant 的孤立 tool 消息
    for index, msg in enumerate(service.messages):
        if msg.get("role") == "tool":
            assert index > 0 and service.messages[index - 1].get("role") != "system"


def test_summary_usage_is_counted() -> None:
    """摘要请求本身也消耗 token，必须计入用量，否则吞吐数字对不上。"""

    service = _service()
    service._requester = _FakeRequester(text = "摘要")

    service._summarize([{"role": "user", "content": "hello"}])

    assert service._metrics["input_tokens"] == 10
    assert service._metrics["output_tokens"] == 5
    assert service._metrics["requests"] == 1


# --- 批次降级 -----------------------------------------------------------


def test_batch_ceiling_halves_on_truncation() -> None:
    service = _service()

    service._reduce_batch_ceiling(100)

    assert service.batch_ceiling() == 50


def test_batch_ceiling_respects_minimum() -> None:
    service = _service()
    service._batch_ceiling = MIN_BATCH_ENTRIES * 2

    service._reduce_batch_ceiling()

    assert service.batch_ceiling() == MIN_BATCH_ENTRIES
    service._reduce_batch_ceiling()
    # 再砍也停在下限，不会归零导致批次取不到条目
    assert service.batch_ceiling() == MIN_BATCH_ENTRIES


def test_batch_ceiling_relaxes_after_success() -> None:
    """成功跑完一批要逐步放宽，避免一次截断永久压着小批次。"""

    service = _service()
    service.context_budget = {"max_messages": 1000}
    service._batch_ceiling = 20

    service._relax_batch_ceiling()

    assert service.batch_ceiling() > 20


def test_batch_ceiling_released_once_back_in_range() -> None:
    service = _service()
    service.context_budget = {"max_messages": 50}
    service._batch_ceiling = 40

    service._relax_batch_ceiling()

    # 放宽到推导值附近就彻底放开限制
    assert service.batch_ceiling() == 0


def test_reset_clears_batch_ceiling() -> None:
    service = _service()
    service._batch_ceiling = 30

    service.reset()

    assert service.batch_ceiling() == 0


# --- 用量恢复 -----------------------------------------------------------


def test_restore_metrics_round_trips() -> None:
    service = _service()
    service.restore_metrics({
        "iterations": 12,
        "steps": 30,
        "requests": 20,
        "input_tokens": 1000,
        "output_tokens": 500,
        "cached_tokens": 200,
        "cache_reported": 5,
        "elapsed_seconds": 61.5,
    })

    summary = service.metrics_summary()
    assert summary["iterations"] == 12
    assert summary["input_tokens"] == 1000
    assert summary["output_tokens"] == 500


def test_restore_metrics_ignores_dirty_values() -> None:
    """脏数据不能让状态栏显示错乱数字。"""

    service = _service()
    service.restore_metrics({
        "iterations": "12",
        "input_tokens": True,
        "elapsed_seconds": "x",
        "steps": None,
    })

    summary = service.metrics_summary()
    assert summary["iterations"] == 0
    assert summary["input_tokens"] == 0
    assert summary["elapsed_seconds"] == 0.0


def test_restore_metrics_after_reset_keeps_values() -> None:
    """open_session 是先 reset 再恢复，顺序不能被 reset 抹掉。"""

    service = _service()
    service.messages = [{"role": "user", "content": "旧"}]
    service.reset()
    service.restore_metrics({"iterations": 7, "input_tokens": 900})

    assert service.metrics_summary()["iterations"] == 7
    assert service.metrics_summary()["input_tokens"] == 900
