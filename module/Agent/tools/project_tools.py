"""Agent 一期的项目查询与项目设定工具。"""

from __future__ import annotations

from typing import Any, Callable

from module.Config import Config
from module.Renpy.ProjectPaths import (
    RenpyProjectPaths,
    apply_to_config,
    looks_like_renpy_path,
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
        message="尚未设定项目目录，请先询问用户游戏所在目录，再调用 set_project。",
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
        return ToolResult(False, "项目路径不能为空。", code="INVALID_PROJECT_PATH")
    if not looks_like_renpy_path(raw_path):
        return ToolResult(
            False,
            "路径不像有效的 Ren'Py 项目（需要 game 或 tl 目录）。",
            code="INVALID_PROJECT_PATH",
        )

    current = _config(config, config_loader)
    paths = RenpyProjectPaths.from_path(raw_path)
    if paths is None or not paths.game_dir.is_dir():
        return ToolResult(
            False,
            "无法定位存在的 game 目录，项目目录未写入配置。",
            code="INVALID_PROJECT_PATH",
        )

    apply_to_config(current, paths)
    current.save()
    data = _path_data(paths)
    return ToolResult(
        True,
        f"已设定项目：{data['project_root']}（语言：{data['language']}）",
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
    return ToolResult(True, f"当前项目：{data['project_root']}（语言：{data['language']}）", data=data)


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
    if not names:
        return ToolResult(True, "当前项目没有找到 RPA 文件。", data={"files": [], "count": 0})
    return ToolResult(
        True,
        f"当前项目找到 {len(names)} 个 RPA 文件：" + ", ".join(names[:50]),
        data={
            "files": names[:100],
            "count": len(names),
            "truncated": len(names) > 100,
        },
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
        message = "脚本扫描完成，未发现错误。"
    else:
        message = f"脚本扫描完成，发现 {total} 个问题，已返回前 {sum(len(v) for v in limited.values())} 个。"
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
