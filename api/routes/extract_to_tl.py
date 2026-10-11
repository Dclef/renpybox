"""抽取到 TL：复用 UnifiedExtractor，对齐 Qt RenpyTranslationPage（非 onekey.prepare）。"""

from __future__ import annotations

import asyncio
import contextlib
import copy
import os
from pathlib import Path
from typing import Any, Callable

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from api.jobs import Job
from module.Cache.CacheManager import CacheManager
from module.Engine.Engine import Engine
from module.Extract.RpyExtractionSettings import selection_for_path
from module.Extract.UnifiedExtractor import UnifiedExtractor
from module.Project.ProjectStore import ProjectStore
from module.Renpy.ProjectPaths import RenpyProjectPaths

router = APIRouter(prefix="/api/extract-to-tl", tags=["extract-to-tl"])

KIND_EXTRACT = "extract_to_tl"
KIND_MERGE = "extract_to_tl_merge"
KIND_RESTORE = "extract_to_tl_restore"
KINDS = (KIND_EXTRACT, KIND_MERGE, KIND_RESTORE)
_BUSY = "已有任务正在运行或收尾，请稍后再试"

# 与 Qt RenpyTranslationPage._is_effective_tl_rpy 一致
_HOOK_START = "hook_"
_MISS_READY = "miss_ready_replace"
_IGNORED_NAMES = frozenset({"replace_text_auto.rpy", "set_default_language_at_startup.rpy"})


class ExtractBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    project_key: str = ""
    game_dir: str = ""
    exe_path: str = ""
    language: str = "chinese"
    use_official: bool = True
    use_custom: bool = True
    supplement_mode: str = "precise"
    skip_hook_files: bool = True
    filter_suspicious_bool_expr: bool = True
    auto_merge_cleanup: bool = True


class LanguageBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    project_key: str = ""
    game_dir: str = ""
    language: str = "chinese"
    incremental_dir: str = ""


class RestoreBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    project_key: str = ""
    game_dir: str = ""
    language: str = "chinese"
    manifest_path: str = ""


class OpenPathBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    project_key: str = ""
    game_dir: str = ""
    path: str = Field(min_length=1)


def current_paths(config: Any) -> RenpyProjectPaths | None:
    return RenpyProjectPaths.from_config(config)


def _norm(value: str) -> str:
    return os.path.normcase(os.path.abspath(value)) if value else ""


def _project_identity(config: Any) -> tuple[str, ...]:
    return tuple(_norm(str(getattr(config, field, "") or "")) for field in (
        "renpy_project_path", "renpy_game_folder", "renpy_tl_folder", "input_folder", "output_folder",
    ))


def _bound_paths(config: Any) -> RenpyProjectPaths:
    paths = current_paths(config)
    if paths is None or not paths.game_dir.is_dir():
        raise HTTPException(status_code=400, detail="未绑定游戏项目")
    return paths


def _ensure_project_key(body_key: str, paths: RenpyProjectPaths) -> str:
    current = paths.project_key
    if body_key and body_key != current:
        raise HTTPException(status_code=409, detail="项目已切换，请重新加载后再操作")
    return current


def _resolve_extract_paths(
    config: Any,
    *,
    game_dir: str,
    language: str,
    body_project_key: str,
) -> RenpyProjectPaths:
    """从 game_dir（或绑定项目）解析抽取目标；不要求目标与当前绑定项目一致。

    body_project_key 可匹配目标键，或（已绑定时）匹配 owner 键；
    不把合法目标 B 强卡成绑定 A。owner 切换由 worker 身份校验负责。
    """
    bound = current_paths(config)
    raw = str(game_dir or "").strip()
    if not raw:
        if bound is None or not bound.game_dir.is_dir():
            raise HTTPException(status_code=400, detail="请提供 game_dir 或先绑定游戏项目")
        raw = str(bound.project_root)
    paths = RenpyProjectPaths.from_path(raw, language)
    if paths is None or not paths.game_dir.is_dir():
        raise HTTPException(status_code=400, detail="路径不是有效的 Ren'Py 项目")
    if paths.language != language:
        raise HTTPException(status_code=400, detail="语言名不能是保留目录或增量目录名")
    body_key = str(body_project_key or "").strip()
    if body_key:
        allowed = {paths.project_key}
        if bound is not None:
            allowed.add(bound.project_key)
        if body_key not in allowed:
            raise HTTPException(status_code=409, detail="项目已切换，请重新加载后再操作")
    return paths


def _resolve_chain_target(
    config: Any,
    *,
    game_dir: str,
    language: str,
    body_project_key: str,
) -> tuple[RenpyProjectPaths, tuple[str, ...] | None]:
    """合并/恢复/打开路径：支持手动目标，不强制已绑定项目。"""
    paths = _resolve_extract_paths(
        config,
        game_dir=game_dir,
        language=language,
        body_project_key=body_project_key,
    )
    bound = current_paths(config)
    owner_identity = _project_identity(config) if bound is not None else None
    return paths, owner_identity


def _path_within_root(root: Path, target: Path) -> bool:
    try:
        root_key = os.path.normcase(str(root.resolve(strict=False)))
        target_key = os.path.normcase(str(target.resolve(strict=False)))
    except OSError:
        return False
    return target_key == root_key or target_key.startswith(root_key + os.sep)


def _assert_under_project(root: Path, target: Path, *, label: str = "路径") -> Path:
    resolved = target.expanduser().resolve(strict=False)
    if not _path_within_root(root, resolved):
        raise HTTPException(status_code=400, detail=f"{label}不在目标项目内")
    return resolved


def _unbound_status(config: Any) -> dict[str, Any]:
    return {
        "project_key": "",
        "project_root": "",
        "game_dir": "",
        "language": "chinese",
        "tl_dir": "",
        "incremental_dir": "",
        "has_existing_tl": False,
        "incremental_dir_exists": False,
        "suspicious_backup_available": False,
        "suspicious_manifests": [],
        "options": _options_from_config(config),
        "rule_mode": "builtin",
    }


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


def _safe_language(language: str) -> str:
    name = str(language or "").strip() or "chinese"
    if name in {".", ".."} or any(ch in name for ch in '/\\<>:"|?*'):
        raise HTTPException(status_code=400, detail="语言名无效")
    return name


def is_effective_tl_rpy(path: Path) -> bool:
    """有效译文脚本：排除 hook / 自动替换 / 默认语言等非翻译产物。"""
    name = path.name.lower()
    if name.startswith(_MISS_READY):
        return False
    if name.startswith(_HOOK_START):
        return False
    if name in _IGNORED_NAMES:
        return False
    return True


def has_existing_translations(tl_dir: Path) -> bool:
    if not tl_dir.is_dir():
        return False
    return any(is_effective_tl_rpy(p) for p in tl_dir.rglob("*.rpy"))


def _rule_mode(project_root: Path) -> str:
    try:
        _, mode, _ = selection_for_path(project_root, "source")
        return str(mode or "builtin")
    except Exception:
        return "builtin"


def resolve_project_root(raw: str | Path) -> Path:
    """游戏目录 / EXE / 项目根 → 项目根（含 game/）。"""
    path = Path(str(raw)).expanduser().resolve(strict=False)
    if path.is_file():
        path = path.parent
    if path.name.lower() == "game":
        path = path.parent
    game = path / "game"
    if not game.is_dir():
        raise HTTPException(status_code=400, detail="未找到 game 目录")
    return path


def auto_find_exe(root_dir: Path) -> Path | None:
    for pattern in ("*.exe", "*.py"):
        for candidate in root_dir.glob(pattern):
            if candidate.is_file() and candidate.stat().st_size > 1024:
                return candidate
    return None


def list_suspicious_manifests(tl_dir: Path) -> list[dict]:
    """列出 _filtered_suspicious 下的 restore_manifest.csv。"""
    root = tl_dir / "_filtered_suspicious"
    if not root.is_dir():
        return []
    items: list[dict] = []
    for manifest in sorted(
        root.glob("*/restore_manifest.csv"),
        key=lambda p: p.stat().st_mtime if p.exists() else 0.0,
        reverse=True,
    ):
        items.append({
            "path": str(manifest),
            "mtime": manifest.stat().st_mtime if manifest.exists() else 0.0,
        })
    fallback = root / "restore_manifest.csv"
    if fallback.is_file() and not any(i["path"] == str(fallback) for i in items):
        items.append({"path": str(fallback), "mtime": fallback.stat().st_mtime})
    return items


def _persist_extract_fields(live: Any, values: dict[str, Any]) -> None:
    """只持久化抽取相关字段，避免整份设置被覆盖。"""
    if not values:
        return
    candidate = copy.deepcopy(live)
    for field, value in values.items():
        setattr(candidate, field, value)
    candidate.save(strict=True)
    for field, value in values.items():
        setattr(live, field, value)


def _result_payload(result: Any) -> dict[str, Any]:
    written_files = list(getattr(result, "written_files", None) or [])
    return {
        "success": bool(getattr(result, "success", False)),
        "message": str(getattr(result, "message", "") or ""),
        "tl_dir": str(getattr(result, "tl_dir", "") or ""),
        "incremental_dir": str(getattr(result, "incremental_dir", "") or ""),
        "preserved_count": int(getattr(result, "preserved_count", 0) or 0),
        "new_strings": int(getattr(result, "new_strings", 0) or 0),
        "total_files": int(getattr(result, "total_files", 0) or 0),
        "official_status": str(getattr(result, "official_status", "") or ""),
        "cancelled": bool(getattr(result, "cancelled", False)),
        "written_files": written_files,
    }


def _extract_config_snapshot(live: Any, values: dict[str, Any]) -> Any:
    """任务内抽取选项快照，避免 worker 再读磁盘配置。"""
    snapshot = copy.deepcopy(live)
    for field, value in values.items():
        setattr(snapshot, field, value)
    return snapshot


def _options_from_config(config: Any) -> dict[str, Any]:
    mode = str(getattr(config, "extract_supplement_mode", "precise") or "precise").lower()
    if mode not in {"precise", "aggressive"}:
        mode = "precise"
    return {
        "use_official": bool(getattr(config, "extract_use_official", True)),
        "use_custom": bool(getattr(config, "extract_use_custom", True)),
        "supplement_mode": mode,
        "skip_hook_files": bool(getattr(config, "extract_skip_hook_files", True)),
        "filter_suspicious_bool_expr": bool(
            getattr(config, "renpy_filter_suspicious_bool_expr", True)
        ),
        "auto_merge_cleanup": bool(
            getattr(config, "renpy_incremental_auto_merge_cleanup", True)
        ),
    }


def _describe(paths: RenpyProjectPaths, config: Any) -> dict[str, Any]:
    language = paths.language or "chinese"
    tl_dir = paths.project_root / "game" / "tl" / language
    incremental = paths.project_root / "game" / "tl" / f"{language}_new"
    manifests = list_suspicious_manifests(tl_dir)
    return {
        "project_key": paths.project_key,
        "project_root": str(paths.project_root),
        "game_dir": str(paths.game_dir),
        "language": language,
        "tl_dir": str(tl_dir),
        "incremental_dir": str(incremental),
        "has_existing_tl": has_existing_translations(tl_dir),
        "incremental_dir_exists": incremental.is_dir(),
        "suspicious_backup_available": bool(manifests),
        "suspicious_manifests": manifests,
        "options": _options_from_config(config),
        "rule_mode": _rule_mode(paths.project_root),
    }


@router.get("")
def read_status(
    request: Request,
    game_dir: str = Query(default=""),
    language: str = Query(default="chinese"),
) -> dict:
    """项目/手动目标状态、抽取选项、最近任务与可疑备份/增量目录信息。"""
    lang = _safe_language(language)
    with CacheManager.LOCK:
        config = request.app.state.config
        raw = str(game_dir or "").strip()
        if raw:
            try:
                paths = _resolve_extract_paths(
                    config,
                    game_dir=raw,
                    language=lang,
                    body_project_key="",
                )
            except HTTPException:
                payload = _unbound_status(config)
                project_key = ""
            else:
                payload = _describe(paths, config)
                # 描述目标自身 key；owner 另由绑定配置表示
                bound = current_paths(config)
                payload["owner_project_key"] = bound.project_key if bound is not None else ""
                project_key = paths.project_key
        else:
            paths = current_paths(config)
            if paths is None or not paths.game_dir.is_dir():
                payload = _unbound_status(config)
                project_key = ""
            else:
                payload = _describe(paths, config)
                project_key = paths.project_key
    job = _latest_job(request, project_key) if project_key else None
    payload["job"] = job.snapshot() if job else None
    return payload


@router.get("/suspicious-backups")
def list_backups(
    request: Request,
    language: str = Query(default="chinese"),
    game_dir: str = Query(default=""),
) -> dict:
    """列出目标项目下可疑过滤备份 CSV（可用 game_dir，不强制绑定）。"""
    lang = _safe_language(language)
    with CacheManager.LOCK:
        paths, _ = _resolve_chain_target(
            request.app.state.config,
            game_dir=game_dir,
            language=lang,
            body_project_key="",
        )
        tl_dir = paths.project_root / "game" / "tl" / lang
        project_key = paths.project_key
    manifests = list_suspicious_manifests(tl_dir)
    return {
        "project_key": project_key,
        "language": lang,
        "tl_dir": str(tl_dir),
        "manifests": manifests,
        "available": bool(manifests),
        "open_path": manifests[0]["path"] if manifests else str(tl_dir / "_filtered_suspicious"),
    }


@router.post("/open-path")
def open_path_helper(request: Request, body: OpenPathBody) -> dict:
    """校验路径属于目标项目后返回，供桌面端 openPath 打开。"""
    language = "chinese"
    with CacheManager.LOCK:
        paths, _ = _resolve_chain_target(
            request.app.state.config,
            game_dir=body.game_dir,
            language=language,
            body_project_key=body.project_key,
        )
        project_key = paths.project_key
        root = paths.project_root.resolve(strict=False)
    try:
        target = _assert_under_project(root, Path(body.path), label="路径")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"路径无效: {exc}") from exc
    if not target.exists():
        raise HTTPException(status_code=404, detail="路径不存在")
    return {"project_key": project_key, "path": str(target), "ok": True}


@router.post("/extract")
async def start_extract(request: Request, body: ExtractBody) -> dict:
    """启动抽取任务：有有效 tl 则增量，否则常规；支持协作取消。"""
    language = _safe_language(body.language)
    supplement = str(body.supplement_mode or "precise").lower()
    if supplement not in {"precise", "aggressive"}:
        raise HTTPException(status_code=400, detail="supplement_mode 仅支持 precise/aggressive")

    engine = _acquire_engine()
    try:
        with CacheManager.LOCK:
            live = request.app.state.config
            target_paths = _resolve_extract_paths(
                live,
                game_dir=body.game_dir,
                language=language,
                body_project_key=body.project_key,
            )
            project_root = target_paths.project_root
            target_key = target_paths.project_key
            exe_path: Path | None = None
            exe_text = (body.exe_path or "").strip()
            if exe_text:
                exe_candidate = Path(exe_text).expanduser().resolve(strict=False)
                if not exe_candidate.is_file():
                    raise HTTPException(status_code=400, detail="指定的可执行文件不存在")
                exe_path = exe_candidate
            raw_target = (body.game_dir or "").strip() or str(project_root)
            raw_as_path = Path(raw_target).expanduser().resolve(strict=False)
            if raw_as_path.is_file():
                exe_path = raw_as_path

            rule_mode = _rule_mode(project_root)
            use_official = bool(body.use_official)
            use_custom = bool(body.use_custom)
            if rule_mode == "custom":
                use_official = use_custom = False
            elif not use_official and not use_custom:
                use_custom = True

            if use_official and exe_path is None:
                exe_path = auto_find_exe(project_root)
            if use_official and exe_path is None:
                use_official = False
                if not use_custom:
                    use_custom = True

            # TL 根/语言已在 _resolve_extract_paths 校验；mkdir 仅在引擎预占后执行
            tl_dir = project_root / "game" / "tl" / language
            if language in {".", ".."} or any(ch in language for ch in '/\\<>:"|?*'):
                raise HTTPException(status_code=400, detail="语言名无效")
            incremental = has_existing_translations(tl_dir) if tl_dir.is_dir() else False
            auto_merge = bool(body.auto_merge_cleanup)

            persist_values: dict[str, Any] = {
                "extract_supplement_mode": supplement,
                "extract_skip_hook_files": bool(body.skip_hook_files),
                "renpy_filter_suspicious_bool_expr": bool(body.filter_suspicious_bool_expr),
                "renpy_incremental_auto_merge_cleanup": auto_merge,
            }
            if rule_mode != "custom":
                persist_values["extract_use_official"] = use_official
                persist_values["extract_use_custom"] = use_custom
            _persist_extract_fields(live, persist_values)
            ProjectStore.get().set_game_folder(live, str(project_root / "game"))
            ProjectStore.get().persist(live, emit=False)

            # 预占成功后再创建 TL，避免 409 污染磁盘
            tl_dir.mkdir(parents=True, exist_ok=True)

            config_snapshot = _extract_config_snapshot(live, persist_values)
            snapshot_root = str(project_root)
            snapshot_exe = str(exe_path) if exe_path else None
            owner_identity = _project_identity(live)

        return await _start_job(
            request,
            kind=KIND_EXTRACT,
            project_key=target_key,
            message="准备抽取到 TL",
            engine=engine,
            owner_identity=owner_identity,
            seed={
                "action": "extract",
                "language": language,
                "incremental": incremental,
                "use_official": use_official,
                "use_custom": use_custom,
                "supplement_mode": supplement,
                "auto_merge_cleanup": auto_merge,
                "rule_mode": rule_mode,
                "project_root": snapshot_root,
                "exe_path": snapshot_exe or "",
                "owner_identity": owner_identity,
                "written": False,
            },
            compute=lambda check_cancel, progress: _run_extract(
                snapshot_root,
                language,
                exe_path=snapshot_exe,
                use_official=use_official,
                use_custom=use_custom,
                incremental=incremental,
                auto_merge_cleanup=auto_merge,
                config_snapshot=config_snapshot,
                check_cancel=check_cancel,
                progress=progress,
                request=request,
                project_key=target_key,
                owner_identity=owner_identity,
            ),
        )
    except BaseException:
        engine.release_status(Engine.Status.TESTING)
        raise


@router.post("/merge-incremental")
async def merge_incremental(request: Request, body: LanguageBody) -> dict:
    """手动合并 game/tl/{lang}_new；支持无绑定项目的独立目标。"""
    language = _safe_language(body.language)
    engine = _acquire_engine()
    try:
        with CacheManager.LOCK:
            live = request.app.state.config
            paths, owner_identity = _resolve_chain_target(
                live,
                game_dir=body.game_dir,
                language=language,
                body_project_key=body.project_key,
            )
            project_key = paths.project_key
            project_root = str(paths.project_root)
            incremental = (body.incremental_dir or "").strip()
            if not incremental:
                incremental = str(paths.project_root / "game" / "tl" / f"{language}_new")
            else:
                incremental_path = _assert_under_project(
                    paths.project_root,
                    Path(incremental),
                    label="增量目录",
                )
                incremental = str(incremental_path)
            # merge 选项快照：与请求语言/路径一致，避免 worker 再读错配置
            config_snapshot = _extract_config_snapshot(live, {
                "renpy_incremental_auto_merge_cleanup": bool(
                    getattr(live, "renpy_incremental_auto_merge_cleanup", True)
                ),
            })
            snapshot_root = project_root
            snapshot_incremental = incremental
            snapshot_identity = owner_identity

        return await _start_job(
            request,
            kind=KIND_MERGE,
            project_key=project_key,
            message="准备合并增量目录",
            engine=engine,
            owner_identity=snapshot_identity,
            seed={
                "action": "merge",
                "language": language,
                "incremental_dir": snapshot_incremental,
                "project_root": snapshot_root,
                "owner_identity": snapshot_identity,
                "written": False,
            },
            compute=lambda check_cancel, progress: _run_merge(
                snapshot_root,
                language,
                incremental_dir=snapshot_incremental,
                config_snapshot=config_snapshot,
                check_cancel=check_cancel,
                progress=progress,
            ),
        )
    except BaseException:
        engine.release_status(Engine.Status.TESTING)
        raise


@router.post("/restore-suspicious")
async def restore_suspicious(request: Request, body: RestoreBody) -> dict:
    """按 restore_manifest.csv 勾选项恢复；支持无绑定项目的独立目标。"""
    language = _safe_language(body.language)
    engine = _acquire_engine()
    try:
        with CacheManager.LOCK:
            live = request.app.state.config
            paths, owner_identity = _resolve_chain_target(
                live,
                game_dir=body.game_dir,
                language=language,
                body_project_key=body.project_key,
            )
            project_key = paths.project_key
            project_root = str(paths.project_root)
            manifest = (body.manifest_path or "").strip() or None
            if manifest:
                manifest_path = _assert_under_project(
                    paths.project_root,
                    Path(manifest),
                    label="恢复清单",
                )
                # 清单必须位于 tl/<lang>/_filtered_suspicious 界限内
                tl_dir = paths.project_root / "game" / "tl" / language
                suspicious_root = tl_dir / "_filtered_suspicious"
                if not _path_within_root(suspicious_root, manifest_path) and not _path_within_root(tl_dir, manifest_path):
                    raise HTTPException(status_code=400, detail="恢复清单不在可疑备份目录内")
                manifest = str(manifest_path)
            snapshot_root = project_root
            snapshot_identity = owner_identity

        return await _start_job(
            request,
            kind=KIND_RESTORE,
            project_key=project_key,
            message="准备恢复可疑过滤条目",
            engine=engine,
            owner_identity=snapshot_identity,
            seed={
                "action": "restore",
                "language": language,
                "manifest_path": manifest or "",
                "project_root": snapshot_root,
                "owner_identity": snapshot_identity,
                "written": False,
            },
            compute=lambda check_cancel, progress: _run_restore(
                snapshot_root,
                language,
                manifest_path=manifest,
                check_cancel=check_cancel,
                progress=progress,
            ),
        )
    except BaseException:
        engine.release_status(Engine.Status.TESTING)
        raise


def _run_extract(
    project_root: str,
    language: str,
    *,
    exe_path: str | None,
    use_official: bool,
    use_custom: bool,
    incremental: bool,
    auto_merge_cleanup: bool,
    config_snapshot: Any,
    check_cancel: Callable[[], None],
    progress: Callable[[str, int], None],
    request: Request,
    project_key: str,
    owner_identity: tuple[str, ...],
) -> dict:
    check_cancel()
    extractor = UnifiedExtractor()
    extractor.set_progress_callback(lambda message, percent: progress(str(message), int(percent)))
    extractor.set_cancel_callback(lambda: _cancel_flag(check_cancel))

    try:
        if incremental:
            progress("增量抽取（保留已有译文）", 5)
            result = extractor.extract_incremental(
                project_root,
                language,
                exe_path=exe_path,
                use_official=use_official,
                output_to_separate_folder=True,
                config_snapshot=config_snapshot,
            )
        else:
            progress("常规抽取", 5)
            result = extractor.extract_regular(
                project_root,
                language,
                exe_path=exe_path,
                use_official=use_official,
                config_snapshot=config_snapshot,
            )
    finally:
        extractor.set_progress_callback(None)
        extractor.set_cancel_callback(None)

    extract_info = _result_payload(result)

    if getattr(result, "cancelled", False) or (
        _cancel_flag(check_cancel) and not getattr(result, "success", False)
    ):
        # 未成功的取消：仅在确有增量目录/已保留译文等副作用时保留 partial
        retain_partial = bool(extract_info.get("incremental_dir")) or (
            int(extract_info.get("preserved_count") or 0) > 0
        )
        if retain_partial:
            return {
                **extract_info,
                "written": True,
                "partial": True,
                "incremental": incremental,
                "language": language,
                "merge": None,
                "message": extract_info.get("message") or "抽取已取消（已保留已写文件）",
            }
        raise asyncio.CancelledError()
    if not getattr(result, "success", False):
        raise RuntimeError(getattr(result, "message", None) or "抽取失败")

    extract_message = getattr(result, "message", None) or "抽取完成"
    merge_payload = None
    if incremental and auto_merge_cleanup and getattr(result, "incremental_dir", None):
        if not _cancel_flag(check_cancel):
            progress("自动合并增量目录", 90)
            merge_result = extractor.merge_incremental_folder(
                project_root,
                language,
                result.incremental_dir,
                clean_duplicates=True,
                config_snapshot=config_snapshot,
            )
            merge_payload = _result_payload(merge_result)
            if not merge_payload.get("success"):
                # 合并失败保留抽取成功信息
                note = merge_payload.get("message") or "合并失败"
                extract_message = f"{extract_message}；{note}"
        else:
            extract_message = f"{extract_message}；合并已跳过（任务取消）"

    # 成功后刷新绑定目录（配置身份未切换时）
    with CacheManager.LOCK:
        live = request.app.state.config
        if _project_identity(live) == owner_identity:
            ProjectStore.get().set_game_folder(
                live,
                str(Path(project_root) / "game"),
            )
            ProjectStore.get().persist(live, emit=False)

    cancelled_after = _cancel_flag(check_cancel)
    payload = {
        **extract_info,
        "written": True,
        "partial": cancelled_after or (
            bool(merge_payload) and not merge_payload.get("success")
        ),
        "incremental": incremental,
        "language": language,
        "merge": merge_payload,
        "message": extract_message,
        "success": True,
    }
    return payload


def _run_merge(
    project_root: str,
    language: str,
    *,
    incremental_dir: str,
    config_snapshot: Any = None,
    check_cancel: Callable[[], None],
    progress: Callable[[str, int], None],
) -> dict:
    check_cancel()
    extractor = UnifiedExtractor()
    extractor.set_progress_callback(lambda message, percent: progress(str(message), int(percent)))
    extractor.set_cancel_callback(lambda: _cancel_flag(check_cancel))
    try:
        progress("合并增量目录", 10)
        result = extractor.merge_incremental_folder(
            project_root,
            language,
            incremental_dir,
            clean_duplicates=True,
            config_snapshot=config_snapshot,
        )
    finally:
        extractor.set_progress_callback(None)
        extractor.set_cancel_callback(None)
    payload = {**_result_payload(result), "language": language}
    if getattr(result, "cancelled", False) or _cancel_flag(check_cancel):
        if payload.get("tl_dir") or payload.get("success"):
            payload["written"] = bool(payload.get("success"))
            payload["partial"] = True
            payload["message"] = payload.get("message") or "合并已取消"
            return payload
        raise asyncio.CancelledError()
    if not getattr(result, "success", False):
        raise RuntimeError(getattr(result, "message", None) or "合并失败")
    return {**payload, "written": True}


def _run_restore(
    project_root: str,
    language: str,
    *,
    manifest_path: str | None,
    check_cancel: Callable[[], None],
    progress: Callable[[str, int], None],
) -> dict:
    check_cancel()
    extractor = UnifiedExtractor()
    extractor.set_progress_callback(lambda message, percent: progress(str(message), int(percent)))
    extractor.set_cancel_callback(lambda: _cancel_flag(check_cancel))
    try:
        progress("恢复可疑过滤条目", 20)
        result = extractor.restore_flagged_suspicious_entries(
            project_root,
            language,
            manifest_path=manifest_path,
        )
    finally:
        extractor.set_progress_callback(None)
        extractor.set_cancel_callback(None)
    payload = {**_result_payload(result), "language": language}
    written_files = list(payload.get("written_files") or [])
    written = bool(written_files) or bool(getattr(result, "success", False))
    cancelled = bool(getattr(result, "cancelled", False)) or _cancel_flag(check_cancel)
    if cancelled:
        if written:
            payload["written"] = True
            payload["partial"] = True
            payload["success"] = False
            payload["message"] = payload.get("message") or "恢复已取消（已保留写入结果）"
            return payload
        raise asyncio.CancelledError()
    # 读/写失败：有副作用则带回 partial 供 worker 记 failed；无写入也不得伪装 done
    if not getattr(result, "success", False):
        message = str(payload.get("message") or "")
        if written_files or message.startswith("恢复失败"):
            payload["written"] = bool(written_files)
            payload["partial"] = bool(written_files)
            payload["success"] = False
            payload["written_files"] = written_files
            if written_files:
                return payload
            raise RuntimeError(message or "恢复失败")
    # 无可恢复项不算硬失败，返回 success=false 供前端提示
    return {**payload, "written": written}


def _cancel_flag(check_cancel: Callable[[], None]) -> bool:
    try:
        check_cancel()
    except asyncio.CancelledError:
        return True
    return False


async def _start_job(
    request: Request,
    *,
    kind: str,
    project_key: str,
    message: str,
    seed: dict[str, Any],
    compute: Callable[[Callable[[], None], Callable[[str, int], None]], dict],
    engine: Engine | None = None,
    owner_identity: tuple[str, ...] | None = None,
) -> dict:
    acquired = engine is None
    if engine is None:
        engine = _acquire_engine()
    manager = request.app.state.jobs
    try:
        job = manager.create(kind, total=100, cooperative_cancel=True)
    except Exception:
        if acquired:
            engine.release_status(Engine.Status.TESTING)
        raise
    job.result = {
        "project_key": project_key,
        "message": message,
        "written": False,
        "worker_active": True,
        **seed,
    }
    loop = asyncio.get_running_loop()
    identity = owner_identity if owner_identity is not None else seed.get("owner_identity")

    def owner_still() -> bool:
        if identity is None:
            # 无绑定 owner：独立目标已冻结在 seed，允许继续
            with CacheManager.LOCK:
                current = current_paths(request.app.state.config)
            if current is None:
                return True
            return current.project_key == project_key
        with CacheManager.LOCK:
            live = request.app.state.config
        return _project_identity(live) == identity

    def check_cancel() -> None:
        if job.cancel_event.is_set():
            raise asyncio.CancelledError()

    def publish(message_text: str, percent: int) -> None:
        if isinstance(job.result, dict):
            job.result["message"] = message_text
        manager.progress(job.id, done=max(0, min(100, int(percent))), total=100)

    def progress(message_text: str, percent: int = 0) -> None:
        loop.call_soon_threadsafe(lambda: publish(message_text, percent))

    def run_compute() -> dict:
        check_cancel()
        if not owner_still():
            raise RuntimeError("项目已切换，未执行抽取")
        check_cancel()
        result = compute(check_cancel, progress)
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
                    # 保留副作用；不 clear cancel，终态保持 cancelled
                    job.result.setdefault("partial", True)
                    job.result.setdefault("success", False)
                    job.result.setdefault("message", "任务已取消（已保留抽取结果）")
                    manager.progress(job.id, done=100, total=100)
                    return job.result
                raise
            if isinstance(job.result, dict):
                job.result.update(result)
                if job.cancel_event.is_set() and job.result.get("written"):
                    # 已有副作用：保留 payload，取消标志不清 → cancelled
                    job.result.setdefault("partial", True)
                    job.result["success"] = False
                    job.result.setdefault("message", "任务已取消（已保留抽取结果）")
                    manager.progress(job.id, done=100, total=100)
                    return job.result
                if job.cancel_event.is_set():
                    job.result["message"] = "任务已取消"
                    raise asyncio.CancelledError()
                if job.result.get("written") and job.result.get("success") is False:
                    raise RuntimeError(
                        job.result.get("message") or "任务失败（已保留写入结果）"
                    )
            manager.progress(job.id, done=100, total=100)
            return job.result
        except asyncio.CancelledError:
            if isinstance(job.result, dict) and job.result.get("written"):
                job.result.setdefault("partial", True)
                job.result["success"] = False
                job.result.setdefault("message", "任务已取消（已保留抽取结果）")
                manager.progress(job.id, done=100, total=100)
                return job.result
            if isinstance(job.result, dict) and not job.result.get("written"):
                job.result["message"] = "任务已取消"
            raise
        except Exception as exc:
            if isinstance(job.result, dict) and job.result.get("written"):
                job.result.setdefault("partial", True)
                job.result["success"] = False
                job.result["message"] = (
                    str(exc) or job.result.get("message") or "任务结束（已保留抽取结果）"
                )
                if job.cancel_event.is_set():
                    manager.progress(job.id, done=100, total=100)
                    return job.result
                raise
            if job.cancel_event.is_set():
                if isinstance(job.result, dict):
                    job.result["message"] = "任务已取消"
                raise asyncio.CancelledError() from exc
            if isinstance(job.result, dict):
                job.result["message"] = str(exc)
                if not job.result.get("written"):
                    job.result["written"] = False
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
