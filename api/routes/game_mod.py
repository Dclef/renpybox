"""游戏模组注入：复用 ModInjector，对齐 Qt GameModPage。"""

from __future__ import annotations

import asyncio
import contextlib
import os
from pathlib import Path
from typing import Any, Callable, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from api.jobs import Job
from module.Cache.CacheManager import CacheManager
from module.Engine.Engine import Engine
from module.Tool.ModInjector import ModInjector

router = APIRouter(prefix="/api/game-mod", tags=["game-mod"])

KIND_INSTALL = "game_mod_install"
KIND_UNINSTALL = "game_mod_uninstall"
KIND_CLEANUP_LEGACY = "game_mod_cleanup_legacy"
KINDS = (KIND_INSTALL, KIND_UNINSTALL, KIND_CLEANUP_LEGACY)
_BUSY = "已有任务正在运行或收尾，请稍后再试"
_MOD_KEYS = frozenset(ModInjector.MODS.keys())
ModKey = Literal["gallery_unlock", "urm", "simple_modifier"]


def _norm(value: str) -> str:
    return os.path.normcase(os.path.abspath(value)) if value else ""


def _project_identity(config: Any) -> tuple[str, ...]:
    """冻结 owner 身份：未绑定时为各字段空串组成的 tuple，绝不能用 None 跳过守卫。"""
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


def _target_key(game_dir: Path) -> str:
    return _norm(str(game_dir)) or "game-mod"


def _acquire_engine() -> Engine:
    engine = Engine.get()
    if not engine.try_set_status(Engine.Status.IDLE, Engine.Status.TESTING):
        raise HTTPException(status_code=409, detail=_BUSY)
    return engine


def _latest_job(request: Request, project_key: str) -> Job | None:
    return next(
        (
            job
            for job in request.app.state.jobs.list()
            if job.kind in KINDS
            and isinstance(job.result, dict)
            and job.result.get("project_key") == project_key
        ),
        None,
    )


def _resolve_game(path_text: str) -> Path:
    text = str(path_text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="游戏路径不能为空")
    injector = ModInjector()
    try:
        return injector.require_game_dir(text)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _parse_owner_identity(value: Any) -> list[str] | None:
    """可选 owner 快照：缺省/None 兼容旧客户端；否则必须是纯字符串 list/tuple。"""
    if value is None:
        return None
    if not isinstance(value, (list, tuple)):
        raise ValueError("owner_identity 必须是字符串列表")
    if not all(isinstance(item, str) for item in value):
        raise ValueError("owner_identity 每项必须是字符串")
    return list(value)


def _reject_stale_owner(body_identity: list[str] | None, live: tuple[str, ...]) -> None:
    """请求携带快照且与当前配置不一致时，创建任务前 409。"""
    if body_identity is None:
        return
    if tuple(body_identity) != live:
        raise HTTPException(status_code=409, detail="项目身份已变化，请刷新后再试")


class _OwnerSnapshotBody(BaseModel):
    """POST 可选 owner_identity；严格校验 list/tuple[str]，缺省兼容旧客户端。"""

    owner_identity: list[str] | None = None

    @field_validator("owner_identity", mode="before")
    @classmethod
    def _validate_owner_identity(cls, value: Any) -> list[str] | None:
        return _parse_owner_identity(value)


class ModBody(_OwnerSnapshotBody):
    model_config = ConfigDict(extra="forbid", strict=True)
    project_key: str = ""
    game_path: str = Field(min_length=1)
    key: ModKey
    confirm: bool = False


class LegacyBody(_OwnerSnapshotBody):
    model_config = ConfigDict(extra="forbid", strict=True)
    project_key: str = ""
    game_path: str = Field(min_length=1)
    confirm: bool = False


def _job_key(body_key: str, game: Path) -> str:
    body = str(body_key or "").strip()
    return body or _target_key(game)


def _describe(game_path: Path) -> dict[str, Any]:
    injector = ModInjector()
    status = injector.status(str(game_path))
    legacy = injector.has_legacy_dumuqiao(str(game_path))
    return {
        "project_key": _target_key(game_path),
        "game_dir": str(game_path.resolve()),
        "mods": status,
        "legacy_dumuqiao": legacy,
        "legacy_files": list(ModInjector.LEGACY_DUMUQIAO_FILES) if legacy else [],
        "requires_project": False,
        "supported_keys": sorted(_MOD_KEYS),
    }


@router.get("")
def read_status(request: Request, game_path: str = Query(default="")) -> dict:
    raw = str(game_path or "").strip()
    with CacheManager.LOCK:
        owner = _project_identity(request.app.state.config)
    if not raw:
        return {
            "project_key": "game-mod",
            "game_dir": "",
            "mods": {key: False for key in ModInjector.MODS},
            "legacy_dumuqiao": False,
            "legacy_files": [],
            "requires_project": False,
            "supported_keys": sorted(_MOD_KEYS),
            "owner_identity": list(owner),
            "job": None,
        }
    try:
        game = _resolve_game(raw)
        payload = _describe(game)
    except HTTPException:
        payload = {
            "project_key": _norm(raw) or "game-mod",
            "game_dir": "",
            "mods": {key: False for key in ModInjector.MODS},
            "legacy_dumuqiao": False,
            "legacy_files": [],
            "requires_project": False,
            "supported_keys": sorted(_MOD_KEYS),
            "error": "未找到有效的 game 目录",
        }
    payload["owner_identity"] = list(owner)
    job = _latest_job(request, payload["project_key"])
    payload["job"] = job.snapshot() if job is not None else None
    return payload


@router.post("/install")
async def install_mod(request: Request, body: ModBody) -> dict:
    with CacheManager.LOCK:
        owner = _project_identity(request.app.state.config)
    _reject_stale_owner(body.owner_identity, owner)
    if body.key not in _MOD_KEYS:
        raise HTTPException(status_code=400, detail="未知模组键")
    if not body.confirm:
        raise HTTPException(status_code=400, detail="安装模组需要确认")
    game = _resolve_game(body.game_path)
    target_key = _job_key(body.project_key, game)
    key = body.key

    def compute(check_cancel, progress, should_stop, touch_result) -> dict:
        del should_stop
        check_cancel()
        progress(f"安装 {key}", 20)
        check_cancel()  # 写前再校验冻结 owner（含空→绑定）
        success, message = ModInjector().install(str(game), key)
        status = ModInjector().status(str(game))
        legacy = ModInjector().has_legacy_dumuqiao(str(game))
        if success:
            # 执行器已写入：立即固化，取消/失败时 worker 可读到 written/partial
            touch_result({
                "written": True,
                "partial": True,
                "success": False,
                "action": "install",
                "key": key,
                "mods": status,
                "legacy_dumuqiao": legacy,
                "game_dir": str(game.resolve()),
                "message": f"{message}（写入完成，收尾中）",
            })
        check_cancel()
        progress("完成", 100)
        if not success:
            raise RuntimeError(message)
        return {
            "success": True,
            "written": True,
            "partial": False,
            "action": "install",
            "key": key,
            "mods": status,
            "legacy_dumuqiao": legacy,
            "game_dir": str(game.resolve()),
            "message": message,
        }

    return await _start_job(
        request,
        kind=KIND_INSTALL,
        project_key=target_key,
        message=f"安装 {key}",
        seed={"action": "install", "key": key, "game_dir": str(game)},
        compute=compute,
        owner_identity=owner,
    )


@router.post("/uninstall")
async def uninstall_mod(request: Request, body: ModBody) -> dict:
    with CacheManager.LOCK:
        owner = _project_identity(request.app.state.config)
    _reject_stale_owner(body.owner_identity, owner)
    if body.key not in _MOD_KEYS:
        raise HTTPException(status_code=400, detail="未知模组键")
    if not body.confirm:
        raise HTTPException(status_code=400, detail="卸载模组需要确认")
    game = _resolve_game(body.game_path)
    target_key = _job_key(body.project_key, game)
    key = body.key

    def compute(check_cancel, progress, should_stop, touch_result) -> dict:
        del should_stop
        check_cancel()
        progress(f"卸载 {key}", 20)
        check_cancel()
        success, message = ModInjector().uninstall(str(game), key)
        status = ModInjector().status(str(game))
        legacy = ModInjector().has_legacy_dumuqiao(str(game))
        if success:
            touch_result({
                "written": True,
                "partial": True,
                "success": False,
                "action": "uninstall",
                "key": key,
                "mods": status,
                "legacy_dumuqiao": legacy,
                "game_dir": str(game.resolve()),
                "message": f"{message}（写入完成，收尾中）",
            })
        check_cancel()
        progress("完成", 100)
        if not success:
            raise RuntimeError(message)
        return {
            "success": True,
            "written": True,
            "partial": False,
            "action": "uninstall",
            "key": key,
            "mods": status,
            "legacy_dumuqiao": legacy,
            "game_dir": str(game.resolve()),
            "message": message,
        }

    return await _start_job(
        request,
        kind=KIND_UNINSTALL,
        project_key=target_key,
        message=f"卸载 {key}",
        seed={"action": "uninstall", "key": key, "game_dir": str(game)},
        compute=compute,
        owner_identity=owner,
    )


@router.post("/cleanup-legacy")
async def cleanup_legacy(request: Request, body: LegacyBody) -> dict:
    with CacheManager.LOCK:
        owner = _project_identity(request.app.state.config)
    _reject_stale_owner(body.owner_identity, owner)
    if not body.confirm:
        raise HTTPException(status_code=400, detail="清理旧版独木桥需要确认")
    game = _resolve_game(body.game_path)
    target_key = _job_key(body.project_key, game)

    def compute(check_cancel, progress, should_stop, touch_result) -> dict:
        del should_stop
        check_cancel()
        progress("清理旧版独木桥", 20)
        check_cancel()
        success, message = ModInjector().remove_legacy_dumuqiao(str(game))
        mods = ModInjector().status(str(game))
        legacy = ModInjector().has_legacy_dumuqiao(str(game))
        if success:
            touch_result({
                "written": True,
                "partial": True,
                "success": False,
                "action": "cleanup_legacy",
                "mods": mods,
                "legacy_dumuqiao": legacy,
                "legacy_files": list(ModInjector.LEGACY_DUMUQIAO_FILES),
                "game_dir": str(game.resolve()),
                "message": f"{message}（写入完成，收尾中）",
            })
        check_cancel()
        progress("完成", 100)
        if not success:
            raise RuntimeError(message)
        return {
            "success": True,
            "written": True,
            "partial": False,
            "action": "cleanup_legacy",
            "mods": mods,
            "legacy_dumuqiao": legacy,
            "legacy_files": list(ModInjector.LEGACY_DUMUQIAO_FILES),
            "game_dir": str(game.resolve()),
            "message": message,
        }

    return await _start_job(
        request,
        kind=KIND_CLEANUP_LEGACY,
        project_key=target_key,
        message="清理旧版独木桥",
        seed={"action": "cleanup_legacy", "game_dir": str(game)},
        compute=compute,
        owner_identity=owner,
    )


async def _start_job(
    request: Request,
    *,
    kind: str,
    project_key: str,
    message: str,
    seed: dict[str, Any],
    compute: Callable[..., dict],
    owner_identity: tuple[str, ...],
) -> dict:
    engine = _acquire_engine()
    manager = request.app.state.jobs
    try:
        job = manager.create(kind, total=100, cooperative_cancel=True)
    except Exception:
        engine.release_status(Engine.Status.TESTING)
        raise
    # 冻结 owner（含全空字段）与 target 键；未绑定不得写成 None 而跳过守卫
    frozen_owner = tuple(owner_identity)
    job.result = {
        "project_key": project_key,
        "message": message,
        "written": False,
        "partial": False,
        "worker_active": True,
        "owner_identity": list(frozen_owner),
        **seed,
    }
    loop = asyncio.get_running_loop()

    def owner_still() -> bool:
        # 取消 truthiness：空串 tuple 也必须与 live 逐项比较
        with CacheManager.LOCK:
            live = request.app.state.config
        return _project_identity(live) == frozen_owner

    def check_cancel() -> None:
        """协作取消 + 冻结 owner；切项目/空→绑定后尚未写入时禁止继续。"""
        if job.cancel_event.is_set():
            raise asyncio.CancelledError()
        if not owner_still():
            raise RuntimeError("项目已切换，未执行操作")

    def should_stop() -> bool:
        return job.cancel_event.is_set()

    def publish(message_text: str, percent: int) -> None:
        if isinstance(job.result, dict):
            job.result["message"] = message_text
        manager.progress(job.id, done=max(0, min(100, int(percent))), total=100)

    def progress(message_text: str, percent: int = 0) -> None:
        loop.call_soon_threadsafe(lambda: publish(message_text, percent))

    def touch_result(patch: dict[str, Any]) -> None:
        # 同步固化 written/partial，避免取消竞态读到旧快照
        if isinstance(job.result, dict) and job.result.get("worker_active"):
            job.result.update(patch)
        loop.call_soon_threadsafe(lambda: manager.progress(job.id))

    def run_compute() -> dict:
        check_cancel()
        result = compute(check_cancel, progress, should_stop, touch_result)
        if isinstance(job.result, dict) and job.result.get("worker_active"):
            job.result.update(result)
        return result

    def _mark_partial_cancel() -> dict:
        assert isinstance(job.result, dict)
        job.result["written"] = True
        job.result["partial"] = True
        job.result["success"] = False
        job.result.setdefault("message", "任务已取消（已保留写入结果）")
        manager.progress(job.id, done=100, total=100)
        return job.result

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
                    return _mark_partial_cancel()
                raise
            if isinstance(job.result, dict):
                job.result.update(result)
                if job.cancel_event.is_set() and job.result.get("written"):
                    return _mark_partial_cancel()
                if job.cancel_event.is_set():
                    job.result["message"] = "任务已取消"
                    raise asyncio.CancelledError()
            manager.progress(job.id, done=100, total=100)
            return job.result
        except asyncio.CancelledError:
            if isinstance(job.result, dict) and job.result.get("written"):
                return _mark_partial_cancel()
            if isinstance(job.result, dict):
                job.result["message"] = "任务已取消"
            raise
        except Exception as exc:
            if isinstance(job.result, dict) and job.result.get("written"):
                job.result["partial"] = True
                job.result["success"] = False
                job.result["message"] = str(exc) or job.result.get("message") or "任务失败"
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
                job.result["written"] = bool(job.result.get("written"))
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
