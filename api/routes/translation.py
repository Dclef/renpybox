"""翻译主流程路由。

翻译引擎（module/Engine/Translator/Translator.py）在 sidecar 启动时已经由
``Engine.get().run()`` 建好，并订阅了 TRANSLATION_START / TRANSLATION_STOP /
TRANSLATION_MANUAL_EXPORT。所以这里不做任何编排，只是把「一次 HTTP 请求」翻译成
「事件总线上的一次 emit」，受理结果、进度、终态全部走既有事件流，渲染端通过
WS 订阅同一条流（见 api/events.py）。

刻意复刻 frontend/TranslationPage.py 的前端语义，避免两端行为漂移：
  * 启动前冻结配置快照（``copy.deepcopy``）——翻译线程可能稍后才真正开始，
    此期间用户切换项目 / 平台不能让本轮任务读到新的全局路径；
  * status 属于 PROJECT_RESUMABLE_STATUSES 时先绑定到上次运行清单选中的缓存目录；
  * UNTRANSLATED 时跑 ``ProjectAssetsRepository`` + ``TranslationPreflightService``，
    没有有效资产就不自动开始，把决定权交回前端（跳工作台 or 明确继续）。

工具箱「翻译方式」（mode=direct|source|supplement）在同一 /start 契约内原子处理：
先建请求级候选并校验，ASSETS_MISSING / 校验失败时不写盘、不改 live；
受理后再只持久化变更字段，快照直接用候选 deepcopy，禁止再 Config().load()。
"""

from __future__ import annotations

import asyncio
import contextlib
import copy
import os
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from api.jobs import Job
from api.routes.settings import sync_output_protocol
from api.schemas import (
    TRANSLATION_TOOLBOX_LANG_CODES,
    TRANSLATION_TOOLBOX_MODES,
    TokenEstimateRequest,
    TokenEstimateResult,
    TranslationOwnerRequest,
    TranslationReinjectRequest,
    TranslationStartRequest,
    TranslationStartResponse,
    TranslationStateResponse,
)
from base.Base import Base
from base.BaseLanguage import BaseLanguage
from base.EventManager import EventManager
from module.Cache.CacheManager import CacheManager
from module.Config import Config
from module.Engine.Engine import Engine
from module.Extract.SimpleRpyExtractor import SimpleRpyExtractor
from module.File.SourceBackup import backup_source_rpy
from module.Project.ProjectStore import ProjectStore
from module.Renpy.ProjectPaths import RenpyProjectPaths, normalise_path, resolve_translation_output

router = APIRouter(prefix = "/api/translation", tags = ["translation"])

BUSY_DETAIL = "上一次翻译仍在停止收尾，请稍候再开始。"
SOURCE_PREBACKUP_KIND = "source_prebackup"

# 工具箱 mode 可能改动的字段；落盘时只写这些，避免冲掉并发改动的其它设置。
_TOOLBOX_FIELD_NAMES = (
    "renpy_project_path",
    "renpy_game_folder",
    "renpy_tl_folder",
    "input_folder",
    "output_folder",
    "renpy_source_translate",
    "renpy_hook_translate",
    "renpy_backup_original",
    "auto_write_back",
    "source_language",
    "target_language",
    "traditional_chinese_enable",
    "renpy_hook_incremental",
)

# 与 Qt ProjectStore.apply_resolved 持久化后广播对齐：仅真实绑定路径变动才发 PROJECT_CHANGED。
_PROJECT_BROADCAST_FIELDS = (
    "renpy_project_path",
    "renpy_game_folder",
    "renpy_tl_folder",
)


def _path_key(path: Path) -> str:
    return os.path.normcase(os.path.normpath(str(path)))


def _norm_identity(value: str) -> str:
    return os.path.normcase(os.path.abspath(value)) if value else ""


def _project_identity(config: Any) -> tuple[str, ...]:
    """当前配置所属 owner 身份；与手动 target 分开。"""
    return tuple(
        _norm_identity(str(getattr(config, field, "") or ""))
        for field in (
            "renpy_project_path",
            "renpy_game_folder",
            "renpy_tl_folder",
            "input_folder",
            "output_folder",
        )
    )


OWNER_MISMATCH_DETAIL = "项目已切换，请重新加载后再操作"


def _bound_owner_key(live: Any) -> str:
    """当前绑定项目的 owner key；未绑定时为空串。"""
    bound = RenpyProjectPaths.from_config(live)
    return bound.project_key if bound is not None else ""


def _require_owner(live: Any, body_project_key: str | None) -> str:
    """要求调用方持有当前绑定项目的 key，返回该 key（未绑定时为空串）。

    与 error_repair / formatter / translation_reuse 的 owner 约定一致：有绑定
    时必须精确匹配，没有绑定时不得携带 key。不校验就会让切项目后仍开着的旧
    页面去驱动新绑定项目的缓存写入与译文导出。
    """
    bound = RenpyProjectPaths.from_config(live)
    body_key = str(body_project_key or "").strip()
    if bound is None:
        if body_key:
            raise HTTPException(status_code = 409, detail = OWNER_MISMATCH_DETAIL)
        return ""

    owner_key = bound.project_key
    if not body_key or body_key != owner_key:
        raise HTTPException(status_code = 409, detail = OWNER_MISMATCH_DETAIL)
    return owner_key


def _check_owner_key(live: Any, body_project_key: str | None) -> tuple[str, tuple[str, ...]]:
    """校验 body.project_key 对应绑定 owner，不锁死手动 target。

    返回 (owner_project_key, owner_identity)。没有绑定时 key 为空，此时必须
    不带 key；有绑定时必须带且相等。
    """
    identity = _project_identity(live)
    return _require_owner(live, body_project_key), identity


def _acquire_testing() -> Engine:
    """原子预占 TESTING；忙碌时 409，且调用方尚未产生副作用。"""
    engine = Engine.get()
    if engine.has_stop_barrier() or engine.has_single_tasks():
        raise HTTPException(status_code = 409, detail = BUSY_DETAIL)
    if engine.get_status() != Engine.Status.IDLE:
        raise HTTPException(status_code = 409, detail = "已有任务正在运行或收尾，请稍后再试")
    if not engine.try_set_status(Engine.Status.IDLE, Engine.Status.TESTING):
        raise HTTPException(status_code = 409, detail = "已有任务正在运行或收尾，请稍后再试")
    return engine


class TranslationStartResultWaiter:
    """在 emit TRANSLATION_START 之前订阅，等待对应 request_id 的 START_RESULT。"""

    def __init__(self, request_id: str) -> None:
        self.request_id = request_id
        self.holder: dict[str, Any] = {}
        self._manager = EventManager.get()
        self._manager.subscribe(Base.Event.TRANSLATION_START_RESULT, self._on_result)

    def _on_result(self, _event: Any, data: dict | None) -> None:
        payload = data if isinstance(data, dict) else {}
        if str(payload.get("request_id") or "") == self.request_id:
            self.holder.update(payload)

    async def wait(self, *, timeout: float = 5.0) -> dict[str, Any]:
        try:
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                EventManager.drain_all()
                if "accepted" in self.holder:
                    return dict(self.holder)
                await asyncio.sleep(0.02)
            return {
                "accepted": False,
                "request_id": self.request_id,
                "reason": "START_RESULT_TIMEOUT",
            }
        finally:
            self._manager.unsubscribe(Base.Event.TRANSLATION_START_RESULT, self._on_result)


async def await_translation_start_result(
    request_id: str,
    *,
    timeout: float = 5.0,
) -> dict[str, Any]:
    """兼容旧调用：若尚未订阅则无法收到同步 START_RESULT，请改用 Waiter。"""
    waiter = TranslationStartResultWaiter(request_id)
    return await waiter.wait(timeout = timeout)


def _paths_overlap(left: Path, right: Path) -> bool:
    """输入输出相同或互相包含时视为冲突（源码翻译禁止）。"""
    try:
        left_resolved = left.resolve(strict = False)
        right_resolved = right.resolve(strict = False)
    except Exception:
        left_resolved, right_resolved = left, right
    if _path_key(left_resolved) == _path_key(right_resolved):
        return True
    try:
        left_resolved.relative_to(right_resolved)
        return True
    except ValueError:
        pass
    try:
        right_resolved.relative_to(left_resolved)
        return True
    except ValueError:
        pass
    return False


def _parse_toolbox_language(value: str | None, *, field: str) -> BaseLanguage.Enum | None:
    """校验工具箱语言码；空值表示沿用候选里已有设置。"""
    text = str(value or "").strip()
    if not text:
        return None
    code = text.upper()
    if code not in TRANSLATION_TOOLBOX_LANG_CODES:
        raise HTTPException(
            status_code = 400,
            detail = f"{field} 仅支持 { '/'.join(TRANSLATION_TOOLBOX_LANG_CODES) }",
        )
    return BaseLanguage.Enum(code)


def _tl_language_name(body: TranslationStartRequest) -> str:
    return str(body.tl_name or body.language or "").strip() or "chinese"


def _apply_language_fields(
    candidate: Any,
    body: TranslationStartRequest,
    *,
    source_default: BaseLanguage.Enum | None = None,
    target_default: BaseLanguage.Enum | None = None,
) -> None:
    """写入 source/target 与繁体开关；繁体独立于语言码。"""
    source = _parse_toolbox_language(body.source_language, field = "source_language")
    target = _parse_toolbox_language(body.target_language, field = "target_language")
    if source is None and source_default is not None:
        source = source_default
    if target is None and target_default is not None:
        target = target_default
    if source is not None:
        candidate.source_language = source
    if target is not None:
        candidate.target_language = target
    if body.traditional_chinese_enable is not None:
        candidate.traditional_chinese_enable = bool(body.traditional_chinese_enable)


def _collect_changed_fields(live: Any, candidate: Any, field_names: tuple[str, ...]) -> dict[str, Any]:
    changed: dict[str, Any] = {}
    for name in field_names:
        if not hasattr(candidate, name):
            continue
        new_val = getattr(candidate, name)
        old_val = getattr(live, name, None)
        if new_val != old_val:
            changed[name] = copy.deepcopy(new_val)
    return changed


def _persist_changed_fields(live: Any, changed: dict[str, Any]) -> None:
    """只把变更字段写盘并同步到 live，避免整表覆盖并发设置。

    保存成功且真实项目绑定字段（规范化后）变动时广播 PROJECT_CHANGED。
    保存失败/空变更/仅候选不落盘/同项目字段字面改写时绝不发事件。
    """
    if not changed:
        return
    before_identity = tuple(
        _norm_identity(str(getattr(live, field, "") or ""))
        for field in _PROJECT_BROADCAST_FIELDS
    )
    to_save = copy.deepcopy(live)
    for name, value in changed.items():
        setattr(to_save, name, value)
    try:
        to_save.save(strict = True)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code = 500, detail = f"翻译方式配置保存失败：{exc}") from exc
    for name, value in changed.items():
        setattr(live, name, value)
    after_identity = tuple(
        _norm_identity(str(getattr(live, field, "") or ""))
        for field in _PROJECT_BROADCAST_FIELDS
    )
    if after_identity != before_identity:
        EventManager.get().emit(Base.Event.PROJECT_CHANGED, {
            "project_root": str(getattr(live, "renpy_project_path", "") or ""),
        })


def _default_source_output(input_path: Path) -> Path:
    if input_path.is_file():
        return input_path.parent / f"{input_path.stem}_source_out"
    return input_path.parent / f"{input_path.name}_source_out"


def _resolve_source_input(raw: Path) -> Path:
    """若输入是项目根且存在 game/，解析为真实 game 目录。"""
    if not raw.is_dir():
        return raw
    game_dir = raw / "game"
    if not game_dir.is_dir():
        return raw
    paths = RenpyProjectPaths.from_path(raw)
    if paths is None:
        return raw
    try:
        if raw.resolve(strict = False) == paths.project_root.resolve(strict = False):
            return paths.game_dir
    except Exception:
        if _path_key(raw) == _path_key(paths.project_root):
            return paths.game_dir
    return raw


def _has_effective_tl_files(tl_dir: Path) -> bool:
    """与 Qt HookSupplementPage 一致：忽略 hook_/replace_text_auto 等非有效 TL。"""
    if not tl_dir.is_dir():
        return False
    for path in tl_dir.rglob("*.rpy"):
        name = path.name.lower()
        if name.startswith("miss_ready_replace"):
            continue
        if name.startswith("hook_"):
            continue
        if name in {"replace_text_auto.rpy", "set_default_language_at_startup.rpy"}:
            continue
        return True
    return False


def _resolve_supplement_tl_dir(
    live: Any,
    body: TranslationStartRequest,
    paths: RenpyProjectPaths,
    tl_name: str,
) -> Path:
    """补全模式 tl 目录：请求 tl_parent 与配置自定义 tl 优先于 canonical game/tl。"""
    tl_parent = normalise_path(body.tl_parent)
    if tl_parent is not None:
        custom = tl_parent / tl_name
        if not custom.is_dir():
            raise HTTPException(status_code = 400, detail = f"tl 目录不存在：{custom}")
        return custom

    configured_tl = str(getattr(live, "renpy_tl_folder", "") or "").strip()
    if configured_tl:
        candidate = Path(configured_tl)
        if candidate.is_dir():
            try:
                candidate.resolve(strict = False).relative_to(
                    paths.project_root.resolve(strict = False),
                )
                same_project = True
            except ValueError:
                same_project = False
            except Exception:
                same_project = False
            if same_project:
                if candidate.parent.name.casefold() == "tl":
                    return candidate
                try:
                    canonical_key = _path_key(paths.tl_language_dir.resolve(strict = False))
                    candidate_key = _path_key(candidate.resolve(strict = False))
                except Exception:
                    canonical_key = _path_key(paths.tl_language_dir)
                    candidate_key = _path_key(candidate)
                if candidate_key != canonical_key:
                    return candidate

    return paths.tl_language_dir


def _resolve_direct_tl(
    live: Any,
    body: TranslationStartRequest,
) -> tuple[Path, RenpyProjectPaths]:
    """解析直接翻译的 tl 语言目录；可不依赖事先绑定项目。"""
    tl_name = _tl_language_name(body)
    tl_parent = normalise_path(body.tl_parent)
    game_path = normalise_path(body.game_path)

    if tl_parent is not None:
        tl_dir = tl_parent / tl_name
        if not tl_dir.is_dir():
            raise HTTPException(status_code = 400, detail = f"tl 目录不存在：{tl_dir}")
        paths = RenpyProjectPaths.from_path(tl_dir, tl_name)
        if paths is None:
            raise HTTPException(status_code = 400, detail = "无法解析 Ren'Py 项目路径")
        # 显式 tl_parent 始终使用 tl_parent/tl_name，不因 from_path 再改写。
        return tl_dir, paths

    if game_path is not None:
        project_dir = game_path.parent if game_path.is_file() else game_path
        tl_dir = SimpleRpyExtractor.find_tl_directory(project_dir, tl_name)
        if tl_dir is None:
            raise HTTPException(
                status_code = 400,
                detail = f"未找到 tl/{tl_name}，请先抽取或显式指定 tl 父目录",
            )
        paths = RenpyProjectPaths.from_path(tl_dir, tl_name)
        if paths is None:
            raise HTTPException(status_code = 400, detail = "无法解析 Ren'Py 项目路径")
        return paths.tl_language_dir, paths

    paths = RenpyProjectPaths.from_config(live, tl_name if body.tl_name or body.language else "")
    if paths is None:
        raise HTTPException(
            status_code = 400,
            detail = "无法解析 Ren'Py 项目路径，请绑定项目或提供游戏/tl 路径",
        )
    tl_dir = paths.tl_language_dir
    if not tl_dir.is_dir():
        raise HTTPException(status_code = 400, detail = f"tl 目录不存在：{tl_dir}")
    return tl_dir, paths


def _build_direct_candidate(live: Any, body: TranslationStartRequest) -> Any:
    candidate = copy.deepcopy(live)
    tl_dir, paths = _resolve_direct_tl(live, body)
    backup = bool(body.renpy_backup_original) if body.renpy_backup_original is not None else False
    auto_write = bool(body.auto_write_back) if body.auto_write_back is not None else True

    def _mutate(current: Any) -> None:
        current.renpy_backup_original = backup
        current.auto_write_back = auto_write
        current.renpy_source_translate = False
        current.renpy_hook_translate = False
        _apply_language_fields(current, body)

    ProjectStore.get().apply_resolved(
        candidate,
        paths,
        input_folder = tl_dir,
        output_folder = tl_dir,
        mutate = _mutate,
        persist = False,
    )
    return candidate


def _build_source_candidate(live: Any, body: TranslationStartRequest) -> Any:
    candidate = copy.deepcopy(live)
    input_path = normalise_path(body.input_folder)
    if input_path is None:
        raise HTTPException(status_code = 400, detail = "源码翻译需要完整的输入路径")
    if not input_path.exists():
        raise HTTPException(status_code = 400, detail = "源码翻译输入路径不存在")
    if input_path.is_file():
        if input_path.suffix.lower() != ".rpy":
            raise HTTPException(status_code = 400, detail = "源码翻译单文件输入必须是 .rpy 文件")
    elif not input_path.is_dir():
        raise HTTPException(status_code = 400, detail = "源码翻译输入必须是目录或 .rpy 文件")

    input_path = _resolve_source_input(input_path)
    # Qt 无可编辑输出：始终按输入推导 *_source_out，忽略客户端 output_folder。
    output_path = _default_source_output(input_path)

    if output_path.exists() and not output_path.is_dir():
        raise HTTPException(status_code = 400, detail = "源码翻译输出必须是目录")
    if _paths_overlap(input_path, output_path):
        raise HTTPException(
            status_code = 400,
            detail = "源码翻译的输入与输出不能相同或互相包含，请使用独立输出目录",
        )
    if input_path.is_file() and _path_key(output_path / input_path.name) == _path_key(input_path):
        raise HTTPException(
            status_code = 400,
            detail = "源码翻译的输出目录不能直接写回原文件所在位置，请使用独立输出目录",
        )

    if body.external_backup_dir is not None and str(body.external_backup_dir).strip():
        backup_root = normalise_path(body.external_backup_dir)
        if backup_root is None:
            raise HTTPException(status_code = 400, detail = "外部备份目录无效")

    candidate.input_folder = str(input_path.resolve(strict = False))
    candidate.output_folder = str(output_path.resolve(strict = False))
    candidate.renpy_source_translate = True
    candidate.renpy_hook_translate = False
    candidate.renpy_backup_original = (
        bool(body.renpy_backup_original) if body.renpy_backup_original is not None else False
    )
    _apply_language_fields(
        candidate,
        body,
        source_default = BaseLanguage.Enum.EN,
        target_default = BaseLanguage.Enum.ZH,
    )
    return candidate


def _source_needs_prebackup(body: TranslationStartRequest, candidate: Any) -> bool:
    if str(body.external_backup_dir or "").strip():
        return True
    return bool(getattr(candidate, "renpy_backup_original", False))


def _source_backup_root(body: TranslationStartRequest) -> Path | None:
    if not str(body.external_backup_dir or "").strip():
        return None
    return normalise_path(body.external_backup_dir)

def _build_supplement_candidate(live: Any, body: TranslationStartRequest) -> Any:
    candidate = copy.deepcopy(live)
    tl_name = _tl_language_name(body)
    game_path = normalise_path(body.game_path)
    if game_path is None:
        # 允许沿用已绑定项目
        paths = RenpyProjectPaths.from_config(live, tl_name)
        if paths is None:
            raise HTTPException(status_code = 400, detail = "补全翻译需要项目目录")
    else:
        root = game_path.parent if game_path.is_file() else game_path
        if root.name.lower() == "game":
            root = root.parent
        paths = RenpyProjectPaths.from_path(root, tl_name)
        if paths is None:
            raise HTTPException(status_code = 400, detail = "无法解析 Ren'Py 项目路径")

    if not paths.game_dir.is_dir():
        raise HTTPException(status_code = 400, detail = f"未找到 game 目录：{paths.game_dir}")
    tl_dir = _resolve_supplement_tl_dir(live, body, paths, tl_name)
    if not tl_dir.is_dir():
        raise HTTPException(status_code = 400, detail = f"未找到 tl 目录：{tl_dir}")
    if not _has_effective_tl_files(tl_dir):
        raise HTTPException(status_code = 400, detail = "未检测到有效 tl 文件，请先完成 tl 抽取")

    def _mutate(current: Any) -> None:
        current.renpy_source_translate = False
        current.renpy_hook_translate = True
        current.renpy_tl_folder = str(tl_dir)
        _apply_language_fields(
            current,
            body,
            source_default = BaseLanguage.Enum.EN,
            target_default = BaseLanguage.Enum.ZH,
        )

    ProjectStore.get().apply_resolved(
        candidate,
        paths,
        input_folder = tl_dir,
        output_folder = tl_dir,
        mutate = _mutate,
        persist = False,
    )
    return candidate


def _build_toolbox_candidate(live: Any, body: TranslationStartRequest) -> Any:
    """按 mode 建请求级候选：只改 mode 相关字段，不落盘、不改 live。"""
    mode = str(body.mode or "").strip()
    if mode not in TRANSLATION_TOOLBOX_MODES:
        raise HTTPException(status_code = 400, detail = f"未知翻译方式：{body.mode}")
    if mode == "direct":
        return _build_direct_candidate(live, body)
    if mode == "source":
        return _build_source_candidate(live, body)
    return _build_supplement_candidate(live, body)


def _emit(event, data: dict) -> None:
    EventManager.get().emit(event, data)


def _bind_resumable_output(config: Config, status: Base.TranslationStatus) -> Config:
    """续跑时把本轮绑定到上次运行清单选中的缓存目录。

    与 frontend/TranslationPage.py:76-96 ``restore_resumable_translation_paths``
    保持一致：只有当清单里的 output_folder 与本轮解析出的目录相同时，
    才采用清单里的 input_folder。
    """
    if status not in Base.PROJECT_RESUMABLE_STATUSES:
        return config

    from module.Renpy.ProjectPaths import RenpyProjectPaths, read_run_manifest

    output_path = resolve_translation_output(config)
    if output_path is None:
        return config

    config.output_folder = str(output_path)
    paths = RenpyProjectPaths.from_config(config)
    manifest = read_run_manifest(paths) if paths is not None else None
    if manifest is None:
        return config

    selected = os.path.normcase(os.path.abspath(str(output_path)))
    if os.path.normcase(os.path.abspath(manifest["output_folder"])) != selected:
        return config

    input_folder = str(manifest.get("input_folder", "") or "").strip()
    if input_folder:
        config.input_folder = input_folder
    return config


def _prepare_payload(
    app: Any,
    status: Base.TranslationStatus,
    request_id: str,
    preflight_confirmed: bool = False,
    *,
    config_snapshot: Any | None = None,
) -> tuple[dict[str, Any] | None, TranslationStartResponse | None]:
    """构造 TRANSLATION_START 载荷。返回 (payload, 拒绝原因)。

    ``config_snapshot`` 为工具箱 mode 的请求级候选：受理快照必须用它，
    禁止再 ``Config().load()``，以免异步全局改动污染本轮或读到未受理的写盘。

    ``preflight_confirmed`` 是用户对「无有效资产」的明确继续决定：PyQt 页在
    preflight 弹窗选「仍然继续」后会置 ``payload["preflight_confirmed"]=True``
    再发事件。不带这个标志重试会拿回同一个 ASSETS_MISSING 拒绝，界面就永远
    停在弹窗里。
    """
    try:
        if config_snapshot is not None:
            config = copy.deepcopy(config_snapshot)
        else:
            config = Config().load()
        config = _bind_resumable_output(config, status)
        # 旧桌面端可能已保存「SINGLE_TEXT + 单行关闭」，快照里规范化，避免整轮请求失败。
        sync_output_protocol(config)

        payload: dict[str, Any] = {
            "status": status,
            "request_id": request_id,
            # 冻结快照：翻译线程稍后才开始，此期间用户改路径 / 平台不能影响本轮。
            "config": copy.deepcopy(config),
        }

        if status == Base.TranslationStatus.UNTRANSLATED:
            from module.Engine.Translator.ProjectAssetsRepository import ProjectAssetsRepository
            from module.Engine.Translator.TranslationPreflightService import TranslationPreflightService

            state = ProjectAssetsRepository.from_config(config).load(config)
            preflight = TranslationPreflightService.check(state.assets)
            if preflight.should_prompt_for_missing_assets and not preflight_confirmed:
                return None, TranslationStartResponse(
                    accepted = False,
                    reason = "ASSETS_MISSING",
                    detail = "当前项目没有可注入的角色卡、世界观或术语资产。",
                )
            # 有有效资产，或用户已明确选择继续。
            payload["preflight_confirmed"] = True

        return payload, None
    except Exception as exc:  # noqa: BLE001
        return None, TranslationStartResponse(
            accepted = False,
            reason = "PREPARE_FAILED",
            detail = f"{type(exc).__name__}: {exc}",
        )


async def _start_source_with_prebackup(
    app: Any,
    body: TranslationStartRequest,
    *,
    live: Any,
    candidate: Any,
    payload: dict[str, Any],
    request_id: str,
    owner_key: str,
    owner_identity: tuple[str, ...],
    reservation: str = "",
) -> TranslationStartResponse:
    """源码前置备份：先原子占 TESTING，后台 job 可取消/有进度，再启动翻译。"""
    jobs = getattr(app.state, "jobs", None)
    if jobs is None:
        Engine.get().release_translation_reservation(reservation)
        raise HTTPException(status_code = 500, detail = "任务管理器未初始化")

    engine = _acquire_testing()
    try:
        job = jobs.create(SOURCE_PREBACKUP_KIND, total = 100, cooperative_cancel = True)
    except Exception:
        engine.release_status(Engine.Status.TESTING)
        Engine.get().release_translation_reservation(reservation)
        raise

    backup_root = _source_backup_root(body)
    input_path = Path(candidate.input_folder)
    output_path = normalise_path(getattr(candidate, "output_folder", ""))
    game_path = normalise_path(getattr(candidate, "renpy_game_folder", ""))
    frozen_candidate = copy.deepcopy(candidate)
    frozen_payload = copy.deepcopy(payload)
    frozen_owner = owner_identity

    job.result = {
        "project_key": owner_key,
        "owner_identity": list(frozen_owner),
        "target_input": str(input_path),
        "request_id": request_id,
        "stage": "backing_up",
        "message": "正在备份源码…",
        "copied": 0,
        "warnings": [],
        "written_files": [],
        "translation_started": False,
        "translation_run_id": 0,
        "worker_active": True,
    }

    loop = asyncio.get_running_loop()
    released = {"done": False}

    def release_testing() -> None:
        if released["done"]:
            return
        released["done"] = True
        engine.release_status(Engine.Status.TESTING)

    def publish(message: str, *, done: int | None = None) -> None:
        if not isinstance(job.result, dict) or not job.result.get("worker_active"):
            return
        job.result["message"] = message
        jobs.progress(job.id, done = done, total = 100)

    def compute() -> dict[str, Any]:
        if job.cancel_event.is_set():
            raise asyncio.CancelledError()

        def progress_callback(current: int, total: int, message: str) -> None:
            if job.cancel_event.is_set():
                return
            percent = int(max(0, min(99, (current / total) * 100))) if total else 0
            loop.call_soon_threadsafe(lambda: publish(message, done = percent))

        backup_result = backup_source_rpy(
            input_path,
            backup_root,
            should_stop = job.cancel_event.is_set,
            progress_callback = progress_callback,
            output_dir = output_path,
            game_dir = game_path,
        )
        return {
            "copied": int(backup_result.get("copied") or 0),
            "warnings": [str(item) for item in backup_result.get("warnings", []) if item],
            "written_files": [str(item) for item in backup_result.get("written_files", []) if item],
            "cancelled": bool(backup_result.get("cancelled")),
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
                    # 与 HOOK 一致：真实 cancel 后仍合并已备份结果，不得丢弃。
                    if isinstance(finished, dict) and isinstance(job.result, dict):
                        for key in ("copied", "warnings", "written_files"):
                            if key in finished:
                                job.result[key] = finished[key]
                raise

            if isinstance(job.result, dict):
                job.result["copied"] = result["copied"]
                job.result["warnings"] = result["warnings"]
                job.result["written_files"] = result["written_files"]

            if job.cancel_event.is_set() or result.get("cancelled"):
                if isinstance(job.result, dict):
                    job.result["stage"] = "cancelled"
                    job.result["message"] = "备份已取消"
                    job.result["translation_started"] = False
                raise asyncio.CancelledError()

            with CacheManager.LOCK:
                live_config = app.state.config
                if frozen_owner and _project_identity(live_config) != frozen_owner:
                    raise RuntimeError("项目已切换，本次备份结果未用于翻译")
                changed = _collect_changed_fields(
                    live_config, frozen_candidate, _TOOLBOX_FIELD_NAMES,
                )
                # 先落盘再释放 TESTING，避免与其它写配置交错。
                _persist_changed_fields(live_config, changed)

            release_testing()
            waiter = TranslationStartResultWaiter(request_id)
            _emit(Base.Event.TRANSLATION_START, frozen_payload or {})
            start_result = await waiter.wait()
            started = bool(start_result.get("accepted"))
            if isinstance(job.result, dict):
                job.result["translation_started"] = started
                job.result["translation_run_id"] = int(start_result.get("run_id") or 0)
                job.result["start_reason"] = str(start_result.get("reason") or "")
                job.result["warnings"] = result["warnings"]
                if started:
                    job.result["stage"] = "translating"
                    detail = "备份完成，翻译已启动"
                    if result["warnings"]:
                        detail = f"{detail}（备份提示：{'；'.join(result['warnings'])}）"
                    job.result["message"] = detail
                else:
                    job.result["stage"] = "failed"
                    job.result["message"] = (
                        f"备份完成，但翻译未启动：{start_result.get('reason') or '未知原因'}"
                    )
                    raise RuntimeError(job.result["message"])
            jobs.progress(job.id, done = 100, total = 100)
            return job.result if isinstance(job.result, dict) else result
        except asyncio.CancelledError:
            if isinstance(job.result, dict):
                job.result["stage"] = "cancelled"
                job.result["message"] = "任务已取消"
                job.result["translation_started"] = False
            raise
        except Exception as exc:
            if job.cancel_event.is_set():
                if isinstance(job.result, dict):
                    job.result["stage"] = "cancelled"
                    job.result["message"] = "任务已取消"
                    job.result["translation_started"] = False
                raise asyncio.CancelledError() from exc
            if isinstance(job.result, dict):
                job.result["stage"] = "failed"
                job.result["message"] = str(exc)
                job.result["translation_started"] = False
            raise
        finally:
            if isinstance(job.result, dict):
                job.result["worker_active"] = False
            release_testing()
            # 票据由翻译线程一次性消费；取消/异常/等待超时都必须归还，
            # 否则引擎会被堵在「预占中」直到票据过期。
            Engine.get().release_translation_reservation(reservation)

    try:
        await jobs.run(job.id, worker)
    except BaseException:
        if isinstance(job.result, dict):
            job.result["worker_active"] = False
        release_testing()
        Engine.get().release_translation_reservation(reservation)
        raise

    return TranslationStartResponse(
        accepted = True,
        request_id = request_id,
        reason = "STARTED",
        detail = "已受理源码备份，完成后将启动翻译",
        stage = "backing_up",
        job = job.snapshot(),
    )


@router.post("/start", response_model = TranslationStartResponse)
async def start_translation(
    request: Request,
    body: TranslationStartRequest,
) -> TranslationStartResponse:
    """受理翻译启动请求；实现见 :func:`request_translation_start`。"""
    return await request_translation_start(request.app, body)


async def request_translation_start(
    app: Any,
    body: TranslationStartRequest,
) -> TranslationStartResponse:
    """受理翻译启动请求。

    无备份时 ``accepted=True`` 表示事件已投递；线程是否真的起来以
    ``TRANSLATION_START_RESULT`` 为准。source 前置备份走后台 job。

    先解析 ``status``（未知立即 400，不落盘不 emit），合法后再按 ``mode``
    建请求级候选；拒绝时不写盘；不带 mode 时保持旧行为。
    """
    engine = Engine.get()
    if engine.get_status() != Engine.Status.IDLE or engine.has_stop_barrier():
        return TranslationStartResponse(
            accepted = False,
            reason = "STOPPING",
            detail = BUSY_DETAIL,
        )
    if engine.has_single_tasks():
        return TranslationStartResponse(
            accepted = False,
            reason = "ENGINE_BUSY",
            detail = "有单条重译任务正在运行，请稍候再开始。",
        )

    # 原子预占：把「检查状态」与「投递事件」之间的空档合并成一次 CAS 语义。
    # 并发的第二个 /start 在这里就拿到空票被拒，而不是两个请求都走到翻译线程
    # 去抢同一个状态位（那会让两边都先返回 accepted=True）。
    reservation = engine.reserve_translation()
    if not reservation:
        return TranslationStartResponse(
            accepted = False,
            reason = "ENGINE_BUSY",
            detail = "已有翻译启动正在处理，请稍候再试。",
        )

    handed_off = False
    try:
        try:
            status = Base.TranslationStatus(body.status)
        except ValueError:
            raise HTTPException(status_code = 400, detail = f"未知翻译状态：{body.status}") from None

        live = app.state.config
        # 工具箱 mode：先校验 owner，再建候选；失败不写盘。
        owner_key = ""
        owner_identity: tuple[str, ...] = ()
        if body.mode is not None:
            owner_key, owner_identity = _check_owner_key(live, body.project_key)

        candidate: Any | None = None
        if body.mode is not None:
            candidate = _build_toolbox_candidate(live, body)
        elif getattr(body, "platform_id", None) is not None:
            # 请求级平台覆盖：只改这一轮的冻结快照，落盘字段由
            # _collect_changed_fields 限定在 _TOOLBOX_FIELD_NAMES，不会污染翻译页设置。
            candidate = copy.deepcopy(live)
            candidate.activate_platform = int(body.platform_id)

        request_id = str(body.request_id or "").strip() or uuid.uuid4().hex[:12]

        payload, rejection = _prepare_payload(
            app,
            status,
            request_id,
            preflight_confirmed = bool(body.preflight_confirmed),
            config_snapshot = candidate,
        )
        if rejection is not None:
            return rejection

        # 票据必须在这里写进载荷：source 前置备份会 deepcopy 出一份冻结载荷，
        # 之后再补就带不进翻译线程了。
        if payload is not None:
            payload["start_reservation"] = reservation

        if candidate is not None and str(body.mode or "") == "source" and _source_needs_prebackup(body, candidate):
            handed_off = True
            return await _start_source_with_prebackup(
                app,
                body,
                live = live,
                candidate = candidate,
                payload = payload or {},
                request_id = request_id,
                owner_key = owner_key,
                owner_identity = owner_identity,
                reservation = reservation,
            )

        if candidate is not None:
            changed = _collect_changed_fields(live, candidate, _TOOLBOX_FIELD_NAMES)
            _persist_changed_fields(live, changed)

        handed_off = True
        _emit(Base.Event.TRANSLATION_START, payload or {})
        return TranslationStartResponse(
            accepted = True,
            request_id = request_id,
            reason = "STARTED",
            detail = "已受理，翻译线程正在启动。",
            stage = "translating",
        )
    finally:
        # 只有「事件已投递」或「备份 job 已接管」才算交票，其余路径一律归还，
        # 否则拒绝/异常会把引擎堵在预占中直到票据超时。
        if not handed_off:
            engine.release_translation_reservation(reservation)

async def request_translation_stop(
    app: Any,
    body: TranslationOwnerRequest | None = None,
) -> dict:
    """请求停止翻译。真正的终态走 WS 的 TRANSLATION_DONE。"""
    engine = Engine.get()
    status = engine.get_status()
    if status == Engine.Status.QUALITY:
        raise HTTPException(status_code = 409, detail = "当前是质量任务，请在质量任务面板中停止")
    if status != Engine.Status.TRANSLATING:
        raise HTTPException(status_code = 409, detail = "当前没有正在运行的翻译任务")
    if engine.has_stop_barrier():
        raise HTTPException(status_code = 409, detail = "翻译正在停止收尾中")

    _require_owner(app.state.config, body.project_key if body is not None else None)

    _emit(Base.Event.TRANSLATION_STOP, {})
    return {"ok": True, "status": "STOPPING"}


@router.post("/stop")
async def stop_translation(request: Request, body: TranslationOwnerRequest | None = None) -> dict:
    """请求停止翻译；实现见 :func:`request_translation_stop`。"""
    return await request_translation_stop(request.app, body)


@router.post("/export")
def export_translation(request: Request, body: TranslationOwnerRequest | None = None) -> dict:
    """把当前译文写回输出目录。

    非运行态走缓存重注入，TRANSLATING 且已初始化走在线导出；
    未初始化时由 Translator 发 APP_TOAST_SHOW 提示「预处理中」。
    其他状态 Translator 会静默忽略事件，这里与 frontend/TranslationPage.py
    ``update_button_status`` 一致直接拒绝，避免前端误以为已写入。
    """
    config = request.app.state.config
    if not str(getattr(config, "output_folder", "") or "").strip():
        raise HTTPException(status_code = 409, detail = "尚未设置翻译输出目录")

    engine = Engine.get()
    status = engine.get_status()
    if engine.has_stop_barrier() or status not in (Engine.Status.IDLE, Engine.Status.TRANSLATING):
        raise HTTPException(status_code = 409, detail = "当前状态不能写入译文文件，请等待任务结束或停止收尾完成")

    _require_owner(config, body.project_key if body is not None else None)

    output_folder = str(config.output_folder)
    if status == Engine.Status.IDLE:
        # 与 /state 读取进度同口径：优先当前项目最近运行清单里含缓存的目录。
        resolved = resolve_translation_output(config)
        if resolved is not None:
            output_folder = str(resolved)

    _emit(Base.Event.TRANSLATION_MANUAL_EXPORT, {"output_folder": output_folder})
    return {"ok": True, "output_folder": output_folder}


def _resolve_reinject_tl(live: Any, body: TranslationReinjectRequest) -> Path:
    """解析手动写回目标 TL：显式 tl_parent/tl_name 或 output_folder，对齐 Direct 选定 TL。"""
    tl_name = str(body.tl_name or "").strip() or "chinese"
    tl_parent = normalise_path(body.tl_parent)
    if tl_parent is not None:
        tl_dir = tl_parent / tl_name
        if not tl_dir.is_dir():
            raise HTTPException(status_code = 400, detail = f"tl 目录不存在：{tl_dir}")
        return tl_dir

    if str(body.output_folder or "").strip():
        output = normalise_path(body.output_folder)
        if output is None:
            raise HTTPException(status_code = 400, detail = "请指定有效的输出目录")
        if not output.is_dir():
            raise HTTPException(status_code = 400, detail = f"输出目录不存在：{output}")
        return output

    game_path = normalise_path(body.game_path)
    if game_path is not None:
        project_dir = game_path.parent if game_path.is_file() else game_path
        tl_dir = SimpleRpyExtractor.find_tl_directory(project_dir, tl_name)
        if tl_dir is None:
            raise HTTPException(
                status_code = 400,
                detail = f"未找到 tl/{tl_name}，请显式指定 tl 父目录",
            )
        return tl_dir

    paths = RenpyProjectPaths.from_config(live, tl_name)
    if paths is None or not paths.tl_language_dir.is_dir():
        raise HTTPException(status_code = 400, detail = "请指定有效的 TL 目录")
    return paths.tl_language_dir


@router.post("/reinject")
def reinject_translation(request: Request, body: TranslationReinjectRequest) -> dict:
    """手动把缓存译文写回选定 TL（对齐 Qt DirectRpyTranslatePage 手动写回）。

    拒绝阶段校验 owner / 缓存存在性，不写盘、不 emit。
    """
    live = request.app.state.config
    _check_owner_key(live, body.project_key)

    engine = Engine.get()
    if engine.get_status() != Engine.Status.IDLE or engine.has_stop_barrier():
        raise HTTPException(status_code = 409, detail = "翻译任务正在运行或停止收尾，请结束后再写回")
    if engine.has_single_tasks():
        raise HTTPException(status_code = 409, detail = "有单条重译任务正在运行，请稍候再写回")

    output = _resolve_reinject_tl(live, body)
    cache_dir = output / "cache"
    db_file = output / "cache.db"
    if not cache_dir.exists() and not db_file.exists():
        raise HTTPException(status_code = 404, detail = "目标目录没有可写回的翻译缓存")

    folder = str(output.resolve(strict = False))
    request_id = str(body.request_id or "").strip()
    payload: dict[str, Any] = {"output_folder": folder}
    if request_id:
        payload["request_id"] = request_id
    _emit(Base.Event.TRANSLATION_CACHE_REINJECT, payload)
    return {"ok": True, "output_folder": folder}


@router.get("/state", response_model = TranslationStateResponse)
def read_state(request: Request) -> TranslationStateResponse:
    """当前引擎与运行状态快照。

    渲染端挂载 / 刷新后用它对齐一次，避免必须等下一条 TRANSLATION_UPDATE 才
    能把按钮和进度显示成正确的样子。
    """
    engine = Engine.get()
    translator = getattr(engine, "translator", None)
    status = engine.get_status()

    progress: dict[str, Any] = {}
    progress_source = "none"
    progress_error = ""
    output_folder = ""
    active = status in (Engine.Status.TRANSLATING, Engine.Status.STOPPING) or engine.has_stop_barrier()
    if active and translator is not None:
        extras = getattr(translator, "extras", None)
        if isinstance(extras, dict):
            progress = dict(extras.get("progress") or {}) if isinstance(extras.get("progress"), dict) else dict(extras)
        output_folder = str(getattr(translator, "_active_cache_output_folder", "") or "")
        progress_source = "runtime"
    elif not active:
        # 与旧版启动预读一致：只读当前项目的元数据，避免加载整份译文或串入上个项目。
        output = resolve_translation_output(request.app.state.config)
        if output is not None:
            output_folder = str(output)
            if any(os.path.isfile(os.path.join(output_folder, "cache", name)) for name in ("cache.db", "project.json")):
                try:
                    manager = CacheManager(service = False)
                    manager.load_project_from_file(output_folder, strict = True)
                    project = manager.get_project()
                    progress = {**project.get_progress(), "status": project.get_status()}
                    progress_source = "cache"
                except Exception as exc:
                    progress_error = f"缓存进度读取失败：{exc}"

    # Quality work runs outside Translator but shares the translation progress contract.
    from module.Engine.Quality.QualityTaskCoordinator import QualityTaskCoordinator
    quality_progress = QualityTaskCoordinator.get().get_progress()
    if quality_progress is not None:
        progress["quality_task"] = quality_progress.as_dict()

    running = {
        "running": int(engine.get_running_task_count()),
        "max": int(getattr(request.app.state.config, "max_workers", 0) or 0),
    }

    return TranslationStateResponse(
        engine_status = str(getattr(status, "value", status)),
        stop_barrier = bool(engine.has_stop_barrier()),
        single_tasks = bool(engine.has_single_tasks()),
        owner_project_key = _bound_owner_key(request.app.state.config),
        request_id = str(getattr(translator, "_active_request_id", "") or ""),
        run_id = int(getattr(translator, "_translation_run_id", 0) or 0),
        running = running,
        progress = progress,
        active_output_folder = output_folder,
        progress_source = progress_source,
        progress_error = progress_error,
    )


def _ensure_engine_idle_for_cache_write(engine: Engine) -> None:
    """与 /start 同口径：引擎忙、停止收尾或单条重译期间拒绝改写缓存。"""
    if engine.get_status() != Engine.Status.IDLE or engine.has_stop_barrier():
        raise HTTPException(status_code = 409, detail = "翻译任务正在运行或停止收尾，请结束后再重置失败项")
    if engine.has_single_tasks():
        raise HTTPException(status_code = 409, detail = "有单条重译任务正在运行，请稍候再重置失败项")


def _refresh_progress_after_failed_reset(manager: CacheManager) -> dict[str, Any]:
    """按条目状态重算进度，口径与 Translator 续跑一致：已译=已完成条目，总数=已完成+待译。"""
    from module.Engine.Quality.TranslationQualityReport import build_translation_quality_report

    items = manager.get_items()
    completed = sum(1 for item in items if Base.is_item_completed(item.get_status()))
    remaining = sum(1 for item in items if item.get_status() == Base.TranslationStatus.UNTRANSLATED)
    # 失败统计只保留仍带重试元数据的条目，已重置的失败不再计入。
    report = build_translation_quality_report(items)

    project = manager.get_project()
    progress = project.get_progress()
    progress.update({
        "line": completed,
        "total_line": completed + remaining,
        "failed_line_count": report.failed_count,
        "line_count_mismatch_count": report.line_mismatch_count,
    })
    project.set_progress(progress)
    if remaining > 0:
        # 项目置为可续跑状态，「继续任务」才会按续译路径读取本缓存。
        project.set_status(Base.TranslationStatus.TRANSLATING)
    return {**progress, "status": project.get_status()}


@router.post("/retry-failed")
def retry_failed(request: Request, body: TranslationOwnerRequest | None = None) -> dict:
    """重置翻译失败条目为未翻译，之后由用户点「继续任务」重翻；本请求不启动翻译。"""
    engine = Engine.get()
    _ensure_engine_idle_for_cache_write(engine)

    config = request.app.state.config
    _require_owner(config, body.project_key if body is not None else None)
    output_path = resolve_translation_output(config)
    if output_path is None:
        raise HTTPException(status_code = 404, detail = "未找到当前项目缓存")
    output_folder = str(output_path)

    # 持有缓存类锁完成「读-改-写」，避免与运行期 CacheManager 的自动保存交错。
    with CacheManager.LOCK:
        _ensure_engine_idle_for_cache_write(engine)
        runtime_manager = getattr(getattr(engine, "translator", None), "cache_manager", None)
        if (
            runtime_manager is not None
            and getattr(runtime_manager, "require_flag", False) is True
            and os.path.normcase(os.path.abspath(str(getattr(runtime_manager, "require_path", "") or "")))
            == os.path.normcase(os.path.abspath(output_folder))
        ):
            raise HTTPException(status_code = 409, detail = "上一轮翻译缓存仍在等待保存，请稍候再重置失败项")

        try:
            manager = CacheManager(service = False)
            manager.load_from_file(output_folder, strict = True)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code = 400, detail = f"缓存载入失败：{exc}") from exc

        count = manager.reset_failed_translation_items()
        if count <= 0:
            return {"ok": True, "count": 0, "detail": "没有找到翻译失败或原译相同的条目"}

        progress = _refresh_progress_after_failed_reset(manager)
        saved = manager.save_to_file(
            project = manager.get_project(),
            items = manager.get_items(),
            output_folder = output_folder,
        )
    if saved is not True:
        raise HTTPException(
            status_code = 500,
            detail = "缓存写入失败，未确认重置结果，请检查输出目录权限后重试",
        )

    # 只推送重算后的缓存进度，不发 TRANSLATION_START，翻译仍需用户点「继续任务」。
    _emit(Base.Event.TRANSLATION_UPDATE, progress)
    return {
        "ok": True,
        "count": count,
        "detail": f"已重置 {count} 条失败项，请点击「继续任务」重新翻译",
    }


@router.post("/estimate", response_model = TokenEstimateResult)
def estimate_tokens(
    request: Request,
    body: TokenEstimateRequest | None = None,
) -> TokenEstimateResult:
    """Token 估算。同步返回，结果直接进对话框。

    兼容无 body / ``{}``：前端 ``request()`` 会带 JSON Content-Type，缺 body 时
    FastAPI 对必填模型会 422；这里显式允许省略，platform_id 缺省走激活平台。
    """
    config = request.app.state.config
    payload = body or TokenEstimateRequest()
    platform_id = (
        payload.platform_id
        if payload.platform_id is not None
        else config.activate_platform
    )
    platform = config.get_platform(platform_id)
    if platform is None:
        raise HTTPException(status_code = 409, detail = "未找到激活的平台配置")

    items = _load_items_for_estimate(config)
    if not items:
        raise HTTPException(status_code = 409, detail = "当前项目没有可估算的翻译条目")

    from module.TokenEstimator import TokenEstimator

    try:
        result = TokenEstimator(config, platform, items).estimate()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code = 400, detail = f"Token 估算失败：{exc}") from exc

    return TokenEstimateResult(
        untranslated_count = int(result.untranslated_count),
        batch_count = int(result.batch_count),
        total_source_tokens = int(result.total_source_tokens),
        estimated_input_tokens = int(result.estimated_input_tokens),
        estimated_output_tokens = int(result.estimated_output_tokens),
        estimated_cost = float(result.estimated_cost),
    )


def _load_items_for_estimate(config: Config) -> list:
    """按运行缓存 → 磁盘缓存 → 输入目录的顺序取条目。

    顺序与 frontend/TranslationPage.py:1893-1927 一致：运行期缓存要确认还是
    同一个项目，否则会拿上一轮的条目估算。
    """
    output_path = resolve_translation_output(config)
    translator = getattr(Engine.get(), "translator", None)

    runtime_manager = getattr(translator, "cache_manager", None)
    if runtime_manager is not None:
        runtime_items = runtime_manager.copy_items()
        runtime_output = str(
            getattr(translator, "_active_cache_output_folder", "")
            or getattr(translator, "_last_runtime_output_folder", "")
            or ""
        ).strip()
        same_project = bool(
            runtime_output
            and output_path is not None
            and os.path.normcase(os.path.abspath(runtime_output))
            == os.path.normcase(os.path.abspath(str(output_path)))
        )
        if runtime_items and same_project:
            return runtime_items

    if output_path is not None:
        manager = CacheManager(service = False)
        try:
            manager.load_items_from_file(str(output_path), strict = True)
            if manager.get_items():
                return manager.get_items()
        except Exception:
            pass

    from module.File.FileManager import FileManager

    _, items = FileManager(config).read_from_path()
    return items
