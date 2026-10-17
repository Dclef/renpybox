"""Agent 流水线工具：反编译、抽取、翻译状态与兜底刷新。"""

from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path
from typing import Any, Callable

from base.Base import Base
from module.Cache.CacheManager import CacheManager
from module.Config import Config
from module.Engine.Engine import Engine
from module.Extract.ReplaceGenerator import write_replace_script
from module.Localizer.Localizer import Localizer
from module.OneKey.flow import (
    detect_game_status,
    existing_translation_summary,
    extract_project_text,
    resolve_extraction_incremental,
)
from module.Renpy.ProjectPaths import RenpyProjectPaths, resolve_translation_output
from module.Renpy.renpy_tl_core import tl_dir_signature
from module.Tool.ArchiveOps import decompile_target

from ..types import ToolResult
from .inspection_tools import _old_new_summary
from .translation_tools import (
    _backup_existing_hook,
    _confirmation_context,
    _load_plan,
)


ConfigLoader = Callable[[], Config]


def _resolve_paths(config_loader: ConfigLoader | None) -> RenpyProjectPaths | None:
    config = config_loader() if config_loader is not None else Config().load()
    paths = RenpyProjectPaths.from_config(config)
    if paths is None or not paths.game_dir.is_dir():
        return None
    return paths


def _entry_count(result: Any) -> int:
    for name in ("new_strings", "total_files", "entry_count", "total_entries"):
        value = getattr(result, name, None)
        if isinstance(value, int) and value >= 0:
            return value
    return 0


def _read_cache_progress(output_folder: str) -> tuple[dict[str, Any], str, int]:
    """从翻译输出目录只读加载进度与待翻译计数。"""
    progress: dict[str, Any] = {}
    project_status = ""
    untranslated_count = 0
    cache_dir = Path(output_folder) / "cache"
    if not any(
        (cache_dir / name).is_file() for name in ("cache.db", "project.json")
    ):
        return progress, project_status, untranslated_count
    try:
        with CacheManager.LOCK:
            manager = CacheManager(service=False)
            manager.load_project_from_file(output_folder, strict=True)
            project = manager.get_project()
            progress = {**project.get_progress(), "status": project.get_status()}
            project_status = str(getattr(project.get_status(), "value", project.get_status()))
            items = manager.get_items()
            untranslated_count = sum(
                1
                for item in items
                if item.get_status() == Base.TranslationStatus.UNTRANSLATED
            )
    except Exception:
        return {}, "", 0
    return progress, project_status, untranslated_count


def _translation_state_snapshot(config: Config) -> dict[str, Any]:
    """复刻 translation.read_state 的取数口径，供 Agent 只读查询。"""
    engine = Engine.get()
    translator = getattr(engine, "translator", None)
    status = engine.get_status()
    engine_status = str(getattr(status, "value", status))

    progress: dict[str, Any] = {}
    project_status = ""
    untranslated_count = 0
    active = (
        status in (Engine.Status.TRANSLATING, Engine.Status.STOPPING)
        or engine.has_stop_barrier()
    )
    if active and translator is not None:
        extras = getattr(translator, "extras", None)
        if isinstance(extras, dict):
            raw = extras.get("progress")
            progress = dict(raw) if isinstance(raw, dict) else dict(extras)
        project_status = engine_status
    elif not active:
        output = resolve_translation_output(config)
        if output is not None:
            progress, project_status, untranslated_count = _read_cache_progress(
                str(output),
            )

    line = progress.get("line")
    total_line = progress.get("total_line")
    if (
        isinstance(line, int)
        and isinstance(total_line, int)
        and total_line > 0
        and "percent" not in progress
    ):
        progress = dict(progress)
        progress["percent"] = round(min(100.0, line / total_line * 100.0), 2)

    running_count = int(engine.get_running_task_count())
    max_workers = int(getattr(config, "max_workers", 0) or 0)
    return {
        "engine_status": engine_status,
        "running": {"running": running_count, "max": max_workers},
        "progress": progress,
        "untranslated_count": untranslated_count,
        "project_status": project_status,
        "stop_barrier": bool(engine.has_stop_barrier()),
        "single_tasks": bool(engine.has_single_tasks()),
    }


def decompile_rpyc_files(
    *,
    config_loader: ConfigLoader | None = None,
    confirmed_game_dir: str | None = None,
    __cancel_check__: Callable[[], bool] | None = None,
) -> ToolResult:
    """反编译当前项目 game 目录中的 RPYC 脚本。"""

    localizer = Localizer.get()
    paths = _resolve_paths(config_loader)
    if paths is None:
        return ToolResult(False, localizer.agent_project_not_set, code="PROJECT_NOT_SET")

    game_dir = paths.game_dir.resolve()
    if confirmed_game_dir is not None:
        confirmed_path = Path(confirmed_game_dir).resolve()
        if os.path.normcase(str(game_dir)) != os.path.normcase(str(confirmed_path)):
            return ToolResult(
                False,
                localizer.agent_unpack_project_changed,
                code="CONFIRMATION_STALE",
            )
        game_dir = confirmed_path

    rpyc_files = list(game_dir.rglob("*.rpyc"))
    if not rpyc_files:
        return ToolResult(
            False,
            localizer.agent_rpyc_not_found,
            data={"game_dir": str(game_dir), "count": 0},
            code="RPYC_NOT_FOUND",
        )

    decompiled_count = len(rpyc_files)
    if __cancel_check__ is not None and __cancel_check__():
        return ToolResult(False, localizer.agent_tool_cancelled, code="CANCELLED")

    result = decompile_target(
        str(paths.project_root),
        overwrite=False,
        use_unren=True,
        fallback_unren_options="2x",
        progress_callback=lambda _message: None,
    )
    if not result.get("success"):
        return ToolResult(
            False,
            localizer.agent_decompile_failed,
            data={"method": str(result.get("method", "failed"))},
            code="DECOMPILE_FAILED",
        )

    message = localizer.agent_decompile_complete.format(count=decompiled_count)
    return ToolResult(
        True,
        message,
        data={
            "decompiled_count": decompiled_count,
            "method": str(result.get("method", "unknown")),
        },
    )


def run_project_extraction(
    *,
    config_loader: ConfigLoader | None = None,
    incremental: bool | None = None,
    confirmed_project_root: str | None = None,
    __cancel_check__: Callable[[], bool] | None = None,
) -> ToolResult:
    """检测脚本就绪状态并抽取当前项目文本，不自动解包或反编译。"""

    localizer = Localizer.get()
    config = config_loader() if config_loader is not None else Config().load()
    paths = RenpyProjectPaths.from_config(config)
    if paths is None or not paths.game_dir.is_dir():
        return ToolResult(False, localizer.agent_project_not_set, code="PROJECT_NOT_SET")

    project_root = paths.project_root.resolve()
    if confirmed_project_root is not None:
        confirmed_root = Path(confirmed_project_root).resolve()
        if os.path.normcase(str(project_root)) != os.path.normcase(str(confirmed_root)):
            return ToolResult(
                False,
                localizer.agent_unpack_project_changed,
                code="CONFIRMATION_STALE",
            )
        project_root = confirmed_root

    language = paths.language
    cancel_check = __cancel_check__
    status, message = detect_game_status(
        str(project_root),
        language,
        cancel_check=cancel_check,
    )
    if status == "need_unpack":
        return ToolResult(
            False,
            message,
            code="NEED_UNPACK",
            data={"next_tool": "unpack_rpa_files"},
        )
    if status == "need_decompile":
        return ToolResult(
            False,
            message,
            code="NEED_DECOMPILE",
            data={"next_tool": "decompile_rpyc_files"},
        )
    if status == "cancelled":
        return ToolResult(False, localizer.agent_tool_cancelled, code="CANCELLED")
    if status == "error":
        return ToolResult(False, message or localizer.agent_extract_failed, code="EXTRACTION_FAILED")
    if status == "empty":
        return ToolResult(False, message or localizer.agent_extract_failed, code="EXTRACTION_FAILED")
    if status != "ready":
        return ToolResult(False, message or localizer.agent_extract_failed, code="EXTRACTION_FAILED")

    existing = existing_translation_summary(paths)
    if incremental is None:
        use_incremental = resolve_extraction_incremental(
            "auto",
            bool(existing["exists"]),
        )
    else:
        use_incremental = bool(incremental)

    def progress_callback(_msg: str, _pct: int) -> None:
        return None

    success, extract_message, result = extract_project_text(
        str(project_root),
        language,
        incremental=use_incremental,
        exe_path=None,
        output_to_separate_folder=True,
        progress_callback=progress_callback,
        cancel_check=cancel_check,
    )
    if getattr(result, "cancelled", False) or (
        cancel_check is not None and cancel_check()
    ):
        return ToolResult(False, localizer.agent_tool_cancelled, code="CANCELLED")
    if not success:
        return ToolResult(
            False,
            extract_message or localizer.agent_extract_failed,
            code="EXTRACTION_FAILED",
        )

    tl_dir = result.tl_dir or paths.tl_language_dir
    if use_incremental:
        output_dir = result.incremental_dir or (
            paths.tl_language_dir.parent / f"{paths.language}_new"
        )
    else:
        output_dir = tl_dir
    entry_count = _entry_count(result)
    data = {
        "tl_dir": str(tl_dir),
        "output_dir": str(output_dir),
        "incremental": use_incremental,
        "entry_count": entry_count,
    }
    message = localizer.agent_extract_complete.format(
        entry_count=entry_count,
        tl_dir=tl_dir,
    )
    return ToolResult(True, message, data=data)


def translation_status(
    *,
    config_loader: ConfigLoader | None = None,
) -> ToolResult:
    """只读查询当前翻译引擎与项目进度，不修改文件也不占用引擎。"""

    localizer = Localizer.get()
    config = config_loader() if config_loader is not None else Config().load()
    paths = RenpyProjectPaths.from_config(config)
    if paths is None or not paths.game_dir.is_dir():
        return ToolResult(False, localizer.agent_project_not_set, code="PROJECT_NOT_SET")

    data = _translation_state_snapshot(config)
    message = localizer.agent_translation_status_ready.format(
        engine_status=data["engine_status"],
        untranslated_count=data["untranslated_count"],
    )
    return ToolResult(True, message, data=data)


def refresh_replace_fallback(
    *,
    config_loader: ConfigLoader | None = None,
    confirmed_context: dict[str, Any] | None = None,
) -> ToolResult:
    """按体检口径刷新 replace_text 运行时兜底补丁。"""

    localizer = Localizer.get()
    paths, plan = _load_plan(config_loader)
    if paths is None or plan is None:
        return ToolResult(False, localizer.agent_project_not_set, code="PROJECT_NOT_SET")

    current_context = _confirmation_context(paths, plan)
    if not confirmed_context or current_context != confirmed_context:
        return ToolResult(
            False,
            localizer.agent_tool_confirmation_stale,
            code="CONFIRMATION_STALE",
        )

    old_new = _old_new_summary(paths)
    if not old_new.get("needs_refresh"):
        return ToolResult(
            True,
            localizer.agent_refresh_fallback_up_to_date,
            data={
                "refreshed": False,
                "output_path": str(plan.output_path.resolve()),
                "pair_count": len(plan.pairs),
                "backup_path": "",
            },
        )

    output_path = plan.output_path
    pair_count = len(plan.pairs)
    if not plan.pairs:
        backup_path = _backup_existing_hook(paths, output_path)
        output_path.unlink(missing_ok=True)
        output_path.with_suffix(".rpyc").unlink(missing_ok=True)
        data = {
            "refreshed": True,
            "output_path": str(output_path.resolve()),
            "pair_count": 0,
            "backup_path": str(backup_path) if backup_path is not None else "",
        }
        return ToolResult(
            True,
            localizer.agent_refresh_fallback_complete.format(count=0, output_path=output_path),
            data=data,
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_existed = output_path.exists()
    backup_path = _backup_existing_hook(paths, output_path)
    try:
        write_replace_script(
            output_path,
            plan.pairs,
            language=plan.language,
            use_translate_python=True,
            wrap_existing=True,
        )
    except Exception:
        if backup_path is not None:
            shutil.copy2(backup_path, output_path)
        elif not output_existed and output_path.exists():
            output_path.unlink()
        raise

    data = {
        "refreshed": True,
        "output_path": str(output_path.resolve()),
        "pair_count": pair_count,
        "backup_path": str(backup_path) if backup_path is not None else "",
        "signature": hashlib.sha256(
            repr(tl_dir_signature(paths.tl_language_dir)).encode("utf-8")
        ).hexdigest(),
    }
    message = localizer.agent_refresh_fallback_complete.format(
        count=pair_count,
        output_path=output_path,
    )
    return ToolResult(True, message, data=data)


__all__ = [
    "decompile_rpyc_files",
    "run_project_extraction",
    "translation_status",
    "refresh_replace_fallback",
]
