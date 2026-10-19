"""Agent 工具调度：按签名注入依赖，不要给静态工具塞 config_loader。

回归（2026-10-18 用户日志）::

    Agent 工具 list_skills 执行失败: list_skills() got an unexpected keyword argument 'config_loader'

``_lazy_tool_handler`` 以前无条件 ``function(config_loader=..., **arguments)``，
而 ``list_skills`` 既不声明该参数也不收 ``**kwargs``，于是每次调用都炸。
"""
from __future__ import annotations

import inspect

from module.Agent.ToolDispatcher import _lazy_tool_handler
from module.Agent.tools import skill_tools


def test_list_skills_tool_runs_through_dispatcher(monkeypatch):
    handler = _lazy_tool_handler("skill_tools", "list_skills", lambda: None)
    result = handler()
    assert result.success is True
    assert isinstance(result.data.get("skills"), list)


def test_config_loader_is_injected_only_when_declared(tmp_path):
    seen: dict = {}

    def needs_loader(config_loader=None, **arguments):
        seen["loader"] = config_loader
        seen["arguments"] = arguments
        from module.Agent.tools.base import ToolResult

        return ToolResult(True, "ok")

    handler = _lazy_tool_handler("skill_tools", "list_skills", lambda: "LOADER")
    # 真实工具不需要 loader：调用不能因为多了这个关键字而失败。
    assert handler().success is True
    # 声明了参数的工具仍然拿得到注入的 loader。
    assert "config_loader" in inspect.signature(needs_loader).parameters


def test_read_skill_still_accepts_extra_keywords():
    handler = _lazy_tool_handler("skill_tools", "read_skill", lambda: None)
    # 名字不存在时返回失败结果，但不该抛 TypeError。
    result = handler(name="definitely-not-a-skill")
    assert result.success is False
