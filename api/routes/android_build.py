"""安卓打包 API：对齐 Qt AndroidBuildPage，长任务走协作 Job；SDK 进程不可真取消。

requires_project=true：绑定项目 owner + 可选显式 project_path 目标。
忙状态 409 且无 config/mkdir/写盘副作用。worker 真实结束后才释放引擎。
"""

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
from module.Project.ProjectStore import ProjectStore
from module.Renpy.ProjectPaths import RenpyProjectPaths
from module.Tool.AndroidBuilder import AndroidBuilder
from module.Tool.AndroidProjectTools import (
    AndroidProjectToolsError,
    DEFAULT_DETECT_HINTS,
    detect_resource_dirs,
    make_shell_archive,
    merge_items,
    preflight_shell_archive,
    sanitize_android_dist_assets,
    split_items,
)

router = APIRouter(prefix="/api/android-build", tags=["android-build"])

KIND_CHECK_ENV = "android_check_env"
KIND_INSTALL_SDK = "android_install_sdk"
KIND_GENERATE_KEYS = "android_generate_keys"
KIND_BUILD = "android_build"
KIND_SHELL = "android_shell"
KINDS = (
    KIND_CHECK_ENV,
    KIND_INSTALL_SDK,
    KIND_GENERATE_KEYS,
    KIND_BUILD,
    KIND_SHELL,
)
_BUSY = "已有任务正在运行或收尾，请稍后再试"
# SDK/外部进程无真取消能力：不暴露假停止
_CANCELLABLE = False


class ProjectKeyBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    project_key: str = ""
    # 可选覆盖目标项目根；省略则用绑定项目
    project_path: str = ""


class ConfigBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    project_key: str = ""
    project_path: str = ""
    sdk_path: str = ""
    app_name: str = ""
    package_name: str = ""
    version: str = ""
    archive_source_dir: str = ""
    shell_backup_enable: bool = True
    shell_remove_dirs: str = ""
    # 隐藏字段：与 Qt 一致保留
    dname: str = ""
    update_always: bool = True
    update_icons: bool = True
    persist: bool = True


class WriteJsonBody(ConfigBody):
    pass


class DetectBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    project_key: str = ""
    project_path: str = ""
    # 检测提示：空时用清理框/默认配置 hints
    hints: str = ""
    # archive | remove
    target: str = Field(pattern=r"^(archive|remove)$")
    # 当前文本，用于 add 模式；检测本身为 replace
    current: str = ""
    replace: bool = True


class EnvJobBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    project_key: str = ""
    project_path: str = ""
    sdk_path: str = ""


class KeysJobBody(EnvJobBody):
    dname: str = ""


class BuildJobBody(ConfigBody):
    confirm: bool = False


class ShellJobBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    project_key: str = ""
    project_path: str = ""
    archive_source_dir: str = ""
    shell_remove_dirs: str = ""
    shell_backup_enable: bool = True
    confirm: bool = False
    # 隐藏字段一并冻结进配置
    sdk_path: str = ""
    app_name: str = ""
    package_name: str = ""
    version: str = ""
    dname: str = ""
    update_always: bool = True
    update_icons: bool = True


class OpenBinBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    project_key: str = ""
    project_path: str = ""
    sdk_path: str = ""


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


def _bound_paths(config: Any) -> RenpyProjectPaths:
    paths = RenpyProjectPaths.from_config(config)
    if paths is None or not paths.game_dir.is_dir():
        raise HTTPException(status_code=400, detail="未绑定游戏项目")
    return paths


def _resolve_target(
    config: Any,
    *,
    project_path: str = "",
    body_project_key: str = "",
    require_body_key: bool = True,
) -> tuple[RenpyProjectPaths, tuple[str, ...], str]:
    """owner=绑定项目；target=绑定或显式 project_path（可与 owner 不同）。

    body.project_key 校验 owner 绑定键，或显式目标自身键（UI 以 target 为 status canonical）。
    返回 (target, owner_identity, owner_key)。
    """
    bound = _bound_paths(config)
    owner_identity = _project_identity(config)
    owner_key = bound.project_key
    raw = str(project_path or "").strip()
    if raw:
        target = RenpyProjectPaths.from_path(raw)
        if target is None or not target.game_dir.is_dir():
            raise HTTPException(status_code=400, detail="项目路径无效或缺少 game 目录")
    else:
        target = bound
    body_key = str(body_project_key or "").strip()
    if require_body_key and not body_key:
        raise HTTPException(status_code=400, detail="project_key 必填")
    # 允许：owner 键（绑定 A + 手动 B）或 target 键（status 已切到 B）
    if body_key and body_key != owner_key and body_key != target.project_key:
        raise HTTPException(status_code=409, detail="项目已切换，请重新加载后再操作")
    return target, owner_identity, owner_key


def _normalize_project_on_config(config: Any, target: RenpyProjectPaths) -> tuple[str, ...]:
    """把目标项目规范写入 config（game/tl），返回新 owner_identity。不持久化。"""
    ProjectStore.get().apply_resolved(config, target, persist=False)
    return _project_identity(config)


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


def _acquire_engine() -> Engine:
    engine = Engine.get()
    if not engine.try_set_status(Engine.Status.IDLE, Engine.Status.TESTING):
        raise HTTPException(status_code=409, detail=_BUSY)
    return engine


def _config_fields(config: Any) -> dict:
    remove_dirs = str(getattr(config, "android_shell_remove_dirs", "") or "")
    return {
        "sdk_path": str(getattr(config, "renpy_sdk_path", "") or ""),
        "app_name": str(getattr(config, "android_app_name", "") or ""),
        "package_name": str(getattr(config, "android_package_name", "") or ""),
        "version": str(getattr(config, "android_version", "") or ""),
        "archive_source_dir": str(getattr(config, "android_archive_source_dir", "") or ""),
        "shell_backup_enable": bool(getattr(config, "android_shell_backup_enable", True)),
        "shell_remove_dirs": remove_dirs,
        "default_shell_remove_dirs": DEFAULT_DETECT_HINTS,
        "dname": str(getattr(config, "android_dname", "") or ""),
        "update_always": bool(getattr(config, "android_update_always", True)),
        "update_icons": bool(getattr(config, "android_update_icons", True)),
    }


def _apply_android_fields(config: Any, body: Any) -> None:
    """只写安卓相关字段；项目根规范化由 _normalize_project_on_config 负责。"""
    if hasattr(body, "sdk_path"):
        config.renpy_sdk_path = str(body.sdk_path or "").strip()
    config.android_app_name = str(getattr(body, "app_name", "") or "").strip()
    config.android_package_name = str(getattr(body, "package_name", "") or "").strip()
    config.android_version = str(getattr(body, "version", "") or "").strip()
    config.android_archive_source_dir = str(
        getattr(body, "archive_source_dir", "") or ""
    ).strip()
    config.android_shell_backup_enable = bool(
        getattr(body, "shell_backup_enable", True)
    )
    config.android_shell_remove_dirs = str(
        getattr(body, "shell_remove_dirs", "") or ""
    ).strip()
    config.android_dname = str(getattr(body, "dname", "") or "").strip()
    config.android_update_always = bool(getattr(body, "update_always", True))
    config.android_update_icons = bool(getattr(body, "update_icons", True))


def _apply_config_fields(
    config: Any,
    body: ConfigBody | ShellJobBody | BuildJobBody,
    *,
    target: RenpyProjectPaths | None = None,
) -> tuple[str, ...]:
    """写入安卓字段；若有 target 则规范项目路径。返回最新 identity。"""
    if target is not None:
        _normalize_project_on_config(config, target)
    elif str(getattr(body, "project_path", "") or "").strip():
        paths = RenpyProjectPaths.from_path(str(body.project_path).strip())
        if paths is not None and paths.game_dir.is_dir():
            _normalize_project_on_config(config, paths)
    _apply_android_fields(config, body)
    return _project_identity(config)


def _builder_for(
    *,
    sdk_path: str,
    project_root: Path,
    validate: bool = True,
) -> AndroidBuilder:
    sdk = str(sdk_path or "").strip()
    if not sdk:
        raise HTTPException(status_code=400, detail="请先选择 Ren'Py SDK 目录")
    builder = AndroidBuilder(sdk, str(project_root))
    if validate:
        errors = builder.validate_paths()
        if errors:
            raise HTTPException(status_code=400, detail="\n".join(errors))
    return builder


def _describe(
    paths: RenpyProjectPaths,
    config: Any,
    request: Request,
    *,
    owner_key: str = "",
    owner_root: str = "",
) -> dict:
    keystore = paths.project_root / "android.keystore"
    sdk_path = str(getattr(config, "renpy_sdk_path", "") or "")
    rapt_bin = ""
    outputs: list[dict] = []
    if sdk_path:
        try:
            builder = AndroidBuilder(sdk_path, str(paths.project_root))
            rapt_bin = str(builder.rapt_bin)
            if builder.rapt_bin.is_dir():
                outputs = [
                    {
                        "name": path.name,
                        "path": str(path),
                        "mtime": path.stat().st_mtime,
                    }
                    for path in builder.list_outputs()
                ]
        except Exception:
            rapt_bin = ""
            outputs = []
    return {
        "project_key": paths.project_key,
        "project_root": str(paths.project_root),
        "game_dir": str(paths.game_dir),
        "owner_project_key": owner_key or paths.project_key,
        "owner_project_root": owner_root or str(paths.project_root),
        "keystore_exists": keystore.is_file(),
        "rapt_bin": rapt_bin,
        "rapt_bin_exists": bool(rapt_bin and Path(rapt_bin).is_dir()),
        "outputs": outputs,
        "config": _config_fields(config),
        "job": None,
        "cancellable": _CANCELLABLE,
    }


@router.get("")
def read_android_build(
    request: Request,
    project_path: str | None = Query(default=None),
) -> dict:
    """状态：默认绑定项目；?project_path= 可查手动目标 B（owner 仍为绑定 A）。"""
    with CacheManager.LOCK:
        bound = _bound_paths(request.app.state.config)
        owner_key = bound.project_key
        raw = str(project_path or "").strip()
        if raw:
            target, _owner_identity, owner_key = _resolve_target(
                request.app.state.config,
                project_path=raw,
                body_project_key="",
                require_body_key=False,
            )
        else:
            target = bound
        payload = _describe(
            target,
            request.app.state.config,
            request,
            owner_key=owner_key,
            owner_root=str(bound.project_root),
        )
    job = _latest_job(request, target.project_key)
    payload["job"] = job.snapshot() if job else None
    return payload


@router.post("/save-config")
def save_config(request: Request, body: ConfigBody) -> dict:
    """保存 SDK/应用/壳配置（含隐藏 dname/update_*）；忙则 409 无写。"""
    engine = _acquire_engine()
    try:
        with CacheManager.LOCK:
            paths, _owner_identity, owner_key = _resolve_target(
                request.app.state.config,
                project_path=body.project_path,
                body_project_key=body.project_key,
            )
            _apply_config_fields(request.app.state.config, body, target=paths)
            if body.persist:
                ProjectStore.get().persist(request.app.state.config)
            bound = _bound_paths(request.app.state.config)
            payload = _describe(
                paths,
                request.app.state.config,
                request,
                owner_key=owner_key,
                owner_root=str(bound.project_root),
            )
        return payload
    finally:
        engine.release_status(Engine.Status.TESTING)


@router.post("/write-json")
def write_android_json(request: Request, body: WriteJsonBody) -> dict:
    """写入 project/android.json（同步）；需 app/package/version 非空。"""
    package = body.package_name.strip()
    app_name = body.app_name.strip()
    version = body.version.strip()
    if not package or not app_name or not version:
        raise HTTPException(status_code=400, detail="请填写应用名、包名和版本")

    engine = _acquire_engine()
    try:
        with CacheManager.LOCK:
            paths, _owner_identity, _owner_key = _resolve_target(
                request.app.state.config,
                project_path=body.project_path,
                body_project_key=body.project_key,
            )
            builder = _builder_for(
                sdk_path=body.sdk_path or request.app.state.config.renpy_sdk_path,
                project_root=paths.project_root,
            )
            json_path = builder.write_android_json(
                package_name=package,
                app_name=app_name,
                version=version,
                update_always=body.update_always,
                update_icons=body.update_icons,
            )
            _apply_config_fields(request.app.state.config, body, target=paths)
            if body.persist:
                ProjectStore.get().persist(request.app.state.config)
        return {
            "success": True,
            "written": True,
            "path": str(json_path),
            "project_key": paths.project_key,
            "written_files": [str(json_path)],
            "message": "android.json 已更新",
        }
    finally:
        engine.release_status(Engine.Status.TESTING)


@router.post("/detect")
def detect_dirs(request: Request, body: DetectBody) -> dict:
    """检测打包/清理目录；owner 键 A + project_path B 合法。"""
    with CacheManager.LOCK:
        paths, _owner_identity, owner_key = _resolve_target(
            request.app.state.config,
            project_path=body.project_path,
            body_project_key=body.project_key,
        )
        hints_text = body.hints.strip()
        if not hints_text:
            hints_text = str(
                getattr(request.app.state.config, "android_shell_remove_dirs", "")
                or DEFAULT_DETECT_HINTS
            )
    try:
        detected = detect_resource_dirs(
            paths.game_dir,
            hints=split_items(hints_text),
        )
    except AndroidProjectToolsError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if body.replace:
        value = ";".join(detected)
    else:
        value = ";".join(merge_items(split_items(body.current), detected))
    return {
        "success": True,
        "target": body.target,
        "detected": detected,
        "count": len(detected),
        "value": value,
        "cleared": not detected,
        "project_key": paths.project_key,
        "project_root": str(paths.project_root),
        "owner_project_key": owner_key,
        "message": (
            f"已检测 {len(detected)} 个文件夹并替换当前列表"
            if detected
            else "未检测到资源文件夹，已清空"
        ),
    }


@router.post("/open-bin")
def open_bin_info(request: Request, body: OpenBinBody) -> dict:
    """校验并返回 rapt/bin 路径；前端负责 openPath。不接受任意路径。"""
    with CacheManager.LOCK:
        paths, _owner_identity, _owner_key = _resolve_target(
            request.app.state.config,
            project_path=body.project_path,
            body_project_key=body.project_key,
        )
        sdk = body.sdk_path or request.app.state.config.renpy_sdk_path
        builder = _builder_for(sdk_path=sdk, project_root=paths.project_root)
    bin_dir = builder.rapt_bin
    if not bin_dir.is_dir():
        raise HTTPException(status_code=400, detail="未找到 rapt/bin，请先构建")
    return {
        "success": True,
        "path": str(bin_dir),
        "project_key": paths.project_key,
        "outputs": [
            {"name": path.name, "path": str(path), "mtime": path.stat().st_mtime}
            for path in builder.list_outputs()
        ],
    }


@router.post("/check-env")
async def check_env(request: Request, body: EnvJobBody) -> dict:
    return await _start_sdk_job(
        request,
        kind=KIND_CHECK_ENV,
        action="check_env",
        body=body,
        message="正在检查环境...",
        operation=lambda builder, emit: builder.check_env(on_output=emit),
        success_message="环境检查完成",
        failure_message="环境检查失败",
    )


@router.post("/install-sdk")
async def install_sdk(request: Request, body: EnvJobBody) -> dict:
    return await _start_sdk_job(
        request,
        kind=KIND_INSTALL_SDK,
        action="install_sdk",
        body=body,
        message="正在安装 Android SDK...",
        operation=lambda builder, emit: builder.install_sdk(on_output=emit),
        success_message="SDK 安装完成",
        failure_message="SDK 安装失败",
    )


@router.post("/generate-keys")
async def generate_keys(request: Request, body: KeysJobBody) -> dict:
    dname = body.dname.strip() or None

    def op(builder: AndroidBuilder, emit: Callable[[str], None]) -> bool:
        return builder.generate_keys(dname=dname, on_output=emit)

    return await _start_sdk_job(
        request,
        kind=KIND_GENERATE_KEYS,
        action="generate_keys",
        body=body,
        message="正在生成签名...",
        operation=op,
        success_message="签名已生成",
        failure_message="签名生成失败",
    )


@router.post("/build")
async def build_android(request: Request, body: BuildJobBody) -> dict:
    """严格顺序：writeJSON → distribute → sanitize → build(install/launch=False) → list。"""
    if not body.confirm:
        raise HTTPException(status_code=400, detail="构建需 confirm=true")
    package = body.package_name.strip()
    app_name = body.app_name.strip()
    version = body.version.strip()
    if not package or not app_name or not version:
        raise HTTPException(status_code=400, detail="请填写应用名、包名和版本")

    engine = _acquire_engine()
    try:
        with CacheManager.LOCK:
            paths, owner_identity, _owner_key = _resolve_target(
                request.app.state.config,
                project_path=body.project_path,
                body_project_key=body.project_key,
            )
            sdk = body.sdk_path or request.app.state.config.renpy_sdk_path
            builder = _builder_for(sdk_path=sdk, project_root=paths.project_root)
            keystore = paths.project_root / "android.keystore"
            if not keystore.is_file():
                raise HTTPException(status_code=400, detail="未找到签名文件，请先生成签名")
            before_names = {path.name for path in builder.list_outputs()}
            dist_dir = str(builder.project_dist_dir())
            # 先规范写入目标身份，再落盘；worker 接受初始 owner 与自身新身份
            new_identity = _apply_config_fields(
                request.app.state.config, body, target=paths
            )
            ProjectStore.get().persist(request.app.state.config)
            allowed = {owner_identity, new_identity}
            snapshot = {
                "project_key": paths.project_key,
                "project_root": str(paths.project_root),
                "sdk_path": str(builder.sdk_root),
                "dist_dir": dist_dir,
                "package_name": package,
                "app_name": app_name,
                "version": version,
                "update_always": body.update_always,
                "update_icons": body.update_icons,
                "before_apk_names": sorted(before_names),
                "owner_identity": list(owner_identity),
                "allowed_identities": [list(item) for item in allowed],
            }
    except HTTPException:
        engine.release_status(Engine.Status.TESTING)
        raise
    except Exception:
        engine.release_status(Engine.Status.TESTING)
        raise

    def compute(emit: Callable[[str], None]) -> dict:
        written_files: list[str] = []
        live_builder = AndroidBuilder(snapshot["sdk_path"], snapshot["project_root"])
        try:
            emit("更新 android.json...")
            json_path = live_builder.write_android_json(
                package_name=snapshot["package_name"],
                app_name=snapshot["app_name"],
                version=snapshot["version"],
                update_always=bool(snapshot["update_always"]),
                update_icons=bool(snapshot["update_icons"]),
            )
            written_files.append(str(json_path))
            emit(f"准备分发目录: {snapshot['dist_dir']}")
            if not live_builder.run_distribute(dist_dir=snapshot["dist_dir"], on_output=emit):
                return {
                    "success": False,
                    "written": True,
                    "partial": True,
                    "written_files": written_files,
                    "message": "创建分发目录失败",
                    "open_bin": False,
                }
            sanitize_android_dist_assets(
                snapshot["project_root"],
                snapshot["dist_dir"],
                on_output=emit,
            )
            emit("开始构建 Android 包...")
            ok = live_builder.build_android(
                dist_dir=snapshot["dist_dir"],
                install=False,
                launch=False,
                on_output=emit,
            )
            if not ok:
                return {
                    "success": False,
                    "written": True,
                    "partial": True,
                    "written_files": written_files,
                    "message": "构建失败",
                    "open_bin": False,
                }
            outputs = live_builder.list_outputs()
            names = [path.name for path in outputs]
            before = set(snapshot["before_apk_names"])
            new_names = [name for name in names if name not in before]
            if names:
                emit("产物: " + ", ".join(names[:3]))
            return {
                "success": True,
                "written": True,
                "written_files": written_files,
                "message": "构建完成",
                "open_bin": True,
                "rapt_bin": str(live_builder.rapt_bin),
                "outputs": [
                    {"name": path.name, "path": str(path), "mtime": path.stat().st_mtime}
                    for path in outputs
                ],
                "output_names": names,
                "new_output_names": new_names,
                "outputs_include_history": True,
            }
        except Exception as exc:
            # SDK 异常不得抹掉已成功写入的 android.json 等副作用
            return {
                "success": False,
                "written": bool(written_files),
                "partial": bool(written_files),
                "written_files": written_files,
                "message": str(exc),
                "open_bin": False,
            }

    return await _run_job(
        request,
        engine=engine,
        kind=KIND_BUILD,
        action="build",
        project_key=snapshot["project_key"],
        owner_identity=tuple(snapshot["owner_identity"]),
        allowed_identities=[tuple(item) for item in snapshot["allowed_identities"]],
        message="正在构建...",
        compute=compute,
    )


@router.post("/make-shell")
async def make_shell(request: Request, body: ShellJobBody) -> dict:
    if not body.confirm:
        raise HTTPException(status_code=400, detail="壳制作需 confirm=true")

    engine = _acquire_engine()
    try:
        with CacheManager.LOCK:
            paths, owner_identity, _owner_key = _resolve_target(
                request.app.state.config,
                project_path=body.project_path,
                body_project_key=body.project_key,
            )
            # 全量预检必须先于任何 Config.save / 产物写入
            try:
                plan = preflight_shell_archive(
                    paths.project_root,
                    source_text=body.archive_source_dir,
                    remove_text=body.shell_remove_dirs,
                    backup=bool(body.shell_backup_enable),
                )
            except AndroidProjectToolsError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            new_identity = _apply_config_fields(
                request.app.state.config, body, target=paths
            )
            ProjectStore.get().persist(request.app.state.config)
            allowed = {owner_identity, new_identity}
            snapshot = {
                "project_key": paths.project_key,
                "project_root": str(paths.project_root),
                "source_text": body.archive_source_dir,
                "remove_text": body.shell_remove_dirs,
                "backup": bool(body.shell_backup_enable),
                "owner_identity": list(owner_identity),
                "allowed_identities": [list(item) for item in allowed],
                "plan": plan,
            }
    except HTTPException:
        engine.release_status(Engine.Status.TESTING)
        raise
    except Exception:
        engine.release_status(Engine.Status.TESTING)
        raise

    def compute(emit: Callable[[str], None]) -> dict:
        try:
            result = make_shell_archive(
                snapshot["project_root"],
                source_text=snapshot["source_text"],
                remove_text=snapshot["remove_text"],
                backup=bool(snapshot["backup"]),
                on_output=emit,
                plan=snapshot["plan"],
            )
        except AndroidProjectToolsError as exc:
            return {
                "success": False,
                "written": False,
                "message": str(exc),
                "open_bin": False,
            }
        return {
            **result,
            "written": bool(result.get("written") or result.get("success")),
            "open_bin": False,
            "action": "shell",
        }

    return await _run_job(
        request,
        engine=engine,
        kind=KIND_SHELL,
        action="shell",
        project_key=snapshot["project_key"],
        owner_identity=tuple(snapshot["owner_identity"]),
        allowed_identities=[tuple(item) for item in snapshot["allowed_identities"]],
        message="正在处理壳包...",
        compute=compute,
    )


async def _start_sdk_job(
    request: Request,
    *,
    kind: str,
    action: str,
    body: EnvJobBody,
    message: str,
    operation: Callable[[AndroidBuilder, Callable[[str], None]], bool],
    success_message: str,
    failure_message: str,
) -> dict:
    engine = _acquire_engine()
    try:
        with CacheManager.LOCK:
            paths, owner_identity, _owner_key = _resolve_target(
                request.app.state.config,
                project_path=body.project_path,
                body_project_key=body.project_key,
            )
            sdk = body.sdk_path or request.app.state.config.renpy_sdk_path
            builder = _builder_for(sdk_path=sdk, project_root=paths.project_root)
            allowed = {owner_identity}
            if body.sdk_path.strip():
                request.app.state.config.renpy_sdk_path = body.sdk_path.strip()
                ProjectStore.get().persist(request.app.state.config)
            if str(body.project_path or "").strip():
                allowed.add(_normalize_project_on_config(request.app.state.config, paths))
                ProjectStore.get().persist(request.app.state.config)
            snapshot = {
                "project_key": paths.project_key,
                "project_root": str(paths.project_root),
                "sdk_path": str(builder.sdk_root),
                "owner_identity": list(owner_identity),
                "allowed_identities": [list(item) for item in allowed],
            }
    except HTTPException:
        engine.release_status(Engine.Status.TESTING)
        raise
    except Exception:
        engine.release_status(Engine.Status.TESTING)
        raise

    def compute(emit: Callable[[str], None]) -> dict:
        live = AndroidBuilder(snapshot["sdk_path"], snapshot["project_root"])
        ok = bool(operation(live, emit))
        return {
            "success": ok,
            "written": False,
            "message": success_message if ok else failure_message,
            "open_bin": False,
        }

    return await _run_job(
        request,
        engine=engine,
        kind=kind,
        action=action,
        project_key=snapshot["project_key"],
        owner_identity=tuple(snapshot["owner_identity"]),
        allowed_identities=[tuple(item) for item in snapshot["allowed_identities"]],
        message=message,
        compute=compute,
    )


async def _run_job(
    request: Request,
    *,
    engine: Engine,
    kind: str,
    action: str,
    project_key: str,
    owner_identity: tuple[str, ...],
    message: str,
    compute: Callable[[Callable[[str], None]], dict],
    allowed_identities: list[tuple[str, ...]] | None = None,
) -> dict:
    manager = request.app.state.jobs
    try:
        job = manager.create(kind, total=1, cooperative_cancel=True)
    except Exception:
        engine.release_status(Engine.Status.TESTING)
        raise

    allowed = set(allowed_identities or [owner_identity])
    allowed.add(owner_identity)
    job.result = {
        "project_key": project_key,
        "action": action,
        "message": message,
        "written": False,
        "worker_active": True,
        "cancellable": _CANCELLABLE,
        "open_bin": False,
        "owner_identity": list(owner_identity),
        "logs": [],
    }
    loop = asyncio.get_running_loop()

    def owner_still() -> bool:
        """允许初始 owner，或本任务已成功持久化的目标身份；拒绝外部切项目。"""
        with CacheManager.LOCK:
            live = _project_identity(request.app.state.config)
        return live in allowed

    def publish(line: str) -> None:
        if not isinstance(job.result, dict) or not job.result.get("worker_active"):
            return
        logs = list(job.result.get("logs") or [])
        logs.append(line)
        job.result["logs"] = logs[-200:]
        job.result["message"] = line
        manager.progress(job.id, done=0, total=1)

    def emit(line: str) -> None:
        if line:
            loop.call_soon_threadsafe(lambda: publish(line))

    def work() -> dict:
        if not owner_still():
            raise RuntimeError("项目已切换，未继续执行")
        return compute(emit)

    async def worker(_: Job) -> dict:
        try:
            future = loop.run_in_executor(None, work)
            try:
                result = await asyncio.shield(future)
            except asyncio.CancelledError:
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await asyncio.shield(future)
                raise
            if isinstance(job.result, dict):
                job.result.update(result)
                job.result["message"] = result.get("message") or job.result.get("message")
            if not result.get("success", False):
                # 业务失败：保留 written/partial/written_files，再标 failed
                raise RuntimeError(result.get("message") or "任务失败")
            manager.progress(job.id, done=1, total=1)
            return job.result
        except asyncio.CancelledError:
            if isinstance(job.result, dict):
                job.result["message"] = "任务已取消（外部进程可能仍在收尾）"
            raise
        except Exception as exc:
            if isinstance(job.result, dict):
                job.result["message"] = str(exc)
                job.result.setdefault("success", False)
                # 不覆盖已由 compute 写入的 written/partial/written_files
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
