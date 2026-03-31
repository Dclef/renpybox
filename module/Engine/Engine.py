import threading
import time
from abc import abstractmethod

import rich
from rich import box
from rich import markup
from rich.table import Table

from base.compat import StrEnum, Self
from base.LogManager import LogManager
from base.Base import Base
from module.Cache.CacheItem import CacheItem
from module.Config import Config
from module.Localizer.Localizer import Localizer

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
            from module.Engine.TaskRequester import TaskRequester
            from module.PromptBuilder import PromptBuilder
            from module.Response.ResponseChecker import ResponseChecker
            from module.Response.ResponseDecoder import ResponseDecoder
            from module.TextProcessor import TextProcessor

            start_time = time.time()
            success = False
            src_text = item.get_src()
            dst_text = ""

            try:
                platform = config.get_platform(config.activate_platform)
                if not platform:
                    return

                processor = TextProcessor(config, item)
                processor.pre_process()

                if len(processor.srcs) == 0:
                    item.set_dst(item.get_src())
                    item.set_status(Base.TranslationStatus.TRANSLATED)
                    dst_text = item.get_src()
                    success = True
                    return

                prompt_builder = PromptBuilder(config)
                if platform.get("api_format") != Base.APIFormat.SAKURALLM:
                    messages, _ = prompt_builder.generate_prompt(
                        srcs = processor.srcs,
                        samples = processor.samples,
                        precedings = [],
                        local_flag = False,
                        items = [item],
                    )
                else:
                    messages, _ = prompt_builder.generate_prompt_sakura(
                        processor.srcs,
                        items = [item],
                    )

                requester = TaskRequester(config, platform, 0)
                skip, _, response_result, _, _ = requester.request(messages)
                if skip:
                    return

                dsts, _ = ResponseDecoder().decode(response_result)
                if len(dsts) < len(processor.srcs):
                    dsts.extend([""] * (len(processor.srcs) - len(dsts)))

                checks = ResponseChecker(config, [item]).check(
                    processor.srcs,
                    dsts[: len(processor.srcs)],
                    item.get_text_type(),
                )
                dst_text = "\n".join(processor.restore_lines_for_log(dsts[: len(processor.srcs)]))
                if any(v != ResponseChecker.Error.NONE for v in checks):
                    return

                name, dst = processor.post_process(dsts[: len(processor.srcs)])
                item.set_dst(dst)
                if name is not None:
                    item.set_first_name_dst(name)
                item.set_status(Base.TranslationStatus.TRANSLATED)
                dst_text = dst
                success = True
            except Exception as e:
                LogManager.get().error("Single item translate failed", e)
                success = False
            finally:
                self._print_single_translate_log(src_text, dst_text, success, start_time)
                if callable(callback):
                    callback(item, success)

        thread = threading.Thread(
            target = task,
            name = f"{Engine.TASK_PREFIX}SINGLE",
        )
        thread.start()

    def _print_single_translate_log(self, src: str, dst: str, success: bool, start_time: float) -> None:
        elapsed = time.time() - start_time

        if success:
            style = "green"
            message = Localizer.get().translator_task_success.replace("{TIME}", f"{elapsed:.2f}").replace("{LINES}", "1").replace("{PT}", "0").replace("{CT}", "0")
        else:
            style = "red"
            message = Localizer.get().translator_task_fail

        rows = [markup.escape(message)]
        pair = f"{markup.escape((src or '').strip())} [bright_blue]-->[/] {markup.escape((dst or '').strip())}"
        rows.append(pair)

        table = Table(
            box = box.ASCII2,
            expand = True,
            title = " ",
            caption = " ",
            highlight = True,
            show_lines = True,
            show_header = False,
            show_footer = False,
            collapse_padding = True,
            border_style = style,
        )
        table.add_column("", style = "white", ratio = 1, overflow = "fold")
        for row in rows:
            table.add_row(row)

        rich.get_console().print(table)
