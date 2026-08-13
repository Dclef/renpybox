"""Agent 系统提示词构建。"""

from __future__ import annotations

from module.Localizer.Localizer import Localizer


class AgentPromptBuilder:
    """描述 Agent 工具边界，不向模型暴露文件系统自由读写能力。"""

    @staticmethod
    def build_system_prompt(_config: object) -> str:
        return Localizer.get().agent_system_prompt
