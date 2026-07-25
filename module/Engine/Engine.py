import threading

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
        return sum(1 for t in threading.enumerate() if t.name.startswith(__class__.TASK_PREFIX))

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
            # 延迟导入避免循环依赖
            from module.Engine.Translator.TranslatorTask import TranslatorTask

            success = False

            try:
                platform = config.get_platform(config.activate_platform)
                if not platform:
                    return

                expected_state = item.get_translation_state()
                working_item = CacheItem.from_dict(item.asdict())
                working_item.reset_translation(clear_dst = False)
                result = TranslatorTask(config, platform, False, [working_item], []).start(0)
                translated = (
                    Base.is_item_completed(working_item.get_status())
                    and not bool(result.get("error", False))
                )
                success = translated and item.commit_translation_from(
                    working_item,
                    expected_state,
                )
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
