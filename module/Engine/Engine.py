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
        STOPPING = "STOPPING"                                               # 停止中

    TASK_PREFIX: str = "ENGINE_"

    def __init__(self) -> None:
        super().__init__()

        # 初始化
        self.status: __class__.Status = __class__.Status.IDLE

        # 线程锁
        self.lock = threading.Lock()

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

    def get_running_task_count(self) -> int:
        return sum(1 for t in threading.enumerate() if t.name.startswith(__class__.TASK_PREFIX))

    def translate_single_item(
        self,
        item: CacheItem,
        config: Config,
        callback,
    ) -> None:
        """对单个条目执行翻译，异步返回结果。"""

        def task() -> None:
            # 延迟导入避免循环依赖
            from module.Engine.Translator.TranslatorTask import TranslatorTask

            success = False

            try:
                platform = config.get_platform(config.activate_platform)
                if not platform:
                    return

                result = TranslatorTask(config, platform, False, [item], []).start(0)
                success = (
                    item.get_status() == Base.TranslationStatus.TRANSLATED
                    and not bool(result.get("error", False))
                )
            except Exception as e:
                LogManager.get().error("Single item translate failed", e)
                success = False
            finally:
                if callable(callback):
                    callback(item, success)

        thread = threading.Thread(
            target = task,
            name = f"{Engine.TASK_PREFIX}SINGLE",
        )
        thread.start()
