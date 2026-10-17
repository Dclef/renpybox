"""Agent 系统提示词构建。"""

from __future__ import annotations

from module.Localizer.Localizer import Localizer


MAX_CATALOG_ENTRIES = 20


def _render_skills_catalog() -> str:
    """把技能包目录渲染成提示词片段。

    只放名字与一句话描述，正文由 ``read_skill`` 按需加载：目录常驻上下文，
    正文不常驻，避免每次请求都为用不到的领域知识付 token。
    """

    try:
        from module.Agent.tools.skill_tools import _iter_skill_metas
    except Exception:  # noqa: BLE001 - 技能目录缺失不应让提示词构建失败
        return ""

    metas = _iter_skill_metas()
    if not metas:
        return ""

    localizer = Localizer.get()
    lines = [localizer.agent_skills_catalog_header]
    for meta in metas[:MAX_CATALOG_ENTRIES]:
        lines.append(f"- {meta.name}: {meta.description}")
    if len(metas) > MAX_CATALOG_ENTRIES:
        lines.append(localizer.agent_skills_catalog_truncated.format(count=len(metas)))
    lines.append(localizer.agent_skills_catalog_hint)
    return "\n".join(lines)


class AgentPromptBuilder:
    """描述 Agent 工具边界，不向模型暴露文件系统自由读写能力。"""

    @staticmethod
    def build_system_prompt(_config: object) -> str:
        base = Localizer.get().agent_system_prompt
        catalog = _render_skills_catalog()
        if not catalog:
            return base
        return f"{base}\n\n{catalog}"
