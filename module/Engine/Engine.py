import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

from base.compat import StrEnum, Self
from base.Base import Base
from base.LogManager import LogManager
from module.Cache.CacheItem import CacheItem
from module.Config import Config

class Engine():

    class Status(StrEnum):

        IDLE = "IDLE"                                                       # 无任务
        TESTING = "TESTING"                                                 # 测试中
        TRANSLATING = "TRANSLATING"                                         # 运行中
        QUALITY = "QUALITY"                                                 # 润色/校对中
        AGENT = "AGENT"                                                       # Agent 独占操作中
        STOPPING = "STOPPING"                                               # 停止中

    TASK_PREFIX: str = "ENGINE_"

    def __init__(self) -> None:
        super().__init__()

        # 初始化
        self.status: __class__.Status = __class__.Status.IDLE
        self.single_task_count: int = 0

        # 线程锁
        self.lock = threading.Lock()

        # 翻译停止超时后，仍可能有旧请求线程在后台收尾。此屏障用于
        # 阻止新的翻译/校对/单条重译抢占同一个全局取消标记，直到旧线程
        # 收尾完成或达到有界清理期限。
        self.stop_barrier: bool = False

    @classmethod
    def get(cls) -> Self:
        if not hasattr(cls, "__instance__"):
            cls.__instance__ = cls()

        return cls.__instance__

    def run(self) -> None:
        from module.Engine.API.APITester import APITester
        self.api_test = APITester()

        from module.Engine.Translator.Translator import Translator

        # Translator 会 subscribe 到类级事件总线上（Base.EventManager），
        # 不退订就会一直活着：重复 run() 会堆叠多个订阅者，一条
        # TRANSLATION_START 就会被启动 N 次翻译线程。
        previous = getattr(self, "translator", None)
        if previous is not None and hasattr(previous, "unsubscribe_events"):
            previous.unsubscribe_events()

        self.translator = Translator()

    def get_status(self) -> Status:
        with self.lock:
            return self.status

    def set_status(self, status: Status) -> None:
        with self.lock:
            self.status = status

    def try_set_status(self, expected: Status, status: Status) -> bool:
        """仅在状态符合预期时原子切换，避免多个 AI 任务同时抢占引擎。"""
        with self.lock:
            if self.status != expected:
                return False
            if (
                self.stop_barrier
                and expected == __class__.Status.IDLE
                and status != __class__.Status.IDLE
            ):
                return False
            if (
                expected == __class__.Status.IDLE
                and status != __class__.Status.IDLE
                and self.single_task_count > 0
            ):
                return False
            self.status = status
            return True

    def release_status(self, expected: Status) -> bool:
        """仅释放调用方拥有的状态，避免覆盖稍后启动的其他任务。"""
        return self.try_set_status(expected, __class__.Status.IDLE)

    def get_running_task_count(self) -> int:
        with self.lock:
            status = self.status

        if status not in (__class__.Status.TRANSLATING, __class__.Status.STOPPING):
            return 0

        translator = getattr(self, "translator", None)
        counter = getattr(translator, "get_active_task_count", None)
        if not callable(counter):
            return 0

        try:
            return max(0, int(counter()))
        except Exception:
            return 0

    def try_begin_single_task(self) -> bool:
        """在空闲状态登记单条重译；允许同一批次并行提交多条。"""
        with self.lock:
            if self.status != __class__.Status.IDLE or self.stop_barrier:
                return False
            self.single_task_count += 1
            return True

    def set_stop_barrier(self, blocked: bool) -> None:
        """设置/解除停止收尾屏障。"""
        with self.lock:
            self.stop_barrier = bool(blocked)

    def has_stop_barrier(self) -> bool:
        """返回是否仍在等待旧翻译线程收尾。"""
        with self.lock:
            return self.stop_barrier

    def end_single_task(self) -> None:
        """结束一个单条重译任务。"""
        with self.lock:
            self.single_task_count = max(0, self.single_task_count - 1)

    def has_single_tasks(self) -> bool:
        with self.lock:
            return self.single_task_count > 0

    def _translate_single_item_task(self, item: CacheItem, config: Config) -> bool:
        """执行一条单条翻译并写回条目，返回是否成功。"""
        # 延迟导入避免循环依赖
        from module.Engine.Translator.TranslatorTask import TranslatorTask

        platform = config.get_platform(config.activate_platform)
        if not platform:
            return False

        expected_state = item.get_translation_state()
        working_item = CacheItem.from_dict(item.asdict())
        working_item.reset_translation(clear_dst = False)
        result = TranslatorTask(config, platform, False, [working_item], []).start(0)
        translated = (
            Base.is_item_completed(working_item.get_status())
            and not bool(result.get("error", False))
        )
        return bool(
            translated
            and item.commit_translation_from(working_item, expected_state)
        )

    def translate_single_item(
        self,
        item: CacheItem,
        config: Config,
        callback,
    ) -> bool:
        """对单个条目执行翻译，异步返回结果。"""

        if not self.try_begin_single_task():
            if callable(callback):
                callback(item, False)
            return False

        def task() -> None:
            success = False

            try:
                success = self._translate_single_item_task(item, config)
            except Exception as e:
                LogManager.get().error("Single item translate failed", e)
                success = False
            finally:
                self.end_single_task()
                if callable(callback):
                    callback(item, success)

        thread = threading.Thread(
            target = task,
            name = f"{Engine.TASK_PREFIX}SINGLE",
        )
        try:
            thread.start()
        except Exception:
            self.end_single_task()
            if callable(callback):
                callback(item, False)
            raise
        return True

    def translate_items(
        self,
        items: list[CacheItem],
        config: Config,
        callback,
        *,
        max_workers: int = 0,
        should_cancel: Callable[[], bool] | None = None,
        on_progress: Callable[[int, int], None] | None = None,
    ) -> int:
        """分批并发执行单条翻译，返回已处理条数。

        ``max_workers<=0`` 时按配置的并发上限取一个保守值。整批在开始前一次性
        登记，使 ``has_single_tasks()`` 在整批结束前保持为真；``should_cancel``
        在每批开始前检查一次，取消后未开始的条目不再发起请求。
        """
        pending = list(items or [])
        if len(pending) == 0:
            return 0

        configured_workers = getattr(config, "max_workers", 0)
        try:
            configured_workers = int(configured_workers)
        except (TypeError, ValueError):
            configured_workers = 0
        workers = max(
            1, min(max_workers if max_workers > 0 else (configured_workers or 4), 8)
        )
        workers = min(workers, len(pending))

        # 整批登记一次，避免登记期间主任务插入而只登记了部分条目。
        with self.lock:
            accepted = self.status == __class__.Status.IDLE and not self.stop_barrier
            if accepted:
                self.single_task_count += len(pending)
        if not accepted:
            for item in pending:
                if callable(callback):
                    callback(item, False)
            return 0

        completed = 0
        try:
            with ThreadPoolExecutor(
                max_workers=workers,
                thread_name_prefix=f"{Engine.TASK_PREFIX}BATCH",
            ) as executor:
                for start in range(0, len(pending), workers):
                    if should_cancel is not None and should_cancel():
                        break
                    # 只提交当前批；取消后仍报告已发出请求的结果，避免漏存已完成译文。
                    futures = [
                        (executor.submit(self._translate_single_item_task, item, config), item)
                        for item in pending[start:start + workers]
                    ]
                    for future, item in futures:
                        success = False
                        try:
                            success = bool(future.result())
                        except Exception as exc:
                            LogManager.get().error("Batch item translate failed", exc)
                        self.end_single_task()
                        completed += 1
                        if callable(callback):
                            callback(item, success)
                        if on_progress is not None:
                            on_progress(completed, len(pending))
        finally:
            for _ in range(len(pending) - completed):
                self.end_single_task()
        return completed
