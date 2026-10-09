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
"""

from __future__ import annotations

import copy
import os
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from api.schemas import (
    TokenEstimateRequest,
    TokenEstimateResult,
    TranslationStartRequest,
    TranslationStartResponse,
    TranslationStateResponse,
)
from base.Base import Base
from base.EventManager import EventManager
from module.Cache.CacheManager import CacheManager
from module.Config import Config
from module.Engine.Engine import Engine
from module.Renpy.ProjectPaths import resolve_translation_output

router = APIRouter(prefix = "/api/translation", tags = ["translation"])

BUSY_DETAIL = "上一次翻译仍在停止收尾，请稍候再开始。"


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
    request: Request,
    status: Base.TranslationStatus,
    request_id: str,
    preflight_confirmed: bool = False,
) -> tuple[dict[str, Any] | None, TranslationStartResponse | None]:
    """构造 TRANSLATION_START 载荷。返回 (payload, 拒绝原因)。

    ``preflight_confirmed`` 是用户对「无有效资产」的明确继续决定：PyQt 页在
    preflight 弹窗选「仍然继续」后会置 ``payload["preflight_confirmed"]=True``
    再发事件。不带这个标志重试会拿回同一个 ASSETS_MISSING 拒绝，界面就永远
    停在弹窗里。
    """
    try:
        config = Config().load()
        config = _bind_resumable_output(config, status)

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


@router.post("/start", response_model = TranslationStartResponse)
def start_translation(request: Request, body: TranslationStartRequest) -> TranslationStartResponse:
    """受理翻译启动请求。

    ``accepted=True`` 只代表事件已投递。线程是否真的起来、run_id 是多少，
    仍以 WS 上的 ``TRANSLATION_START_RESULT`` 为准。
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

    request_id = str(body.request_id or "").strip() or uuid.uuid4().hex[:12]
    try:
        status = Base.TranslationStatus(body.status)
    except ValueError:
        raise HTTPException(status_code = 400, detail = f"未知翻译状态：{body.status}") from None

    payload, rejection = _prepare_payload(
        request,
        status,
        request_id,
        preflight_confirmed=bool(body.preflight_confirmed),
    )
    if rejection is not None:
        return rejection

    _emit(Base.Event.TRANSLATION_START, payload or {})
    return TranslationStartResponse(
        accepted = True,
        request_id = request_id,
        reason = "STARTED",
        detail = "已受理，翻译线程正在启动。",
    )


@router.post("/stop")
def stop_translation(request: Request) -> dict:
    """请求停止翻译。真正的终态走 WS 的 TRANSLATION_DONE。"""
    engine = Engine.get()
    status = engine.get_status()
    if status == Engine.Status.QUALITY:
        raise HTTPException(status_code = 409, detail = "当前是质量任务，请在质量任务面板中停止")
    if status != Engine.Status.TRANSLATING:
        raise HTTPException(status_code = 409, detail = "当前没有正在运行的翻译任务")
    if engine.has_stop_barrier():
        raise HTTPException(status_code = 409, detail = "翻译正在停止收尾中")

    _emit(Base.Event.TRANSLATION_STOP, {})
    return {"ok": True, "status": "STOPPING"}


@router.post("/export")
def export_translation(request: Request) -> dict:
    """把当前译文写回输出目录。

    非运行态走缓存重注入，TRANSLATING 且已初始化走在线导出；
    未初始化时由 Translator 发 APP_TOAST_SHOW 提示「预处理中」。
    """
    config = request.app.state.config
    if not str(getattr(config, "output_folder", "") or "").strip():
        raise HTTPException(status_code = 409, detail = "尚未设置翻译输出目录")

    _emit(Base.Event.TRANSLATION_MANUAL_EXPORT, {"output_folder": str(config.output_folder)})
    return {"ok": True, "output_folder": str(config.output_folder)}


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
        request_id = str(getattr(translator, "_active_request_id", "") or ""),
        run_id = int(getattr(translator, "_translation_run_id", 0) or 0),
        running = running,
        progress = progress,
        active_output_folder = output_folder,
        progress_source = progress_source,
        progress_error = progress_error,
    )


@router.post("/retry-failed")
def retry_failed(request: Request) -> dict:
    """重置「原译相同」的条目为未翻译，之后可用继续任务重翻。"""
    config = request.app.state.config
    output_path = resolve_translation_output(config)
    if output_path is None:
        raise HTTPException(status_code = 404, detail = "未找到当前项目缓存")

    try:
        manager = CacheManager(service = False)
        manager.load_from_file(str(output_path), strict = True)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code = 400, detail = f"缓存载入失败：{exc}") from exc

    count = manager.reset_same_translation_items()
    if count <= 0:
        return {"ok": True, "count": 0, "detail": "没有找到原译相同的条目"}

    saved = manager.save_to_file(
        project = manager.get_project(),
        items = manager.get_items(),
        output_folder = str(output_path),
    )
    if saved is not True:
        raise HTTPException(
            status_code = 500,
            detail = "缓存写入失败，未确认重置结果，请检查输出目录权限后重试",
        )

    # 与翻译页一致：立刻把新的项目状态推给渲染端，让进度回落到待翻译。
    _emit(Base.Event.TRANSLATION_UPDATE, manager.get_project().get_progress())
    return {"ok": True, "count": count}


@router.post("/estimate", response_model = TokenEstimateResult)
def estimate_tokens(request: Request, body: TokenEstimateRequest) -> TokenEstimateResult:
    """Token 估算。同步返回，结果直接进对话框。"""
    config = request.app.state.config
    platform = config.get_platform(config.activate_platform)
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
