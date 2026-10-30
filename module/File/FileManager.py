import copy
import json
import os
import random
from datetime import datetime
from pathlib import Path

from base.Base import Base
from base.BaseLanguage import BaseLanguage
from module.Engine.Engine import Engine
from module.Cache.CacheItem import CacheItem
from module.Cache.CacheProject import CacheProject
from module.Config import Config
from module.File.ASS import ASS
from module.File.AtomicWrite import atomic_write_text
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
            self.emit(Base.Event.TRANSLATION_UPDATE, {
                "phase": "preparing",
                "message": "正在扫描翻译输入目录…",
            })
            if os.path.isfile(input_folder):
                paths = [input_folder]
            elif os.path.isdir(input_folder):
                for root, dirs, files in os.walk(input_folder):
                    if self._is_stop_requested():
                        break
                    # Runtime rule payloads are generated artifacts, not new
                    # translation input (their JSON arrays are not MESSAGEJSON).
                    dirs[:] = [name for name in dirs if name not in (".renpybox_replace", ".renpybox_metrics")]
                    for file in files:
                        if self._is_stop_requested():
                            break
                        paths.append(f"{root}/{file}".replace("\\", "/"))

            # 扫描阶段被取消时，不再把已经收集的文件交给后续解析器，
            # 避免停止按钮之后仍长时间占用事件线程和磁盘。
            if self._is_stop_requested():
                return project, items

            self.emit(Base.Event.TRANSLATION_UPDATE, {
                "phase": "preparing",
                "message": f"正在解析翻译输入文件…（{len(paths)} 个文件）",
            })

            paths_by_extension: dict[str, list[str]] = {}
            for path in paths:
                if self._is_stop_requested():
                    return project, items
                candidate = Path(path)
                if any(part in (".renpybox_replace", ".renpybox_metrics") for part in candidate.parts):
                    continue
                if candidate.name in ("replace_text_auto.diagnostics.json", "replace_text.diagnostics.json"):
                    continue
                extension = os.path.splitext(path)[1].lower()
                paths_by_extension.setdefault(extension, []).append(path)

            read_errors: list[str] = []

            def read_if_active(parser_name: str, parser, extension: str) -> None:
                """仅在未收到停止请求时运行单个文件解析器。"""
                if self._is_stop_requested():
                    return
                try:
                    items.extend(parser.read_from_path(paths_by_extension.get(extension, [])))
                except Exception as exc:
                    self.error(f"{parser_name} 读取失败", exc)
                    read_errors.append(f"{parser_name}: {exc}")

            # 优先处理 translations JSON（避免被其他 json 解析器抢先处理）
            read_if_active("RENPYTRANSLATIONSJSON", RENPYTRANSLATIONSJSON(self.config), ".json")
            read_if_active("MD", MD(self.config), ".md")
            read_if_active("TXT", TXT(self.config), ".txt")
            read_if_active("ASS", ASS(self.config), ".ass")
            read_if_active("SRT", SRT(self.config), ".srt")
            read_if_active("EPUB", EPUB(self.config), ".epub")
            read_if_active("XLSX", XLSX(self.config), ".xlsx")
            read_if_active("WOLFXLSX", WOLFXLSX(self.config), ".xlsx")
            read_if_active("RENPY", RENPY(self.config), ".rpy")
            read_if_active("TRANS", TRANS(self.config), ".trans")
            read_if_active("KVJSON", KVJSON(self.config), ".json")
            read_if_active("MESSAGEJSON", MESSAGEJSON(self.config), ".json")
            if read_errors:
                raise RuntimeError("部分输入文件读取失败：" + "；".join(read_errors))
        except Exception as e:
            self.error(f"{Localizer.get().log_read_file_fail}", e)
            raise

        return project, items

    # 写回失败诊断：完整异常落到 JSON 明细，抛给界面的消息只保留可读摘要，
    # 避免几 KB 的异常原文直接糊在 Toast 里。
    WRITEBACK_FAILURE_REPORT_NAME: str = "writeback_failures.json"
    WRITEBACK_FAILURE_MESSAGE_LIMIT: int = 1500
    WRITEBACK_FAILURE_DETAIL_LIMIT: int = 400

    def _truncate_writeback_failure_text(self, text: str, limit: int) -> str:
        if not isinstance(text, str):
            text = str(text)
        if limit <= 0:
            return ""
        if len(text) <= limit:
            return text
        return text[: limit - 1] + "…"

    def _write_writeback_failure_report(self, failures: list[dict]) -> Path | None:
        """把逐 writer 的完整异常落盘；诊断文件自身失败绝不能掩盖原始异常。"""
        try:
            output_folder = getattr(self.config, "output_folder", "") or ""
            if not output_folder:
                return None

            folder = Path(output_folder)
            report_path = folder / self.WRITEBACK_FAILURE_REPORT_NAME
            folder.mkdir(parents = True, exist_ok = True)
            atomic_write_text(
                report_path,
                json.dumps(failures, ensure_ascii = False, indent = 2),
                allowed_roots = [folder],
            )
            return Path(os.path.abspath(report_path))
        except Exception as exc:
            # 明细落盘失败（含日志不可用）都不能掩盖原始写回异常。
            try:
                self.warning(f"{self.WRITEBACK_FAILURE_REPORT_NAME} 写回失败明细落盘失败", exc)
            except Exception:
                pass
            return None

    def _build_writeback_failure_error(
        self,
        failures: list[dict],
        report_path: Path | None,
    ) -> RuntimeError:
        header = "部分文件写回失败："
        suffix = f"（完整明细见 {report_path}）" if report_path is not None else ""
        budget = max(self.WRITEBACK_FAILURE_MESSAGE_LIMIT - len(header) - len(suffix), 0)
        details = [
            (
                f"{failure['writer']}: "
                f"{self._truncate_writeback_failure_text(failure['message'], self.WRITEBACK_FAILURE_DETAIL_LIMIT)}"
            )
            for failure in failures
        ]
        joined = "；".join(details)
        if len(joined) > budget:
            joined = self._truncate_writeback_failure_text(joined, budget)

        message = header + joined + suffix
        if len(message) > self.WRITEBACK_FAILURE_MESSAGE_LIMIT:
            # 极端长路径等异常情况下仍保证总量上限，保留开头的关键前缀。
            message = self._truncate_writeback_failure_text(
                message,
                self.WRITEBACK_FAILURE_MESSAGE_LIMIT,
            )
        return RuntimeError(message)

    # 写
    def write_to_path(self, items: list[CacheItem]) -> None:
        items_to_write = self._prepare_items_for_write(items)
        writers = (
            ("RENPYTRANSLATIONSJSON", RENPYTRANSLATIONSJSON(self.config)),
            ("MD", MD(self.config)),
            ("TXT", TXT(self.config)),
            ("ASS", ASS(self.config)),
            ("SRT", SRT(self.config)),
            ("EPUB", EPUB(self.config)),
            ("XLSX", XLSX(self.config)),
            ("WOLFXLSX", WOLFXLSX(self.config)),
            ("RENPYHOOK", RENPYHOOK(self.config)),
            ("RENPYSOURCE", RENPYSOURCE(self.config)),
            ("RENPY", RENPY(self.config)),
            ("TRANS", TRANS(self.config)),
            ("KVJSON", KVJSON(self.config)),
            ("MESSAGEJSON", MESSAGEJSON(self.config)),
        )
        failures: list[dict] = []
        for writer_name, writer in writers:
            try:
                writer.write_to_path(items_to_write)
            except Exception as exc:
                # 先记完整异常（日志/控制台），再收集明细用于落盘与最终报错。
                self.error(f"{writer_name} 写回失败", exc)
                failures.append({
                    "writer": writer_name,
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                })
        if failures:
            report_path = self._write_writeback_failure_report(failures)
            error = self._build_writeback_failure_error(failures, report_path)
            self.error(f"{Localizer.get().log_write_file_fail}", error)
            raise error
