"""错误修复：扫描 / 自动修复 / lint / 导出报告，对齐 Qt ErrorRepairPage。"""

from __future__ import annotations

import asyncio
import contextlib
import os
from pathlib import Path
from typing import Any, Callable

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from api.jobs import Job
from module.Cache.CacheManager import CacheManager
from module.Engine.Engine import Engine
from module.Extract.GameExtractionRules import project_key as derive_project_key
from module.Localizer.Localizer import Localizer
from module.Renpy.ProjectPaths import RenpyProjectPaths
from module.Tool import ErrorRepairer as error_repairer_module
from module.Tool.ErrorRepairer import ErrorRepairer
from module.Tool.LexicalFs import lexical_abs, require_no_link_escape
from utils.call_game_python import get_game_path_from_game_dir

router = APIRouter(prefix="/api/error-repair", tags=["error-repair"])

KIND_SCAN = "error_repair_scan"
KIND_FIX = "error_repair_fix"
KIND_LINT = "error_repair_lint"
KINDS = (KIND_SCAN, KIND_FIX, KIND_LINT)
_BUSY = "已有任务正在运行或收尾，请稍后再试"

# 轮询快照必须保持小体积：明细只给样本，全量走导出。
MANUAL_SAMPLE_LIMIT = 10
# lint 结果同样走样本：轮询每 1.5 秒拉一次，大项目动辄上千条。
LINT_SAMPLE_LIMIT = 20
_AUTO_FIX_TYPES = frozenset({"indent", "empty_block", "duplicate_old_new", "unescaped_dialogue_quotes"})
_CONDITIONAL_FIX_TYPES = frozenset({"indentation_level", "quotes"})

# 进程内按目录身份缓存最近一次成功扫描，扫描失败时保留供导出
_LAST_SCAN: dict[str, dict[str, list[dict]]] = {}


def _norm(value: str) -> str:
    return os.path.normcase(os.path.abspath(value)) if value else ""


def _project_identity(config: Any) -> tuple[str, ...]:
    return tuple(
        _norm(str(getattr(config, field, "") or ""))
        for field in (
            "renpy_project_path",
            "renpy_game_folder",
            "renpy_tl_folder",
            "input_folder",
            "output_folder",
        )
    )


def _folder_key(folder: Path) -> str:
    return derive_project_key(folder)


class FolderBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    folder: str = Field(min_length=1, pattern=r"\S")
    project_key: str = ""
    # 绑定项目 owner 快照；与 target project_key 分离，切项目后旧请求必须 409
    owner_project_key: str = ""


class ScanBody(FolderBody):
    check_indent: bool = True
    check_indent_level: bool = False


class FixBody(FolderBody):
    fix_indent: bool = True
    fix_indent_level: bool = False
    fix_quotes: bool = False
    fix_dialogue_quotes: bool = False
    fix_empty_blocks: bool = False
    fix_trailing_spaces: bool = False
    fix_duplicates: bool = False
    fix_environment: bool = False
    environment_action: str = Field(default="merge", pattern=r"^(merge|move)$")
    # 单卡片操作：只处理本次扫描里路径一致的那一条环境问题；为空表示处理全部。
    environment_path: str = ""
    confirm: bool = False
    # 修复后顺带跑一次 Ren'Py Lint 复检（只看译文真问题），省得再单独检查一遍。
    lint_after: bool = False


class LintBody(FolderBody):
    game_exe: str = Field(min_length=1, pattern=r"\S")
    # 大型项目首次 lint 常需数分钟；旧版固定 120 秒会把正常项目判成失败。
    timeout_seconds: int = Field(default=1800, ge=30, le=7200)
    # 检查范围：译文与源码分开检查、分开出结果；all 一次给两组（兼容旧调用）。
    scope: str = Field(default="all", pattern=r"^(tl|source|all)$")


class ExportBody(FolderBody):
    output_path: str = Field(min_length=1, pattern=r"\S")
    report: dict[str, list[dict]] | None = None


def current_paths(config: Any) -> RenpyProjectPaths | None:
    return RenpyProjectPaths.from_config(config)


def _resolve_folder_operation(
    config: Any,
    *,
    folder: str,
    body_project_key: str,
    body_owner_key: str,
    require_lexical_clean: bool = False,
) -> tuple[str, Path, str, tuple[str, ...] | None]:
    """解析目标目录 + 校验 owner/target 快照。

    - project_key：必须等于目标目录键（若提供）
    - owner_project_key：有绑定时必须精确等于当前 owner；未绑定则必须为空
    """
    bound = current_paths(config)
    owner_key = bound.project_key if bound is not None else ""
    owner_identity = _project_identity(config) if bound is not None else None
    raw = str(folder or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="翻译目录必填")
    resolved = ErrorRepairer.resolve_translation_folder(raw)
    try:
        if require_lexical_clean:
            resolved = require_no_link_escape(resolved, label="翻译目录")
        else:
            resolved = lexical_abs(resolved)
            if not resolved.is_dir():
                raise FileNotFoundError(f"翻译目录不存在: {resolved}")
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if resolved.parent == resolved:
        raise HTTPException(status_code=400, detail="不能对磁盘根目录操作")
    target_key = _folder_key(resolved)
    body_key = str(body_project_key or "").strip()
    body_owner = str(body_owner_key or "").strip()
    if body_key and body_key != target_key:
        raise HTTPException(status_code=409, detail="项目已切换，请重新加载后再操作")
    if owner_key:
        if body_owner != owner_key:
            raise HTTPException(status_code=409, detail="项目已切换，请重新加载后再操作")
    elif body_owner:
        raise HTTPException(status_code=409, detail="项目已切换，请重新加载后再操作")
    return target_key, resolved, owner_key, owner_identity


def _latest_job(request: Request, project_key: str) -> Job | None:
    return next(
        (
            job for job in request.app.state.jobs.list()
            if job.kind in KINDS and isinstance(job.result, dict)
            and job.result.get("project_key") == project_key
        ),
        None,
    )


def _acquire_engine() -> Engine:
    engine = Engine.get()
    if not engine.try_set_status(Engine.Status.IDLE, Engine.Status.TESTING):
        raise HTTPException(status_code=409, detail=_BUSY)
    return engine


def _lint_sample(items: list[dict], limit: int = LINT_SAMPLE_LIMIT) -> list[dict]:
    """轮询快照只带样本：大项目 lint 动辄上千条。"""
    return [
        {
            "file": str(item.get("file") or ""),
            "line": int(item.get("line") or 0),
            "type": str(item.get("type") or ""),
            "message": str(item.get("message") or item.get("raw") or ""),
        }
        for item in items[:limit]
    ]


def _split_lint_hits(repairer: ErrorRepairer, output: str, folder: str) -> tuple[list[dict], list[dict], int]:
    """解析 lint 报告 → (译文真问题, 源码真问题, 已忽略的常见写法提示数)。"""
    parsed = repairer.parse_lint_errors(output)
    tl_hits, source_hits = repairer.split_lint_errors(parsed, folder)
    hints = frozenset(str(item) for item in error_repairer_module.IGNORED_LINT_HINT_TYPES)
    real_source = [item for item in source_hits if str(item.get("type") or "") not in hints]
    return tl_hits, real_source, len(source_hits) - len(real_source)


def _detect_game_exe(bound: RenpyProjectPaths | None, folder: Path | None) -> str:
    """猜一个可直接执行 lint 的游戏主程序（同名 .py + .exe 才算数）。

    深度 Lint 要求填游戏主程序；这一项在项目里其实能自动定出来，让用户每次
    手填等于把 lint 挡在门外。候选顺序：已绑定项目的根目录 → 翻译目录向上找
    到的项目根。找不到就留空，仍可手选。
    """
    roots: list[Path] = []
    if bound is not None:
        roots.append(Path(bound.project_root))
    if folder is not None:
        cursor = folder
        for _ in range(4):
            if (cursor / "game").is_dir():
                roots.append(cursor)
                break
            if cursor.parent == cursor:
                break
            cursor = cursor.parent
    for root in roots:
        try:
            found = get_game_path_from_game_dir(str(root))
        except OSError:
            found = None
        if found:
            return str(found)
    return ""


def _describe(folder: Path, *, owner_key: str = "") -> dict[str, Any]:
    key = _folder_key(folder)
    return {
        "project_key": key,
        "folder": str(folder),
        "owner_project_key": owner_key,
        "has_scan_report": key in _LAST_SCAN,
    }


def _cancelled(check_cancel: Callable[[], None]) -> Callable[[], bool]:
    """把「取消即抛 CancelledError」的检查适配成引擎使用的 should_cancel 回调。"""

    def probe() -> bool:
        try:
            check_cancel()
        except asyncio.CancelledError:
            return True
        return False

    return probe


def _make_scan_progress(
    progress: Callable[[str, int], None],
    check_cancel: Callable[[], None],
    *,
    base: int = 0,
    span: int = 99,
) -> Callable[[dict], None]:
    """把扫描进度回调映射到任务进度条；base/span 供修复流程分阶段复用。"""
    phases = {
        "enumerate": "收集文件",
        "read": "读取",
        "parse": "解析",
        "check": "检查格式",
        "translation": "检查译文",
        "file_done": "文件完成",
    }

    def report(state: dict) -> None:
        check_cancel()
        done, total = state["scanned_files"], state["total_files"]
        percent = base if not total else base + int(span * (done + state["fraction"]) / total)
        name = Path(state["file"]).name if state["file"] else ""
        line = f"，第 {state['line']} 行" if state["line"] else ""
        progress(
            f"{phases[state['phase']]} {name}{line}（已完成 {done}/{total} 个文件，{state['elapsed']:.0f} 秒）",
            percent,
        )

    return report


def _issues_by_type(report: dict[str, list[dict]]) -> dict[str, int]:
    """按类型统计问题数，数量倒序，便于前端直接展示。"""
    counts: dict[str, int] = {}
    for errors in report.values():
        for error in errors:
            kind = str(error.get("type") or "")
            if not kind:
                continue
            counts[kind] = counts.get(kind, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def _classify_issue(issue_type: str) -> str:
    """优先用引擎分类；引擎未提供时回落到本地白名单，未知类型按需人工处理。"""
    classifier = getattr(error_repairer_module, "classify_issue_type", None)
    if callable(classifier):
        try:
            return str(classifier(issue_type))
        except Exception:  # pragma: no cover - 分类异常时保守处理
            pass
    if issue_type in _AUTO_FIX_TYPES:
        return "auto"
    if issue_type in _CONDITIONAL_FIX_TYPES:
        return "conditional"
    return "manual"


def _environment_issues(scan: Any) -> list[dict]:
    items = getattr(scan, "environment_issues", None) or []
    return [dict(item) for item in items if isinstance(item, dict)]


def _manual_sample(report: dict[str, list[dict]], limit: int = MANUAL_SAMPLE_LIMIT) -> list[dict]:
    """轮询快照只带少量需人工条目，全量明细走 /export。"""
    sample: list[dict] = []
    for file_path, errors in report.items():
        for error in errors:
            issue_type = str(error.get("type") or "")
            if _classify_issue(issue_type) == "auto":
                continue
            sample.append({
                "file": str(file_path),
                "line": int(error.get("line") or 0),
                "type": issue_type,
                "message": str(error.get("message") or ""),
                "fixable": False,
            })
            if len(sample) >= limit:
                return sample
    return sample


def _sample_limit(total: int) -> int:
    """大结果收敛样本条数：轮询快照必须足够小（既有测试要求 2000 条问题时 <3000 字节）。"""
    if total <= 300:
        return MANUAL_SAMPLE_LIMIT
    if total <= 1200:
        return 3
    return 2


def _normalize_environment_fix(outcome: Any, issue: dict, action: str) -> dict:
    """环境修复结果统一成 {path, action, ok, message}。"""
    data = dict(outcome) if isinstance(outcome, dict) else {}
    path = str(data.get("path") or issue.get("path") or "")
    ok = bool(data.get("ok", data.get("success", False)))
    message = str(data.get("message") or "")
    if not message:
        loc = Localizer.get()
        name = Path(path).name
        if ok:
            message = (
                loc.error_repair_env_merged.format(name=name, tl=Path(path).parent.name)
                if action == "merge"
                else loc.error_repair_env_moved.format(name=name, target=str(data.get("target") or path))
            )
        else:
            message = loc.error_repair_env_failed.format(name=name, error=str(data.get("error") or ""))
    normalized = {"path": path, "action": action, "ok": ok, "message": message}
    if data.get("backup"):
        normalized["backup"] = str(data["backup"])
    return normalized


@router.get("")
def read_status(
    request: Request,
    folder: str = Query(default=""),
) -> dict:
    """按翻译目录定位最近任务；始终带回 owner_project_key 快照。"""
    with CacheManager.LOCK:
        config = request.app.state.config
        bound = current_paths(config)
        owner_key = bound.project_key if bound is not None else ""
        raw = str(folder or "").strip()
        if raw:
            try:
                resolved = lexical_abs(ErrorRepairer.resolve_translation_folder(raw))
            except Exception:
                resolved = None
            if resolved is not None and resolved.is_dir():
                payload = _describe(resolved, owner_key=owner_key)
                project_key = payload["project_key"]
            else:
                payload = {
                    "project_key": "",
                    "folder": raw,
                    "owner_project_key": owner_key,
                    "has_scan_report": False,
                }
                project_key = ""
        elif bound is not None and bound.tl_language_dir.is_dir():
            payload = _describe(lexical_abs(bound.tl_language_dir), owner_key=owner_key)
            project_key = payload["project_key"]
        else:
            payload = {
                "project_key": "",
                "folder": "",
                "owner_project_key": owner_key,
                "has_scan_report": False,
            }
            project_key = ""
        # 自动带出可执行 lint 的游戏主程序：省掉每次手填。
        payload["game_exe"] = _detect_game_exe(
            bound, Path(str(payload.get("folder") or "")) if payload.get("folder") else None,
        )
    job = _latest_job(request, project_key) if project_key else None
    payload["job"] = job.snapshot() if job else None
    return payload


@router.post("/scan")
async def start_scan(request: Request, body: ScanBody) -> dict:
    """扫描错误；引号两类始终开启。扫描可跳过联接子树，不强制拒绝。"""
    with CacheManager.LOCK:
        project_key, folder, owner_key, owner_identity = _resolve_folder_operation(
            request.app.state.config,
            folder=body.folder,
            body_project_key=body.project_key,
            body_owner_key=body.owner_project_key,
            require_lexical_clean=False,
        )
    folder_key = project_key
    check_indent = body.check_indent
    check_indent_level = body.check_indent_level
    snapshot = str(folder)

    def compute(check_cancel, progress, should_stop, touch_result, owner_still):
        del should_stop, touch_result
        check_cancel()
        if not owner_still():
            raise RuntimeError("项目已切换，未执行操作")
        progress("正在收集翻译文件", 0)
        repairer = ErrorRepairer()
        scan = repairer.scan_folder(
            snapshot,
            check_indent=check_indent,
            check_indent_level=check_indent_level,
            check_quotes=True,
            check_dialogue_quotes=True,
            encoding="utf-8",
            should_cancel=_cancelled(check_cancel),
            on_progress=_make_scan_progress(progress, check_cancel),
            detect_environment=True,
        )
        check_cancel()
        if scan.budget_exhausted:
            raise RuntimeError("扫描未完成，请缩小扫描目录后重试")
        if not owner_still():
            raise RuntimeError("项目已切换，未执行操作")
        report = scan.errors
        total = sum(len(v) for v in report.values())
        _LAST_SCAN.pop(folder_key, None)
        _LAST_SCAN[folder_key] = report
        # Keep recent reports for export without retaining every visited project.
        while len(_LAST_SCAN) > 4:
            _LAST_SCAN.pop(next(iter(_LAST_SCAN)))
        issues_by_type = _issues_by_type(report)
        environment_issues = _environment_issues(scan)
        fixable = sum(count for kind, count in issues_by_type.items() if _classify_issue(kind) == "auto")
        manual = max(0, total - fixable)
        progress("扫描完成", 100)
        loc = Localizer.get()
        return {
            "success": True,
            "action": "scan",
            "written": False,
            "has_scan_report": True,
            "affected_files": len(report),
            "scanned_files": scan.scanned_files,
            "total_files": scan.total_files,
            "total_issues": total,
            "issues_by_type": issues_by_type,
            "fixable_issues": fixable,
            "manual_issues": manual,
            "environment_issues": environment_issues,
            "manual_sample": _manual_sample(report, _sample_limit(total)),
            "folder": snapshot,
            "message": (
                loc.error_repair_scan_summary.format(
                    total=total,
                    fixable=fixable,
                    manual=manual,
                    env=len(environment_issues),
                )
                if total or environment_issues
                else loc.error_repair_no_issues
            ),
        }

    return await _start_job(
        request,
        kind=KIND_SCAN,
        project_key=project_key,
        owner_project_key=owner_key,
        message="准备扫描错误",
        owner_identity=owner_identity,
        seed={"action": "scan", "folder": snapshot, "written": False},
        compute=compute,
    )


@router.post("/fix")
async def start_fix(request: Request, body: FixBody) -> dict:
    """自动修复；写前拒绝联接逃逸；逐文件重验 owner；取消后如实汇报已写增量。"""
    if not body.confirm:
        raise HTTPException(status_code=400, detail="自动修复会直接改写文件，需要 confirm=true")
    selected_environment = str(body.environment_path or "").strip()
    if selected_environment and not body.fix_environment:
        raise HTTPException(status_code=400, detail="指定残留目录时需要 fix_environment=true")
    with CacheManager.LOCK:
        project_key, folder, owner_key, owner_identity = _resolve_folder_operation(
            request.app.state.config,
            folder=body.folder,
            body_project_key=body.project_key,
            body_owner_key=body.owner_project_key,
            require_lexical_clean=True,
        )
        # Lint 复检要游戏主程序：这里顺手记下来，compute 里直接用。
        bound = current_paths(request.app.state.config)
    snapshot = str(folder)
    folder_key = project_key

    def compute(check_cancel, progress, should_stop, touch_result, owner_still):
        del should_stop
        loc = Localizer.get()
        cancelled = _cancelled(check_cancel)

        def guard() -> None:
            check_cancel()
            if not owner_still():
                raise RuntimeError("项目已切换，未执行操作")

        guard()
        repairer = ErrorRepairer()
        progress("正在扫描错误", 3)
        scan = repairer.scan_folder(
            snapshot,
            check_indent=True,
            check_indent_level=body.fix_indent_level,
            check_quotes=True,
            check_dialogue_quotes=True,
            encoding="utf-8",
            should_cancel=cancelled,
            on_progress=_make_scan_progress(progress, check_cancel, base=0, span=20),
            detect_environment=True,
        )
        if scan.budget_exhausted:
            raise RuntimeError("扫描未完成，请缩小扫描目录后重试")
        guard()
        before_by_type = _issues_by_type(scan.errors)
        before_total = sum(before_by_type.values())
        environment_issues = _environment_issues(scan)

        if selected_environment:
            wanted = _norm(selected_environment)
            environment_issues = [
                issue for issue in environment_issues
                if _norm(str(issue.get("path") or "")) == wanted
            ]
            if not environment_issues:
                raise RuntimeError("所选残留目录不在当前翻译目录的扫描结果中，请重新扫描后再试")

        written_files: set[str] = set()
        direct_items = 0
        failed_files = 0
        environment_fixes: list[dict] = []

        def any_written() -> bool:
            # 合并/移出残留目录与合并前备份同样是磁盘副作用，不能只看 .rpy 改写。
            return bool(written_files) or any(
                item.get("ok") or item.get("backup")
                for item in environment_fixes
            )

        def publish(message_text: str) -> None:
            # 任一副作用后立即固化，取消时 worker 能看到 written/partial
            touch_result({
                "written": any_written(),
                "partial": True,
                "fixed_files": len(written_files),
                "fixed_items": direct_items,
                "failed_files": failed_files,
                "environment_fixes": list(environment_fixes),
                "rescan_skipped": True,
                "action": "fix",
                "folder": snapshot,
                "message": message_text,
            })

        # 1) 环境残留优先处理：合并/移出后主目录才是干净的可修复对象
        if body.fix_environment and environment_issues:
            total_env = len(environment_issues)
            for index, issue in enumerate(environment_issues):
                guard()
                name = Path(str(issue.get("path") or "")).name
                progress(f"处理残留目录 {name}", 22 + int(10 * index / max(total_env, 1)))
                outcome = repairer.fix_environment_issue(issue, body.environment_action)
                environment_fixes.append(
                    _normalize_environment_fix(outcome, issue, body.environment_action)
                )
                publish(loc.error_repair_fix_summary.format(files=len(written_files), items=direct_items))
                guard()

        # 2) 逐文件修复
        files = repairer.get_rpy_files(snapshot)
        guard()
        for index, rpy in enumerate(files):
            guard()
            progress(f"修复 {rpy.name}", 35 + int(45 * index / max(len(files), 1)))
            ok, count = repairer.auto_fix_file(
                str(rpy),
                fix_indent=body.fix_indent,
                fix_indent_level=body.fix_indent_level,
                fix_quotes=body.fix_quotes,
                fix_dialogue_quotes=body.fix_dialogue_quotes,
                fix_empty_blocks=body.fix_empty_blocks,
                fix_trailing_spaces=body.fix_trailing_spaces,
                checkpoint=check_cancel,
                encoding="utf-8",
            )
            if not ok:
                failed_files += 1
            elif count > 0:
                written_files.add(str(rpy))
                direct_items += count
            if written_files or failed_files:
                publish(loc.error_repair_fix_summary.format(files=len(written_files), items=direct_items))
            guard()

        # 3) 跨文件重复 old/new 去重（保留原文注释掉后出现的条目）
        if body.fix_duplicates:
            progress("正在合并重复译文", 82)
            guard()

            def on_dedupe_file(path: str, count: int) -> None:
                # 每写完一个文件就固化计数，之后取消/切项目也不会丢已写增量。
                nonlocal direct_items
                direct_items += int(count)
                written_files.add(str(path))
                publish(loc.error_repair_fix_summary.format(files=len(written_files), items=direct_items))

            repairer.fix_duplicate_strings(
                snapshot,
                checkpoint=check_cancel,
                before_write=guard,
                on_file=on_dedupe_file,
            )
            guard()

        # 4) 复扫：给出剩余分类与需人工样本
        progress("正在复扫确认", 86)
        scan_after = repairer.scan_folder(
            snapshot,
            check_indent=True,
            check_indent_level=body.fix_indent_level,
            check_quotes=True,
            check_dialogue_quotes=True,
            encoding="utf-8",
            should_cancel=cancelled,
            on_progress=_make_scan_progress(progress, check_cancel, base=86, span=13),
            detect_environment=False,
        )
        rescan_complete = not scan_after.budget_exhausted
        if rescan_complete:
            after_by_type = _issues_by_type(scan_after.errors)
            after_total: int | None = sum(after_by_type.values())
            fixed_by_type = {
                kind: before_by_type[kind] - after_by_type.get(kind, 0)
                for kind in before_by_type
                if before_by_type[kind] - after_by_type.get(kind, 0) > 0
            }
            # 直接写盘计数与前后差值取大，空块等「修完仍被计问题」的类型也不漏报
            fixed_items = max(direct_items, max(0, before_total - after_total))
            manual_sample = _manual_sample(scan_after.errors, _sample_limit(after_total))
            _LAST_SCAN.pop(folder_key, None)
            _LAST_SCAN[folder_key] = scan_after.errors
            while len(_LAST_SCAN) > 4:
                _LAST_SCAN.pop(next(iter(_LAST_SCAN)))
        else:
            # 复扫被取消或超预算：未扫到的文件不代表已修好，只报告直接写盘计数。
            after_by_type = {}
            after_total = None
            fixed_by_type = {}
            fixed_items = direct_items
            manual_sample = []
        # 5) 可选 Lint 复检：并入同一次任务，省得再单独检查一遍；失败不影响修复结果。
        lint_info: dict[str, Any] | None = None
        if body.lint_after:
            progress("正在运行 Ren'Py Lint 复检", 92)
            guard()
            exe = _detect_game_exe(bound, Path(snapshot))
            if not exe:
                lint_info = {"skipped": "未识别到游戏主程序，跳过 Lint 复检"}
            else:
                limit = float(ErrorRepairer.LINT_TIMEOUT)

                def lint_tick(elapsed: float) -> None:
                    progress(f"Ren'Py Lint 复检运行中，已用 {int(elapsed)} 秒",
                             92 + min(7, int(7 * elapsed / limit)))

                lint_repairer = ErrorRepairer()
                lint_output = lint_repairer.exec_renpy_lint(
                    exe, checkpoint=check_cancel, timeout=limit, on_tick=lint_tick,
                )
                if lint_output is None:
                    lint_info = {
                        "skipped": f"Lint 未完成：{lint_repairer.last_lint_error or '请查看运行日志'}",
                    }
                else:
                    tl_hits, real_source, hint_count = _split_lint_hits(lint_repairer, lint_output, snapshot)
                    lint_info = {
                        "issues": _lint_sample(tl_hits),
                        "issue_count": len(tl_hits),
                        "source_count": len(real_source),
                        "ignored_hints": hint_count,
                        "exit_code": int(getattr(lint_repairer, "last_lint_exit_code", 0) or 0),
                    }

        partial = failed_files > 0 or any(not item["ok"] for item in environment_fixes)
        written = any_written()
        progress("修复完成", 100)
        message = loc.error_repair_fix_summary.format(files=len(written_files), items=fixed_items)
        if failed_files:
            message += f"；{failed_files} 个文件失败"
        if not rescan_complete:
            message += loc.error_repair_fix_rescan_incomplete
        elif after_total:
            message += loc.error_repair_fix_remaining.format(count=after_total)
        if lint_info is not None:
            if lint_info.get("skipped"):
                message += f"；{lint_info['skipped']}"
            else:
                message += (
                    f"；Lint 复检：译文 {lint_info['issue_count']} 条待处理、"
                    f"源码 {lint_info['source_count']} 条，已忽略 {lint_info['ignored_hints']} 条常见写法提示"
                )
        return {
            "success": not partial or written,
            "partial": partial,
            "action": "fix",
            "written": written,
            "fixed_files": len(written_files),
            "fixed_items": fixed_items,
            "failed_files": failed_files,
            "fixed_by_type": fixed_by_type,
            "environment_fixes": environment_fixes,
            "remaining_issues": after_total,
            "remaining_by_type": after_by_type,
            "manual_sample": manual_sample,
            "rescan_skipped": not rescan_complete,
            "lint": lint_info,
            "folder": snapshot,
            "message": message,
        }

    return await _start_job(
        request,
        kind=KIND_FIX,
        project_key=project_key,
        owner_project_key=owner_key,
        message="准备自动修复",
        owner_identity=owner_identity,
        seed={"action": "fix", "folder": snapshot, "written": False},
        compute=compute,
    )


@router.post("/lint")
async def start_lint(request: Request, body: LintBody) -> dict:
    """深度 lint：None 失败、空串成功；仅过滤选定 TL。"""
    with CacheManager.LOCK:
        project_key, folder, owner_key, owner_identity = _resolve_folder_operation(
            request.app.state.config,
            folder=body.folder,
            body_project_key=body.project_key,
            body_owner_key=body.owner_project_key,
            require_lexical_clean=False,
        )
    exe = Path(body.game_exe).expanduser()
    if not exe.is_file():
        raise HTTPException(status_code=400, detail=f"游戏主程序不存在: {exe}")
    snapshot_folder = str(folder)
    snapshot_exe = str(exe.resolve(strict=False))

    def compute(check_cancel, progress, should_stop, touch_result, owner_still):
        del should_stop, touch_result
        check_cancel()
        if not owner_still():
            raise RuntimeError("项目已切换，未执行操作")
        progress("正在执行 Ren'Py lint", 30)
        repairer = ErrorRepairer()
        timeout = float(body.timeout_seconds)

        def tick(elapsed: float) -> None:
            # 心跳：进度条往前走 + 文案累计秒数，避免长时间无输出像卡死。
            percent = 30 + min(65, int(65 * elapsed / timeout))
            progress(f"Ren'Py lint 运行中，已用 {int(elapsed)} 秒（上限 {int(timeout)} 秒，可取消）", percent)

        lint_output = repairer.exec_renpy_lint(
            snapshot_exe,
            checkpoint=check_cancel,
            timeout=timeout,
            on_tick=tick,
        )
        if lint_output is None:
            reason = str(getattr(repairer, "last_lint_error", "") or "").strip()
            raise RuntimeError(f"Lint 未完成：{reason}" if reason else "Lint 执行失败，请查看运行日志")
        check_cancel()
        if not owner_still():
            raise RuntimeError("项目已切换，未执行操作")
        parsed = repairer.parse_lint_errors(lint_output)
        # 译文问题 = 当前翻译目录里的；其余算源码问题。译者只需要看前者，
        # 后者用来解释「游戏本体为什么起不来」，界面上分两组显示。
        tl_errors, source_errors = repairer.split_lint_errors(parsed, snapshot_folder)
        exit_code = int(getattr(repairer, "last_lint_exit_code", 0) or 0)
        lint_file = str(Path(snapshot_exe).parent / "lint_errors.txt") if lint_output else ""

        hints = frozenset(str(item) for item in error_repairer_module.IGNORED_LINT_HINT_TYPES)
        hint_count = sum(
            1 for item in source_errors if str(item.get("type") or "") in hints
        )
        real_source = [
            item for item in source_errors if str(item.get("type") or "") not in hints
        ]
        note = (
            f"；已忽略 {hint_count} 条常见写法提示（运行时变量当角色名，Ren'Py 支持，与译文无关）"
            if hint_count
            else ""
        )
        scope = str(body.scope or "all")
        # 分组检查：只把本次范围那一组的明细带回去，另一组只留计数提示。
        tl_sample = _lint_sample(tl_errors) if scope in ("tl", "all") else []
        source_sample = _lint_sample(real_source) if scope in ("source", "all") else []
        if scope == "tl":
            message = (
                f"译文检查：发现 {len(tl_errors)} 条问题"
                if tl_errors
                else "译文检查：当前译文目录没有需要处理的问题"
            )
            if real_source:
                message += f"（另有源码问题 {len(real_source)} 条，可单独检查）"
            message += note
        elif scope == "source":
            message = (
                f"源码检查：发现 {len(real_source)} 条问题"
                if real_source
                else "源码检查：游戏本体没有需要处理的问题"
            )
            if tl_errors:
                message += f"（另有译文问题 {len(tl_errors)} 条，可单独检查）"
            message += note
        elif tl_errors:
            message = f"Lint 发现 {len(tl_errors)} 条译文问题"
            if real_source:
                message += f"，另有 {len(real_source)} 条源码问题（与翻译无关）"
            message += note
        elif real_source:
            message = f"译文目录没有 Lint 问题；游戏源码有 {len(real_source)} 条（与翻译无关）"
            message += note
        elif exit_code:
            message = f"Lint 未完成：Ren'Py 以退出码 {exit_code} 结束，且没有可解析的条目"
        else:
            message = "Lint 未发现翻译目录相关问题"
        progress("Lint 完成", 100)
        return {
            "success": True,
            "action": "lint",
            "scope": scope,
            "written": bool(lint_output and Path(lint_file).is_file()),
            # error_count 保持旧含义（译文条目），另给源码条数与合计。
            "error_count": len(tl_errors),
            "source_error_count": len(real_source),
            "ignored_hint_count": hint_count,
            "total_error_count": len(tl_errors) + len(real_source),
            "lint_exit_code": exit_code,
            "tl_errors": tl_sample,
            "source_errors": source_sample,
            "lint_errors_path": lint_file if lint_output else "",
            "folder": snapshot_folder,
            "game_exe": snapshot_exe,
            "message": message,
        }

    return await _start_job(
        request,
        kind=KIND_LINT,
        project_key=project_key,
        owner_project_key=owner_key,
        message="准备执行 Lint",
        owner_identity=owner_identity,
        seed={"action": "lint", "folder": snapshot_folder, "written": False},
        compute=compute,
    )


@router.post("/export")
def export_report(request: Request, body: ExportBody) -> dict:
    """同步导出 XLSX；引擎忙时 409 且无副作用。"""
    engine = _acquire_engine()
    try:
        with CacheManager.LOCK:
            project_key, folder, owner_key, _identity = _resolve_folder_operation(
                request.app.state.config,
                folder=body.folder,
                body_project_key=body.project_key,
                body_owner_key=body.owner_project_key,
                require_lexical_clean=False,
            )
        report = body.report
        if report is None:
            report = _LAST_SCAN.get(project_key)
        if report is None:
            job = _latest_job(request, project_key)
            if job and isinstance(job.result, dict) and job.result.get("action") == "scan":
                candidate = job.result.get("report")
                if isinstance(candidate, dict):
                    report = candidate
        if report is None:
            raise HTTPException(status_code=400, detail="请先扫描错误后再导出")

        output = Path(body.output_path).expanduser()
        output_text = str(output)
        if not output_text.lower().endswith(".xlsx"):
            output_text += ".xlsx"
        ok = ErrorRepairer().export_error_report(report, output_text)
        if not ok:
            raise HTTPException(status_code=500, detail="导出错误报告失败")
        final = Path(output_text)
        if not final.is_file():
            raise HTTPException(status_code=500, detail="导出失败：目标文件未生成")
        return {
            "success": True,
            "output_path": str(final.resolve(strict=False)),
            "folder": str(folder),
            "project_key": project_key,
            "owner_project_key": owner_key,
            "message": f"报告已保存到 {final}",
        }
    finally:
        engine.release_status(Engine.Status.TESTING)


async def _start_job(
    request: Request,
    *,
    kind: str,
    project_key: str,
    owner_project_key: str,
    message: str,
    seed: dict[str, Any],
    compute: Callable[..., dict],
    owner_identity: tuple[str, ...] | None = None,
) -> dict:
    engine = _acquire_engine()
    manager = request.app.state.jobs
    try:
        job = manager.create(kind, total=100, cooperative_cancel=True)
    except Exception:
        engine.release_status(Engine.Status.TESTING)
        raise
    job.result = {
        "project_key": project_key,
        "owner_project_key": owner_project_key,
        "message": message,
        "written": False,
        "worker_active": True,
        **seed,
    }
    loop = asyncio.get_running_loop()
    identity = owner_identity
    folder_snapshot = str(seed.get("folder") or "")
    frozen_owner_key = owner_project_key
    frozen_target_key = project_key

    def owner_still() -> bool:
        with CacheManager.LOCK:
            live = request.app.state.config
            bound = current_paths(live)
            live_owner = bound.project_key if bound is not None else ""
        if frozen_owner_key:
            if live_owner != frozen_owner_key:
                return False
            if identity is not None and _project_identity(live) != identity:
                return False
        elif live_owner:
            # 冻结时未绑定，运行中又绑上了别的项目 → 拒绝
            return False
        if folder_snapshot and _folder_key(Path(folder_snapshot)) != frozen_target_key:
            return False
        return True

    def check_cancel() -> None:
        if job.cancel_event.is_set():
            raise asyncio.CancelledError()

    def should_stop() -> bool:
        return job.cancel_event.is_set()

    def publish(message_text: str, percent: int) -> None:
        if isinstance(job.result, dict):
            job.result["message"] = message_text
        manager.progress(job.id, done=max(0, min(100, int(percent))), total=100)

    def progress(message_text: str, percent: int = 0) -> None:
        loop.call_soon_threadsafe(lambda: publish(message_text, percent))

    def touch_result(patch: dict[str, Any]) -> None:
        # 同步写入 result，避免取消竞态读到旧的 written=false
        if isinstance(job.result, dict) and job.result.get("worker_active"):
            job.result.update(patch)
        loop.call_soon_threadsafe(lambda: manager.progress(job.id))

    def run_compute() -> dict:
        check_cancel()
        if not owner_still():
            raise RuntimeError("项目已切换，未执行操作")
        result = compute(check_cancel, progress, should_stop, touch_result, owner_still)
        if not owner_still() and not (isinstance(result, dict) and result.get("written")):
            raise RuntimeError("项目已切换，未执行操作")
        if isinstance(job.result, dict) and job.result.get("worker_active"):
            job.result.update(result)
        return result

    async def worker(_: Job) -> dict:
        try:
            check_cancel()
            future = loop.run_in_executor(None, run_compute)
            try:
                result = await asyncio.shield(future)
            except asyncio.CancelledError:
                job.cancel_event.set()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await asyncio.shield(future)
                if isinstance(job.result, dict) and job.result.get("written"):
                    job.result.setdefault("partial", True)
                    job.result.setdefault("success", False)
                    job.result.setdefault("message", "任务已取消（已保留写入结果）")
                    manager.progress(job.id, done=100, total=100)
                    return job.result
                raise
            if isinstance(job.result, dict):
                job.result.update(result)
                if job.cancel_event.is_set() and job.result.get("written"):
                    job.result.setdefault("partial", True)
                    job.result["success"] = False
                    job.result.setdefault("message", "任务已取消（已保留写入结果）")
                    manager.progress(job.id, done=100, total=100)
                    return job.result
                if job.cancel_event.is_set():
                    job.result["message"] = "任务已取消"
                    raise asyncio.CancelledError()
                if job.result.get("success") is False and job.result.get("written"):
                    raise RuntimeError(job.result.get("message") or "任务失败")
            if isinstance(job.result, dict) and job.result.get("partial") and job.result.get("written"):
                # 正常结束的部分失败：清 cancel，标 done
                if not job.cancel_event.is_set():
                    job.result["partial"] = bool(job.result.get("failed_files")) or any(
                        isinstance(item, dict) and not item.get("ok")
                        for item in job.result.get("environment_fixes") or []
                    )
                job.cancel_event.clear()
                manager.progress(job.id, done=100, total=100)
                return job.result
            job.cancel_event.clear()
            manager.progress(job.id, done=100, total=100)
            return job.result
        except asyncio.CancelledError:
            if isinstance(job.result, dict) and job.result.get("written"):
                job.result.setdefault("partial", True)
                job.result["success"] = False
                job.result.setdefault("message", "任务已取消（已保留写入结果）")
                manager.progress(job.id, done=100, total=100)
                return job.result
            if isinstance(job.result, dict):
                job.result["message"] = "任务已取消"
            raise
        except Exception as exc:
            if isinstance(job.result, dict) and job.result.get("written"):
                job.result.setdefault("partial", True)
                job.result["success"] = False
                job.result["message"] = str(exc)
            elif isinstance(job.result, dict):
                job.result["message"] = str(exc)
            raise
        finally:
            if isinstance(job.result, dict):
                job.result["worker_active"] = False
            engine.release_status(Engine.Status.TESTING)

    try:
        await manager.run(job.id, worker)
    except BaseException:
        if isinstance(job.result, dict):
            job.result["worker_active"] = False
        engine.release_status(Engine.Status.TESTING)
        raise
    return {"job": job.snapshot()}
