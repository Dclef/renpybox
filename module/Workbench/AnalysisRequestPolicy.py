"""术语扫描 / 工作台分析请求的平台策略。"""

from __future__ import annotations

import copy
from typing import Any, Callable

from module.Engine.TaskRequester import TaskRequester, ThinkingLevel

# 术语抽取与世界观/角色卡分析只需要结构化短输出，高思考档位会让单次请求
# 产出数万字推理却只有几百字结果；这类任务把思考档位封顶到 LOW。
ANALYSIS_THINKING_CAP = ThinkingLevel.LOW
_REDUCIBLE_LEVELS = frozenset({ThinkingLevel.MEDIUM, ThinkingLevel.HIGH, ThinkingLevel.MAX})


def build_analysis_platform(
    platform: Any,
    log: Callable[[str], None] | None = None,
) -> Any:
    """返回思考档位封顶为 LOW 的独立平台副本；OFF/LOW 与其他字段保持不变。"""
    if not isinstance(platform, dict):
        return platform

    request_platform = copy.deepcopy(platform)
    raw_thinking = request_platform.get("thinking")
    level = TaskRequester.resolve_thinking_level(raw_thinking)
    if level not in _REDUCIBLE_LEVELS:
        return request_platform

    if isinstance(raw_thinking, dict):
        raw_thinking["level"] = ANALYSIS_THINKING_CAP.value
    else:
        request_platform["thinking"] = {"level": ANALYSIS_THINKING_CAP.value}
    if callable(log):
        log(f"分析请求思考档位：{level.value} → {ANALYSIS_THINKING_CAP.value}")
    return request_platform
