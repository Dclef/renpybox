import concurrent.futures
import copy
import json
import os
import re
import threading
import time
import webbrowser
from collections.abc import Mapping
from itertools import zip_longest

import httpx
from rich.progress import TaskID

from base.Base import Base
from base.LogManager import LogManager
from module.Cache.CacheItem import CacheItem
from module.Cache.CacheManager import CacheManager
from module.Config import Config
from module.Engine.Engine import Engine
from module.Engine.TaskLimiter import TaskLimiter
from module.Engine.TaskRequester import TaskRequester
from module.Engine.Translator.TranslationPreflightService import TranslationPreflightService
from module.Engine.Translator.ProjectAssetsRepository import ProjectAssetsRepository
from module.Engine.Translator.TranslationTaskContext import (
    ProjectAssets,
    TermAsset,
    TranslationTaskContext,
    merge_provider_credentials,
)
from module.Engine.Translator.TranslatorTask import TranslatorTask
from module.File.FileManager import FileManager
from module.Filter.LanguageFilter import LanguageFilter
from module.Filter.RuleFilter import RuleFilter
from module.Localizer.Localizer import Localizer
from module.ProgressBar import ProgressBar
from module.PromptBuilder import PromptBuilder
from module.ResultChecker import ResultChecker
from module.Response.ResponseChecker import ResponseChecker
from module.Renpy.ProjectPaths import (
    RenpyProjectPaths,
    read_run_manifest,
    resolve_translation_output,
    write_run_manifest,
)
from module.TextProcessor import TextProcessor


class TranslationCancelled(RuntimeError):
    """翻译在准备阶段被用户取消。"""


# 翻译器
class Translator(Base):

    # 停止收尾最多等待已有任务多久，避免 SDK/网络异常导致 watcher 永不结束。
    STOP_WAIT_TIMEOUT: float = 30.0
    STOP_WAIT_POLL: float = 0.1
    # watcher 超时后的残留线程清理也必须有上限，避免全局取消标记永久保留。
    CANCEL_CLEANUP_TIMEOUT: float = 30.0

    def __init__(self) -> None:
        super().__init__()

        # 初始化
        self.cache_manager = CacheManager(service = True)
        self._last_runtime_output_folder: str = ""
        self._active_cache_output_folder: str = ""

        # 线程锁
        self.data_lock = threading.Lock()

        # 运行中的线程池（用于停止任务时快速取消）
        self._active_executor: concurrent.futures.ThreadPoolExecutor | None = None
        self._translation_thread: threading.Thread | None = None
        self._stop_watcher: threading.Thread | None = None
        self._stop_watcher_lock = threading.Lock()
        self._cancel_cleanup_thread: threading.Thread | None = None
        self._translation_run_initialized: bool = False
        self._translation_run_id: int = 0
        self._active_run_cancel_event: threading.Event | None = None
        self._run_context = threading.local()

        # 注册事件
        self.subscribe(Base.Event.TRANSLATION_STOP, self.translation_stop)
        self.subscribe(Base.Event.TRANSLATION_START, self.translation_start)
        self.subscribe(Base.Event.TRANSLATION_MANUAL_EXPORT, self.translation_manual_export)
        self.subscribe(Base.Event.TRANSLATION_CACHE_REINJECT, self.translation_cache_reinject)
        self.subscribe(Base.Event.PROJECT_STATUS, self.translation_project_status_check)

    # 翻译停止事件
    def translation_stop(self, event: str, data: dict) -> None:
        current_status = Engine.get().get_status()
        if current_status not in (
            Engine.Status.TRANSLATING,
            Engine.Status.STOPPING,
        ):
            return

        with self._stop_watcher_lock:
            cleanup = getattr(self, "_cancel_cleanup_thread", None)
            if cleanup is not None and cleanup.is_alive():
                return

        # 状态切换、取消事件登记和 MAIN 快照使用与启动相同的锁顺序
        #（先 data_lock，再 Engine.lock），避免极早停止时出现锁反转。
        with self.data_lock:
            if Engine.get().get_status() not in (
                Engine.Status.TRANSLATING,
                Engine.Status.STOPPING,
            ):
                return
            Engine.get().set_status(Engine.Status.STOPPING)
            Engine.get().set_stop_barrier(True)

            # 线程池可能在停止快照后才懒创建工作线程，新线程仍会绑定这个
            # 已设置的事件，不会因下一轮清理全局事件而复活。
            active_thread = getattr(self, "_translation_thread", None)
            active_run_id = getattr(self, "_translation_run_id", None)
            run_cancel_event = getattr(self, "_active_run_cancel_event", None)
            if run_cancel_event is not None:
                run_cancel_event.set()

        # 在关闭客户端前固定旧轮线程集合，并把取消状态绑定到线程对象；
        # 独立运行事件负责覆盖快照之后才创建的迟到线程。
        stop_workers_list = [
            thread
            for thread in threading.enumerate()
            if thread.name.startswith(Engine.TASK_PREFIX)
        ]
        # 极早停止时，MAIN 线程可能尚未完成 enumerate 注册；显式加入
        # 引用，确保它不会在 watcher 清除取消标记后继续初始化新任务。
        if active_thread is not None and active_thread not in stop_workers_list:
            stop_workers_list.append(active_thread)
        stop_workers = tuple(stop_workers_list)

        # 先取消排队任务，再异步释放网络客户端；关闭第三方 SDK 不能阻塞
        # Qt 事件线程，否则点击停止后界面会长时间无响应。
        self._shutdown_active_executor()
        TaskRequester.cancel_all_clients(
            asynchronous = True,
            threads = stop_workers,
        )

        # 只等待停止请求发出时已经存在的引擎线程。若使用全局线程计数，
        # 超时后新启动的质量/单条任务也会被误算进旧任务清理范围。

        def task(event: str, data: dict) -> None:
            deadline = time.monotonic() + __class__.STOP_WAIT_TIMEOUT
            timed_out = False
            workers_finished = False
            try:
                while any(thread.is_alive() for thread in stop_workers):
                    if time.monotonic() >= deadline:
                        timed_out = True
                        break
                    time.sleep(__class__.STOP_WAIT_POLL)

                workers_finished = not timed_out and not any(
                    thread.is_alive() for thread in stop_workers
                )

                if timed_out:
                    self.warning(
                        f"[STOP] 等待翻译线程超时（{__class__.STOP_WAIT_TIMEOUT:.1f}s），"
                        "跳过本次缓存写入，保留现有缓存供下次恢复。"
                    )
                elif (
                    self._is_translation_run_current(active_run_id)
                    and self._translation_run_initialized
                ):
                    # 只有本轮初始化完成且所有工作线程退出后才保存，避免
                    # 早停时使用旧配置/旧项目覆盖其他路径的缓存。
                    output_folder = str(self._active_cache_output_folder or "").strip()
                    if output_folder:
                        self.cache_manager.save_to_file(
                            project = self.cache_manager.get_project(),
                            items = self.cache_manager.get_items(),
                            output_folder = output_folder,
                            strict = True,
                        )

                self.print("")
                self.info(Localizer.get().translator_stop)
                self.print("")
                self.emit(Base.Event.APP_TOAST_SHOW, {
                    "type": Base.ToastType.SUCCESS,
                    "message": Localizer.get().translator_stop,
                })
            except Exception as exc:
                # 停止收尾不能因为路径/磁盘异常而把引擎永久留在 STOPPING。
                self.error("[STOP] 停止收尾失败，已跳过缓存写入", exc)
                self.emit(Base.Event.APP_TOAST_SHOW, {
                    "type": Base.ToastType.WARNING,
                    "message": f"停止完成，但缓存保存失败：{type(exc).__name__}",
                })
            finally:
                # 只有确认所有旧线程退出后才清除全局标记；线程级标记仍会
                # 保护迟到的旧回调，即使清理期限后新一轮已经开始。
                if workers_finished:
                    TaskRequester.CANCEL_EVENT.clear()
                    Engine.get().set_stop_barrier(False)
                elif timed_out:
                    with self._stop_watcher_lock:
                        cleanup = threading.Thread(
                            target = self._clear_cancel_after_workers,
                            args = (stop_workers,),
                            name = "REN_TRANSLATION_CANCEL_CLEANUP",
                            daemon = True,
                        )
                        self._cancel_cleanup_thread = cleanup
                    cleanup.start()
                else:
                    # 异常路径也必须解除屏障，避免引擎永久无法接收新任务。
                    TaskRequester.CANCEL_EVENT.clear()
                    Engine.get().set_stop_barrier(False)
                # 只释放自己持有的 STOPPING 状态，避免覆盖其他任务的状态。
                Engine.get().release_status(Engine.Status.STOPPING)
                self.emit(Base.Event.TRANSLATION_DONE, {
                    "success": False,
                    "stopped": True,
                    "run_id": active_run_id,
                })
                with self._stop_watcher_lock:
                    self._stop_watcher = None

        with self._stop_watcher_lock:
            if self._stop_watcher is not None and self._stop_watcher.is_alive():
                return
            watcher = threading.Thread(
                target = task,
                args = (event, data),
                # watcher 使用独立前缀，避免被旧版线程统计逻辑误算为工作线程。
                name = "REN_TRANSLATION_STOP_WATCHER",
                daemon = True,
            )
            self._stop_watcher = watcher
            watcher.start()

    def _clear_cancel_after_workers(
        self,
        workers: tuple[threading.Thread, ...] = (),
    ) -> None:
        """停止超时后有界等待旧工作线程，再清除全局取消标记。"""
        # 兼容旧测试/外部调用：未传线程列表时退回当前线程快照，仍受期限限制。
        if not workers:
            workers = tuple(
                thread
                for thread in threading.enumerate()
                if thread.name.startswith(Engine.TASK_PREFIX)
            )

        deadline = time.monotonic() + __class__.CANCEL_CLEANUP_TIMEOUT
        while any(thread.is_alive() for thread in workers):
            if time.monotonic() >= deadline:
                break
            time.sleep(__class__.STOP_WAIT_POLL)

        if any(thread.is_alive() for thread in workers):
            self.warning(
                "[STOP] 残留翻译线程超过清理期限，解除停止屏障并交由守护线程退出"
            )
        TaskRequester.CANCEL_EVENT.clear()
        Engine.get().set_stop_barrier(False)
        with self._stop_watcher_lock:
            if self._cancel_cleanup_thread is threading.current_thread():
                self._cancel_cleanup_thread = None

    def _shutdown_active_executor(self) -> None:
        with self.data_lock:
            executor = self._active_executor

        if executor is None:
            return

        try:
            executor.shutdown(wait = False, cancel_futures = True)
        except Exception:
            pass

    def _is_translation_run_current(self, run_id: int | None) -> bool:
        """判断回调/线程是否仍属于当前翻译代次。"""
        if run_id is None:
            # 兼容旧测试与外部直接调用 translation_start_task 的入口。
            return True
        with self.data_lock:
            return getattr(self, "_translation_run_id", 0) == run_id

    def _bind_run_context(
        self,
        run_id: int | None,
        cancel_event: threading.Event | None,
    ) -> None:
        context = getattr(self, "_run_context", None)
        if context is None:
            context = threading.local()
            self._run_context = context
        context.run_id = run_id
        context.cancel_event = cancel_event
        TaskRequester.bind_run_cancel_event(cancel_event)

    def _unbind_run_context(self) -> None:
        TaskRequester.unbind_run_cancel_event()
        context = getattr(self, "_run_context", None)
        if context is None:
            return
        for name in ("run_id", "cancel_event"):
            if hasattr(context, name):
                delattr(context, name)

    def _should_stop_requested(
        self,
        run_id: int | None = None,
        cancel_event: threading.Event | None = None,
    ) -> bool:
        context = getattr(self, "_run_context", None)
        if run_id is None:
            run_id = getattr(context, "run_id", None)
        if cancel_event is None:
            cancel_event = getattr(context, "cancel_event", None)
        return (
            not self._is_translation_run_current(run_id)
            or (cancel_event is not None and cancel_event.is_set())
            or Engine.get().get_status() == Engine.Status.STOPPING
            or TaskRequester.is_cancel_requested()
        )

    def _raise_if_stop_requested(self) -> None:
        """在不可逆的准备步骤之间快速退出。"""
        if self._should_stop_requested():
            raise TranslationCancelled()

    # 翻译开始事件
    def translation_start(self, event: str, data: dict) -> None:
        with self._stop_watcher_lock:
            stop_watcher = self._stop_watcher
            cancel_cleanup = getattr(self, "_cancel_cleanup_thread", None)
        if (
            stop_watcher is not None and stop_watcher.is_alive()
        ) or (
            cancel_cleanup is not None and cancel_cleanup.is_alive()
        ):
            self.emit(Base.Event.APP_TOAST_SHOW, {
                "type": Base.ToastType.WARNING,
                "message": "上一次翻译仍在停止收尾，请稍候再开始。",
            })
            return

        start_failed = False
        with self.data_lock:
            active_thread = self._translation_thread
            if active_thread is not None and active_thread.is_alive():
                start_failed = True
            elif Engine.get().try_set_status(Engine.Status.IDLE, Engine.Status.TRANSLATING):
                # 状态占用、运行登记和线程启动必须处于同一个临界区。停止事件
                # 一旦看到 TRANSLATING，就一定能取得已登记且已启动的 MAIN。
                self._translation_run_id = self._translation_run_id + 1
                run_id = self._translation_run_id
                run_cancel_event = threading.Event()
                self._active_run_cancel_event = run_cancel_event
                self._translation_run_initialized = False
                self._active_cache_output_folder = ""
                thread = threading.Thread(
                    target = self.translation_start_task,
                    args = (event, data, run_id, run_cancel_event),
                    name = f"{Engine.TASK_PREFIX}MAIN",
                )
                self._translation_thread = thread
                try:
                    thread.start()
                except Exception:
                    run_cancel_event.set()
                    if self._translation_thread is thread:
                        self._translation_thread = None
                    Engine.get().release_status(Engine.Status.TRANSLATING)
                    raise
                return
            else:
                start_failed = True

        if start_failed:
            self.emit(Base.Event.APP_TOAST_SHOW, {
                "type": Base.ToastType.WARNING,
                "message": Localizer.get().translator_running,
            })

    # 翻译结果手动导出事件
    def translation_manual_export(self, event: str, data: dict) -> None:
        if Engine.get().get_status() != Engine.Status.TRANSLATING:
            return None

        # 复制一份以避免影响原始数据
        def task(event: str, data: dict) -> None:
            try:
                items = self.cache_manager.copy_items()
                self.mtool_optimizer_postprocess(items)
                self.check_and_wirte_result(items)
            except Exception as exc:
                # 写回失败会抛出，子线程里必须自行提示，否则用户只能在日志里看到。
                self.error("[EXPORT] 手动导出失败", exc)
                self.emit(Base.Event.APP_TOAST_SHOW, {
                    "type": Base.ToastType.ERROR,
                    "message": str(exc),
                })
        threading.Thread(target = task, args = (event, data)).start()

    # 从缓存重新注入翻译结果
    def translation_cache_reinject(self, event: str, data: dict) -> None:
        def task(event: str, data: dict) -> None:
            config = Config().load()
            output_folder = data.get("output_folder") or config.output_folder
            if not output_folder:
                self.emit(Base.Event.APP_TOAST_SHOW, {
                    "type": Base.ToastType.WARNING,
                    "message": Localizer.get().translation_page_reinject_cache_no_cache,
                })
                return

            cache_manager = CacheManager(service = False)
            cache_manager.load_items_from_file(output_folder)
            items = cache_manager.get_items()

            if not items:
                self.emit(Base.Event.APP_TOAST_SHOW, {
                    "type": Base.ToastType.WARNING,
                    "message": Localizer.get().translation_page_reinject_cache_no_cache,
                })
                return

            # 使用输出目录作为读写根，避免写回错位
            config.output_folder = output_folder
            config.input_folder = output_folder

            self.info(f"[REINJECT] 从缓存重新注入：{output_folder} (items={len(items)})")
            try:
                FileManager(config).write_to_path(items)
            except Exception as exc:
                # 写回失败会抛出，子线程里必须自行提示，否则用户只能在日志里看到。
                self.error("[REINJECT] 从缓存重新注入失败", exc)
                self.emit(Base.Event.APP_TOAST_SHOW, {
                    "type": Base.ToastType.ERROR,
                    "message": str(exc),
                })
                return
            self.info(f"[REINJECT] 注入完成：{output_folder}")

            self.emit(Base.Event.APP_TOAST_SHOW, {
                "type": Base.ToastType.SUCCESS,
                "message": Localizer.get().translation_page_reinject_cache_success,
            })

        threading.Thread(target = task, args = (event, data)).start()

    # 翻译状态检查事件
    def translation_project_status_check(self, event: str, data: dict) -> None:

        def task(event: str, data: dict) -> None:
            if Engine.get().get_status() != Engine.Status.IDLE:
                status = Base.TranslationStatus.UNTRANSLATED
                extras = {}
            else:
                output_folder = self._resolve_project_status_output_folder(data)
                cache_manager = CacheManager(service = False)
                cache_manager.load_project_from_file(output_folder)
                status = cache_manager.get_project().get_status()
                extras = cache_manager.get_project().get_progress() or {}

            payload = {
                "status" : status,
            }
            if isinstance(extras, dict):
                payload.update(extras)
            self.emit(Base.Event.PROJECT_STATUS_CHECK_DONE, payload)
        threading.Thread(target = task, args = (event, data)).start()

    def _resolve_project_status_output_folder(self, data: dict) -> str:
        current_config = Config().load()
        current_output = current_config.output_folder
        runtime_output = getattr(self, "_last_runtime_output_folder", "")
        requested_output = ""
        prefer_runtime = False

        if isinstance(data, dict):
            requested_output = str(data.get("output_folder", "") or "").strip()
            prefer_runtime = bool(data.get("prefer_runtime_output", False))

        candidates: list[str] = []

        def add_candidate(path: str) -> None:
            path = str(path or "").strip()
            if path != "" and path not in candidates:
                candidates.append(path)

        add_candidate(requested_output)
        if not requested_output:
            resolved = resolve_translation_output(
                current_config,
                runtime_output if prefer_runtime else None,
            )
            if resolved is not None:
                add_candidate(str(resolved))
        if prefer_runtime:
            add_candidate(runtime_output)
            add_candidate(current_output)
        else:
            add_candidate(current_output)
            add_candidate(runtime_output)

        for path in candidates:
            if self._has_cache_snapshot(path):
                return path

        return candidates[0] if len(candidates) > 0 else current_output

    def _has_cache_snapshot(self, output_folder: str) -> bool:
        path = str(output_folder or "").strip()
        if path == "":
            return False

        cache_dir = os.path.join(path, "cache")
        return any(
            os.path.isfile(candidate)
            for candidate in (
                os.path.join(cache_dir, "project.json"),
                os.path.join(cache_dir, "items.json"),
                os.path.join(cache_dir, CacheManager.RESET_JOURNAL_NAME),
                os.path.join(cache_dir, CacheManager.CACHE_DB_NAME),
            )
        )

    @staticmethod
    def _get_active_platform(config: Config) -> dict:
        platform = config.get_platform(config.activate_platform)
        if not isinstance(platform, dict):
            raise ValueError("未找到当前启用的翻译平台配置")
        return copy.deepcopy(platform)

    @classmethod
    def _get_resume_runtime_provider(cls, snapshot: dict, config: Config) -> dict:
        request_policy = snapshot.get("request_policy", {})
        persisted = (
            request_policy.get("provider", {})
            if isinstance(request_policy, Mapping)
            else {}
        )
        persisted = dict(persisted) if isinstance(persisted, Mapping) else {}

        current: dict = {}
        persisted_id = persisted.get("id")
        if isinstance(config.platforms, list):
            for platform in config.platforms:
                if isinstance(platform, dict) and platform.get("id") == persisted_id:
                    current = platform
                    break
        if persisted and not current:
            raise ValueError("快照中的翻译接口已不存在，请恢复原接口后再继续翻译")
        if not current:
            current = cls._get_active_platform(config)

        if not persisted:
            return copy.deepcopy(current)
        return merge_provider_credentials(persisted, current)

    @staticmethod
    def _copy_entry_config(data: dict) -> Config:
        supplied = data.get("config") if isinstance(data, dict) else None
        config = copy.deepcopy(supplied) if isinstance(supplied, Config) else Config().load()

        overrides = {
            "input_folder": data.get("input_folder"),
            "output_folder": data.get("output_folder"),
            "source_language": data.get("source_language"),
            "target_language": data.get("target_language"),
        }
        for key, value in overrides.items():
            if value is not None and value != "":
                setattr(config, key, str(value) if key.endswith("_folder") else value)
        return config

    @staticmethod
    def _remember_runtime_manifest(config: Config) -> None:
        """记录本次 Ren'Py 运行目录，供页面重开后恢复实际缓存。"""
        try:
            paths = RenpyProjectPaths.from_config(config)
            if paths is None:
                return
            if not paths.game_dir.is_dir():
                # 专用字段残留但项目已不存在时，不要为普通文本任务写入
                # 一个指向旧项目的清单。
                return
            if not any(
                str(getattr(config, field, "") or "").strip()
                for field in ("renpy_project_path", "renpy_game_folder", "renpy_tl_folder")
            ):
                return

            output_folder = getattr(config, "output_folder", "")
            input_folder = getattr(config, "input_folder", "")
            application_target_dir = paths.application_target_dir
            existing = read_run_manifest(paths)

            def same_path(left, right) -> bool:
                if not left or not right:
                    return False
                return os.path.normcase(os.path.abspath(str(left))) == os.path.normcase(
                    os.path.abspath(str(right))
                )

            if getattr(config, "renpy_hook_translate", False):
                run_kind = "hook"
            elif getattr(config, "renpy_source_translate", False):
                run_kind = "source"
            elif existing is not None and same_path(
                output_folder,
                existing.get("output_folder"),
            ):
                # A resumed incremental run may be launched after the global config
                # has been restored to the stable main paths.  Keep the manifest's
                # scope when the selected cache still matches it.
                run_kind = str(existing.get("run_kind", "translation") or "translation")
                input_folder = existing.get("input_folder") or input_folder
                application_target_dir = (
                    existing.get("application_target_dir") or application_target_dir
                )
            elif same_path(
                output_folder,
                paths.translation_output_dir.parent / f"{paths.language}_new",
            ):
                run_kind = "incremental"
            else:
                run_kind = "translation"
            write_run_manifest(
                paths,
                output_folder = output_folder,
                input_folder = input_folder,
                application_target_dir = application_target_dir,
                run_kind = run_kind,
                status = "active",
            )
        except Exception as exc:
            # 清单是恢复辅助信息，写入失败不能阻断翻译主流程。
            LogManager.get().warning(f"写入 Ren'Py 运行清单失败：{exc}")

    @staticmethod
    def _assets_have_project_state(assets: ProjectAssets) -> bool:
        return bool(
            assets.revision > 0
            or assets.updated_at
            or assets.worldbook_enabled
            or assets.character_cards_enabled
            or assets.glossary_enabled
            or assets.do_not_translate_enabled
            or len(assets.worldbook) > 0
            or len(assets.character_cards) > 0
            or len(assets.glossary) > 0
            or len(assets.do_not_translate) > 0
        )

    def _load_project_assets(self, config: Config) -> ProjectAssets:
        project = self.cache_manager.get_project()
        runtime_assets = ProjectAssets.from_dict(project.get_project_assets())

        # 工作台资产按项目主输出目录持久化；当前运行可能是
        # ``<lang>_new`` 增量目录。即使运行缓存已有资产，也要比较 revision，
        # 避免旧的增量快照覆盖主工作台后来更新的角色卡或世界观。
        try:
            stable_state = ProjectAssetsRepository.from_config(config).load(config)
            stable_assets = ProjectAssets.from_dict(stable_state.assets)
        except Exception as exc:
            if self._assets_have_project_state(runtime_assets):
                self.warning(f"[ASSET] 读取主项目资产失败，继续使用当前运行快照：{exc}")
                return runtime_assets
            self.warning(f"[ASSET] 读取项目资产失败，回退到全局配置：{exc}")
            stable_assets = ProjectAssets.from_config(config)

        runtime_has_state = self._assets_have_project_state(runtime_assets)
        stable_has_state = self._assets_have_project_state(stable_assets)
        if (
            stable_has_state
            and (
                not runtime_has_state
                or stable_assets.revision >= runtime_assets.revision
            )
        ) or not runtime_has_state:
            project.set_project_assets(stable_assets)
            return stable_assets
        return runtime_assets

    def _build_task_context(
        self,
        config: Config,
        assets: ProjectAssets,
        platform: dict,
        *,
        legacy_bootstrap: bool = False,
    ) -> TranslationTaskContext:
        prompt = PromptBuilder(config).build_task_prompt_snapshot()
        if platform.get("api_format") in (
            Base.APIFormat.SAKURALLM,
            Base.APIFormat.DEEPL,
            Base.APIFormat.DEEPLX,
        ):
            prompt["protocol"] = Config.OUTPUT_PROTOCOL_JSONLINE

        return TranslationTaskContext.from_config(
            config,
            assets,
            prompt = prompt,
            legacy_bootstrap = legacy_bootstrap,
        )

    def _run_asset_preflight(self, context: TranslationTaskContext, data: dict) -> None:
        builder = PromptBuilder(context)
        fixed_prompt = "\n\n".join(
            section
            for section in (
                builder.build_main(),
                builder.build_worldbook_context(),
            )
            if section.strip() != ""
        )
        result = TranslationPreflightService.check(
            context.assets,
            fixed_prompt = fixed_prompt,
            provider = context.runtime_provider,
            reserved_output_tokens = TaskRequester.DEFAULT_MAX_OUTPUT_TOKENS,
        )
        if not result.can_start:
            raise ValueError(
                "固定提示词与完整世界观超过模型上下文窗口："
                + ", ".join(result.errors)
            )
        if result.has_effective_assets or bool(data.get("preflight_confirmed", False)):
            return

        message = getattr(
            Localizer.get(),
            "translation_preflight_missing_assets",
            "当前项目没有可用的已确认资产；可先打开工作台或仍然继续翻译。",
        )
        self.emit(Base.Event.APP_TOAST_SHOW, {
            "type": Base.ToastType.WARNING,
            "message": message,
        })

    def _initialize_translation_run(
        self,
        current_config: Config,
        status: Base.TranslationStatus,
        data: dict,
    ) -> TranslationTaskContext:
        self._raise_if_stop_requested()
        output_folder = current_config.output_folder
        self.cache_manager.cache_use_sqlite = bool(current_config.cache_use_sqlite)
        current_platform = self._get_active_platform(current_config)
        try:
            normalized_status = Base.normalize_translation_status(status)
        except (TypeError, ValueError):
            normalized_status = Base.TranslationStatus.UNTRANSLATED

        if normalized_status in Base.PROJECT_RESUMABLE_STATUSES:
            self._raise_if_stop_requested()
            self.cache_manager.load_from_file(output_folder, strict = True)
            project = self.cache_manager.get_project()
            snapshot = project.get_translation_snapshot()
            if snapshot is None:
                self._raise_if_stop_requested()
                assets = self._load_project_assets(current_config)
                context = self._build_task_context(
                    current_config,
                    assets,
                    current_platform,
                    legacy_bootstrap = True,
                )
                project.set_translation_snapshot(context)
                self._raise_if_stop_requested()
                self.cache_manager.save_to_file(
                    project = project,
                    items = self.cache_manager.get_items(),
                    output_folder = output_folder,
                    strict = True,
                )
            else:
                self._raise_if_stop_requested()
                runtime_provider = self._get_resume_runtime_provider(snapshot, current_config)
                context = TranslationTaskContext.from_snapshot(
                    snapshot,
                    runtime_provider = runtime_provider,
                )

            self._run_asset_preflight(context, data)
            self._raise_if_stop_requested()
            return context

        fresh_project, items = FileManager(current_config).read_from_path()
        self._raise_if_stop_requested()
        if self._has_cache_snapshot(output_folder):
            self.cache_manager.load_project_from_file(output_folder, strict = True)
            if self.cache_manager.get_project().get_id() == "":
                # 工作台可以在首次翻译前先创建只含长期资产的项目记录。
                # 此时只补项目 ID，不能用 fresh_project 覆盖已有 assets/candidates。
                self.cache_manager.get_project().set_id(fresh_project.get_id())
        else:
            self.cache_manager.set_project(fresh_project)

        assets = self._load_project_assets(current_config)
        context = self._build_task_context(current_config, assets, current_platform)
        self._run_asset_preflight(context, data)
        self._raise_if_stop_requested()
        progress = self._new_progress_extras(
            sum(
                1
                for item in items
                if item.get_status() == Base.TranslationStatus.UNTRANSLATED
            )
        )
        self._raise_if_stop_requested()
        self.cache_manager.reset_translation_run(
            items,
            output_folder,
            snapshot = context,
            progress = progress,
        )
        return context

    def _completed_item_count(self) -> int:
        return sum(
            1
            for item in self.cache_manager.get_items()
            if Base.is_item_completed(item.get_status())
        )

    def _merge_analysis_candidates(self, candidates: list[dict[str, str]]) -> None:
        if not candidates:
            return

        with self.data_lock:
            project = self.cache_manager.get_project()
            payload = project.get_analysis_candidates()
            items = payload.get("items", []) if isinstance(payload, dict) else []
            items = [copy.deepcopy(item) for item in items if isinstance(item, dict)]
            known_sources = {
                str(item.get("source", item.get("src", ""))).strip().casefold()
                for item in items
            }

            for candidate in candidates:
                source = str(candidate.get("source", "") or "").strip()
                target = str(candidate.get("target", "") or "").strip()
                source_key = source.casefold()
                if source == "" or target == "" or source_key in known_sources:
                    continue
                known_sources.add(source_key)
                items.append({
                    "record_id": TermAsset.build_record_id("ANALYSIS", source),
                    "origin": "ANALYSIS",
                    "source": source,
                    "target": target,
                    "enabled": True,
                    "regex": False,
                    "note": str(candidate.get("note", "") or "").strip(),
                })

            payload = copy.deepcopy(payload) if isinstance(payload, dict) else {}
            payload["schema_version"] = 1
            payload["items"] = items
            project.set_analysis_candidates(payload)
            runtime_output = str(getattr(self.config, "output_folder", "") or "").strip()
            if runtime_output:
                self.cache_manager.require_save_to_file(runtime_output)

            # 分析候选属于项目长期资产；增量运行写入 ``*_new`` 时也同步到
            # 稳定主输出，应用翻译后工作台不会丢失本轮候选。
            try:
                stable_config = getattr(self, "config", None)
                if stable_config is not None:
                    ProjectAssetsRepository.from_config(stable_config).save_analysis_candidates(payload)
            except Exception as exc:
                self.warning(f"[ASSET] 保存分析候选到稳定项目失败：{exc}")

    def _merge_analysis_candidates_for_run(
        self,
        run_id: int | None,
        cancel_event: threading.Event | None,
        candidates: list[dict[str, str]],
    ) -> None:
        """只接收当前运行产生的候选术语，丢弃停止后的迟到结果。"""
        if self._should_stop_requested(run_id, cancel_event):
            return
        self._merge_analysis_candidates(candidates)

    def _run_translation_task(
        self,
        task: TranslatorTask,
        current_round: int,
        run_id: int | None,
        cancel_event: threading.Event | None,
    ) -> dict[str, object]:
        """在线程池工作线程中绑定本轮取消令牌并执行任务。"""
        TaskRequester.bind_run_cancel_event(cancel_event)
        try:
            if self._should_stop_requested(run_id, cancel_event):
                return {"cancelled": True}
            return task.start(current_round)
        finally:
            TaskRequester.unbind_run_cancel_event()

    def _new_progress_extras(self, total_line: int) -> dict:
        """创建新的翻译进度统计。"""
        return {
            "start_time": time.time(),
            "total_line": total_line,
            "line": 0,
            "total_tokens": 0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "failed_line_count": 0,
            "fallback_line_count": 0,
            "line_count_mismatch_count": 0,
            "requested_line_count": 0,
            "time": 0,
        }

    def _resume_progress_extras(self) -> dict:
        """从缓存恢复翻译进度，并按当前条目状态修正已完成行数。"""
        extras = dict(self.cache_manager.get_project().get_progress() or {})
        elapsed = extras.get("time", 0) or 0
        extras["start_time"] = time.time() - elapsed
        extras["line"] = self._completed_item_count()

        for key in (
            "total_line",
            "total_tokens",
            "total_input_tokens",
            "total_output_tokens",
            "failed_line_count",
            "fallback_line_count",
            "line_count_mismatch_count",
            "requested_line_count",
            "time",
        ):
            extras.setdefault(key, 0)

        return extras

    def _merge_task_result_into_progress(self, result: dict) -> dict:
        """把单个 TranslatorTask 的返回值累加到全局进度。"""
        input_tokens = int(result.get("input_tokens", 0) or 0)
        output_tokens = int(result.get("output_tokens", 0) or 0)
        start_time = self.extras.get("start_time", time.time())

        return {
            "start_time": start_time,
            "total_line": self.extras.get("total_line", 0),
            "line": self.extras.get("line", 0) + int(result.get("row_count", 0) or 0),
            "total_tokens": self.extras.get("total_tokens", 0) + input_tokens + output_tokens,
            "total_input_tokens": self.extras.get("total_input_tokens", 0) + input_tokens,
            "total_output_tokens": self.extras.get("total_output_tokens", 0) + output_tokens,
            "failed_line_count": self.extras.get("failed_line_count", 0) + int(result.get("failed_line_count", 0) or 0),
            "fallback_line_count": self.extras.get("fallback_line_count", 0) + int(result.get("fallback_line_count", 0) or 0),
            "line_count_mismatch_count": self.extras.get("line_count_mismatch_count", 0) + int(result.get("line_count_mismatch_count", 0) or 0),
            "requested_line_count": self.extras.get("requested_line_count", 0) + int(result.get("requested_line_count", 0) or 0),
            "time": time.time() - start_time,
        }

    def _reconcile_round_progress(self, remaining: int, *, fresh_run: bool) -> None:
        """Keep run-local completed and total counts consistent after prefilters."""
        remaining = max(0, int(remaining or 0))
        try:
            completed = max(0, int(self.extras.get("line", 0) or 0))
        except (TypeError, ValueError):
            completed = 0

        if fresh_run:
            try:
                initial_total = max(0, int(self.extras.get("total_line", 0) or 0))
            except (TypeError, ValueError):
                initial_total = 0
            # Rules may complete/exclude entries before the first task is built.
            # Preserve those completed rows instead of replacing the run total
            # with only the remaining rows.
            completed = max(completed, initial_total - remaining)

        self.extras["line"] = completed
        self.extras["total_line"] = completed + remaining

    def _finish_no_items_run(self, run_id: int | None) -> None:
        """以明确的空数据结果结束任务，避免误走“用户停止”流程。"""
        progress = dict(self.cache_manager.get_project().get_progress() or {})
        progress["time"] = float(progress.get("time", 0) or 0)
        self.cache_manager.get_project().set_progress(progress)
        self.extras = progress

        if (
            self._is_translation_run_current(run_id)
            and Engine.get().release_status(Engine.Status.TRANSLATING)
        ):
            self.emit(Base.Event.TRANSLATION_UPDATE, progress)
            self.emit(Base.Event.TRANSLATION_DONE, {
                "success": False,
                "run_id": run_id,
                "error": "NO_ITEMS",
                "no_items": True,
            })

    def _is_relative_to(self, path_a: str, path_b: str) -> bool:
        try:
            return os.path.commonpath([os.path.abspath(path_a), os.path.abspath(path_b)]) == os.path.abspath(path_b)
        except Exception:
            return False

    def _validate_renpy_source_io_layout(self, config: Config | None = None) -> tuple[bool, str]:
        selected_config = config or self.config
        input_folder = str(getattr(selected_config, "input_folder", "") or "").strip()
        output_folder = str(getattr(selected_config, "output_folder", "") or "").strip()

        if input_folder == "" or output_folder == "":
            return False, "源码翻译缺少输入目录或输出目录。"

        input_path = os.path.abspath(input_folder)
        output_path = os.path.abspath(output_folder)

        if os.path.isfile(input_path):
            input_dir = os.path.dirname(input_path)
            target_output_file = os.path.join(output_path, os.path.basename(input_path))
            if os.path.abspath(target_output_file) == input_path:
                return False, "源码翻译禁止直接覆盖原始 .rpy 文件，请使用独立输出目录。"
            return True, ""

        if input_path == output_path:
            return False, "源码翻译要求输入目录和输出目录分离，不能直接写回原 game 目录。"
        if self._is_relative_to(output_path, input_path):
            return False, "源码翻译的输出目录不能放在输入目录内部，否则会污染原文缓存。"
        if self._is_relative_to(input_path, output_path):
            return False, "源码翻译的输入目录不能放在输出目录内部，请使用完全分离的目录。"
        return True, ""

    # 实际的翻译流程
    def translation_start_task(
        self,
        event: str,
        data: dict,
        run_id: int | None = None,
        cancel_event: threading.Event | None = None,
    ) -> None:
        self._bind_run_context(run_id, cancel_event)
        try:
            data = data if isinstance(data, dict) else {}
            status = data.get("status", Base.TranslationStatus.UNTRANSLATED)

            if self._should_stop_requested(run_id, cancel_event):
                return None

            # 兼容直接调用入口；事件入口已经原子占用 TRANSLATING。
            engine_status = Engine.get().get_status()
            if run_id is not None:
                # 事件入口登记的线程不能在极早停止后重新把 IDLE 占回去。
                if engine_status != Engine.Status.TRANSLATING:
                    return None
            elif engine_status == Engine.Status.IDLE:
                if Engine.get().has_single_tasks():
                    return None
                Engine.get().set_status(Engine.Status.TRANSLATING)
            elif engine_status != Engine.Status.TRANSLATING:
                return None

            # 预处理提示（解析/生成任务阶段）
            self.emit(Base.Event.TRANSLATION_UPDATE, {
                "phase": "preparing",
                "message": "预处理中…",
            })

            # 重置无状态组件，然后在唯一边界创建/恢复不可变任务上下文。
            TextProcessor.reset()
            TaskRequester.reset()
            # 丢弃上一轮停止后遗留的延迟保存目标，避免后台服务线程把
            # 新一轮条目写回旧项目/旧语言目录。
            with self.cache_manager.LOCK:
                self.cache_manager.require_flag = False
                self.cache_manager.require_path = ""
            if self._should_stop_requested(run_id, cancel_event):
                return None
            PromptBuilder.reset()
            current_config = self._copy_entry_config(data)
            if self._should_stop_requested(run_id, cancel_event):
                return None
            self._last_runtime_output_folder = current_config.output_folder
            self._active_cache_output_folder = ""
            self._remember_runtime_manifest(current_config)

            if getattr(current_config, "renpy_source_translate", False):
                valid_layout, layout_message = self._validate_renpy_source_io_layout(current_config)
                if not valid_layout:
                    self.warning(f"[INIT] 已阻止不安全的源码翻译路径: {layout_message}")
                    self.emit(Base.Event.APP_TOAST_SHOW, {
                        "type": Base.ToastType.WARNING,
                        "message": layout_message,
                    })
                    if self._is_translation_run_current(run_id):
                        Engine.get().release_status(Engine.Status.TRANSLATING)
                        self.emit(Base.Event.TRANSLATION_DONE, {
                            "success": False,
                            "run_id": run_id,
                            "error": "INVALID_SOURCE_LAYOUT",
                        })
                    return None

            try:
                task_context = self._initialize_translation_run(
                    current_config,
                    status,
                    data,
                )
                self._raise_if_stop_requested()
                runtime_config = task_context.to_runtime_config(current_config)
                runtime_platform = self._get_active_platform(runtime_config)
                self.task_context = task_context
                self._active_cache_output_folder = current_config.output_folder
                self.config = runtime_config
                self.platform = runtime_platform
                self._translation_run_initialized = True
            except TranslationCancelled:
                # 用户主动取消准备阶段，不显示错误，也不写入未完成的缓存。
                return None
            except Exception as e:
                if not self._should_stop_requested(run_id, cancel_event):
                    self.error("[INIT] 翻译任务上下文初始化失败", e)
                    self.emit(Base.Event.APP_TOAST_SHOW, {
                        "type": Base.ToastType.ERROR,
                        "message": str(e),
                    })
                    Engine.get().release_status(Engine.Status.TRANSLATING)
                    self.emit(Base.Event.TRANSLATION_DONE, {
                        "success": False,
                        "run_id": run_id,
                        "error": type(e).__name__,
                    })
                return None

            local_flag = self.initialize_local_flag()
            max_workers, rpm_threshold = self.initialize_max_workers()

            # 添加初始化日志
            self.info(f"[INIT] 配置加载完成: platform={self.platform.get('name', 'unknown')}, model={self.platform.get('model', 'unknown')}")
            self.info(f"[INIT] 最大并发: {max_workers}, RPM限制: {rpm_threshold}")

            if self._should_stop_requested():
                return None

            if self.cache_manager.get_item_count() == 0:
                self.emit(Base.Event.APP_TOAST_SHOW, {
                    "type": Base.ToastType.WARNING,
                    "message": Localizer.get().translator_no_items,
                })
                self._finish_no_items_run(run_id)
                return None

            try:
                normalized_status = Base.normalize_translation_status(status)
            except (TypeError, ValueError):
                normalized_status = Base.TranslationStatus.UNTRANSLATED

            # 续译恢复旧进度；新任务的初始进度已和 snapshot 一起持久化。
            if normalized_status in Base.PROJECT_RESUMABLE_STATUSES:
                self.extras = self._resume_progress_extras()
            else:
                total_untranslated = self.cache_manager.get_item_count_by_status(Base.TranslationStatus.UNTRANSLATED)
                self.info(f"[INIT] 初始化进度: 待翻译 {total_untranslated} 行")
                self.extras = self.cache_manager.get_project().get_progress()
                if not self.extras:
                    self.extras = self._new_progress_extras(total_untranslated)

            # 更新翻译进度
            self.cache_manager.get_project().set_progress(self.extras)
            self.cache_manager.get_project().set_status(Base.TranslationStatus.TRANSLATING)
            self.emit(Base.Event.TRANSLATION_UPDATE, self.extras)

            if self._should_stop_requested():
                return None

            # 规则过滤
            self.rule_filter(self.cache_manager.get_items())
            if self._should_stop_requested():
                return None

            # 语言过滤
            self.language_filter(self.cache_manager.get_items())
            if self._should_stop_requested():
                return None

            # Older validators may have left unchanged technical tokens (for
            # example ``USB``) in a failed state.  Reconcile cached results with
            # the current preservation rules before creating remote requests.
            accepted_preserved = self.accept_preserved_untranslated_items(
                self.cache_manager.get_items()
            )
            if accepted_preserved:
                remaining = self.cache_manager.get_item_count_by_status(
                    Base.TranslationStatus.UNTRANSLATED
                )
                try:
                    total_line = max(0, int(self.extras.get("total_line", 0)))
                except (TypeError, ValueError):
                    total_line = 0
                if total_line:
                    self.extras["line"] = max(
                        int(self.extras.get("line", 0) or 0),
                        total_line - remaining,
                    )
                self.cache_manager.get_project().set_progress(self.extras)
                self.emit(Base.Event.TRANSLATION_UPDATE, self.extras)

            # MTool 优化器预处理
            self.mtool_optimizer_preprocess(self.cache_manager.get_items())
            if self._should_stop_requested():
                return None

            # 自适应批大小是本次运行的局部状态，不写回任务快照或 Config。
            initial_token_threshold = max(1, int(self.config.token_threshold))

            # 开始循环
            for current_round in range(self.config.max_round):
                if current_round == 0:
                    self.emit(Base.Event.TRANSLATION_UPDATE, {
                        "phase": "preparing",
                        "message": "生成任务中…",
                    })
                # 检测是否需要停止任务
                # 目的是避免用户正好在两轮之间停止任务
                if self._should_stop_requested():
                    return None

                # 第一轮且不是继续翻译时，记录任务的总行数
                if current_round == 0:
                    remaining = self.cache_manager.get_item_count_by_status(Base.TranslationStatus.UNTRANSLATED)
                    self._reconcile_round_progress(
                        remaining,
                        fresh_run=(normalized_status == Base.TranslationStatus.UNTRANSLATED),
                    )

                # 第二轮开始切分（基于初始值计算，避免累积除法）
                # 采用 2 倍率衰减而非 3 倍率，避免重试时批次过快坍缩到单行，
                # 在保证最终能逐行隔离顽固错误的同时，显著减少串行化、提升吞吐。
                round_token_threshold = max(
                    1,
                    int(initial_token_threshold / (2 ** current_round)),
                )

                # 生成缓存数据条目片段
                chunk_line_threshold = round_token_threshold
                if getattr(self.config, "single_line_translation_enable", False) and self.platform.get("api_format") not in (Base.APIFormat.DEEPL, Base.APIFormat.DEEPLX):
                    chunk_line_threshold = 1
                chunks, precedings = self.cache_manager.generate_item_chunks(
                    chunk_line_threshold,
                    self.config.preceding_lines_threshold,
                )

                # 第四轮开始才禁用参考上文（多保留一轮上下文以提升重试译文质量）
                if current_round >= 3:
                    precedings = [[] for _ in range(len(precedings))]

                # 生成翻译任务
                self.print("")
                tasks: list[TranslatorTask] = []
                with ProgressBar(transient = False) as progress:
                    pid = progress.new()
                    for items, precedings in zip(chunks, precedings):
                        progress.update(pid, advance = 1, total = len(chunks))
                        task_config = self.task_context.to_runtime_config(self.config)
                        task_config.token_threshold = round_token_threshold
                        tasks.append(TranslatorTask(
                            self.task_context,
                            self.platform,
                            local_flag,
                            items,
                            precedings,
                            runtime_config = task_config,
                            candidate_sink = lambda candidates, current_run_id = run_id, current_cancel_event = cancel_event: self._merge_analysis_candidates_for_run(
                                current_run_id,
                                current_cancel_event,
                                candidates,
                            ),
                        ))

                # 打印日志
                self.info(Localizer.get().translator_task_generation_log.replace("{COUNT}", str(len(chunks))))

                # 输出开始翻译的日志
                self.print("")
                self.print("")
                self.info(f"{Localizer.get().translator_current_round} - {current_round + 1}")
                self.info(f"{Localizer.get().translator_max_round} - {self.config.max_round}")
                self.print("")
                self.info(f"{Localizer.get().translator_name} - {self.platform.get('name')}")
                self.info(f"{Localizer.get().translator_api_url} - {self.platform.get('api_url')}")
                self.info(f"{Localizer.get().translator_model} - {self.platform.get('model')}")
                if getattr(self.config, "single_line_translation_enable", False) and self.platform.get("api_format") not in (Base.APIFormat.DEEPL, Base.APIFormat.DEEPLX):
                    self.info("[INIT] 单行翻译模式已启用：每次请求只处理一行文本")
                self.print("")
                if self.platform.get("api_format") != Base.APIFormat.SAKURALLM:
                    self.info(PromptBuilder(self.task_context).build_main())
                    self.print("")

                # 开始执行翻译任务
                task_limiter = TaskLimiter(rps = max_workers, rpm = rpm_threshold, max_concurrency = max_workers)
                with ProgressBar(transient = True) as progress:
                    pid = progress.new()
                    executor = concurrent.futures.ThreadPoolExecutor(
                        max_workers = max_workers,
                        thread_name_prefix = Engine.TASK_PREFIX,
                    )
                    with self.data_lock:
                        self._active_executor = executor

                    stopping = False
                    try:
                        for task in tasks:
                            # 检测是否需要停止任务
                            # 目的是绕过限流器，快速结束所有剩余任务
                            if Engine.get().get_status() == Engine.Status.STOPPING:
                                stopping = True
                                break

                            if not task_limiter.acquire(
                                lambda: self._should_stop_requested(run_id, cancel_event)
                            ):
                                stopping = True
                                break

                            if not task_limiter.wait(
                                lambda: self._should_stop_requested(run_id, cancel_event)
                            ):
                                task_limiter.release()
                                stopping = True
                                break

                            try:
                                future = executor.submit(
                                    self._run_translation_task,
                                    task,
                                    current_round,
                                    run_id,
                                    cancel_event,
                                )
                            except RuntimeError:
                                task_limiter.release()
                                stopping = True
                                break
                            future.add_done_callback(task_limiter.release)
                            future.add_done_callback(
                                lambda future, current_run_id = run_id, current_cancel_event = cancel_event: self.task_done_callback(
                                    future,
                                    pid,
                                    progress,
                                    current_run_id,
                                    current_cancel_event,
                                )
                            )
                    finally:
                        # 停止可能发生在最后一次 submit 之后，不能只依赖循环内
                        # 的局部标志；否则会在 shutdown(wait=True) 中继续等待网络任务。
                        stopping = stopping or self._should_stop_requested()
                        try:
                            executor.shutdown(
                                wait = not stopping,
                                cancel_futures = stopping,
                            )
                        except Exception:
                            # 关闭线程池失败不应阻塞后续停止收尾；正在运行的任务
                            # 仍会通过取消事件自行退出。
                            pass
                        finally:
                            with self.data_lock:
                                if self._active_executor is executor:
                                    self._active_executor = None

                # 停止信号可能恰好在 shutdown 后到达，离开线程池后再检查一次，
                # 避免继续进入结果判断、缓存写入等昂贵阶段。
                if stopping or self._should_stop_requested():
                    return None

                # 判断是否需要继续翻译
                if self.cache_manager.get_item_count_by_status(Base.TranslationStatus.UNTRANSLATED) == 0:
                    self.cache_manager.get_project().set_status(Base.TranslationStatus.TRANSLATED)

                    # 日志
                    self.print("")
                    self.info(Localizer.get().translator_done)
                    self.info(Localizer.get().translator_writing)
                    self.print("")

                    # 通知
                    self.emit(Base.Event.APP_TOAST_SHOW, {
                        "type": Base.ToastType.SUCCESS,
                        "message": Localizer.get().translator_done,
                    })
                    break

                # 检查是否达到最大轮次
                if current_round >= self.config.max_round - 1:
                    # 日志
                    self.print("")
                    self.warning(Localizer.get().translator_fail)
                    self.warning(Localizer.get().translator_writing)
                    self.print("")

                    # 通知
                    self.emit(Base.Event.APP_TOAST_SHOW, {
                        "type": Base.ToastType.SUCCESS,
                        "message": Localizer.get().translator_fail,
                    })
                    break

            # 等待回调执行完毕；拆成短片段，确保停止请求不会被固定睡眠拖住。
            deadline = time.monotonic() + 1.0
            while time.monotonic() < deadline:
                if self._should_stop_requested():
                    return None
                time.sleep(min(0.1, max(0.0, deadline - time.monotonic())))

            if self._should_stop_requested():
                return None

            # ============ 大写特殊候选：第二次整体翻译验证 ============
            # 第一轮仍保持原文未译的大写特殊候选（2~6 位大写/数字），整体
            # 再翻译一遍。两次 AI 都未翻译（第二次干净返回原文且通过格式
            # 审查）的，判定为“不需要翻译”并标记 EXCLUDED，由合并流程连同
            # 文件溯源记入项目级判定不译清单；任一一次被翻译则保留译文。
            try:
                self._verify_uppercase_untranslated(
                    run_id,
                    cancel_event,
                    current_round + 1,
                    local_flag,
                )
            except Exception as exc:
                self.warning(f"[VERIFY] 大写特殊候选二次验证失败: {exc}")

            if self._should_stop_requested():
                return None

            # MTool 优化器后处理
            self.mtool_optimizer_postprocess(self.cache_manager.get_items())

            if self._should_stop_requested():
                return None

            # 写入缓存
            self.cache_manager.save_to_file(
                project = self.cache_manager.get_project(),
                items = self.cache_manager.get_items(),
                output_folder = self.config.output_folder,
                strict = True,
            )

            if self._should_stop_requested():
                return None

            # 检查结果并写入文件
            self.check_and_wirte_result(self.cache_manager.get_items())

            if self._should_stop_requested():
                return None

            # 只有当前运行才能释放状态并通知完成，迟到旧线程不得影响新任务。
            if self._is_translation_run_current(run_id):
                Engine.get().release_status(Engine.Status.TRANSLATING)
                self.emit(Base.Event.TRANSLATION_DONE, {
                    "success": True,
                    "run_id": run_id,
                    "output_folder": self.config.output_folder,
                })
        except Exception as e:
            if self._is_translation_run_current(run_id):
                self.error("[TRANSLATION] 翻译主流程异常终止", e)
            if (
                self._is_translation_run_current(run_id)
                and Engine.get().get_status() != Engine.Status.STOPPING
            ):
                Engine.get().release_status(Engine.Status.TRANSLATING)
                self.emit(Base.Event.APP_TOAST_SHOW, {
                    "type": Base.ToastType.ERROR,
                    "message": str(e),
                })
                self.emit(Base.Event.TRANSLATION_DONE, {
                    "success": False,
                    "run_id": run_id,
                    "error": type(e).__name__,
                })
        finally:
            self._unbind_run_context()
            current_thread = threading.current_thread()
            with self.data_lock:
                if (
                    getattr(self, "_translation_thread", None) is current_thread
                    and (
                        run_id is None
                        or getattr(self, "_translation_run_id", 0) == run_id
                    )
                ):
                    self._translation_thread = None

    # 初始化本地标识
    def initialize_local_flag(self) -> bool:
        return re.search(
            r"^http[s]*://localhost|^http[s]*://\d+\.\d+\.\d+\.\d+",
            self.platform.get("api_url"),
            flags = re.IGNORECASE,
        ) is not None

    # 初始化速度控制器
    def initialize_max_workers(self) -> tuple[int, int]:
        try:
            max_workers: int = max(0, int(self.config.max_workers))
        except (TypeError, ValueError):
            max_workers = 0
        try:
            rpm_threshold: int = max(0, int(self.config.rpm_threshold))
        except (TypeError, ValueError):
            rpm_threshold = 0

        # 当 max_workers = 0 时，尝试获取 llama.cpp 槽数
        if max_workers == 0:
            try:
                response_json = None
                response = httpx.get(re.sub(r"/v1$", "", self.platform.get("api_url")) + "/slots")
                response.raise_for_status()
                response_json = response.json()
            except Exception as e:
                self.print("")
                self.debug("", e)
            if isinstance(response_json, list) and len(response_json) > 0:
                max_workers = len(response_json)

        if max_workers == 0 and rpm_threshold == 0:
            max_workers = 8
            rpm_threshold = 0
        elif max_workers > 0 and rpm_threshold == 0:
            pass
        elif max_workers == 0 and rpm_threshold > 0:
            # RPM 不是并发数；没有本地槽位信息时使用小的安全默认值，
            # 避免把线程池误建成 8192 个线程导致内存和停止操作卡顿。
            max_workers = min(8, max(1, rpm_threshold))

        # 配置文件可能来自旧版本或手工编辑，给线程池设置最终上限。
        max_workers = min(max_workers, 64)

        return max_workers, rpm_threshold

    # 规则过滤
    def accept_preserved_untranslated_items(self, items: list[CacheItem]) -> int:
        """Complete unchanged cached items explicitly allowed by validation."""
        checker = ResponseChecker(self.config, items)
        accepted = 0
        for item in items:
            if item.get_status() != Base.TranslationStatus.UNTRANSLATED:
                continue
            src = str(item.get_src() or "")
            dst = str(item.get_dst() or "")
            if src == "" or src != dst:
                continue
            if checker.is_preserve_allowed(src, dst, item):
                item.set_status(Base.TranslationStatus.TRANSLATED)
                accepted += 1
        return accepted

    def _verify_uppercase_untranslated(
        self,
        run_id: int | None,
        cancel_event: threading.Event | None,
        round_index: int,
        local_flag: bool,
    ) -> int:
        """第二次整体翻译：对第一轮仍未被翻译的大写特殊候选再整体翻译一遍。

        判定规则：两次 AI 都未翻译（第二次响应干净返回原文、通过格式审查）
        的候选才是“不需要翻译”的内容，标记为 EXCLUDED 并记入项目级判定
        不译清单（保留文件溯源）；任一一次被翻译则保留该译文。
        """
        from module.Text.SkipRules import RE_UPPERCASE_ACRONYM_CANDIDATE
        from module.Response.ResponseChecker import ResponseChecker

        items = [
            item
            for item in self.cache_manager.get_items()
            if item.get_status() == Base.TranslationStatus.UNTRANSLATED
            and isinstance(item.get_src(), str)
            and RE_UPPERCASE_ACRONYM_CANDIDATE.fullmatch(item.get_src().strip())
        ]
        if not items or self._should_stop_requested(run_id, cancel_event):
            return 0

        self.info(f"[VERIFY] 大写特殊候选第二次整体翻译：{len(items)} 条")
        checker = ResponseChecker(self.config, items)
        excluded: list[CacheItem] = []
        chunk_size = 40
        chunks = [
            items[index : index + chunk_size]
            for index in range(0, len(items), chunk_size)
        ]
        for chunk in chunks:
            if self._should_stop_requested(run_id, cancel_event):
                break
            task_config = self.task_context.to_runtime_config(self.config)
            try:
                task = TranslatorTask(
                    self.task_context,
                    self.platform,
                    local_flag,
                    chunk,
                    [[] for _ in chunk],
                    runtime_config=task_config,
                    candidate_sink=lambda candidates, cid=run_id, ce=cancel_event: self._merge_analysis_candidates_for_run(
                        cid,
                        ce,
                        candidates,
                    ),
                )
                task.start(round_index)
            except Exception as exc:
                self.warning(f"[VERIFY] 第二次翻译请求失败: {exc}")
                continue
            for item in chunk:
                if item.get_status() != Base.TranslationStatus.UNTRANSLATED:
                    continue
                try:
                    checks = checker.check(
                        [str(item.get_src() or "")],
                        [str(item.get_dst() or "")],
                        item.get_text_type(),
                        line_items=[item],
                    )
                except Exception:
                    continue
                # 只有“干净返回原文”才构成未翻译证据；请求失败/格式错误
                # （FAIL_*）不判定为不需要翻译。
                if checks == [ResponseChecker.Error.LINE_ERROR_SIMILARITY]:
                    item.set_status(Base.TranslationStatus.EXCLUDED)
                    excluded.append(item)

        if excluded:
            self._record_verified_declined(excluded)
            self.info(f"[VERIFY] 两次都未翻译，判定不译 {len(excluded)} 条")
        return len(excluded)

    def _record_verified_declined(self, items: list[CacheItem]) -> None:
        """把二次验证判定不译的候选连同文件溯源记入项目清单。"""
        try:
            from module.Renpy.ProjectPaths import RenpyProjectPaths
            from module.Extract.ReplaceGenerator import record_declined_candidates

            paths = RenpyProjectPaths.from_config(self.config)
            if paths is None:
                return
            tl_name = paths.language or "chinese"
            srcs = {str(item.get_src() or "") for item in items if item.get_src()}
            source_map = {
                str(item.get_src() or ""): str(item.get_file_path() or "")
                for item in items
                if item.get_src()
            }
            recorded = record_declined_candidates(
                paths.project_root,
                tl_name,
                srcs,
                source_map=source_map,
            )
            if recorded:
                self.info(f"[VERIFY] 已记录 {recorded} 条判定不译候选（含溯源）")
        except Exception as exc:
            self.warning(f"[VERIFY] 记录判定不译候选失败: {exc}")

    def rule_filter(self, items: list[CacheItem]) -> None:
        if len(items) == 0:
            return None

        # 筛选
        self.print("")
        count: int = 0
        with ProgressBar(transient = False) as progress:
            pid = progress.new()
            for item in items:
                if self._should_stop_requested():
                    return None
                progress.update(pid, advance = 1, total = len(items))
                if RuleFilter.filter(item.get_src()) == True:
                    count = count + 1
                    item.set_status(Base.TranslationStatus.EXCLUDED)

        # 打印日志
        self.info(Localizer.get().translator_rule_filter_log.replace("{COUNT}", str(count)))

    # 语言过滤
    def language_filter(self, items: list[CacheItem]) -> None:
        if len(items) == 0:
            return None

        # 筛选
        self.print("")
        count: int = 0
        with ProgressBar(transient = False) as progress:
            pid = progress.new()
            for item in items:
                if self._should_stop_requested():
                    return None
                progress.update(pid, advance = 1, total = len(items))
                if LanguageFilter.filter(item.get_src(), self.config.source_language) == True:
                    count = count + 1
                    item.set_status(Base.TranslationStatus.EXCLUDED)

        # 打印日志
        self.info(Localizer.get().translator_language_filter_log.replace("{COUNT}", str(count)))

    # MTool 优化器预处理
    def mtool_optimizer_preprocess(self, items: list[CacheItem]) -> None:
        if len(items) == 0 or self.config.mtool_optimizer_enable == False:
            return None

        # 筛选
        self.print("")
        count: int = 0
        items_kvjson: list[CacheItem] = []
        with ProgressBar(transient = False) as progress:
            pid = progress.new()
            for item in items:
                if self._should_stop_requested():
                    return None
                progress.update(pid, advance = 1, total = len(items))
                if item.get_file_type() == CacheItem.FileType.KVJSON:
                    items_kvjson.append(item)

        # 按文件路径分组
        group_by_file_path: dict[str, list[CacheItem]] = {}
        for item in items_kvjson:
            group_by_file_path.setdefault(item.get_file_path(), []).append(item)

        # 分别处理每个文件的数据
        for items_by_file_path in group_by_file_path.values():
            # 找出子句
            target = set()
            for item in items_by_file_path:
                src = item.get_src()
                if src.count("\n") > 0:
                    target.update([line.strip() for line in src.splitlines() if line.strip() != ""])

            # 移除子句
            for item in items_by_file_path:
                if item.get_src() in target:
                    count = count + 1
                    item.set_status(Base.TranslationStatus.EXCLUDED)

        # 打印日志
        self.info(Localizer.get().translator_mtool_optimizer_pre_log.replace("{COUNT}", str(count)))

    # MTool 优化器后处理
    def mtool_optimizer_postprocess(self, items: list[CacheItem]) -> None:
        if len(items) == 0 or self.config.mtool_optimizer_enable == False:
            return None

        # 筛选
        self.print("")
        items_kvjson: list[CacheItem] = []
        with ProgressBar(transient = True) as progress:
            pid = progress.new()
            for item in items:
                progress.update(pid, advance = 1, total = len(items))
                if item.get_file_type() == CacheItem.FileType.KVJSON:
                    items_kvjson.append(item)

        # 按文件路径分组
        group_by_file_path: dict[str, list[CacheItem]] = {}
        for item in items_kvjson:
            group_by_file_path.setdefault(item.get_file_path(), []).append(item)

        # 分别处理每个文件的数据
        for items_by_file_path in group_by_file_path.values():
            for item in items_by_file_path:
                src = item.get_src()
                dst = item.get_dst()
                if src.count("\n") > 0:
                    for src_line, dst_line in zip_longest(src.splitlines(), dst.splitlines(), fillvalue = ""):
                        item_ex = CacheItem.from_dict(item.asdict())
                        item_ex.set_src(src_line.strip())
                        item_ex.set_dst(dst_line.strip())
                        item_ex.set_row(len(items_by_file_path))
                        items.append(item_ex)

        # 打印日志
        self.info(Localizer.get().translator_mtool_optimizer_post_log)

    # 检查结果并写入文件
    def check_and_wirte_result(self, items: list[CacheItem]) -> None:
        # 检查结果（异常不影响写文件）
        try:
            ResultChecker(self.config, items).check()
        except Exception as e:
            self.warning(f"[ResultChecker] 检查阶段出现异常，已跳过: {e}")

        # 写入文件
        # 写回失败时 write_to_path 会抛出，但兜底注入仍要按写回报告尝试一次，
        # 之后再把原始异常抛给调用方，保证失败不会被静默吞掉。
        try:
            FileManager(self.config).write_to_path(items)
        except Exception:
            self._auto_reinject_on_writeback_fail(items)
            raise
        self.info(f"[WRITEBACK] 输出目录写回完成: {self.config.output_folder}")
        self._auto_reinject_on_writeback_fail(items)
        self.print("")
        self.info(Localizer.get().translator_write.replace("{PATH}", self.config.output_folder))
        self.print("")

        # 打开输出文件夹
        if self.config.output_folder_open_on_finish == True:
            webbrowser.open(os.path.abspath(self.config.output_folder))

    def _auto_reinject_on_writeback_fail(self, items: list[CacheItem]) -> None:
        """写回失败时自动从缓存再次注入（兜底）。"""
        try:
            report_path = os.path.join(self.config.output_folder, "writeback_report_renpy.json")
            if not os.path.isfile(report_path):
                return

            with open(report_path, "r", encoding="utf-8") as reader:
                report = json.load(reader)

            if not isinstance(report, list):
                return

            need_reinject = False
            for entry in report:
                if not isinstance(entry, dict):
                    continue
                translated = entry.get("translated_items", 0)
                applied = entry.get("applied", 0)
                if isinstance(translated, int) and isinstance(applied, int):
                    if translated > 0 and applied == 0:
                        need_reinject = True
                        break

            if not need_reinject:
                return

            reinject_config = copy.deepcopy(self.config)
            reinject_config.output_folder = self.config.output_folder
            reinject_config.input_folder = self.config.output_folder
            self.warning(f"[REINJECT] 检测到写回失败，自动重新注入：{self.config.output_folder}")

            # 重新从缓存读取，避免内存中的条目与写回基准不一致
            cache_manager = CacheManager(service = False)
            cache_manager.load_items_from_file(self.config.output_folder)
            reinject_items = cache_manager.get_items()
            FileManager(reinject_config).write_to_path(reinject_items)
            self.info(f"[REINJECT] 自动注入完成：{self.config.output_folder}")
        except Exception as exc:
            self.warning(f"[REINJECT] 自动注入失败: {exc}")

    # 翻译任务完成时
    def task_done_callback(
        self,
        future: concurrent.futures.Future,
        pid: TaskID,
        progress: ProgressBar,
        run_id: int | None = None,
        cancel_event: threading.Event | None = None,
    ) -> None:
        # 停止任务时不再更新进度/写缓存，避免 UI 卡顿或进度对象已释放导致异常
        # 线程级取消标记还会覆盖“停止超时后新轮已启动”的窗口，防止旧轮
        # 的迟到回调写入新轮共享的缓存管理器。
        if (
            self._should_stop_requested(run_id, cancel_event)
        ):
            return

        try:
            # 获取结果
            result = future.result()

            # 结果为空则跳过后续的更新步骤
            if not isinstance(result, dict) or len(result) == 0:
                return

            if result.get("cancelled") is True:
                return

            # future 完成到回调执行之间也可能恰好发生停止/新一轮启动。
            if self._should_stop_requested(run_id, cancel_event):
                return
            
            # 检查是否为错误返回 (配合 TranslatorTask 的异常捕获)
            if result.get("error"):
                self.error(f"[CALLBACK] 子任务报告错误: {result.get('error_msg', '未知错误')}")
                return

            # 记录数据
            with self.data_lock:
                if run_id is not None and self._translation_run_id != run_id:
                    return
                self.extras = self._merge_task_result_into_progress(result)

            # 更新翻译进度
            self.cache_manager.get_project().set_progress(self.extras)

            # 更新翻译状态
            self.cache_manager.get_project().set_status(Base.TranslationStatus.TRANSLATING)

            # 请求保存缓存文件
            self.cache_manager.require_save_to_file(self.config.output_folder)

            # 日志
            progress.update(
                pid,
                total = self.extras.get("total_line", 0),
                completed = self.extras.get("line", 0),
            )

            # 触发翻译进度更新事件
            self.emit(Base.Event.TRANSLATION_UPDATE, self.extras)
        except Exception as e:
            # 捕获 future.result() 或后续处理中的异常
            self.error(f"[CALLBACK-CRASH] 处理任务结果时发生异常: {str(e)}")
            import traceback
            self.error(traceback.format_exc())
