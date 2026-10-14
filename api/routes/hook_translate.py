"""运行时 EXE HOOK 翻译：先 runtime_extract，成功后再 TRANSLATION_START。

与补全翻译（mode=supplement / renpy_hook_translate）严格区分：
本路由只做 EXE 运行时抽取，翻译阶段 source=false、hook=false。
"""

from __future__ import annotations

import asyncio
import contextlib
import copy
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from api.jobs import Job
from api.routes.settings import sync_output_protocol
from api.routes.translation import (
    BUSY_DETAIL,
    _collect_changed_fields,
    _parse_toolbox_language,
    _persist_changed_fields,
    _prepare_payload,
    _project_identity,
    _TOOLBOX_FIELD_NAMES,
    TranslationStartResultWaiter,
)
from base.Base import Base
from base.BaseLanguage import BaseLanguage
from base.EventManager import EventManager
from module.Cache.CacheManager import CacheManager
from module.Engine.Engine import Engine
from module.Extract.RenpyExtractor import RenpyExtractor
from module.Project.ProjectStore import ProjectStore
from module.Renpy.ProjectPaths import RenpyProjectPaths, normalise_path

router = APIRouter(prefix = "/api/hook-translate", tags = ["hook-translate"])

KIND = "hook_translate"


class HookTranslateStartBody(BaseModel):
    game_path: str
    tl_name: str = "chinese"
    source_language: str | None = None
    target_language: str | None = None
    traditional_chinese_enable: bool | None = None
    renpy_backup_original: bool = False
    renpy_hook_incremental: bool = True
    generate_empty: bool = False
    preflight_confirmed: bool = False
    # 当前绑定项目 owner；与手动 game_path 目标分开，不能拿 target key 误判。
    project_key: str = ""
    request_id: str | None = None


class HookTranslateStartResponse(BaseModel):
    accepted: bool = False
    reason: str = ""
    detail: str = ""
    request_id: str = ""
    job: dict[str, Any] | None = None


def _emit(event, data: dict) -> None:
    EventManager.get().emit(event, data)


def _safe_language(language: str) -> str:
    name = str(language or "").strip() or "chinese"
    if name in {".", ".."} or any(ch in name for ch in '/\\<>:"|?*'):
        raise HTTPException(status_code = 400, detail = "语言名无效")
    return name


def _resolve_paths(game_path: str, tl_name: str) -> RenpyProjectPaths:
    raw = normalise_path(game_path)
    if raw is None:
        raise HTTPException(status_code = 400, detail = "请选择游戏 EXE 或项目目录")
    language = _safe_language(tl_name)
    paths = RenpyProjectPaths.from_path(raw, language)
    if paths is None:
        raise HTTPException(status_code = 400, detail = "无法解析 Ren'Py 项目路径")
    if not paths.game_dir.is_dir():
        raise HTTPException(status_code = 400, detail = f"未找到 game 目录：{paths.game_dir}")
    return paths


def _resolve_hook_context(
    live: Any,
    body: HookTranslateStartBody,
) -> tuple[RenpyProjectPaths, str, tuple[str, ...], str]:
    """解析 target 路径 + 冻结 owner。

    - owner_key / owner_identity：当前绑定项目（写前校验未切换）
    - target_key：手动 game_path 的 canonical 键（可与 owner 不同）
    """
    bound = RenpyProjectPaths.from_config(live)
    owner_identity = _project_identity(live)
    owner_key = bound.project_key if bound is not None else ""
    body_key = str(body.project_key or "").strip()
    if bound is not None and body_key and body_key != owner_key:
        raise HTTPException(status_code = 409, detail = "项目已切换，请重新加载后再操作")

    paths = _resolve_paths(body.game_path, body.tl_name)
    target_key = paths.project_key
    return paths, owner_key, owner_identity, target_key


def _latest_job(request: Request, owner_key: str | None = None, request_id: str | None = None) -> Job | None:
    req = str(request_id or "").strip()
    key = str(owner_key or "").strip()
    for job in request.app.state.jobs.list():
        if job.kind != KIND or not isinstance(job.result, dict):
            continue
        if key and str(job.result.get("owner_key") or job.result.get("project_key") or "") != key:
            continue
        if req and str(job.result.get("request_id") or "") != req:
            continue
        return job
    return None


def _build_hook_candidate(
    live: Any,
    paths: RenpyProjectPaths,
    body: HookTranslateStartBody,
    *,
    tl_dir: Path | None = None,
) -> Any:
    """抽取成功后用于翻译的候选：source=false hook=false，input=output=真实 tl。"""
    candidate = copy.deepcopy(live)
    source = _parse_toolbox_language(body.source_language, field = "source_language")
    target = _parse_toolbox_language(body.target_language, field = "target_language")
    actual_tl = Path(tl_dir) if tl_dir is not None else paths.tl_language_dir

    def _mutate(current: Any) -> None:
        current.renpy_backup_original = bool(body.renpy_backup_original)
        current.renpy_source_translate = False
        current.renpy_hook_translate = False
        current.renpy_hook_incremental = bool(body.renpy_hook_incremental)
        if source is not None:
            current.source_language = source
        else:
            current.source_language = BaseLanguage.Enum.EN
        if target is not None:
            current.target_language = target
        else:
            current.target_language = BaseLanguage.Enum.ZH
        if body.traditional_chinese_enable is not None:
            current.traditional_chinese_enable = bool(body.traditional_chinese_enable)

    ProjectStore.get().apply_resolved(
        candidate,
        paths,
        input_folder = actual_tl,
        output_folder = actual_tl,
        mutate = _mutate,
        persist = False,
    )
    return candidate


def _acquire_engine() -> Engine:
    engine = Engine.get()
    if engine.has_stop_barrier() or engine.has_single_tasks():
        raise HTTPException(status_code = 409, detail = BUSY_DETAIL)
    if engine.get_status() != Engine.Status.IDLE:
        raise HTTPException(status_code = 409, detail = "已有任务正在运行或收尾，请稍后再试")
    if not engine.try_set_status(Engine.Status.IDLE, Engine.Status.TESTING):
        raise HTTPException(status_code = 409, detail = "已有任务正在运行或收尾，请稍后再试")
    return engine


@router.get("/status")
def read_status(
    request: Request,
    project_key: str = "",
    request_id: str = "",
) -> dict:
    """返回指定 owner/request 最近一次 HOOK 任务。"""
    key = str(project_key or "").strip()
    if not key and not request_id:
        paths = RenpyProjectPaths.from_config(request.app.state.config)
        key = paths.project_key if paths else ""
    job = _latest_job(request, key or None, request_id or None)
    return {
        "project_key": key,
        "job": job.snapshot() if job else None,
    }


@router.post("/start", response_model = HookTranslateStartResponse)
async def start_hook_translate(
    request: Request,
    body: HookTranslateStartBody,
) -> HookTranslateStartResponse:
    """ASSETS_MISSING 预检 → 占 TESTING → Job runtime_extract → START_RESULT 真值。"""
    with CacheManager.LOCK:
        live = request.app.state.config
        paths, owner_key, owner_identity, target_key = _resolve_hook_context(live, body)
        # 预检用候选（路径已指向标准 tl）；抽取失败则不会落盘。
        candidate = _build_hook_candidate(live, paths, body)

    request_id = str(body.request_id or "").strip() or uuid.uuid4().hex[:12]
    _, rejection = _prepare_payload(
        request,
        Base.TranslationStatus.UNTRANSLATED,
        request_id,
        preflight_confirmed = bool(body.preflight_confirmed),
        config_snapshot = candidate,
    )
    if rejection is not None:
        return HookTranslateStartResponse(
            accepted = False,
            reason = rejection.reason,
            detail = rejection.detail,
            request_id = request_id,
        )

    engine = _acquire_engine()
    manager = request.app.state.jobs
    try:
        job = manager.create(KIND, total = 100, cooperative_cancel = True)
    except Exception:
        engine.release_status(Engine.Status.TESTING)
        raise

    game_path = str(normalise_path(body.game_path) or body.game_path)
    tl_name = _safe_language(body.tl_name)
    incremental = bool(body.renpy_hook_incremental)
    generate_empty = bool(body.generate_empty)
    frozen_owner = owner_identity

    job.result = {
        "project_key": owner_key or target_key,
        "owner_key": owner_key,
        "target_key": target_key,
        "owner_identity": list(frozen_owner),
        "game_path": game_path,
        "tl_name": tl_name,
        "tl_dir": "",
        "message": "正在准备运行时 HOOK 抽取…",
        "stage": "extracting",
        "worker_active": True,
        "request_id": request_id,
        "translation_started": False,
        "translation_run_id": 0,
        "written_files": [],
        "partial": False,
    }

    loop = asyncio.get_running_loop()
    released = {"done": False}

    def release_testing() -> None:
        if released["done"]:
            return
        released["done"] = True
        engine.release_status(Engine.Status.TESTING)

    def publish(message: str, *, stage: str | None = None, done: int | None = None) -> None:
        if not isinstance(job.result, dict) or not job.result.get("worker_active"):
            return
        job.result["message"] = message
        if stage:
            job.result["stage"] = stage
        manager.progress(job.id, done = done, total = 100)

    def progress_callback(message: str) -> None:
        if job.cancel_event.is_set():
            return
        loop.call_soon_threadsafe(lambda: publish(message, stage = "extracting"))

    def compute() -> dict:
        if job.cancel_event.is_set():
            raise asyncio.CancelledError()
        extractor = RenpyExtractor()
        # 只记录本次 runtime 实际写入，不能把旧 TL 整树当本次产物。
        written: list[str] = []
        try:
            tl_dir = extractor.runtime_extract(
                game_path,
                tl_name,
                generate_empty = generate_empty,
                incremental = incremental,
                timeout = 300,
                progress_callback = progress_callback,
                should_stop = job.cancel_event.is_set,
                written_files = written,
            )
        except Exception:
            if isinstance(job.result, dict):
                job.result["written_files"] = list(written)
                job.result["partial"] = bool(written)
            raise
        if isinstance(job.result, dict):
            job.result["tl_dir"] = str(tl_dir) if tl_dir else ""
            job.result["written_files"] = list(written)
            job.result["partial"] = False

        if job.cancel_event.is_set():
            raise asyncio.CancelledError()

        # 必须以 runtime_extract 返回的真实 tl 启动，不能用预猜目录。
        resolved_paths = RenpyProjectPaths.from_path(tl_dir, tl_name)
        if resolved_paths is None:
            raise RuntimeError("运行时抽取完成，但无法解析 tl 目录")

        with CacheManager.LOCK:
            live_config = request.app.state.config
            if frozen_owner and _project_identity(live_config) != frozen_owner:
                raise RuntimeError("项目已切换，本次抽取结果未用于翻译")
            configured = _build_hook_candidate(
                live_config, resolved_paths, body, tl_dir = Path(tl_dir),
            )
            configured.input_folder = str(Path(tl_dir).resolve(strict = False))
            configured.output_folder = configured.input_folder
            sync_output_protocol(configured)
            changed = _collect_changed_fields(live_config, configured, _TOOLBOX_FIELD_NAMES)
            _persist_changed_fields(live_config, changed)
            snapshot = copy.deepcopy(configured)

        return {
            "project_key": owner_key or target_key,
            "owner_key": owner_key,
            "target_key": target_key,
            "tl_dir": str(tl_dir),
            "written_files": list(written),
            "partial": False,
            "snapshot": snapshot,
            "message": "运行时抽取完成，正在启动翻译…",
            "stage": "translating",
            "worker_active": True,
        }

    async def worker(_: Job) -> dict:
        try:
            if job.cancel_event.is_set():
                raise asyncio.CancelledError()
            future = loop.run_in_executor(None, compute)
            try:
                result = await asyncio.shield(future)
            except asyncio.CancelledError:
                job.cancel_event.set()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    finished = await asyncio.shield(future)
                    if isinstance(finished, dict) and isinstance(job.result, dict):
                        for key in ("tl_dir", "written_files", "partial"):
                            if key in finished:
                                job.result[key] = finished[key]
                raise

            snapshot = result.pop("snapshot", None)
            job.result.update({k: v for k, v in result.items() if k != "snapshot"})
            manager.progress(job.id, done = 100, total = 100)

            if job.cancel_event.is_set():
                if isinstance(job.result, dict):
                    job.result["stage"] = "cancelled"
                    job.result["message"] = "任务已取消"
                    job.result["translation_started"] = False
                raise asyncio.CancelledError()

            # 必须先释放 TESTING，引擎才能受理 TRANSLATION_START。
            release_testing()
            if snapshot is None:
                raise RuntimeError("抽取结果缺少配置快照")

            payload, rejection = _prepare_payload(
                request,
                Base.TranslationStatus.UNTRANSLATED,
                request_id,
                preflight_confirmed = True,
                config_snapshot = snapshot,
            )
            if rejection is not None:
                raise RuntimeError(rejection.detail or rejection.reason or "翻译启动被拒绝")

            waiter = TranslationStartResultWaiter(request_id)
            _emit(Base.Event.TRANSLATION_START, payload or {})
            start_result = await waiter.wait()
            started = bool(start_result.get("accepted"))
            if isinstance(job.result, dict):
                job.result["translation_started"] = started
                job.result["translation_run_id"] = int(start_result.get("run_id") or 0)
                job.result["start_reason"] = str(start_result.get("reason") or "")
                if started:
                    job.result["message"] = "运行时抽取完成，翻译已启动"
                    job.result["stage"] = "translating"
                else:
                    job.result["message"] = (
                        f"抽取完成，但翻译未启动：{start_result.get('reason') or '未知原因'}"
                    )
                    job.result["stage"] = "failed"
                    raise RuntimeError(job.result["message"])
            return job.result
        except asyncio.CancelledError:
            if isinstance(job.result, dict):
                job.result["message"] = "任务已取消"
                job.result["stage"] = "cancelled"
                job.result["translation_started"] = False
                # 取消时保留已写产物信息，不能报成零写入。
                if job.result.get("written_files"):
                    job.result["partial"] = True
            raise
        except Exception as exc:
            if job.cancel_event.is_set():
                if isinstance(job.result, dict):
                    job.result["message"] = "任务已取消"
                    job.result["stage"] = "cancelled"
                    job.result["translation_started"] = False
                    if job.result.get("written_files"):
                        job.result["partial"] = True
                raise asyncio.CancelledError() from exc
            if isinstance(job.result, dict):
                job.result["message"] = str(exc)
                job.result["stage"] = "failed"
                job.result["translation_started"] = False
            raise
        finally:
            if isinstance(job.result, dict):
                job.result["worker_active"] = False
            release_testing()

    try:
        await manager.run(job.id, worker)
    except BaseException:
        if isinstance(job.result, dict):
            job.result["worker_active"] = False
        release_testing()
        raise

    return HookTranslateStartResponse(
        accepted = True,
        reason = "STARTED",
        detail = "已受理运行时 HOOK 抽取",
        request_id = request_id,
        job = job.snapshot(),
    )


@router.post("/stop")
def stop_hook_translate(
    request: Request,
    project_key: str = "",
    request_id: str = "",
    run_id: int = 0,
) -> dict:
    """仅停止本页 request/run 归属的抽取或翻译，不跨任务盲停。"""
    key = str(project_key or "").strip()
    req = str(request_id or "").strip()
    job = _latest_job(request, key or None, req or None)

    if job is not None and job.status.value in ("pending", "running"):
        hook_req = str((job.result or {}).get("request_id") or "")
        if req and hook_req and req != hook_req:
            raise HTTPException(status_code = 409, detail = "当前没有可停止的 HOOK 抽取或翻译任务")
        if key:
            job_owner = str((job.result or {}).get("owner_key") or (job.result or {}).get("project_key") or "")
            if job_owner and job_owner != key:
                raise HTTPException(status_code = 409, detail = "当前没有可停止的 HOOK 抽取或翻译任务")
        request.app.state.jobs.cancel(job.id)
        return {"ok": True, "stage": "extracting", "job_id": job.id}

    engine = Engine.get()
    if job is None or not isinstance(job.result, dict) or not job.result.get("translation_started"):
        raise HTTPException(status_code = 409, detail = "当前没有可停止的 HOOK 抽取或翻译任务")

    hook_request_id = str(job.result.get("request_id") or "")
    hook_run_id = int(job.result.get("translation_run_id") or 0)
    if req and hook_request_id and req != hook_request_id:
        raise HTTPException(status_code = 409, detail = "当前没有可停止的 HOOK 抽取或翻译任务")
    if run_id and hook_run_id and int(run_id) != hook_run_id:
        raise HTTPException(status_code = 409, detail = "当前没有可停止的 HOOK 抽取或翻译任务")

    translator = getattr(engine, "translator", None)
    if translator is None:
        raise HTTPException(status_code = 409, detail = "当前没有可停止的 HOOK 抽取或翻译任务")
    active_request_id = str(getattr(translator, "_active_request_id", "") or "")
    active_run_id = int(getattr(translator, "_translation_run_id", 0) or 0)

    if engine.get_status() != Engine.Status.TRANSLATING or engine.has_stop_barrier():
        raise HTTPException(status_code = 409, detail = "当前没有可停止的 HOOK 抽取或翻译任务")

    owns_translation = (
        hook_request_id
        and active_request_id == hook_request_id
        and (not hook_run_id or active_run_id == hook_run_id)
    )
    if not owns_translation:
        raise HTTPException(status_code = 409, detail = "当前没有可停止的 HOOK 抽取或翻译任务")

    _emit(Base.Event.TRANSLATION_STOP, {})
    return {"ok": True, "stage": "translating", "request_id": hook_request_id, "run_id": hook_run_id}
