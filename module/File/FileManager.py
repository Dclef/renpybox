import copy
import os
import random
from datetime import datetime

from base.Base import Base
from base.BaseLanguage import BaseLanguage
from module.Engine.Engine import Engine
from module.Cache.CacheItem import CacheItem
from module.Cache.CacheProject import CacheProject
from module.Config import Config
from module.File.ASS import ASS
from module.File.EPUB import EPUB
from module.File.KVJSON import KVJSON
from module.File.MD import MD
from module.File.MESSAGEJSON import MESSAGEJSON
from module.File.RENPY import RENPY
from module.File.RENPYHOOK import RENPYHOOK
from module.File.RENPYSOURCE import RENPYSOURCE
from module.File.SRT import SRT
from module.File.TRANS.TRANS import TRANS
from module.File.TXT import TXT
from module.File.WOLFXLSX import WOLFXLSX
from module.File.XLSX import XLSX
from module.File.RENpyTranslationsJSON import RENPYTRANSLATIONSJSON
from module.Localizer.Localizer import Localizer
from module.OpenCCHelper import OpenCCHelper

class FileManager(Base):

    def __init__(self, config: Config) -> None:
        super().__init__()

        # 初始化
        self.config = config

    def _is_stop_requested(self) -> bool:
        try:
            # 延迟导入避免 FileManager/Translator 循环依赖；线程局部取消
            # 令牌可覆盖停止超时后 Engine 状态已恢复的窗口。
            from module.Engine.TaskRequester import TaskRequester

            return (
                Engine.get().get_status() == Engine.Status.STOPPING
                or TaskRequester.is_cancel_requested()
            )
        except Exception:
            return False

    def _should_apply_traditional_output(self) -> bool:
        return (
            self.config.target_language == BaseLanguage.Enum.ZH
            and self.config.traditional_chinese_enable == True
        )

    def _convert_text_for_write(self, text: str) -> str:
        if not isinstance(text, str) or text == "":
            return text
        return OpenCCHelper.convert("s2tw", text)

    def _prepare_items_for_write(self, items: list[CacheItem]) -> list[CacheItem]:
        if self._should_apply_traditional_output() == False:
            return items

        prepared_items: list[CacheItem] = []
        for item in items:
            cloned = CacheItem.from_dict(copy.deepcopy(item.asdict()))
            cloned.set_dst(self._convert_text_for_write(cloned.get_dst()))

            name_dst = cloned.get_name_dst()
            if isinstance(name_dst, str):
                cloned.set_name_dst(self._convert_text_for_write(name_dst))
            elif isinstance(name_dst, list):
                cloned.set_name_dst([
                    self._convert_text_for_write(value) if isinstance(value, str) else value
                    for value in name_dst
                ])

            prepared_items.append(cloned)

        return prepared_items

    def _collect_source_rpy_paths(self, input_folder: str) -> list[str]:
        paths: list[str] = []

        if os.path.isfile(input_folder):
            if input_folder.lower().endswith(".rpy"):
                paths = [input_folder.replace("\\", "/")]
            return paths

        if not os.path.isdir(input_folder):
            return paths

        self.emit(Base.Event.TRANSLATION_UPDATE, {
            "phase": "preparing",
            "message": "正在扫描源码目录…",
        })

        scanned_dirs = 0
        for root, dirs, files in os.walk(input_folder):
            if self._is_stop_requested():
                break

            # 源码翻译不需要扫描 tl 目录，避免重复处理现有翻译脚本。
            dirs[:] = [d for d in dirs if d.lower() != "tl"]

            scanned_dirs += 1
            for file in files:
                if file.lower().endswith(".rpy"):
                    paths.append(f"{root}/{file}".replace("\\", "/"))

            if scanned_dirs % 20 == 0:
                self.emit(Base.Event.TRANSLATION_UPDATE, {
                    "phase": "preparing",
                    "message": f"正在扫描源码目录… 已发现 {len(paths)} 个 .rpy 文件",
                })

        return paths

    # 读
    def read_from_path(self) -> tuple[CacheProject, list[CacheItem]]:
        project: CacheProject = CacheProject.from_dict({
            "id": f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{random.randint(100000, 999999)}",
        })

        items: list[CacheItem] = []
        try:
            if getattr(self.config, "renpy_hook_translate", False):
                items.extend(RENPYHOOK(self.config).read_from_path([]))
                return project, items

            # 源码翻译模式：仅处理 .rpy 源码
            if getattr(self.config, "renpy_source_translate", False):
                rpy_paths = self._collect_source_rpy_paths(self.config.input_folder)
                items.extend(RENPYSOURCE(self.config).read_from_path(rpy_paths))
                return project, items

            paths: list[str] = []
            input_folder: str = self.config.input_folder
            if os.path.isfile(input_folder):
                paths = [input_folder]
            elif os.path.isdir(input_folder):
                for root, _, files in os.walk(input_folder):
                    if self._is_stop_requested():
                        break
                    for file in files:
                        if self._is_stop_requested():
                            break
                        paths.append(f"{root}/{file}".replace("\\", "/"))

            # 扫描阶段被取消时，不再把已经收集的文件交给后续解析器，
            # 避免停止按钮之后仍长时间占用事件线程和磁盘。
            if self._is_stop_requested():
                return project, items

            paths_by_extension: dict[str, list[str]] = {}
            for path in paths:
                if self._is_stop_requested():
                    return project, items
                extension = os.path.splitext(path)[1].lower()
                paths_by_extension.setdefault(extension, []).append(path)

            def read_if_active(parser, extension: str) -> None:
                """仅在未收到停止请求时运行单个文件解析器。"""
                if self._is_stop_requested():
                    return
                items.extend(parser.read_from_path(paths_by_extension.get(extension, [])))

            # 优先处理 translations JSON（避免被其他 json 解析器抢先处理）
            read_if_active(RENPYTRANSLATIONSJSON(self.config), ".json")
            read_if_active(MD(self.config), ".md")
            read_if_active(TXT(self.config), ".txt")
            read_if_active(ASS(self.config), ".ass")
            read_if_active(SRT(self.config), ".srt")
            read_if_active(EPUB(self.config), ".epub")
            read_if_active(XLSX(self.config), ".xlsx")
            read_if_active(WOLFXLSX(self.config), ".xlsx")
            read_if_active(RENPY(self.config), ".rpy")
            read_if_active(TRANS(self.config), ".trans")
            read_if_active(KVJSON(self.config), ".json")
            read_if_active(MESSAGEJSON(self.config), ".json")
        except Exception as e:
            self.error(f"{Localizer.get().log_read_file_fail}", e)

        return project, items

    # 写
    def write_to_path(self, items: list[CacheItem]) -> None:
        try:
            items_to_write = self._prepare_items_for_write(items)

            RENPYTRANSLATIONSJSON(self.config).write_to_path(items_to_write)
            MD(self.config).write_to_path(items_to_write)
            TXT(self.config).write_to_path(items_to_write)
            ASS(self.config).write_to_path(items_to_write)
            SRT(self.config).write_to_path(items_to_write)
            EPUB(self.config).write_to_path(items_to_write)
            XLSX(self.config).write_to_path(items_to_write)
            WOLFXLSX(self.config).write_to_path(items_to_write)
            # 按条目类型分别写回，避免“从缓存重新注入”时因配置开关不一致导致
            # RENPYSOURCE / RENPY 写回分支走错。
            RENPYHOOK(self.config).write_to_path(items_to_write)
            RENPYSOURCE(self.config).write_to_path(items_to_write)
            RENPY(self.config).write_to_path(items_to_write)
            TRANS(self.config).write_to_path(items_to_write)
            KVJSON(self.config).write_to_path(items_to_write)
            MESSAGEJSON(self.config).write_to_path(items_to_write)
        except Exception as e:
            self.error(f"{Localizer.get().log_write_file_fail}", e)
