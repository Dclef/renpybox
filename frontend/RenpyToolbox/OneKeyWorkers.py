"""一键翻译页的后台线程：文本提取与应用翻译。

从 OneKeyTranslatePage 外移的 QThread（行为零变化），信号签名与构造参数
保持原样，页面模块继续 re-export 以兼容既有 import。无 Qt 编排见 module.OneKey.flow。
"""

import os
import shutil  # 保留旧测试和调用方的文件操作替换入口。
from pathlib import Path

from PyQt5.QtCore import QCoreApplication, QThread, pyqtSignal

from base.LogManager import LogManager
from module.Localizer.Localizer import Localizer
from frontend.RenpyToolbox.OneKeyNameService import OneKeyNameService
from module.OneKey.flow import (
    _cache_item_identity,
    _numbered_disk_identity,
    _remember_translation_run,
    _localize_extraction_result,
    _localize_extractor_progress,
    apply_full_translation,
    apply_incremental_translation,
    apply_translation_files_transactionally,
    configure_incremental_translation_paths,
    configure_main_translation_paths,
    configure_tl_translation_mode,
    detect_game_status,
    merge_incremental_translation_cache,
    preserve_incremental_translation_cache,
    resolve_translation_apply_paths,
)

# 兼容旧 import：页面与测试继续从本模块取用纯函数。
__all__ = [
    "ApplyTranslationWorker",
    "CharacterScanWorker",
    "ExtractionWorker",
    "GameStatusWorker",
    "TranslationFileScanWorker",
    "apply_translation_files_transactionally",
    "configure_incremental_translation_paths",
    "configure_main_translation_paths",
    "configure_tl_translation_mode",
    "detect_game_status",
    "merge_incremental_translation_cache",
    "preserve_incremental_translation_cache",
    "resolve_translation_apply_paths",
]

class GameStatusWorker(QThread):
    """后台检测游戏脚本状态，避免递归扫描占用界面线程。"""

    result_ready = pyqtSignal(object)  # 结果字典：status/message

    def __init__(self, game_dir: str, tl_name: str):
        # 页面关闭后线程仍由应用持有，避免 QThread 在扫描期间被销毁。
        super().__init__(QCoreApplication.instance())
        self.game_dir = str(game_dir)
        self.tl_name = str(tl_name)

    def run(self) -> None:
        if self.isInterruptionRequested():
            self.result_ready.emit({"status": "cancelled", "message": ""})
            return
        try:
            status, message = detect_game_status(
                self.game_dir,
                self.tl_name,
                cancel_check=self.isInterruptionRequested,
            )
        except Exception as exc:
            if self.isInterruptionRequested():
                self.result_ready.emit({"status": "cancelled", "message": ""})
                return
            LogManager.get().error(f"检测游戏脚本状态失败: {exc}")
            self.result_ready.emit(
                {
                    "status": "error",
                    "message": str(exc),
                }
            )
            return
        if self.isInterruptionRequested():
            self.result_ready.emit({"status": "cancelled", "message": ""})
            return
        self.result_ready.emit({"status": status, "message": message})


# Worker Thread for Extraction
class ExtractionWorker(QThread):
    progress = pyqtSignal(str, int) # message, percent
    finished = pyqtSignal(bool, str, object) # success, message, result (ExtractionResult)
    
    def __init__(self, unified_extractor, game_dir, tl_name, exe_path, incremental=False, output_to_separate_folder=True):
        super().__init__()
        self.unified_extractor = unified_extractor
        self.game_dir = game_dir
        self.tl_name = tl_name
        self.exe_path = exe_path
        self.incremental = incremental  # 增量模式：保留已有翻译
        self.output_to_separate_folder = output_to_separate_folder  # 增量输出到单独文件夹

    def cancel(self):
        self.requestInterruption()
        
    def run(self):
        try:
            if hasattr(self.unified_extractor, "set_cancel_callback"):
                self.unified_extractor.set_cancel_callback(self.isInterruptionRequested)
            # 设置进度回调
            self.unified_extractor.set_progress_callback(
                lambda msg, pct: self.progress.emit(
                    _localize_extractor_progress(
                        msg, Localizer.get().onekey_extracting_text
                    ),
                    pct,
                )
            )
            
            if self.incremental:
                # 增量模式：使用统一提取器的增量抽取
                result = self.unified_extractor.extract_incremental(
                    self.game_dir,
                    self.tl_name,
                    self.exe_path,
                    use_official=bool(self.exe_path),
                    output_to_separate_folder=self.output_to_separate_folder
                )
            else:
                # 常规模式：使用统一提取器的完整抽取
                result = self.unified_extractor.extract_regular(
                    self.game_dir,
                    self.tl_name,
                    self.exe_path,
                    use_official=bool(self.exe_path)
                )
            
            if not result.success and result.message and not getattr(result, "cancelled", False):
                LogManager.get().error(f"文本提取失败: {result.message}")
            self.finished.emit(
                result.success, _localize_extraction_result(result, self.incremental), result
            )
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            LogManager.get().error(f"文本提取失败: {e}")
            self.finished.emit(
                False,
                Localizer.localize(
                    f"文本提取失败：{e}",
                    "Text extraction failed. Check the logs for details.",
                ),
                None,
            )
        finally:
            self.unified_extractor.set_progress_callback(None)
            if hasattr(self.unified_extractor, "set_cancel_callback"):
                self.unified_extractor.set_cancel_callback(None)


class TranslationFileScanWorker(QThread):
    """Enumerate translation files without blocking the GUI event loop."""

    def __init__(self, directory, *, collect_files=False):
        # The application owns running threads even if their page is destroyed.
        super().__init__(QCoreApplication.instance())
        self.directory = Path(directory)
        self.collect_files = collect_files
        self.files = []
        self.file_count = 0
        self.error = ""

    def run(self):
        try:
            def fail(error):
                raise error

            for directory, _subdirs, names in os.walk(self.directory, onerror=fail):
                if self.isInterruptionRequested():
                    return
                for name in names:
                    if self.isInterruptionRequested():
                        return
                    if not os.path.normcase(name).endswith(".rpy"):
                        continue
                    self.file_count += 1
                    if self.collect_files:
                        self.files.append(Path(directory) / name)
        except OSError as exc:
            self.error = str(exc)


class CharacterScanWorker(QThread):
    """后台扫描角色名和变量引用，避免抽取完成后阻塞界面线程。"""

    finished = pyqtSignal(bool, str)

    def __init__(self, game_dir: str, tl_name: str, *, force: bool = False):
        super().__init__()
        self.game_dir = game_dir
        self.tl_name = tl_name
        self.force = force

    def run(self) -> None:
        LogManager.get().info(
            f"开始后台扫描角色名和变量引用: game={self.game_dir}, language={self.tl_name}"
        )
        try:
            OneKeyNameService.get().extract_character_names(
                self.game_dir,
                self.tl_name,
                force=self.force,
            )
            LogManager.get().info("后台角色名和变量引用扫描完成")
            self.finished.emit(True, "角色名和变量引用扫描完成")
        except Exception as exc:
            LogManager.get().warning(f"角色名扫描失败：{exc}")
            self.finished.emit(False, str(exc))


class ApplyTranslationWorker(QThread):
    """后台执行“应用翻译到游戏”，避免大批量文件操作阻塞 UI。

    - incremental 模式：语义合并增量目录 -> 迁移缓存 -> 清理增量目录 -> 恢复主路径；
    - 全量模式：事务性覆盖目标 TL 文件。
    进度通过 progress 信号上报，结果通过 finished 信号回传 UI 线程。
    """

    progress = pyqtSignal(str, int)  # message, percent
    finished = pyqtSignal(bool, str, object)  # success, message, payload

    def __init__(
        self,
        unified_extractor,
        *,
        incremental_mode: bool,
        game_dir=None,
        tl_name: str = "chinese",
        output_dir=None,
        input_dir=None,
        output_files=None,
        main_output=None,
        incremental_dir=None,
        config=None,
        project_root=None,
        project_language=None,
    ):
        super().__init__()
        self.unified_extractor = unified_extractor
        self.incremental_mode = incremental_mode
        self.game_dir = game_dir
        self.tl_name = tl_name
        self.output_dir = Path(output_dir) if output_dir else None
        self.input_dir = Path(input_dir) if input_dir else None
        self.output_files = list(output_files) if output_files else []
        self.main_output = Path(main_output) if main_output else None
        self.incremental_dir = Path(incremental_dir) if incremental_dir else None
        self.config = config
        self.project_root = project_root
        self.project_language = project_language

    def run(self):
        try:
            self.unified_extractor.set_progress_callback(
                lambda msg, pct: self.progress.emit(
                    _localize_extractor_progress(
                        msg, Localizer.get().onekey_applying_translation
                    ),
                    pct,
                )
            )
            if self.incremental_mode:
                self._run_incremental()
            else:
                self._run_full()
        except Exception as exc:
            import traceback
            traceback.print_exc()
            LogManager.get().error(f"应用翻译失败: {exc}")
            self.finished.emit(
                False,
                Localizer.localize(
                    f"应用翻译失败：{exc}",
                    "Failed to apply the translation. Check the logs for details.",
                ),
                None,
            )
        finally:
            self.unified_extractor.set_progress_callback(None)

    def _run_incremental(self):
        ok, message, payload = apply_incremental_translation(
            extractor=self.unified_extractor,
            config=self.config,
            game_dir=self.game_dir,
            tl_name=self.tl_name,
            output_dir=self.output_dir,
            main_output=self.main_output,
            incremental_dir=self.incremental_dir,
            progress_callback=lambda msg, pct: self.progress.emit(msg, pct),
        )
        if ok:
            self.config.save()
        self.finished.emit(ok, message, payload)

    def _run_full(self):
        ok, message, payload = apply_full_translation(
            config=self.config,
            output_files=self.output_files,
            output_dir=self.output_dir,
            input_dir=self.input_dir,
            project_root=self.project_root,
            project_language=self.project_language,
            progress_callback=lambda msg, pct: self.progress.emit(msg, pct),
        )
        if ok and self.project_root and self.project_language:
            self.config.save()
        self.finished.emit(ok, message, payload)
