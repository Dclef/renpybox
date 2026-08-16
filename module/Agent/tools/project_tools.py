"""Agent 一期的项目查询与项目设定工具。"""

from __future__ import annotations

from typing import Any, Callable

from module.Config import Config
from module.Localizer.Localizer import Localizer
from module.Renpy.ProjectPaths import (
    RenpyProjectPaths,
    apply_to_config,
    looks_like_renpy_path,
    source_script_counts,
)
from module.Tool.ErrorRepairer import ErrorRepairer


ConfigLoader = Callable[[], Config]


def _config(config: Config | None, loader: ConfigLoader | None) -> Config:
    if config is not None:
        return config
    return loader() if loader is not None else Config().load()


def _not_set() -> "ToolResult":
    from module.Agent.types import ToolResult

    return ToolResult(
        success=False,
        code="PROJECT_NOT_SET",
        message=Localizer.get().agent_project_not_set_ask,
    )


def _resolve_paths(config: Config) -> RenpyProjectPaths | None:
    paths = RenpyProjectPaths.from_config(config)
    if paths is None or not paths.game_dir.is_dir():
        return None
    return paths


def _path_data(paths: RenpyProjectPaths) -> dict[str, str]:
    return {
        "project_root": str(paths.project_root),
        "game_dir": str(paths.game_dir),
        "language": paths.language,
    }


def set_project(
    path: str,
    *,
    config: Config | None = None,
    config_loader: ConfigLoader | None = None,
) -> "ToolResult":
    """设定全局项目目录；这是一期唯一接收路径的工具。"""
    from module.Agent.types import ToolResult

    raw_path = str(path or "").strip()
    if not raw_path:
        return ToolResult(
            False,
            Localizer.get().agent_project_path_empty,
            code="INVALID_PROJECT_PATH",
        )
    if not looks_like_renpy_path(raw_path):
        return ToolResult(
            False,
            Localizer.get().agent_project_path_invalid,
            code="INVALID_PROJECT_PATH",
        )

    current = _config(config, config_loader)
    paths = RenpyProjectPaths.from_path(raw_path)
    if paths is None or not paths.game_dir.is_dir():
        return ToolResult(
            False,
            Localizer.get().agent_project_game_not_found,
            code="INVALID_PROJECT_PATH",
        )

    apply_to_config(current, paths)
    current.save()
    data = _path_data(paths)
    return ToolResult(
        True,
        Localizer.get().agent_project_set.format(**data),
        data=data,
    )


def get_project_info(
    *,
    config: Config | None = None,
    config_loader: ConfigLoader | None = None,
) -> "ToolResult":
    """读取当前全局项目，不接收路径参数。"""
    from module.Agent.types import ToolResult

    paths = _resolve_paths(_config(config, config_loader))
    if paths is None:
        return _not_set()
    data = _path_data(paths)
    return ToolResult(
        True,
        Localizer.get().agent_project_current.format(**data),
        data=data,
    )


def list_rpa_files(
    *,
    config: Config | None = None,
    config_loader: ConfigLoader | None = None,
) -> "ToolResult":
    """列出当前项目 game 目录下的 RPA 文件，不接收路径参数。"""
    from module.Agent.types import ToolResult

    paths = _resolve_paths(_config(config, config_loader))
    if paths is None:
        return _not_set()
    files = sorted(paths.game_dir.glob("*.rpa"), key=lambda item: item.name.casefold())
    names = [item.name for item in files]
    rpy_count, rpyc_count = source_script_counts(paths)
    unpack_required = bool(names) and rpy_count == 0 and rpyc_count == 0
    rpa_state = (
        "required"
        if unpack_required
        else "scripts_present"
        if names
        else "not_applicable"
    )
    data = {
        "files": names[:100],
        "count": len(names),
        "truncated": len(names) > 100,
        "rpy_count": rpy_count,
        "rpyc_count": rpyc_count,
        "unpack_required": unpack_required,
        "rpa_state": rpa_state,
    }
    if not names:
        return ToolResult(
            True,
            Localizer.get().agent_rpa_not_found,
            data=data,
        )
    return ToolResult(
        True,
        Localizer.get().agent_rpa_found.format(
            count=len(names),
            files=", ".join(names[:50]),
        ),
        data=data,
    )


def scan_script_errors(
    *,
    config: Config | None = None,
    config_loader: ConfigLoader | None = None,
) -> "ToolResult":
    """扫描当前项目脚本错误，不接收路径参数，也不修改文件。"""
    from module.Agent.types import ToolResult

    paths = _resolve_paths(_config(config, config_loader))
    if paths is None:
        return _not_set()
    errors = ErrorRepairer().check_folder(str(paths.game_dir))
    total = sum(len(items) for items in errors.values())
    limited: dict[str, list[dict[str, Any]]] = {}
    remaining = 100
    for file_path, items in sorted(errors.items()):
        if remaining <= 0:
            break
        selected = list(items[:remaining])
        limited[file_path] = selected
        remaining -= len(selected)
    if total == 0:
        message = Localizer.get().agent_scan_no_errors
    else:
        returned = sum(len(v) for v in limited.values())
        message = Localizer.get().agent_scan_errors.format(
            total=total,
            returned=returned,
        )
    return ToolResult(
        True,
        message,
        data={
            "errors": limited,
            "file_count": len(errors),
            "error_count": total,
            "truncated": total > sum(len(v) for v in limited.values()),
        },
    )
