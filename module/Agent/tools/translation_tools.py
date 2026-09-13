"""Agent 的翻译后确定性优化工具。"""

from __future__ import annotations

import hashlib
import shutil
import time
from pathlib import Path
from typing import Any, Callable

from module.Config import Config
from module.Extract.ReplaceGenerator import (
    OldNewReplacePlan,
    build_old_new_replace_plan,
    write_replace_script,
)
from module.Localizer.Localizer import Localizer
from module.Renpy.ProjectPaths import RenpyProjectPaths
from module.Renpy.renpy_tl_core import tl_dir_signature

from ..types import ToolResult


def _load_plan(
    config_loader: Callable[[], Config] | None,
) -> tuple[RenpyProjectPaths | None, OldNewReplacePlan | None]:
    config = config_loader() if config_loader is not None else Config().load()
    paths = RenpyProjectPaths.from_config(config)
    if paths is None or not paths.game_dir.is_dir():
        return None, None
    return paths, build_old_new_replace_plan(
        paths.game_dir,
        paths.language,
        tl_dir=paths.tl_language_dir,
    )


def _confirmation_context(
    paths: RenpyProjectPaths,
    plan: OldNewReplacePlan,
) -> dict[str, Any]:
    signature = hashlib.sha256(
        repr(tl_dir_signature(paths.tl_language_dir)).encode("utf-8")
    ).hexdigest()
    compiled_path = plan.output_path.with_suffix(".rpyc")
    try:
        compiled_stat = compiled_path.stat()
        compiled_signature = [compiled_stat.st_mtime_ns, compiled_stat.st_size]
    except OSError:
        compiled_signature = []
    return {
        "game_dir": str(paths.game_dir.resolve()),
        "tl_dir": str(paths.tl_language_dir.resolve()),
        "output_path": str(plan.output_path.resolve()),
        "old_new_count": plan.old_new_count,
        "supplement_count": plan.supplement_count,
        "total_count": len(plan.pairs),
        "conflict_count": plan.conflict_count,
        "output_exists": plan.output_path.is_file(),
        "output_compiled_signature": compiled_signature,
        "signature": signature,
    }


def old_new_replace_confirmation_context(
    *,
    config_loader: Callable[[], Config] | None = None,
) -> dict[str, Any]:
    """返回确认框使用的可信项目、文件签名和替换统计。"""

    paths, plan = _load_plan(config_loader)
    if paths is None or plan is None:
        return {}
    return _confirmation_context(paths, plan)


def _backup_existing_hook(paths: RenpyProjectPaths, output_path: Path) -> Path | None:
    if not output_path.is_file():
        return None
    backup_dir = paths.translation_output_dir / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    base = backup_dir / f"replace_text_auto_before_old_new_{stamp}.rpy.txt"
    backup = base
    suffix = 1
    while backup.exists():
        backup = backup_dir / f"{base.stem}_{suffix}{base.suffix}"
        suffix += 1
    shutil.copy2(output_path, backup)
    return backup


def optimize_old_new_translations(
    *,
    config_loader: Callable[[], Config] | None = None,
    confirmed_context: dict[str, Any] | None = None,
) -> ToolResult:
    """把补充抽取译文生成运行时 replace_text 补丁。"""

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
    if not plan.pairs and not (
        plan.output_path.exists() or plan.output_path.with_suffix(".rpyc").exists()
    ):
        return ToolResult(
            False,
            localizer.agent_old_new_translation_not_found,
            data=current_context,
            code="OLD_NEW_TRANSLATION_NOT_FOUND",
        )

    if not plan.pairs:
        backup_path = _backup_existing_hook(paths, plan.output_path)
        plan.output_path.unlink(missing_ok=True)
        plan.output_path.with_suffix(".rpyc").unlink(missing_ok=True)
        data = dict(current_context)
        data["backup_path"] = str(backup_path) if backup_path is not None else ""
        data["signature"] = hashlib.sha256(
            repr(tl_dir_signature(paths.tl_language_dir)).encode("utf-8")
        ).hexdigest()
        return ToolResult(
            True,
            localizer.agent_old_new_stale_hook_removed.format(
                output_path=plan.output_path,
            ),
            data=data,
        )

    plan.output_path.parent.mkdir(parents=True, exist_ok=True)
    output_existed = plan.output_path.exists()
    backup_path = _backup_existing_hook(paths, plan.output_path)
    try:
        write_replace_script(
            plan.output_path,
            plan.pairs,
            language=plan.language,
            use_translate_python=True,
            wrap_existing=True,
        )
    except Exception:
        if backup_path is not None:
            shutil.copy2(backup_path, plan.output_path)
        elif not output_existed and plan.output_path.exists():
            plan.output_path.unlink()
        raise

    data = dict(current_context)
    data["backup_path"] = str(backup_path) if backup_path is not None else ""
    data["signature"] = hashlib.sha256(
        repr(tl_dir_signature(paths.tl_language_dir)).encode("utf-8")
    ).hexdigest()
    message = localizer.agent_old_new_optimization_complete.format(
        count=len(plan.pairs),
        output_path=plan.output_path,
    )
    return ToolResult(True, message, data=data)
