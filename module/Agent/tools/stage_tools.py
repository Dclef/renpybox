"""Agent 阶段播报。只改会话阶段，不碰项目文件。"""

from __future__ import annotations

from module.Localizer.Localizer import Localizer
from module.OneKey.pipeline import PIPELINE_STAGES

from ..types import ToolResult


def set_stage(*, stage: str = "", config_loader=None) -> ToolResult:
    """校验阶段名并交回给会话层写入 snapshot。"""
    del config_loader
    localizer = Localizer.get()
    value = str(stage or "")
    if value not in PIPELINE_STAGES and value != "":
        return ToolResult(
            False,
            localizer.agent_pipeline_stage_invalid.format(stage=value),
            code="INVALID_STAGE",
        )
    labels = {
        "detect": localizer.agent_stage_detect,
        "unpack": localizer.agent_stage_unpack,
        "decompile": localizer.agent_stage_decompile,
        "extract": localizer.agent_stage_extract,
        "translate": localizer.agent_stage_translate,
        "apply": localizer.agent_stage_apply,
        "fallback": localizer.agent_stage_fallback,
        "done": localizer.agent_stage_done,
        "": "",
    }
    return ToolResult(
        True,
        localizer.agent_pipeline_stage_set.format(stage=labels.get(value, value)),
        data={"stage": value},
    )
