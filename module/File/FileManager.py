import os
import random
from datetime import datetime

from base.Base import Base
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
from module.File.RENPYSOURCE import RENPYSOURCE
from module.File.SRT import SRT
from module.File.TRANS.TRANS import TRANS
from module.File.TXT import TXT
from module.File.WOLFXLSX import WOLFXLSX
from module.File.XLSX import XLSX
from module.File.RENpyTranslationsJSON import RENPYTRANSLATIONSJSON
from module.Localizer.Localizer import Localizer

class FileManager(Base):

    def __init__(self, config: Config) -> None:
        super().__init__()

        # 初始化
        self.config = config

    def _is_stop_requested(self) -> bool:
        try:
            return Engine.get().get_status() == Engine.Status.STOPPING
        except Exception:
            return False

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
                    paths.extend([f"{root}/{file}".replace("\\", "/") for file in files])
            # 优先处理 translations JSON（避免被其他 json 解析器抢先处理）
            items.extend(RENPYTRANSLATIONSJSON(self.config).read_from_path([path for path in paths if path.lower().endswith(".json")]))
            items.extend(MD(self.config).read_from_path([path for path in paths if path.lower().endswith(".md")]))
            items.extend(TXT(self.config).read_from_path([path for path in paths if path.lower().endswith(".txt")]))
            items.extend(ASS(self.config).read_from_path([path for path in paths if path.lower().endswith(".ass")]))
            items.extend(SRT(self.config).read_from_path([path for path in paths if path.lower().endswith(".srt")]))
            items.extend(EPUB(self.config).read_from_path([path for path in paths if path.lower().endswith(".epub")]))
            items.extend(XLSX(self.config).read_from_path([path for path in paths if path.lower().endswith(".xlsx")]))
            items.extend(WOLFXLSX(self.config).read_from_path([path for path in paths if path.lower().endswith(".xlsx")]))
            items.extend(RENPY(self.config).read_from_path([path for path in paths if path.lower().endswith(".rpy")]))
            items.extend(TRANS(self.config).read_from_path([path for path in paths if path.lower().endswith(".trans")]))
            items.extend(KVJSON(self.config).read_from_path([path for path in paths if path.lower().endswith(".json")]))
            items.extend(MESSAGEJSON(self.config).read_from_path([path for path in paths if path.lower().endswith(".json")]))
        except Exception as e:
            self.error(f"{Localizer.get().log_read_file_fail}", e)

        return project, items

    # 写
    def write_to_path(self, items: list[CacheItem]) -> None:
        try:
            RENPYTRANSLATIONSJSON(self.config).write_to_path(items)
            MD(self.config).write_to_path(items)
            TXT(self.config).write_to_path(items)
            ASS(self.config).write_to_path(items)
            SRT(self.config).write_to_path(items)
            EPUB(self.config).write_to_path(items)
            XLSX(self.config).write_to_path(items)
            WOLFXLSX(self.config).write_to_path(items)
            if getattr(self.config, "renpy_source_translate", False):
                RENPYSOURCE(self.config).write_to_path(items)
            else:
                RENPY(self.config).write_to_path(items)
            TRANS(self.config).write_to_path(items)
            KVJSON(self.config).write_to_path(items)
            MESSAGEJSON(self.config).write_to_path(items)
        except Exception as e:
            self.error(f"{Localizer.get().log_write_file_fail}", e)
