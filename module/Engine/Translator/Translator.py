import concurrent.futures
import copy
import json
import os
import re
import shutil
import threading
import time
import webbrowser
from itertools import zip_longest

import httpx
from rich.progress import TaskID

from base.Base import Base
from module.Cache.CacheItem import CacheItem
from module.Cache.CacheManager import CacheManager
from module.Config import Config
from module.Engine.Engine import Engine
from module.Engine.TaskLimiter import TaskLimiter
from module.Engine.TaskRequester import TaskRequester
from module.Engine.Translator.TranslatorTask import TranslatorTask
from module.File.FileManager import FileManager
from module.Filter.LanguageFilter import LanguageFilter
from module.Filter.RuleFilter import RuleFilter
from module.Localizer.Localizer import Localizer
from module.ProgressBar import ProgressBar
from module.PromptBuilder import PromptBuilder
from module.ResultChecker import ResultChecker
from module.TextProcessor import TextProcessor

# 翻译器
class Translator(Base):

    def __init__(self) -> None:
        super().__init__()

        # 初始化
        self.cache_manager = CacheManager(service = True)
        self._last_runtime_output_folder: str = ""

        # 线程锁
        self.data_lock = threading.Lock()

        # 运行中的线程池（用于停止任务时快速取消）
        self._active_executor: concurrent.futures.ThreadPoolExecutor | None = None
        self._translation_thread: threading.Thread | None = None

        # 注册事件
        self.subscribe(Base.Event.TRANSLATION_STOP, self.translation_stop)
        self.subscribe(Base.Event.TRANSLATION_START, self.translation_start)
        self.subscribe(Base.Event.TRANSLATION_MANUAL_EXPORT, self.translation_manual_export)
        self.subscribe(Base.Event.TRANSLATION_CACHE_REINJECT, self.translation_cache_reinject)
        self.subscribe(Base.Event.PROJECT_STATUS, self.translation_project_status_check)

    # 翻译停止事件
    def translation_stop(self, event: str, data: dict) -> None:
        # 更新运行状态
        Engine.get().set_status(Engine.Status.STOPPING)

        # 立即中断网络连接并取消未执行的任务，避免停止后界面卡顿
        TaskRequester.close_all_clients()
        self._shutdown_active_executor()

        def task(event: str, data: dict) -> None:
            while True:
                time.sleep(0.5)

                if Engine.get().get_running_task_count() == 0:
                    # 等待回调执行完毕
                    time.sleep(1.0)

                    # 写入缓存
                    self.cache_manager.save_to_file(
                        project = self.cache_manager.get_project(),
                        items = self.cache_manager.get_items(),
                        output_folder = self.config.output_folder,
                    )

                    # 日志
                    self.print("")
                    self.info(Localizer.get().translator_stop)
                    self.print("")

                    # 通知
                    self.emit(Base.Event.APP_TOAST_SHOW, {
                        "type": Base.ToastType.SUCCESS,
                        "message": Localizer.get().translator_stop,
                    })

                    # 更新运行状态
                    Engine.get().set_status(Engine.Status.IDLE)
                    self.emit(Base.Event.TRANSLATION_DONE, {})
                    break
        threading.Thread(target = task, args = (event, data)).start()

    def _shutdown_active_executor(self) -> None:
        with self.data_lock:
            executor = self._active_executor

        if executor is None:
            return

        try:
            executor.shutdown(wait = False, cancel_futures = True)
        except Exception:
            pass

    def _should_stop_requested(self) -> bool:
        return Engine.get().get_status() == Engine.Status.STOPPING

    # 翻译开始事件
    def translation_start(self, event: str, data: dict) -> None:
        if Engine.get().get_status() == Engine.Status.IDLE:
            thread = threading.Thread(
                target = self.translation_start_task,
                args = (event, data),
                name = f"{Engine.TASK_PREFIX}MAIN",
            )
            self._translation_thread = thread
            thread.start()
        else:
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
            items = self.cache_manager.copy_items()
            self.mtool_optimizer_postprocess(items)
            self.check_and_wirte_result(items)
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
            FileManager(config).write_to_path(items)
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
                extras = cache_manager.get_project().get_extras() or {}

            payload = {
                "status" : status,
            }
            if isinstance(extras, dict):
                payload.update(extras)
            self.emit(Base.Event.PROJECT_STATUS_CHECK_DONE, payload)
        threading.Thread(target = task, args = (event, data)).start()

    def _resolve_project_status_output_folder(self, data: dict) -> str:
        current_output = Config().load().output_folder
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
                os.path.join(cache_dir, CacheManager.CACHE_DB_NAME),
            )
        )

    def _is_relative_to(self, path_a: str, path_b: str) -> bool:
        try:
            return os.path.commonpath([os.path.abspath(path_a), os.path.abspath(path_b)]) == os.path.abspath(path_b)
        except Exception:
            return False

    def _validate_renpy_source_io_layout(self) -> tuple[bool, str]:
        input_folder = str(getattr(self.config, "input_folder", "") or "").strip()
        output_folder = str(getattr(self.config, "output_folder", "") or "").strip()

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
    def translation_start_task(self, event: str, data: dict) -> None:
        try:
            config: Base.TranslationStatus = data.get("config")
            status: Base.TranslationStatus = data.get("status")

            # 更新运行状态
            Engine.get().set_status(Engine.Status.TRANSLATING)

            # 初始化
            self.config = config if isinstance(config, Config) else Config().load()
            # 预处理提示（解析/生成任务阶段）
            self.emit(Base.Event.TRANSLATION_UPDATE, {
                "phase": "preparing",
                "message": "预处理中…",
            })
            override_input = data.get("input_folder")
            override_output = data.get("output_folder")
            override_source = data.get("source_language")
            override_target = data.get("target_language")
            if override_input:
                self.config.input_folder = str(override_input)
            if override_output:
                self.config.output_folder = str(override_output)
            if override_source:
                self.config.source_language = override_source
            if override_target:
                self.config.target_language = override_target
            self.platform = self.config.get_platform(self.config.activate_platform)
            self._last_runtime_output_folder = self.config.output_folder
            local_flag = self.initialize_local_flag()
            max_workers, rpm_threshold = self.initialize_max_workers()

            if getattr(self.config, "renpy_source_translate", False):
                valid_layout, layout_message = self._validate_renpy_source_io_layout()
                if not valid_layout:
                    self.warning(f"[INIT] 已阻止不安全的源码翻译路径: {layout_message}")
                    self.emit(Base.Event.APP_TOAST_SHOW, {
                        "type": Base.ToastType.WARNING,
                        "message": layout_message,
                    })
                    Engine.get().set_status(Engine.Status.IDLE)
                    self.emit(Base.Event.TRANSLATION_DONE, {})
                    return None
            
            # 添加初始化日志
            self.info(f"[INIT] 配置加载完成: platform={self.platform.get('name', 'unknown')}, model={self.platform.get('model', 'unknown')}")
            self.info(f"[INIT] 最大并发: {max_workers}, RPM限制: {rpm_threshold}")

            # 重置
            TextProcessor.reset()
            TaskRequester.reset()
            PromptBuilder.reset()

            # 生成缓存列表
            try:
                # 根据 status 判断是否为继续翻译
                if status == Base.TranslationStatus.TRANSLATING:
                    self.cache_manager.load_from_file(self.config.output_folder)
                else:
                    shutil.rmtree(f"{self.config.output_folder}/cache", ignore_errors = True)
                    project, items = FileManager(self.config).read_from_path()
                    self.cache_manager.set_items(items)
                    self.cache_manager.set_project(project)
            except Exception as e:
                self.error(f"{Localizer.get().log_read_file_fail}", e)
                return None

            if self._should_stop_requested():
                return None

            if self.cache_manager.get_item_count() == 0:
                # 通知
                self.emit(Base.Event.APP_TOAST_SHOW, {
                    "type": Base.ToastType.WARNING,
                    "message": Localizer.get().translator_no_items,
                })

                self.emit(Base.Event.TRANSLATION_STOP, {})
                return None

            # 从头翻译时加载默认数据
            if status == Base.TranslationStatus.TRANSLATING:
                self.extras = self.cache_manager.get_project().get_extras()
                self.extras["start_time"] = time.time() - self.extras.get("time", 0)
                # 根据实际的 Item 状态重新计算 line，避免缓存与项目数据不一致
                self.extras["line"] = self.cache_manager.get_item_count_by_status(Base.TranslationStatus.TRANSLATED)
                self.extras.setdefault("total_tokens", 0)
                self.extras.setdefault("total_input_tokens", 0)
                self.extras.setdefault("total_output_tokens", 0)
            else:
                # 修复: 计算实际的总行数，而不是硬编码为0
                total_untranslated = self.cache_manager.get_item_count_by_status(
                    Base.TranslationStatus.UNTRANSLATED
                )
                self.info(f"[INIT] 初始化进度: 待翻译 {total_untranslated} 行")
                
                self.extras = {
                    "start_time": time.time(),
                    "total_line": total_untranslated,  # 使用实际值
                    "line": 0,
                    "total_tokens": 0,
                    "total_input_tokens": 0,
                    "total_output_tokens": 0,
                    "time": 0,
                }

            # 更新翻译进度
            self.cache_manager.get_project().set_extras(self.extras)
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

            # MTool 优化器预处理
            self.mtool_optimizer_preprocess(self.cache_manager.get_items())
            if self._should_stop_requested():
                return None

            # 保存初始 token_threshold，避免多轮累积除法导致值趋近于 1
            self._initial_token_threshold = self.config.token_threshold

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
                    if status == Base.TranslationStatus.UNTRANSLATED:
                        self.extras["total_line"] = remaining
                    else:
                        self.extras["total_line"] = self.extras.get("line", 0) + remaining

                # 第二轮开始切分（基于初始值计算，避免累积除法）
                if current_round > 0:
                    self.config.token_threshold = max(1, int(self._initial_token_threshold / (3 ** current_round)))

                # 生成缓存数据条目片段
                chunks, precedings = self.cache_manager.generate_item_chunks(
                    self.config.token_threshold,
                    self.config.preceding_lines_threshold,
                )

                # 仅在第一轮启用参考上文功能
                if current_round > 0:
                    precedings = [[] for _ in range(len(precedings))]

                # 生成翻译任务
                self.print("")
                tasks: list[TranslatorTask] = []
                with ProgressBar(transient = False) as progress:
                    pid = progress.new()
                    for items, precedings in zip(chunks, precedings):
                        progress.update(pid, advance = 1, total = len(chunks))
                        tasks.append(TranslatorTask(self.config, self.platform, local_flag, items, precedings))

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
                self.print("")
                if self.platform.get("api_format") != Base.APIFormat.SAKURALLM:
                    self.info(PromptBuilder(self.config).build_main())
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

                            if not task_limiter.acquire(lambda: Engine.get().get_status() == Engine.Status.STOPPING):
                                stopping = True
                                break

                            if not task_limiter.wait(lambda: Engine.get().get_status() == Engine.Status.STOPPING):
                                task_limiter.release()
                                stopping = True
                                break

                            try:
                                future = executor.submit(task.start, current_round)
                            except RuntimeError:
                                task_limiter.release()
                                stopping = True
                                break
                            future.add_done_callback(task_limiter.release)
                            future.add_done_callback(lambda future: self.task_done_callback(future, pid, progress))
                    finally:
                        with self.data_lock:
                            if self._active_executor is executor:
                                self._active_executor = None

                        if stopping:
                            try:
                                executor.shutdown(wait = False, cancel_futures = True)
                            except Exception:
                                pass
                        else:
                            executor.shutdown(wait = True)

                if stopping:
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

            # 等待回调执行完毕
            time.sleep(1.0)

            # MTool 优化器后处理
            self.mtool_optimizer_postprocess(self.cache_manager.get_items())

            # 写入缓存
            self.cache_manager.save_to_file(
                project = self.cache_manager.get_project(),
                items = self.cache_manager.get_items(),
                output_folder = self.config.output_folder,
            )

            # 检查结果并写入文件
            self.check_and_wirte_result(self.cache_manager.get_items())

            # 重置内部状态（正常完成翻译）
            Engine.get().set_status(Engine.Status.IDLE)

            # 触发翻译停止完成的事件
            self.emit(Base.Event.TRANSLATION_DONE, {})
        finally:
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
        max_workers: int = self.config.max_workers
        rpm_threshold: int = self.config.rpm_threshold

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
            max_workers = 8192
            rpm_threshold = rpm_threshold

        return max_workers, rpm_threshold

    # 规则过滤
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
        # 启用自动术语表的时，更新配置文件
        if self.config.glossary_enable == True and self.config.auto_glossary_enable == True:
            # 更新配置文件
            config = Config().load()
            config.glossary_data = self.config.glossary_data
            config.save()

            # 术语表刷新事件
            self.emit(Base.Event.GLOSSARY_REFRESH, {})

        # 检查结果（异常不影响写文件）
        try:
            ResultChecker(self.config, items).check()
        except Exception as e:
            self.warning(f"[ResultChecker] 检查阶段出现异常，已跳过: {e}")

        # 写入文件
        FileManager(self.config).write_to_path(items)
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
    def task_done_callback(self, future: concurrent.futures.Future, pid: TaskID, progress: ProgressBar) -> None:
        # 停止任务时不再更新进度/写缓存，避免 UI 卡顿或进度对象已释放导致异常
        if Engine.get().get_status() == Engine.Status.STOPPING:
            return

        try:
            # 获取结果
            result = future.result()

            # 结果为空则跳过后续的更新步骤
            if not isinstance(result, dict) or len(result) == 0:
                return
            
            # 检查是否为错误返回 (配合 TranslatorTask 的异常捕获)
            if result.get("error"):
                self.error(f"[CALLBACK] 子任务报告错误: {result.get('error_msg', '未知错误')}")
                return

            # 记录数据
            with self.data_lock:
                new = {}
                new["start_time"] = self.extras.get("start_time", 0)
                new["total_line"] = self.extras.get("total_line", 0)
                new["line"] = self.extras.get("line", 0) + result.get("row_count", 0)
                new["total_tokens"] = self.extras.get("total_tokens", 0) + result.get("input_tokens", 0) + result.get("output_tokens", 0)
                new["total_input_tokens"] = self.extras.get("total_input_tokens", 0) + result.get("input_tokens", 0)
                new["total_output_tokens"] = self.extras.get("total_output_tokens", 0) + result.get("output_tokens", 0)
                new["time"] = time.time() - self.extras.get("start_time", 0)
                self.extras = new

            # 更新翻译进度
            self.cache_manager.get_project().set_extras(self.extras)

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
