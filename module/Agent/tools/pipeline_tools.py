"""Agent 流水线工具：反编译、抽取、翻译状态与兜底刷新。"""

from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

from base.LogManager import LogManager

from base.Base import Base
from module.Cache.CacheManager import CacheManager
from module.Config import Config
from module.Engine.Engine import Engine
from module.Extract.ReplaceGenerator import write_replace_script
from module.Extract.UnifiedExtractor import UnifiedExtractor
from module.Localizer.Localizer import Localizer
from module.OneKey import flow
from module.OneKey.flow import (
    detect_game_status,
    existing_translation_summary,
    extract_project_text,
    resolve_extraction_incremental,
)
from module.OneKey.pipeline import pipeline_identity, run_pipeline
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


def _read_cache_progress(
    output_folder: str,
) -> tuple[dict[str, Any], str, int, bool]:
    """从翻译输出目录只读加载进度与待翻译计数。

    第四个返回值表示缓存是否真实存在：只有它为真时，「待译 0 条」才是可信
    的结论，否则只是「还没有缓存」。
    """

    progress: dict[str, Any] = {}
    project_status = ""
    untranslated_count = 0
    cache_dir = Path(output_folder) / "cache"
    if not any(
        (cache_dir / name).is_file() for name in ("cache.db", "project.json")
    ):
        return progress, project_status, untranslated_count, False
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
        return {}, "", 0, False
    return progress, project_status, untranslated_count, True


def _translation_state_snapshot(config: Config) -> dict[str, Any]:
    """复刻 translation.read_state 的取数口径，供 Agent 只读查询。"""
    engine = Engine.get()
    translator = getattr(engine, "translator", None)
    status = engine.get_status()
    engine_status = str(getattr(status, "value", status))

    progress: dict[str, Any] = {}
    project_status = ""
    untranslated_count = 0
    cache_ready = False
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
            progress, project_status, untranslated_count, cache_ready = (
                _read_cache_progress(str(output))
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
        "cache_ready": bool(cache_ready and not active),
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


def _official_exe(project_root: Path, exe_path: str | None) -> tuple[str | None, bool]:
    """对齐一键页：未指定时自动找项目根目录下的游戏 exe。返回 (路径, 是否非法)。"""
    from module.Tool.RenpyDecompiler import RenpyDecompiler

    selected = str(exe_path or "").strip()
    if not selected:
        found = RenpyDecompiler()._find_game_exe(project_root)
        return (str(found), False) if found else (None, False)
    executable = Path(selected).resolve()
    root = project_root.resolve()
    invalid = (
        not executable.is_file()
        or executable.suffix.lower() != ".exe"
        or executable.parent != root
    )
    if invalid:
        return None, True
    return str(executable), False


def _persist_config(config: Config) -> bool:
    save = getattr(config, "save", None)
    if not callable(save):
        return False
    try:
        save()
    except Exception as exc:
        LogManager.get().error(f"抽取路径落盘失败: {exc}")
        return False
    return True


def run_project_extraction(
    *,
    config_loader: ConfigLoader | None = None,
    incremental: bool | None = None,
    exe_path: str | None = None,
    supplement_mode: str | None = None,
    confirmed_project_root: str | None = None,
    progress_callback: Callable[[str, int, str], None] | None = None,
    __cancel_check__: Callable[[], bool] | None = None,
) -> ToolResult:
    """检测脚本就绪状态并抽取当前项目文本，不自动解包或反编译。

    ``supplement_mode`` 省略时沿用磁盘上的现有设置，避免 Agent 一次抽取把
    用户在设置页选的补充模式悄悄改掉。
    """

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

    supplement = (
        None if supplement_mode is None else str(supplement_mode).strip().lower()
    )
    if supplement is not None and supplement not in ("off", "precise", "aggressive"):
        return ToolResult(False, localizer.agent_extract_failed, code="EXTRACTION_FAILED")
    official_exe, exe_invalid = _official_exe(project_root, exe_path)
    if exe_invalid:
        return ToolResult(False, localizer.agent_extract_failed, code="EXTRACTION_FAILED")

    # 抽取器从磁盘配置读补充模式；只有调用方显式指定时才改，并先落盘再抽取。
    if supplement is not None:
        config.extract_supplement_mode = supplement
        config.extract_use_custom = supplement != "off"
    if not _persist_config(config):
        return ToolResult(False, localizer.agent_extract_failed, code="EXTRACTION_FAILED")

    previous_input = str(getattr(config, "input_folder", "") or "")
    previous_output = str(getattr(config, "output_folder", "") or "")
    try:
        flow.prepare_extraction_paths(
            config,
            str(project_root),
            language,
            incremental=use_incremental,
        )
    except Exception as exc:
        LogManager.get().error(f"抽取前配置翻译路径失败: {exc}")
        return ToolResult(False, localizer.agent_extract_failed, code="EXTRACTION_FAILED")

    def report_progress(message: str, percent: int) -> None:
        if progress_callback is None:
            return
        try:
            progress_callback("extract", int(percent), str(message or ""))
        except Exception as exc:
            LogManager.get().error(f"抽取进度回调失败: {exc}")

    success, extract_message, result = extract_project_text(
        str(project_root),
        language,
        incremental=use_incremental,
        exe_path=official_exe,
        output_to_separate_folder=True,
        progress_callback=report_progress,
        cancel_check=cancel_check,
    )
    if getattr(result, "cancelled", False) or (
        cancel_check is not None and cancel_check()
    ):
        config.input_folder = previous_input
        config.output_folder = previous_output
        _persist_config(config)
        return ToolResult(False, localizer.agent_tool_cancelled, code="CANCELLED")
    if not success:
        config.input_folder = previous_input
        config.output_folder = previous_output
        _persist_config(config)
        return ToolResult(
            False,
            extract_message or localizer.agent_extract_failed,
            code="EXTRACTION_FAILED",
        )
    if not _persist_config(config):
        return ToolResult(False, localizer.agent_extract_failed, code="EXTRACTION_FAILED")

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


def translation_apply_confirmation_context(
    *,
    config_loader: ConfigLoader | None = None,
    config: Config | None = None,
    paths: RenpyProjectPaths | None = None,
) -> dict[str, Any]:
    """返回 apply_translation 的确认上下文。

    tl 目录签名与路径一起参与比对：用户确认后若又抽取/改动了 TL 文件，
    或切换了项目，执行前会判为过期，避免把译文写进错误的目录。
    """
    if config is None:
        config = config_loader() if config_loader is not None else Config().load()
    if paths is None:
        paths = RenpyProjectPaths.from_config(config)
    if paths is None:
        return {}

    output_dir, input_dir = flow.resolve_translation_apply_paths(config)
    return {
        "tl_dir": str(paths.tl_language_dir.resolve()),
        "output_dir": str(output_dir.resolve()) if output_dir is not None else "",
        "input_dir": str(input_dir.resolve()) if input_dir is not None else "",
        "signature": hashlib.sha256(
            repr(tl_dir_signature(paths.tl_language_dir)).encode("utf-8")
        ).hexdigest(),
    }


def start_translation(
    *,
    config_loader: ConfigLoader | None = None,
    pipeline_callbacks: dict[str, Callable[..., dict]] | None = None,
    status: str = "untranslated",
    preflight_confirmed: bool = False,
    use_agent_model: bool = True,
) -> ToolResult:
    """经主事件循环启动翻译；Qt5 侧没有桥，会明确要求手动操作。"""

    localizer = Localizer.get()
    callback = (pipeline_callbacks or {}).get("start_translation")
    if callback is None:
        return ToolResult(
            False,
            localizer.agent_app_context_missing,
            code="AGENT_APP_CONTEXT_MISSING",
        )

    result = callback({
        "status": status,
        "preflight_confirmed": bool(preflight_confirmed),
        # 批量翻译默认沿用 Agent 自己配置的模型：只改写本轮冻结快照的激活平台，
        # 不落盘，也不改动翻译页的设置。
        "platform_source": "agent" if bool(use_agent_model) else "configured",
    })
    if not isinstance(result, dict):
        return ToolResult(
            False,
            localizer.agent_tool_invalid_result,
            code="INVALID_TOOL_RESULT",
        )

    if bool(result.get("accepted")):
        data = {
            "request_id": str(result.get("request_id") or ""),
            "reason": str(result.get("reason") or ""),
            "stage": str(result.get("stage") or ""),
        }
        return ToolResult(True, localizer.agent_start_translation_accepted, data=data)

    reason = str(result.get("reason") or "ERROR")
    detail = str(result.get("detail") or "")
    data = {"reason": reason, "detail": detail}
    status_code = result.get("status_code")
    if isinstance(status_code, int):
        data["status_code"] = status_code
    return ToolResult(
        False,
        localizer.agent_start_translation_rejected.format(reason=reason, detail=detail),
        data=data,
        code=reason,
    )


def stop_translation(
    *,
    config_loader: ConfigLoader | None = None,
    pipeline_callbacks: dict[str, Callable[..., dict]] | None = None,
) -> ToolResult:
    """经主事件循环请求停止翻译；真正的终态由翻译进度事件返回。"""

    localizer = Localizer.get()
    callback = (pipeline_callbacks or {}).get("stop_translation")
    if callback is None:
        return ToolResult(
            False,
            localizer.agent_app_context_missing,
            code="AGENT_APP_CONTEXT_MISSING",
        )

    result = callback({})
    if not isinstance(result, dict):
        return ToolResult(
            False,
            localizer.agent_tool_invalid_result,
            code="INVALID_TOOL_RESULT",
        )

    status = str(result.get("status") or "")
    if bool(result.get("ok")) or status == "STOPPING":
        return ToolResult(
            True,
            localizer.agent_translation_stopped,
            data={"status": status},
        )

    reason = str(result.get("reason") or "ERROR")
    detail = str(result.get("detail") or "")
    message = localizer.agent_translation_stop_failed
    if detail:
        message = f"{message} {detail}"
    return ToolResult(
        False,
        message,
        data={"reason": reason, "detail": detail},
        code=reason,
    )


def apply_translation(
    *,
    config_loader: ConfigLoader | None = None,
    mode: str = "full",
    confirmed_context: dict[str, Any] | None = None,
) -> ToolResult:
    """把翻译输出目录中的译文写回游戏 TL 目录（full / incremental）。"""

    localizer = Localizer.get()
    config = config_loader() if config_loader is not None else Config().load()
    paths = RenpyProjectPaths.from_config(config)
    if paths is None:
        return ToolResult(
            False,
            localizer.agent_project_not_set,
            code="PROJECT_NOT_SET",
        )

    current_context = translation_apply_confirmation_context(config=config, paths=paths)
    if not confirmed_context or current_context != dict(confirmed_context):
        return ToolResult(
            False,
            localizer.agent_tool_confirmation_stale,
            code="CONFIRMATION_STALE",
        )

    output_dir, input_dir = flow.resolve_translation_apply_paths(config)
    if (
        output_dir is None
        or input_dir is None
        or not str(getattr(config, "output_folder", "") or "").strip()
        or not str(getattr(config, "input_folder", "") or "").strip()
    ):
        return ToolResult(
            False,
            localizer.agent_apply_target_invalid,
            code="APPLY_TARGET_INVALID",
        )

    normalized = str(mode or "full").strip().lower()
    if normalized not in ("full", "incremental"):
        return ToolResult(
            False,
            localizer.agent_apply_translation_failed,
            code="APPLY_FAILED",
        )

    file_count = 0
    if normalized == "incremental":
        ok, message, payload = flow.apply_incremental_translation(
            extractor = UnifiedExtractor(),
            config = config,
            game_dir = str(paths.project_root),
            tl_name = paths.language,
            output_dir = Path(output_dir),
            main_output = paths.translation_output_dir,
            incremental_dir = paths.tl_root / f"{paths.language}_new",
            progress_callback = None,
            clean_duplicates = bool(
                getattr(config, "renpy_incremental_auto_merge_cleanup", True)
            ),
        )
    else:
        files = [path for path in Path(output_dir).rglob("*.rpy") if path.is_file()]
        file_count = len(files)
        if not files:
            return ToolResult(
                False,
                localizer.agent_apply_no_output_files,
                data={"output_dir": str(output_dir)},
                code="NO_OUTPUT_FILES",
            )
        ok, message, payload = flow.apply_full_translation(
            config = config,
            output_files = files,
            output_dir = Path(output_dir),
            input_dir = Path(input_dir),
            project_root = str(paths.project_root),
            project_language = paths.language,
        )

    if not ok:
        return ToolResult(
            False,
            message or localizer.agent_apply_translation_failed,
            data={
                "mode": normalized,
                "output_dir": str(output_dir),
                "target_dir": str(input_dir),
            },
            code="APPLY_FAILED",
        )

    applied_count = 0
    if isinstance(payload, dict):
        for key in ("count", "applied_count", "success_count", "files"):
            value = payload.get(key)
            if isinstance(value, int) and value >= 0:
                applied_count = value
                break
        else:
            applied_count = file_count
    else:
        applied_count = file_count

    failed_count = 0
    if isinstance(payload, dict):
        for key in ("failed_count", "failed"):
            value = payload.get(key)
            if isinstance(value, int) and value >= 0:
                failed_count = value
                break

    data = {
        "mode": normalized,
        "applied_count": applied_count,
        "failed_count": failed_count,
        "output_dir": str(output_dir),
        "target_dir": str(input_dir),
    }
    return ToolResult(
        True,
        localizer.agent_apply_translation_complete.format(
            count=applied_count,
            output_dir=Path(input_dir),
        ),
        data=data,
    )


def _pipeline_stage_label(stage: str) -> str:
    localizer = Localizer.get()
    labels = {
        "detect": localizer.agent_stage_detect,
        "unpack": localizer.agent_stage_unpack,
        "decompile": localizer.agent_stage_decompile,
        "extract": localizer.agent_stage_extract,
        "translate": localizer.agent_stage_translate,
        "apply": localizer.agent_stage_apply,
        "fallback": localizer.agent_stage_fallback,
        "done": localizer.agent_stage_done,
    }
    return labels.get(stage, stage)


def _pipeline_message(outcome) -> str:
    localizer = Localizer.get()
    data = outcome.data or {}
    code = outcome.code
    if code == "OK":
        return localizer.agent_pipeline_complete.format(
            steps=len(data.get("steps") or []),
            applied_files=data.get("applied_files", 0),
            fallback_count=data.get("fallback_count", 0),
        )
    if code == "CANCELLED":
        return localizer.agent_pipeline_cancelled
    if code == "ENGINE_BUSY":
        return localizer.agent_pipeline_engine_busy
    if code == "TRANSLATION_INCOMPLETE":
        return localizer.agent_pipeline_translation_incomplete.format(
            untranslated_count=data.get("untranslated_count", 0),
        )
    if code == "PROJECT_CHANGED":
        return localizer.agent_pipeline_project_changed
    if code == "PROJECT_NOT_SET":
        return localizer.agent_project_not_set
    if code == "TRANSLATION_NOT_STARTED":
        return localizer.agent_pipeline_translation_not_started
    steps = data.get("steps") or []
    stage = str(steps[-1].get("stage") or "") if steps else ""
    return localizer.agent_pipeline_stage_failed.format(
        stage=_pipeline_stage_label(stage),
        detail=outcome.message or code,
    )


def run_onekey_pipeline(
    *,
    config_loader: ConfigLoader | None = None,
    pipeline_callbacks: dict[str, Callable[..., dict]] | None = None,
    incremental: str = "auto",
    auto_apply: bool = True,
    auto_fallback: bool = True,
    preflight_confirmed: bool = False,
    use_agent_model: bool = True,
    progress_callback: Callable[..., Any] | None = None,
    __cancel_check__: Callable[[], bool] | None = None,
    confirmed_context: dict | None = None,
) -> ToolResult:
    """一次确认跑完整盘：解包、反编译、抽取、翻译、回填、兜底。"""
    localizer = Localizer.get()
    config = config_loader() if config_loader is not None else Config().load()
    current = pipeline_identity(config)
    if not confirmed_context or dict(confirmed_context) != current:
        return ToolResult(
            False,
            localizer.agent_tool_confirmation_stale,
            code="CONFIRMATION_STALE",
        )

    bridge = pipeline_callbacks or {}

    def unpack(cancel_check):
        from .archive_tools import unpack_rpa_files

        paths = _resolve_paths(config_loader)
        return unpack_rpa_files(
            config_loader=config_loader,
            confirmed_game_dir=str(paths.game_dir.resolve()) if paths is not None else "",
        )

    def decompile(cancel_check):
        paths = _resolve_paths(config_loader)
        return decompile_rpyc_files(
            config_loader=config_loader,
            confirmed_game_dir=str(paths.game_dir.resolve()) if paths is not None else "",
            __cancel_check__=cancel_check,
        )

    def extract(use_incremental: bool, cancel_check, progress):
        paths = _resolve_paths(config_loader)
        return run_project_extraction(
            config_loader=config_loader,
            incremental=use_incremental,
            confirmed_project_root=str(paths.project_root.resolve()) if paths is not None else "",
            progress_callback=progress,
            __cancel_check__=cancel_check,
        )

    def start_translation_callback(params: dict) -> dict:
        callback = bridge.get("start_translation")
        if callback is None:
            return {
                "accepted": False,
                "reason": "AGENT_APP_CONTEXT_MISSING",
                "detail": localizer.agent_app_context_missing,
            }
        result = callback(params)
        return result if isinstance(result, dict) else {"accepted": False, "reason": "ERROR", "detail": ""}

    def stop_translation_callback() -> dict:
        callback = bridge.get("stop_translation")
        if callback is None:
            return {"ok": False, "reason": "AGENT_APP_CONTEXT_MISSING"}
        result = callback({})
        return result if isinstance(result, dict) else {"ok": False}

    def translation_state() -> dict:
        live = config_loader() if config_loader is not None else Config().load()
        return _translation_state_snapshot(live)

    def apply(mode: str):
        context = translation_apply_confirmation_context(config_loader=config_loader)
        return apply_translation(
            config_loader=config_loader,
            mode=mode,
            confirmed_context=context,
        )

    def fallback():
        paths, plan = _load_plan(config_loader)
        if paths is None or plan is None:
            return ToolResult(False, localizer.agent_project_not_set, code="PROJECT_NOT_SET")
        return refresh_replace_fallback(
            config_loader=config_loader,
            confirmed_context=_confirmation_context(paths, plan),
        )

    outcome = run_pipeline(
        config,
        callbacks=SimpleNamespace(
            unpack=unpack,
            decompile=decompile,
            extract=extract,
            start_translation=start_translation_callback,
            stop_translation=stop_translation_callback,
            translation_state=translation_state,
            apply=apply,
            fallback=fallback,
        ),
        progress=progress_callback,
        cancel_check=__cancel_check__,
        incremental=incremental,
        auto_apply=auto_apply,
        auto_fallback=auto_fallback,
        preflight_confirmed=preflight_confirmed,
        use_agent_model=use_agent_model,
    )
    return ToolResult(
        outcome.success,
        _pipeline_message(outcome),
        data=dict(outcome.data or {}),
        code=outcome.code if outcome.success or outcome.code else "OK",
        continues=False,
    )


__all__ = [
    "apply_translation",
    "decompile_rpyc_files",
    "pipeline_identity",
    "refresh_replace_fallback",
    "run_onekey_pipeline",
    "run_project_extraction",
    "start_translation",
    "stop_translation",
    "translation_apply_confirmation_context",
    "translation_status",
]
