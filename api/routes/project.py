"""项目路径设置。

写项目路径会触发 ProjectStore 发 PROJECT_CHANGED 事件，
由 api/events.py 的桥转成 WS 消息推给渲染端——这条链路正好用来验证
「业务逻辑 → 事件总线 → WebSocket」全链路是否通。
"""

from __future__ import annotations

import contextlib
import copy
import dataclasses
import os
import shutil
import tempfile
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from api.schemas import ProjectInfo, ProjectPathRequest, ProjectResolveRequest
from base.BaseLanguage import BaseLanguage
from base.Version import Version
from module.Cache.CacheDB import CacheDB
from module.Cache.CacheItem import CacheItem
from module.Cache.CacheManager import CacheManager
from module.Cache.CacheProject import CacheProject
from module.Config import Config
from module.Engine.Engine import Engine
from module.Engine.Translator.ProjectAssetsRepository import ProjectAssetsRepository
from module.Localizer.Localizer import Localizer
from module.Project.ProjectFile import ProjectFile, ProjectFileError, ProjectFileInfo
from module.Project.ProjectStore import (
    ProjectStore,
    ensure_output_folder,
    resolve_target_language,
)
from module.Renpy.ProjectPaths import (
    RenpyProjectPaths,
    looks_like_renpy_path,
    resolve_translation_output,
    translation_output_candidates,
)

router = APIRouter(prefix = "/api/project", tags = ["project"])


def _info(request: Request) -> ProjectInfo:
    config = request.app.state.config
    return ProjectInfo(
        renpy_project_path = getattr(config, "renpy_project_path", ""),
        renpy_game_folder = getattr(config, "renpy_game_folder", ""),
        renpy_tl_folder = getattr(config, "renpy_tl_folder", ""),
        theme = getattr(config, "theme", ""),
        app_language = getattr(config, "app_language", ""),
    )


@router.get("", response_model = ProjectInfo)
def read_project(request: Request) -> ProjectInfo:
    return _info(request)


@router.post("/path", response_model = ProjectInfo)
def set_project_path(request: Request, body: ProjectPathRequest) -> ProjectInfo:
    config = request.app.state.config

    if not body.project_path.strip():
        raise HTTPException(status_code = 400, detail = "项目路径不能为空")

    store = ProjectStore.get()
    store.set_project_path(config, body.project_path.strip())
    if body.game_folder:
        store.set_game_folder(config, body.game_folder)

    # persist() 才会发PROJECT_CHANGED：set_project_path 只改内存，
    # 单独调用它事件不会触发，渲染端就收不到路径变更。
    store.persist(config)

    return _info(request)


@router.post("/resolve", response_model = ProjectInfo)
def resolve_project(request: Request, body: ProjectResolveRequest) -> ProjectInfo:
    """按给定目录解析 Ren'Py 项目身份。

    与 frontend/Project/ProjectPage.py:135-161 ``_sync_renpy_paths_from_selection``
    等价（只是去掉了 Qt）：**只有路径本身带 Ren'Py 项目结构时才同步项目身份**。
    用户选的翻译输入目录通常是自己建的任意文件夹，把它当成项目根会让
    ``renpy_project_path`` / ``renpy_tl_folder`` 指向一个并不存在的
    ``game/tl/<lang>``，项目设置反而变错。

    所以不含项目结构时返回 409，调用方应忽略并只保留 input_folder。

    绑定成功时补齐两个 Qt5 副作用（``_auto_fill_by_renpy_config``）：
    按真实 ``tl/<lang>`` 目录推断 ``target_language``（推断不出则保留原值），
    以及按需创建输出目录（失败只忽略，不影响响应）。
    """
    config = request.app.state.config
    raw = str(body.path or "").strip()
    if not raw:
        raise HTTPException(status_code = 400, detail = "路径不能为空")

    if not looks_like_renpy_path(raw):
        raise HTTPException(
            status_code = 409,
            detail = "该目录不含 Ren'Py 项目结构（未找到 game/ 或 *.rpy），仅作为输入目录保留",
        )

    paths = RenpyProjectPaths.from_path(raw)
    if paths is None:
        raise HTTPException(status_code = 409, detail = "无法从该目录推导 Ren'Py 项目结构")

    # apply_resolved 内部会走 apply_to_config 规范五字段，再 persist 发 PROJECT_CHANGED；
    # mutate 在持久化前按真实 tl/<lang> 目录推断目标语言，与 Qt5 语义一致。
    ProjectStore.get().apply_resolved(
        config,
        paths,
        mutate = lambda current: resolve_target_language(current, paths),
    )
    # 输出目录必须存在，否则第一个任务会因为目录不存在直接失败。
    ensure_output_folder(config)
    return _info(request)


# ---------- .rbox 工程文件 ----------
# .rbox 是单文件工程：绑定后直接作为工作缓存被读写（回滚日志模式，无 -wal/-shm
# 旁路文件），随时可拷贝分享；「保存/导出」另存的是快照副本。Ren'Py 源码保持外部
# 绑定，译文 .rpy 产物照旧写输出目录。bind=False 时退回旧语义（内容复制进
# <output>/cache/，快照与工作缓存分离）。
# 导入只替换当前配置解析出的输出缓存和白名单设置，从不改写项目/输入/输出路径；
# 规范输出目录（工作台资产所在）与之不同时，只同步其资产分区，两处缓存一起备份/回滚。


class ProjectFileRequest(BaseModel):
    path: str
    # 绑定模式（默认）：该 .rbox 直接作为工作缓存使用，不再物化目录缓存副本。
    bind: bool = True


class LegacyCacheRequest(BaseModel):
    folder: str


class LegacyCacheExportRequest(BaseModel):
    folder: str
    path: str


@dataclasses.dataclass(frozen = True)
class _CacheBackup:
    folder: str                                                                 # 空串表示导入前没有缓存文件
    files: tuple[str, ...]


_LANGUAGES = frozenset(language.value for language in BaseLanguage.Enum)


def _is_bool(value: Any) -> bool:
    return isinstance(value, bool)


def _is_text(value: Any) -> bool:
    return isinstance(value, str)


def _is_text_map(value: Any) -> bool:
    return isinstance(value, dict) and all(
        isinstance(key, str) and isinstance(item, str) for key, item in value.items()
    )


def _is_rule_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(entry, (str, dict)) for entry in value)


def _is_choice(allowed: frozenset[str]):
    return lambda value: isinstance(value, str) and value in allowed


# 随工程文件迁移的项目级翻译规则；路径、平台/凭据、界面、并发等全局设置一律不进入。
PROJECT_FILE_SETTINGS = {
    "source_language": _is_choice(_LANGUAGES),
    "target_language": _is_choice(_LANGUAGES),
    "traditional_chinese_enable": _is_bool,
    "text_preserve_enable": _is_bool,
    "text_preserve_data": _is_rule_list,
    "pre_translation_replacement_enable": _is_bool,
    "pre_translation_replacement_data": _is_rule_list,
    "post_translation_replacement_enable": _is_bool,
    "post_translation_replacement_data": _is_rule_list,
    "mixed_language_cleanup_enable": _is_bool,
    "mixed_language_replacements": _is_text_map,
    "mixed_language_sentence_overrides": _is_text_map,
    "honorific_placeholder_bridge_enable": _is_bool,
    "honorific_placeholder_titles": _is_rule_list,
    "translation_prompt_mode": _is_choice(Config.PROMPT_MODES),
    "translation_custom_prompts": _is_text_map,
    "translation_custom_prompt_enabled_languages": lambda value: value is None or (
        isinstance(value, list) and all(isinstance(entry, str) for entry in value)
    ),
    "translation_style_id": _is_choice(Config.STYLE_IDS),
    "translation_custom_style": _is_text,
}

_CACHE_FILES = (
    CacheManager.CACHE_DB_NAME,
    f"{CacheManager.CACHE_DB_NAME}-wal",
    f"{CacheManager.CACHE_DB_NAME}-journal",
    "items.json",
    "project.json",
    CacheManager.RESET_JOURNAL_NAME,
)
# -shm 只是 WAL 索引，SQLite 打开时会按 -wal 重建；恢复时删除，不备份。
_CACHE_SCRATCH_FILES = (f"{CacheManager.CACHE_DB_NAME}-shm",)


def _path_key(path: Any) -> str:
    return os.path.normcase(os.path.abspath(str(path)))


def _project_file_error(exc: ProjectFileError) -> HTTPException:
    status = {
        ProjectFileError.NOT_FOUND: 404,
        ProjectFileError.WRITE_FAILED: 500,
    }.get(exc.code, 400)
    return HTTPException(
        status_code = status,
        detail = Localizer.get().project_file_api_invalid.format(code = exc.code, error = exc),
    )


class _EngineReservation:
    """IDLE→TESTING 占用引擎，任何退出路径都只释放自己持有的 TESTING。"""

    def __enter__(self) -> Engine:
        self.engine = Engine.get()
        if not self.engine.try_set_status(Engine.Status.IDLE, Engine.Status.TESTING):
            raise HTTPException(status_code = 409, detail = Localizer.get().project_file_api_busy)
        return self.engine

    def __exit__(self, *_exc) -> None:
        self.engine.release_status(Engine.Status.TESTING)


def _target_output(config: Any) -> str:
    output = resolve_translation_output(config)
    if output is None:
        raise HTTPException(status_code = 400, detail = Localizer.get().project_file_api_no_output)
    return str(output)


def _project_root(config: Any) -> str:
    paths = RenpyProjectPaths.from_config(config)
    if paths is not None:
        return str(paths.project_root)
    return str(getattr(config, "renpy_project_path", "") or "")


def _describe(config: Any, info: ProjectFileInfo, output: str) -> dict[str, Any]:
    current_root = _project_root(config)
    return {
        "info": dataclasses.asdict(info),
        "output_folder": output,
        "current_project_root": current_root,
        "project_root_matches": bool(
            current_root and info.project_root and _path_key(current_root) == _path_key(info.project_root)
        ),
    }


def _runtime_cache(output: str) -> CacheManager | None:
    """返回仍持有该输出目录内存缓存的翻译器 CacheManager。"""
    translator = getattr(Engine.get(), "translator", None)
    manager = getattr(translator, "cache_manager", None)
    if manager is None:
        return None
    key = _path_key(output)
    owners = (
        getattr(translator, "_active_cache_output_folder", ""),
        getattr(translator, "_last_runtime_output_folder", ""),
        manager.require_path if manager.require_flag else "",
    )
    if any(str(owner or "").strip() and _path_key(owner) == key for owner in owners):
        return manager
    return None


def _flush_runtime_cache(output: str) -> CacheManager | None:
    """先落盘翻译器待保存结果，导出/备份才拿得到最新译文。调用方须持有 CacheManager.LOCK。"""
    runtime = _runtime_cache(output)
    if (
        runtime is not None
        and runtime.require_flag
        and _path_key(runtime.require_path or output) == _path_key(output)
    ):
        try:
            saved = runtime.save_to_file(runtime.get_project(), runtime.get_items(), output, strict = True)
            if saved is not True:
                raise RuntimeError("未确认缓存保存成功")
        except Exception as exc:
            raise HTTPException(
                status_code = 500,
                detail = Localizer.get().project_file_api_pending_save.format(error = exc),
            ) from exc
    return runtime


def _new_cache_manager(config: Any) -> CacheManager:
    manager = CacheManager(service = False)
    manager.cache_use_sqlite = bool(getattr(config, "cache_use_sqlite", True))
    return manager


def _export_settings(config: Any) -> dict[str, Any]:
    settings: dict[str, Any] = {}
    for key, valid in PROJECT_FILE_SETTINGS.items():
        value = getattr(config, key, None)
        value = value.value if isinstance(value, BaseLanguage.Enum) else copy.deepcopy(value)
        if valid(value):
            settings[key] = value
    return settings


# 旧版输出目录可能在当前绑定的 Ren'Py 项目之外。只认调用方点名的目录，
# 不放宽项目路径校验，也不改走 resolve_translation_output。
_LEGACY_SQLITE_FILES = (
    CacheManager.CACHE_DB_NAME,
    f"{CacheManager.CACHE_DB_NAME}-wal",
    f"{CacheManager.CACHE_DB_NAME}-shm",
    f"{CacheManager.CACHE_DB_NAME}-journal",
)
_LEGACY_JSON_FILES = (
    "items.json",
    "project.json",
    CacheManager.RESET_JOURNAL_NAME,
)


@dataclasses.dataclass(frozen = True)
class _LegacySource:
    output_folder: str
    cache_folder: str
    cache_format: str
    project: CacheProject
    items: list[CacheItem]


def _legacy_format(folder: str) -> str | None:
    """该目录直接存放的缓存形态；SQLite 优先，残缺文件也要报错而不是静默换格式。"""
    if os.path.isfile(os.path.join(folder, CacheManager.CACHE_DB_NAME)):
        return "sqlite"
    if any(os.path.isfile(os.path.join(folder, name)) for name in _LEGACY_SQLITE_FILES):
        return "sqlite"
    if any(os.path.isfile(os.path.join(folder, name)) for name in _LEGACY_JSON_FILES):
        return "json"
    return None


def _locate_legacy_cache(folder: str) -> tuple[str, str, str]:
    raw = str(folder or "").strip()
    if raw == "":
        raise HTTPException(status_code = 400, detail = Localizer.get().project_file_api_legacy_folder_invalid)
    if not os.path.exists(raw):
        raise HTTPException(status_code = 404, detail = Localizer.get().project_file_api_legacy_no_cache)
    if not os.path.isdir(raw):
        raise HTTPException(status_code = 400, detail = Localizer.get().project_file_api_legacy_folder_invalid)
    selected = os.path.abspath(raw)
    nested = os.path.join(selected, "cache")
    direct = _legacy_format(selected)
    child = _legacy_format(nested) if os.path.isdir(nested) else None
    if direct is not None and child is not None and os.path.basename(selected).casefold() == "cache":
        child = None
    if child is not None and direct is None:
        return selected, nested, child
    if direct is not None and child is None:
        return os.path.dirname(selected), selected, direct
    if child is not None:
        return selected, nested, child
    raise HTTPException(status_code = 404, detail = Localizer.get().project_file_api_legacy_no_cache)


def _stage_legacy_cache(cache_folder: str, cache_format: str) -> str:
    """把源缓存复制到临时目录再读，这样严格加载和 JSON 日志恢复都不会改源文件。"""
    names = _LEGACY_SQLITE_FILES if cache_format == "sqlite" else _LEGACY_JSON_FILES
    staging = tempfile.mkdtemp(prefix = "rbox-legacy-")
    try:
        destination = os.path.join(staging, "cache")
        os.makedirs(destination)
        copied = False
        for name in names:
            source = os.path.join(cache_folder, name)
            if not os.path.isfile(source):
                continue
            shutil.copy2(source, os.path.join(destination, name))
            copied = True
        if not copied:
            raise HTTPException(status_code = 404, detail = Localizer.get().project_file_api_legacy_no_cache)
        return staging
    except HTTPException:
        shutil.rmtree(staging, ignore_errors = True)
        raise
    except Exception as exc:
        shutil.rmtree(staging, ignore_errors = True)
        raise HTTPException(
            status_code = 400,
            detail = Localizer.get().project_file_api_legacy_cache_invalid.format(error = exc),
        ) from exc


def _read_legacy_source(config: Any, folder: str) -> _LegacySource:
    output_folder, cache_folder, cache_format = _locate_legacy_cache(folder)
    staging = _stage_legacy_cache(cache_folder, cache_format)
    try:
        manager = _new_cache_manager(config)
        try:
            manager.load_from_file(staging, strict = True)
        except Exception as exc:
            raise HTTPException(
                status_code = 400,
                detail = Localizer.get().project_file_api_legacy_cache_invalid.format(error = exc),
            ) from exc
        return _LegacySource(
            output_folder = output_folder,
            cache_folder = cache_folder,
            cache_format = cache_format,
            project = manager.get_project(),
            items = list(manager.get_items()),
        )
    finally:
        shutil.rmtree(staging, ignore_errors = True)


def _require_bound_game(config: Any) -> str:
    paths = RenpyProjectPaths.from_config(config)
    root = str(paths.project_root) if paths is not None else ""
    if paths is None or root.strip() == "" or not os.path.isdir(root):
        raise HTTPException(status_code = 400, detail = Localizer.get().project_file_api_legacy_unbound)
    return root


def _path_keys(path: str) -> tuple[str, str]:
    text = str(path)
    return _path_key(text), os.path.normcase(os.path.realpath(text))


def _is_within_key(path: str, root: str) -> bool:
    if path == root:
        return True
    try:
        return os.path.commonpath((path, root)) == root
    except ValueError:
        return False


def _is_within(path: str, root: str) -> bool:
    return any(
        _is_within_key(candidate, base)
        for candidate in _path_keys(path)
        for base in _path_keys(root)
    )


def _live_cache_dirs(config: Any) -> list[str]:
    """当前仍可能被翻译或工作台使用的缓存目录，导出不能往这里覆盖文件。"""
    folders: list[str] = []
    configured = str(getattr(config, "output_folder", "") or "").strip()
    if configured:
        folders.append(configured)
    # 路径枚举不打开数据库。resolve_translation_output 会探测 WAL 库，
    # 即使 mode=ro 也可能在当前缓存目录创建 -wal/-shm。
    folders.extend(str(path) for path in translation_output_candidates(config))
    paths = RenpyProjectPaths.from_config(config)
    if paths is not None:
        folders.append(str(paths.translation_output_dir))
    translator = getattr(Engine.get(), "translator", None)
    manager = getattr(translator, "cache_manager", None)
    if manager is not None and getattr(manager, "require_flag", False):
        pending = str(getattr(manager, "require_path", "") or "").strip()
        if pending:
            folders.append(pending)
    for name in ("_active_cache_output_folder", "_last_runtime_output_folder"):
        active = str(getattr(translator, name, "") or "").strip()
        if active:
            folders.append(active)
    cache_dirs: list[str] = []
    seen: set[str] = set()
    for folder in folders:
        cache_dir = os.path.join(folder, "cache")
        key = _path_key(cache_dir)
        if key in seen:
            continue
        seen.add(key)
        cache_dirs.append(cache_dir)
    return cache_dirs


def _legacy_destination_forbidden(path: str, source_output: str, source_cache: str, config: Any) -> bool:
    target = str(path or "").strip()
    if target == "":
        return False
    if any(_is_within(target, cache_dir) for cache_dir in (source_cache, *_live_cache_dirs(config))):
        return True
    if os.path.lexists(target) and _is_within(target, source_output):
        return True
    return os.path.lexists(target) and os.path.splitext(target)[1].lower() != ProjectFile.SUFFIX


def _import_settings(settings: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """校验白名单设置；未知键（含路径字段）只忽略，白名单键类型错误则整体拒绝。"""
    applied: dict[str, Any] = {}
    ignored: list[str] = []
    for key, value in settings.items():
        valid = PROJECT_FILE_SETTINGS.get(key)
        if valid is None:
            ignored.append(key)
            continue
        if not valid(value):
            raise HTTPException(
                status_code = 400,
                detail = Localizer.get().project_file_api_invalid_setting.format(key = key),
            )
        if key in ("source_language", "target_language"):
            value = BaseLanguage.Enum(value)
        applied[key] = copy.deepcopy(value)
    return applied, sorted(ignored)


def _backup_cache(output: str) -> _CacheBackup:
    cache_dir = os.path.join(output, "cache")
    files = tuple(name for name in _CACHE_FILES if os.path.isfile(os.path.join(cache_dir, name)))
    if not files:
        return _CacheBackup("", ())
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    # 放在 cache/ 内：各类源码/输出扫描都会跳过 cache 目录，CacheManager 只认固定文件名。
    folder = os.path.join(cache_dir, "backup", f"rbox-import-{stamp}-{uuid.uuid4().hex[:8]}")
    os.makedirs(folder)
    try:
        for name in files:
            shutil.copy2(os.path.join(cache_dir, name), os.path.join(folder, name))
    except Exception:
        shutil.rmtree(folder, ignore_errors = True)
        raise
    return _CacheBackup(folder, files)


@contextlib.contextmanager
def _legacy_store_scope():
    """临时忽略工程文件绑定：安装/恢复目录缓存时必须写 ``<输出>/cache``。

    绑定模式下缓存路径解析会指向 .rbox；``bind=false`` 导入或同步资产分区时，
    写入目标必须是目录缓存，否则会把内容写进正在绑定的工程文件。
    期间冻结绑定镜像：``CacheManager`` 构造时的 ``Config().load()`` 不得把它
    改回已持久化的旧绑定。
    """
    saved = Config.BOUND_PROJECT_FILE
    Config.BOUND_PROJECT_FILE = ("", "")
    Config.BOUND_PROJECT_FILE_FROZEN = True
    try:
        yield
    finally:
        Config.BOUND_PROJECT_FILE_FROZEN = False
        Config.BOUND_PROJECT_FILE = saved


def _retire_cache_files(output: str, backup: _CacheBackup) -> None:
    """绑定工程文件后收走旧目录缓存文件（备份已先行复制）。

    不留旧 cache.db 的原因：它会成为绑定失效时的静默回退，把过期条目
    当作进度继续读。备份目录里的副本仍然可以随时手动还原。
    """
    cache_dir = os.path.join(output, "cache")
    for name in (*_CACHE_FILES, *_CACHE_SCRATCH_FILES):
        path = os.path.join(cache_dir, name)
        if os.path.isfile(path):
            os.remove(path)


def _restore_cache(output: str, backup: _CacheBackup) -> None:
    cache_dir = os.path.join(output, "cache")
    for name in backup.files:
        target = os.path.join(cache_dir, name)
        temp = f"{target}.restore.tmp"
        shutil.copy2(os.path.join(backup.folder, name), temp)
        os.replace(temp, target)
    for name in (*_CACHE_FILES, *_CACHE_SCRATCH_FILES):
        if name not in backup.files:
            path = os.path.join(cache_dir, name)
            if os.path.isfile(path):
                os.remove(path)


def _install_cache(
    config: Any,
    output: str,
    project: CacheProject,
    items: list[CacheItem],
    expected_digest: str,
) -> None:
    """按 CacheManager 现有后端选择写入（SQLite 单事务 / JSON 写前日志），再严格读回校验。"""
    manager = _new_cache_manager(config)
    if manager.save_to_file(project, items, output, strict = True) is not True:
        raise RuntimeError("未确认缓存保存成功")
    check = _new_cache_manager(config)
    check.load_from_file(output, strict = True)
    if CacheDB.items_digest(check.get_items()) != expected_digest:
        raise RuntimeError("写入后的缓存条目与工程文件不一致")


def _runtime_sections_restorer(runtime: CacheManager | None):
    """记下运行态项目的资产/候选分区，回滚时只还原这两个分区，不替换条目。"""
    if runtime is None:
        return None
    live = runtime.get_project()
    assets = live.get_project_assets()
    candidates = live.get_analysis_candidates()

    def restore() -> None:
        with live.lock:
            live.extras["project_assets"] = copy.deepcopy(assets)
            live.extras["analysis_candidates"] = copy.deepcopy(candidates)

    return restore


def _rollback_failed(
    targets: list[tuple[str, _CacheBackup]],
    reason: str,
    exc: Exception,
    restore_runtime = None,
) -> HTTPException:
    folders = [backup.folder for _, backup in targets if backup.folder]
    retained = (
        Localizer.get().project_file_api_backups_retained.format(
            paths = Localizer.get().project_file_api_path_separator.join(folders)
        )
        if folders
        else ""
    )
    errors: list[str] = []
    for output, backup in targets:
        try:
            _restore_cache(output, backup)
        except Exception as restore_exc:
            errors.append(
                Localizer.get().project_file_api_restore_error.format(
                    path = output,
                    error = restore_exc,
                )
            )
    if restore_runtime is not None:
        restore_runtime()
    if errors:
        return HTTPException(
            status_code = 500,
            detail = Localizer.get().project_file_api_cache_restore_failed.format(
                reason = reason,
                backups = retained,
                error = exc,
                restore_errors = "；".join(errors),
            ),
        )
    return HTTPException(
        status_code = 500,
        detail = Localizer.get().project_file_api_cache_restored.format(
            reason = reason,
            backups = retained,
            error = exc,
        ),
    )


@router.post("/file/inspect")
def inspect_project_file(request: Request, body: ProjectFileRequest) -> dict[str, Any]:
    """只读快速校验 .rbox 元数据，不解析条目、不占用引擎、不触碰缓存。"""
    try:
        info = ProjectFile.inspect(body.path)
    except ProjectFileError as exc:
        raise _project_file_error(exc) from exc
    config = request.app.state.config
    output = resolve_translation_output(config)
    return _describe(config, info, str(output) if output is not None else "")


@router.post("/file/export")
def export_project_file(request: Request, body: ProjectFileRequest) -> dict[str, Any]:
    """把当前输出缓存（SQLite 或旧版 JSON）与白名单项目设置导出为 .rbox。"""
    config = request.app.state.config
    with _EngineReservation():
        output = _target_output(config)
        with CacheManager.LOCK:
            _flush_runtime_cache(output)
            cache_dir = os.path.join(output, "cache")
            store_db = CacheManager.db_path_for(output)
            if not (
                os.path.isfile(store_db)
                or any(
                    os.path.isfile(os.path.join(cache_dir, name))
                    for name in ("items.json", "project.json")
                )
            ):
                raise HTTPException(
                    status_code = 404,
                    detail = Localizer.get().project_file_api_no_cache,
                )
            manager = _new_cache_manager(config)
            try:
                manager.load_from_file(output, strict = True)
            except Exception as exc:
                raise HTTPException(
                    status_code = 500,
                    detail = Localizer.get().project_file_api_cache_read_failed.format(error = exc),
                ) from exc
            # 旧版本资产可能仍只在全局配置里；只补进快照副本，不回写当前输出缓存。
            try:
                snapshot_project = ProjectAssetsRepository.from_config(config).prepare_project_snapshot(
                    manager.get_project(),
                    config,
                )
            except Exception as exc:
                raise HTTPException(
                    status_code = 500,
                    detail = Localizer.get().project_file_api_assets_read_failed.format(error = exc),
                ) from exc
            settings = _export_settings(config)
            try:
                info = ProjectFile.export(
                    body.path,
                    snapshot_project,
                    manager.get_items(),
                    project_root = _project_root(config),
                    settings = settings,
                    app_version = Version.CURRENT,
                )
            except ProjectFileError as exc:
                raise _project_file_error(exc) from exc
    result = _describe(config, info, output)
    result["settings"] = sorted(settings)
    return result


@router.post("/file/legacy/inspect")
def inspect_legacy_cache(request: Request, body: LegacyCacheRequest) -> dict[str, Any]:
    """只读校验调用方指定的旧输出目录或 cache 子目录，不迁移、不改源缓存。"""
    config = request.app.state.config
    with _EngineReservation():
        with CacheManager.LOCK:
            source = _read_legacy_source(config, body.folder)
    return {
        "output_folder": source.output_folder,
        "cache_folder": source.cache_folder,
        "cache_format": source.cache_format,
        "item_count": len(source.items),
        "current_project_root": _project_root(config),
        "settings": sorted(_export_settings(config)),
    }


@router.post("/file/legacy/export")
def export_legacy_cache(request: Request, body: LegacyCacheExportRequest) -> dict[str, Any]:
    """把指定旧缓存导出为 .rbox：项目根和白名单设置取当前绑定，不读取旧配置。"""
    config = request.app.state.config
    with _EngineReservation():
        project_root = _require_bound_game(config)
        with CacheManager.LOCK:
            output_folder, cache_folder, _cache_format = _locate_legacy_cache(body.folder)
            if _legacy_destination_forbidden(body.path, output_folder, cache_folder, config):
                raise HTTPException(
                    status_code = 400,
                    detail = Localizer.get().project_file_api_legacy_destination_forbidden,
                )
            source = _read_legacy_source(config, body.folder)
            try:
                snapshot_project = ProjectAssetsRepository.from_config(config).prepare_project_snapshot(
                    source.project,
                    config,
                )
            except Exception as exc:
                raise HTTPException(
                    status_code = 500,
                    detail = Localizer.get().project_file_api_assets_read_failed.format(error = exc),
                ) from exc
            settings = _export_settings(config)
            try:
                info = ProjectFile.export(
                    body.path,
                    snapshot_project,
                    source.items,
                    project_root = project_root,
                    settings = settings,
                    app_version = Version.CURRENT,
                )
            except ProjectFileError as exc:
                raise _project_file_error(exc) from exc
    current_outputs = translation_output_candidates(config)
    current_output = str(current_outputs[0]) if current_outputs else ""
    result = _describe(config, info, current_output)
    result["settings"] = sorted(settings)
    result["source_output_folder"] = source.output_folder
    return result


def _binding_payload(
    config: Any,
    *,
    bound: str = "",
    output: str = "",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    bound_path = bound if bound != "" else str(getattr(config, "project_file_path", "") or "").strip()
    output_folder = output if output != "" else str(getattr(config, "project_file_output", "") or "").strip()
    exists = bound_path != "" and os.path.isfile(bound_path)
    payload: dict[str, Any] = {
        "bound": bound_path != "",
        "path": bound_path,
        "output_folder": output_folder,
        "exists": exists,
        "size": 0,
        "item_count": 0,
        "updated_at": "",
        "detail": "",
    }
    if bound_path != "" and exists:
        payload["size"] = os.path.getsize(bound_path)
        try:
            info = ProjectFile.inspect(bound_path)
            payload["item_count"] = int(info.item_count or 0)
            payload["updated_at"] = str(info.updated_at or "")
        except Exception as exc:  # noqa: BLE001
            payload["detail"] = Localizer.get().project_file_api_bound_read_failed.format(error = exc)
    elif bound_path != "":
        payload["detail"] = Localizer.get().project_file_api_bound_missing.format(path = bound_path)
    if extra:
        payload.update(extra)
    return payload


@router.get("/file/binding")
def read_project_file_binding(request: Request) -> dict[str, Any]:
    """当前单文件工程绑定状态：哪个 .rbox 在工作、还在不在原地、是否有同步风险。

    只读：不解条目、不占用引擎、不改任何缓存。
    """
    return _binding_payload(request.app.state.config)


@router.post("/file/unbind")
def unbind_project_file(request: Request) -> dict[str, Any]:
    """解除绑定：把 .rbox 里的进度落回 ``<输出>/cache``，工程文件留作只读快照。

    为什么不顺便删掉 .rbox：它是唯一可分享/可回滚的完整副本，删了就没有退路。
    """
    config = request.app.state.config
    bound = str(getattr(config, "project_file_path", "") or "").strip()
    if bound == "":
        raise HTTPException(
            status_code = 404,
            detail = Localizer.get().project_file_api_no_binding,
        )
    with _EngineReservation():
        output = _target_output(config)
        with CacheManager.LOCK:
            manager = _new_cache_manager(config)
            try:
                manager.load_from_file(output, strict = True)
            except Exception as exc:
                raise HTTPException(
                    status_code = 500,
                    detail = Localizer.get().project_file_api_cache_read_failed.format(error = exc),
                ) from exc
            project = manager.get_project()
            items = manager.get_items()
            try:
                # 写目录缓存必须忽略绑定：否则内容又写回 .rbox。
                with _legacy_store_scope():
                    saved = CacheManager(service = False).save_to_file(
                        project,
                        items,
                        output,
                        strict = True,
                    )
                if saved is not True:
                    raise RuntimeError("目录缓存写入未返回成功")
            except Exception as exc:
                raise HTTPException(
                    status_code = 500,
                    detail = Localizer.get().project_file_api_unbind_failed.format(error = exc),
                ) from exc
            config.project_file_path = ""
            config.project_file_output = ""
            try:
                config.save(strict = True)
            except Exception as exc:
                raise HTTPException(
                    status_code = 500,
                    detail = Localizer.get().project_file_api_settings_save_failed.format(error = exc),
                ) from exc

    result = _binding_payload(config, bound = "", output = output)
    result["snapshot"] = bound
    result["item_count"] = len(items)
    return result


@router.post("/file/import")
def import_project_file(request: Request, body: ProjectFileRequest) -> dict[str, Any]:
    """完整校验后把 .rbox 设为工作缓存（默认绑定）或安装目录缓存，失败回滚。

    绑定模式（单文件工程）：``project_file_path`` 指向该 .rbox，翻译缓存
    直接读写它，不再物化 ``<输出>/cache/cache.db`` 副本；旧目录缓存先备份
    再收走。``bind=False`` 保持旧语义（内容复制进目录缓存）。
    """
    config = request.app.state.config
    with _EngineReservation():
        try:
            snapshot = ProjectFile.load(body.path)
        except ProjectFileError as exc:
            raise _project_file_error(exc) from exc
        applied, ignored = _import_settings(snapshot.settings)
        output = _target_output(config)
        # 工作台资产固定读 Ren'Py 规范输出目录；它与当前输出不同时须同步资产分区，否则工作台仍读旧资料。
        assets_repository = ProjectAssetsRepository.from_config(config)
        assets_output = assets_repository.output_folder
        sync_assets = bool(assets_output) and _path_key(assets_output) != _path_key(output)
        expected_digest = CacheDB.items_digest(snapshot.items)
        bind = bool(getattr(body, "bind", True))
        staged = copy.deepcopy(config)
        for key, value in applied.items():
            setattr(staged, key, value)
        if bind:
            staged.project_file_path = os.path.abspath(body.path)
            staged.project_file_output = output
        else:
            # 显式关闭绑定：先解除旧绑定，安装才不会继续写进 .rbox。
            staged.project_file_path = ""
            staged.project_file_output = ""

        with CacheManager.LOCK:
            runtime = _flush_runtime_cache(output)
            assets_runtime = _flush_runtime_cache(assets_output) if sync_assets else None
            try:
                backup = _backup_cache(output)
            except Exception as exc:
                raise HTTPException(
                    status_code = 500,
                    detail = Localizer.get().project_file_api_cache_backup_failed.format(error = exc),
                ) from exc
            assets_backup = _CacheBackup("", ())
            if sync_assets:
                try:
                    assets_backup = _backup_cache(assets_output)
                except Exception as exc:
                    if backup.folder:
                        shutil.rmtree(backup.folder, ignore_errors = True)
                    raise HTTPException(
                        status_code = 500,
                        detail = Localizer.get().project_file_api_assets_backup_failed.format(error = exc),
                    ) from exc
            try:
                if bind:
                    _retire_cache_files(output, backup)
                else:
                    with _legacy_store_scope():
                        _install_cache(config, output, snapshot.project, snapshot.items, expected_digest)
            except Exception as exc:
                raise _rollback_failed(
                    [(output, backup)],
                    Localizer.get().project_file_api_cache_install_failed,
                    exc,
                ) from exc
            restore_targets = [(output, backup)]
            restore_runtime = None
            if sync_assets:
                restore_targets.append((assets_output, assets_backup))
                restore_runtime = _runtime_sections_restorer(assets_runtime)
                try:
                    # 资产分区恒写目录缓存（资产一定读规范输出目录，与绑定的运行输出无关）。
                    with _legacy_store_scope():
                        assets_repository.replace_asset_sections(
                            snapshot.project.get_project_assets(),
                            snapshot.project.get_analysis_candidates(),
                        )
                except Exception as exc:
                    raise _rollback_failed(
                        restore_targets,
                        Localizer.get().project_file_api_assets_sync_failed,
                        exc,
                        restore_runtime,
                    ) from exc
            try:
                staged.save(strict = True)
            except Exception as exc:
                raise _rollback_failed(
                        restore_targets,
                        Localizer.get().project_file_api_settings_save_failed,
                        exc,
                        restore_runtime,
                    ) from exc

            for key in applied:
                setattr(config, key, getattr(staged, key))
            # 绑定字段不在白名单里，单独落到 live 配置（bind=false 时是解除绑定）。
            config.project_file_path = staged.project_file_path
            config.project_file_output = staged.project_file_output
            if runtime is not None:
                # 停止后的翻译器仍会自动保存内存缓存；同步成导入结果，避免旧快照覆盖。
                runtime.set_project(CacheProject.from_dict(snapshot.project.asdict()))
                runtime.set_items([CacheItem.from_dict(item.asdict()) for item in snapshot.items])
                runtime.require_flag = False

    result = _describe(config, snapshot.info, output)
    result.update(
        backup_folder = backup.folder,
        assets_output_folder = assets_output if sync_assets else "",
        assets_backup_folder = assets_backup.folder,
        item_count = len(snapshot.items),
        applied_settings = sorted(applied),
        ignored_settings = ignored,
        bound = bind,
        project_file_path = staged.project_file_path if bind else "",
    )
    return result
