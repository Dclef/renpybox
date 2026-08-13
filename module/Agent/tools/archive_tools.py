"""Agent 的 RPA 归档工具。"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

from module.Config import Config
from module.Localizer.Localizer import Localizer
from module.Renpy.ProjectPaths import RenpyProjectPaths
from module.Tool.Packer import Packer

from ..types import ToolResult


def unpack_rpa_files(
    *,
    config_loader: Callable[[], Config] | None = None,
    packer_factory: Callable[[], Packer] = Packer,
    confirmed_game_dir: str | None = None,
) -> ToolResult:
    """解包当前项目的全部 RPA；路径只从服务端配置读取。"""
    config = config_loader() if config_loader is not None else Config().load()
    paths = RenpyProjectPaths.from_config(config)
    if paths is None or not paths.game_dir.is_dir():
        return ToolResult(
            False,
            Localizer.get().agent_project_not_set,
            code="PROJECT_NOT_SET",
        )

    game_dir = paths.game_dir.resolve()
    if confirmed_game_dir is not None:
        confirmed_path = Path(confirmed_game_dir).resolve()
        if os.path.normcase(str(game_dir)) != os.path.normcase(str(confirmed_path)):
            return ToolResult(
                False,
                Localizer.get().agent_unpack_project_changed,
                code="CONFIRMATION_STALE",
            )
        game_dir = confirmed_path

    files = list(game_dir.glob("*.rpa"))
    if not files:
        return ToolResult(
            False,
            Localizer.get().agent_rpa_not_found,
            data={"game_dir": str(game_dir), "count": 0},
            code="RPA_NOT_FOUND",
        )

    result = packer_factory().unpack_rpa_files(
        str(game_dir),
        direct=True,
        script_only=False,
        remove_archives=False,
    )
    success = bool(result.get("success"))
    count = int(result.get("count", 0))
    method = str(result.get("method", "none"))
    data = {
        "game_dir": str(game_dir),
        "archive_count": len(files),
        "unpacked_count": count,
        "method": method,
        "archives_removed": False,
    }
    if success:
        message = Localizer.get().agent_unpack_complete.format(count=count)
        return ToolResult(True, message, data=data)
    return ToolResult(
        False,
        Localizer.get().agent_unpack_failed,
        data=data,
        code="RPA_UNPACK_FAILED",
    )
