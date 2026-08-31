"""解包/反编译/打包页面 - 后台线程调用 UnRen/rpatool 解包，unrpyc 反编译，以及 rpatool 打包能力。"""
import re
from decimal import Decimal
from pathlib import Path

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFileDialog
from qfluentwidgets import (
    CardWidget,
    PushButton,
    PrimaryPushButton,
    LineEdit,
    CheckBox,
    InfoBar,
    FluentIcon,
    SingleDirectionScrollArea,
    TitleLabel,
    StrongBodyLabel,
    ProgressBar,
)

from base.Base import Base
from base.LogManager import LogManager
from module.Localizer.Localizer import Localizer
from module.Tool.Packer import Packer, PackerUnpackError
from module.Tool.RenpyDecompiler import RenpyDecompiler, remove_decompiled_rpyc
from widget.ThemeHelper import mark_toolbox_widget, mark_toolbox_scroll_area

EXE_SUFFIX = ".exe"
GAME_DIR_NAME = "game"
RPY_SUFFIX = ".rpy"
RPYC_SUFFIX = ".rpyc"
SIZE_LIMIT_PATTERN = re.compile(
    r"^\s*([0-9]+(?:\.[0-9]+)?)\s*(G(?:I?B)?|M(?:I?B)?)?\s*$",
    re.IGNORECASE,
)


def _parse_rpa_size_limit(value: str) -> int:
    """解析 G、GB、GiB、M、MB、MiB 容量格式，无单位时按 MiB。"""
    match = SIZE_LIMIT_PATTERN.fullmatch(value)
    if not match:
        raise ValueError(
            Localizer.get().pack_unpack_invalid_part_size_enter_1g_1_5g
        )

    number = Decimal(match.group(1))
    if number <= 0:
        raise ValueError(Localizer.get().pack_unpack_part_size_must_greater_than_0)

    unit = (match.group(2) or "M").upper()
    multiplier = 1024 ** 3 if unit.startswith("G") else 1024 ** 2
    size_bytes = int(number * multiplier)
    if size_bytes <= 0:
        raise ValueError(Localizer.get().pack_unpack_part_size_must_greater_than_0)
    return size_bytes


class PackWorker(QThread):
    """后台打包工作线程"""
    progress = pyqtSignal(int, int, str)  # current, total, message
    finished = pyqtSignal(bool, str)  # success, message

    def __init__(
        self,
        src_dir: str,
        output_file: str,
        max_part_size_bytes: int | None = None,
    ):
        super().__init__()
        self.src_dir = src_dir
        self.output_file = output_file
        self.max_part_size_bytes = max_part_size_bytes
        self.should_stop = False

    def run(self):
        try:
            packer = Packer()
            output_paths = packer.pack_from_dir(
                self.src_dir,
                self.output_file,
                progress_callback=self._on_progress,
                stop_check=lambda: self.should_stop,
                max_part_size_bytes=self.max_part_size_bytes,
            )
            self.finished.emit(
                True,
                Localizer.get().pack_unpack_packaging_complete_generated_rpa_file_s.format(output_paths_count=len(output_paths)),
            )
        except Exception as e:
            LogManager.get().error(f"打包失败: {e}")
            self.finished.emit(
                False,
                (
                    Localizer.get().pack_unpack_cancelled
                    if self.should_stop
                    else Localizer.localize(
                        str(e), "Packaging failed. Check the logs for details."
                    )
                ),
            )

    def _on_progress(self, current: int, total: int, filename: str):
        self.progress.emit(current, total, filename)

    def stop(self):
        self.should_stop = True


class UnpackWorker(QThread):
    """后台解包工作线程（避免阻塞 UI）"""

    progress = pyqtSignal(str)  # message
    finished = pyqtSignal(object)  # result dict

    def __init__(self, game_dir: str, *, direct: bool, script_only: bool):
        super().__init__()
        self.game_dir = game_dir
        self.direct = direct
        self.script_only = script_only

    def run(self):
        try:
            packer = Packer()

            progress_messages = {
                "direct": Localizer.get().pack_unpack_trying_direct_unpacking,
                "direct_failed": Localizer.get().pack_unpack_direct_unpacking_failed_trying_external_tools,
                "external": Localizer.get().pack_unpack_unpacking,
                "unren_bat": Localizer.get().pack_unpack_trying_unren_fallback,
            }
            result = packer.unpack_rpa_files(
                self.game_dir,
                direct=self.direct,
                script_only=self.script_only,
                remove_archives=False,
                progress_callback=lambda stage: self.progress.emit(
                    progress_messages.get(stage, stage)
                ),
            )
            method = result.get("method")
            count = int(result.get("count", 0))
            if result.get("success"):
                if method == "direct":
                    message = Localizer.get().pack_unpack_directly_unpacked_archive_s.format(count=count)
                elif method == "external":
                    message = Localizer.get().pack_unpack_unpacked_rpa_file_s.format(count=count)
                else:
                    message = Localizer.get().pack_unpack_unpacked_unren_fallback_check_game_folder_output
                self.finished.emit({
                    "level": "success",
                    "title": Localizer.get().local_glossary_completed,
                    "message": message,
                })
                return

            self.finished.emit({
                "level": "info",
                "title": Localizer.get().notice,
                "message": Localizer.get().pack_unpack_error(str(result.get("code") or "")),
            })
        except PackerUnpackError as exc:
            LogManager.get().error(f"解包失败: {exc}")
            self.finished.emit({
                "level": "error",
                "title": Localizer.get().error,
                "message": Localizer.get().pack_unpack_error(exc.code),
            })
        except Exception as exc:
            LogManager.get().error(f"解包失败: {exc}")
            self.finished.emit({
                "level": "error",
                "title": Localizer.get().error,
                "message": Localizer.get().pack_unpack_error(""),
            })


class DecompileWorker(QThread):
    """后台反编译工作线程（避免阻塞 UI）"""

    progress = pyqtSignal(str)  # message
    finished = pyqtSignal(object)  # result dict

    def __init__(self, target: str, *, overwrite: bool, fallback_unren_options: str | None = None, use_unren: bool = True):
        super().__init__()
        self.target = target
        self.overwrite = overwrite
        self.fallback_unren_options = fallback_unren_options
        self.use_unren = use_unren

    def _resolve_game_dir(self) -> Path:
        target = Path(self.target).resolve()
        if target.is_file() and target.suffix.lower() == ".exe":
            root_dir = target.parent
        else:
            root_dir = target

        if target.is_dir() and target.name.lower() == "game":
            return target

        game_dir = root_dir / "game"
        if game_dir.is_dir():
            return game_dir

        raise FileNotFoundError(
            Localizer.get().pack_unpack_could_not_locate_game_folder_unren_fallback
        )

    def run(self):
        unren_error: Exception | None = None
        if self.use_unren and self.fallback_unren_options:
            try:
                self.progress.emit(Localizer.get().pack_unpack_decompiling_unren)
                game_dir = self._resolve_game_dir()
                ok, _lines = Packer().unpack_all_unren_bat(
                    str(game_dir),
                    lang="zh",
                    options=self.fallback_unren_options,
                    purpose="反编译",
                    timeout_s=60 * 60,
                )
                if ok:
                    removed = remove_decompiled_rpyc(game_dir)
                    LogManager.get().info(f"反编译后已清理 {removed} 个同名 .rpyc")
                    self.finished.emit({
                        "level": "success",
                        "title": Localizer.get().local_glossary_completed,
                        "message": Localizer.get().pack_unpack_decompilation_completed_unren,
                    })
                    return
            except Exception as unren_exc:
                unren_error = unren_exc
                LogManager.get().error(f"UnRen 反编译失败: {unren_exc}")

        try:
            self.progress.emit(Localizer.get().pack_unpack_decompiling)
            game_dir = self._resolve_game_dir()
            decompiler = RenpyDecompiler()
            decompiler.decompile(self.target, overwrite=self.overwrite)
            removed = remove_decompiled_rpyc(game_dir)
            LogManager.get().info(f"反编译后已清理 {removed} 个同名 .rpyc")
            self.finished.emit({
                "level": "success",
                "title": Localizer.get().local_glossary_completed,
                "message": Localizer.get().pack_unpack_decompilation_complete_generated_rpy_files,
            })
        except Exception as exc:
            LogManager.get().error(f"反编译失败: {exc}")
            extra = (
                Localizer.get().pack_unpack_unren_failed.format(unren_error=unren_error)
                if unren_error
                else ""
            )
            self.finished.emit({
                "level": "error",
                "title": Localizer.get().error,
                "message": Localizer.get().pack_unpack_decompilation_failed_2.format(exc=exc, extra=extra),
            })

class CleanupWorker(QThread):
    """后台清理工作线程（避免阻塞 UI）"""

    progress = pyqtSignal(str)  # message
    finished = pyqtSignal(object)  # result dict

    def __init__(self, game_dir: str):
        super().__init__()
        self.game_dir = game_dir

    def run(self):
        try:
            self.progress.emit(Localizer.get().pack_unpack_cleaning_temporary_files)

            game_path = Path(self.game_dir)
            root_dir = game_path.parent

            to_delete = [
                game_path / "__pycache__",
                game_path / "unpacked_rpa",
                root_dir / "unpack.finish",
                root_dir / "game.pid",
                root_dir / "common_backup.zip",
                root_dir / "unrpyc.complete",
                root_dir / "decomp.cab",
                root_dir / "decomp.cab.tmp",
                root_dir / "unrpyc.py",
                root_dir / "unrpyc.pyo",
                root_dir / "deobfuscate.py",
                root_dir / "deobfuscate.pyo",
                root_dir / "decompiler",
            ]

            removed = 0
            for p in to_delete:
                try:
                    if not p.exists():
                        continue
                    if p.is_dir():
                        import shutil

                        shutil.rmtree(p, ignore_errors=True)
                    else:
                        p.unlink(missing_ok=True)
                    removed += 1
                except Exception:
                    continue

            if removed:
                self.finished.emit({
                    "level": "success",
                    "title": Localizer.get().local_glossary_completed,
                    "message": Localizer.get().pack_unpack_removed_temporary_item_s.format(removed=removed),
                })
            else:
                self.finished.emit({
                    "level": "info",
                    "title": Localizer.get().notice,
                    "message": Localizer.get().pack_unpack_no_temporary_files_need_cleaned,
                })
        except Exception as exc:
            LogManager.get().error(f"清理失败: {exc}")
            self.finished.emit({
                "level": "error",
                "title": Localizer.get().error,
                "message": Localizer.get().pack_unpack_cleanup_failed_2.format(exc=exc),
            })


class RpycCleanupWorker(QThread):
    """后台清理 RPYC 文件工作线程（避免阻塞 UI）"""

    progress = pyqtSignal(str)  # message
    finished = pyqtSignal(object)  # result dict

    def __init__(self, target: str) -> None:
        super().__init__()
        self.target = target

    def run(self) -> None:
        try:
            self.progress.emit(Localizer.get().pack_unpack_cleaning_rpyc_files)
            game_dir = self.resolve_game_dir(Path(self.target))
            removed, skipped, total = self.cleanup_rpyc_files(game_dir)
            if removed:
                detail = Localizer.get().pack_unpack_removed_rpyc_file_s.format(removed=removed)
                if skipped:
                    detail += Localizer.get().pack_unpack_skipped_file_s_without_matching_rpy_files.format(skipped=skipped)
                self.finished.emit({
                    "level": "success",
                    "title": Localizer.get().local_glossary_completed,
                    "message": detail,
                })
                return

            if total == 0:
                message = Localizer.get().pack_unpack_no_rpyc_files_found
            elif skipped:
                message = Localizer.get().pack_unpack_no_removable_rpyc_files_found_because_matching
            else:
                message = Localizer.get().pack_unpack_no_removable_rpyc_files_found
            self.finished.emit({
                "level": "info",
                "title": Localizer.get().notice,
                "message": message,
            })
        except Exception as exc:
            LogManager.get().error("清理 RPYC 失败", exc)
            self.finished.emit({
                "level": "error",
                "title": Localizer.get().error,
                "message": Localizer.get().pack_unpack_cleanup_failed_2.format(exc=exc),
            })

    def resolve_game_dir(self, target: Path) -> Path:
        resolved = target.resolve()
        if resolved.is_file() and resolved.suffix.lower() == EXE_SUFFIX:
            root_dir = resolved.parent
        else:
            root_dir = resolved

        if resolved.is_dir() and resolved.name.lower() == GAME_DIR_NAME:
            return resolved

        game_dir = root_dir / GAME_DIR_NAME
        if game_dir.is_dir():
            return game_dir

        raise FileNotFoundError(
            Localizer.get().pack_unpack_could_not_locate_game_folder_rpyc_cleanup
        )

    def cleanup_rpyc_files(self, game_dir: Path) -> tuple[int, int, int]:
        removed = 0
        skipped = 0
        total = 0
        for rpyc_file in game_dir.rglob(f"*{RPYC_SUFFIX}"):
            total += 1
            rpy_file = rpyc_file.with_suffix(RPY_SUFFIX)
            # 保留未成功反编译的脚本，避免误删唯一脚本来源。
            if not rpy_file.exists():
                skipped += 1
                continue
            try:
                rpyc_file.unlink()
                removed += 1
            except Exception as exc:
                skipped += 1
                LogManager.get().warning(f"清理 RPYC 失败 {rpyc_file}", exc)
        return removed, skipped, total


class PackUnpackPage(Base, QWidget):
    """解包/打包页面"""

    def __init__(self, object_name: str, parent=None):
        Base.__init__(self)
        QWidget.__init__(self, parent)
        self.setObjectName(object_name)
        mark_toolbox_widget(self)
        
        self.window = parent
        self.pack_worker = None
        self.unpack_worker = None
        self.decompile_worker = None
        self.cleanup_worker = None
        self._init_ui()

    def set_game_directory(self, path: str | Path) -> bool:
        """填写解包使用的 game 目录，兼容传入项目根目录。"""
        game_dir = Path(path)
        if game_dir.name.casefold() != GAME_DIR_NAME and (game_dir / GAME_DIR_NAME).is_dir():
            game_dir = game_dir / GAME_DIR_NAME
        if not game_dir.is_dir():
            return False
        self.unpack_game_dir_edit.setText(str(game_dir))
        return True

    def _init_ui(self):
        """初始化界面"""
        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        layout.setContentsMargins(24, 24, 24, 24)

        # 标题
        layout.addWidget(
            TitleLabel(
                Localizer.get().pack_unpack_unpack_decompile_pack
            )
        )

        # 创建滚动区域
        scroll_area = SingleDirectionScrollArea(orient=Qt.Orientation.Vertical)
        scroll_area.setWidgetResizable(True)
        scroll_area.enableTransparentBackground()
        mark_toolbox_scroll_area(scroll_area)

        scroll_widget = QWidget()
        mark_toolbox_widget(scroll_widget, "toolboxScroll")
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.setSpacing(12)

        # 解包卡片
        scroll_layout.addWidget(self._create_unpack_card())

        # 反编译卡片
        scroll_layout.addWidget(self._create_decompile_card())

        # 打包卡片
        scroll_layout.addWidget(self._create_pack_card())

        scroll_layout.addStretch(1)
        scroll_area.setWidget(scroll_widget)
        layout.addWidget(scroll_area)

    def _create_unpack_card(self) -> CardWidget:
        """创建解包卡片"""
        card = CardWidget(self)
        layout = QVBoxLayout(card)
        layout.setSpacing(12)

        layout.addWidget(
            StrongBodyLabel(Localizer.get().pack_unpack_unpack_rpa_files)
        )

        # game 目录
        row1 = QHBoxLayout()
        row1.addWidget(QLabel(Localizer.get().pack_unpack_game_folder))
        self.unpack_game_dir_edit = LineEdit()
        self.unpack_game_dir_edit.setPlaceholderText(
            Localizer.get().pack_unpack_select_game_folder_containing_rpa_files
        )
        btn_browse_unpack = PushButton(Localizer.get().browse, icon=FluentIcon.FOLDER)
        btn_browse_unpack.clicked.connect(self._browse_unpack_dir)
        row1.addWidget(self.unpack_game_dir_edit, 1)
        row1.addWidget(btn_browse_unpack)
        layout.addLayout(row1)

        # 选项
        self.unpack_direct_check = CheckBox(
            Localizer.get().pack_unpack_direct_unpacking_unren_uses_game_s_python
        )
        self.unpack_direct_check.setToolTip(
            Localizer.get().pack_unpack_try_game_s_python_first_then_fall
        )
        self.unpack_direct_check.setChecked(True)
        layout.addWidget(self.unpack_direct_check)

        self.unpack_script_only_check = CheckBox(
            Localizer.get().pack_unpack_scripts_only_rpy_rpyc_skip_images_audio
        )
        self.unpack_script_only_check.setToolTip(
            Localizer.get().pack_unpack_extract_script_files_only_faster_smaller_output
        )
        self.unpack_script_only_check.setChecked(False)
        layout.addWidget(self.unpack_script_only_check)

        # 按钮
        btn_row = QHBoxLayout()
        self.unpack_button = PrimaryPushButton(Localizer.get().pack_unpack_unpack, icon=FluentIcon.FOLDER_ADD)
        self.unpack_button.clicked.connect(self._unpack)
        self.unpack_cleanup_button = PushButton(
            Localizer.get().pack_unpack_clean_temporary_files,
            icon=FluentIcon.DELETE,
        )
        self.unpack_cleanup_button.clicked.connect(self._cleanup_unpack_artifacts)
        btn_row.addWidget(self.unpack_button)
        btn_row.addWidget(self.unpack_cleanup_button)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        # 解包进度（不确定进度）
        self.unpack_progress = ProgressBar(self)
        self.unpack_progress.setRange(0, 0)
        self.unpack_progress.setVisible(False)
        layout.addWidget(self.unpack_progress)

        self.unpack_status_label = QLabel("")
        self.unpack_status_label.setStyleSheet("color: gray; font-size: 11px;")
        self.unpack_status_label.setVisible(False)
        layout.addWidget(self.unpack_status_label)

        return card

    def _create_pack_card(self) -> CardWidget:
        """创建打包卡片"""
        card = CardWidget(self)
        layout = QVBoxLayout(card)
        layout.setSpacing(12)

        layout.addWidget(
            StrongBodyLabel(Localizer.get().pack_unpack_pack_rpa_files)
        )

        # 源目录
        row1 = QHBoxLayout()
        row1.addWidget(QLabel(Localizer.get().pack_unpack_source_folder))
        self.pack_src_dir_edit = LineEdit()
        self.pack_src_dir_edit.setPlaceholderText(
            Localizer.get().pack_unpack_select_folder_package
        )
        btn_browse_pack_src = PushButton(Localizer.get().browse, icon=FluentIcon.FOLDER)
        btn_browse_pack_src.clicked.connect(self._browse_pack_src)
        row1.addWidget(self.pack_src_dir_edit, 1)
        row1.addWidget(btn_browse_pack_src)
        layout.addLayout(row1)

        # 输出文件
        row2 = QHBoxLayout()
        row2.addWidget(QLabel(Localizer.get().pack_unpack_output_base_file))
        self.pack_output_edit = LineEdit()
        self.pack_output_edit.setPlaceholderText(
            Localizer.get().pack_unpack_leave_blank_use_folder_name_rpa_parent
        )
        self.pack_output_edit.setToolTip(
            Localizer.get().pack_unpack_splitting_enabled_images_rpa_produces_images_part001
        )
        btn_browse_pack_out = PushButton(Localizer.get().select, icon=FluentIcon.SAVE)
        btn_browse_pack_out.clicked.connect(self._browse_pack_output)
        row2.addWidget(self.pack_output_edit, 1)
        row2.addWidget(btn_browse_pack_out)
        layout.addLayout(row2)

        # 分包选项
        split_row = QHBoxLayout()
        self.pack_split_check = CheckBox(Localizer.get().pack_unpack_split_size)
        self.pack_split_check.setToolTip(
            Localizer.get().pack_unpack_create_independent_part001_rpa_part002_rpa_similar
        )
        self.pack_part_size_edit = LineEdit()
        self.pack_part_size_edit.setText("1G")
        self.pack_part_size_edit.setPlaceholderText(Localizer.get().pack_unpack_e_g_1g_1024m)
        self.pack_part_size_edit.setToolTip(
            Localizer.get().pack_unpack_supports_1g_1_5g_1024m_1024mib_values
        )
        self.pack_part_size_edit.setMaxLength(20)
        self.pack_part_size_edit.setEnabled(False)
        self.pack_part_size_edit.setFixedWidth(150)
        self.pack_split_check.toggled.connect(self.pack_part_size_edit.setEnabled)
        split_row.addWidget(self.pack_split_check)
        split_row.addStretch(1)
        split_row.addWidget(QLabel(Localizer.get().pack_unpack_maximum_per_part))
        split_row.addWidget(self.pack_part_size_edit)
        layout.addLayout(split_row)

        # 进度条
        self.pack_progress = ProgressBar(self)
        self.pack_progress.setRange(0, 100)
        self.pack_progress.setValue(0)
        self.pack_progress.setVisible(False)
        layout.addWidget(self.pack_progress)

        # 进度状态
        self.pack_status_label = QLabel("")
        self.pack_status_label.setStyleSheet("color: gray; font-size: 11px;")
        self.pack_status_label.setVisible(False)
        layout.addWidget(self.pack_status_label)

        # 按钮
        btn_row = QHBoxLayout()
        self.pack_button = PrimaryPushButton(Localizer.get().pack_unpack_pack, icon=FluentIcon.ZIP_FOLDER)
        self.pack_button.clicked.connect(self._pack)
        self.pack_cancel_button = PushButton(Localizer.get().app_update_cancel, icon=FluentIcon.CANCEL)
        self.pack_cancel_button.clicked.connect(self._cancel_pack)
        self.pack_cancel_button.setEnabled(False)
        btn_row.addWidget(self.pack_button)
        btn_row.addWidget(self.pack_cancel_button)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        return card

    def _create_decompile_card(self) -> CardWidget:
        """创建反编译卡片"""
        card = CardWidget(self)
        layout = QVBoxLayout(card)
        layout.setSpacing(12)

        layout.addWidget(
            StrongBodyLabel(Localizer.get().pack_unpack_decompile_rpyc_rpy)
        )

        row1 = QHBoxLayout()
        row1.addWidget(QLabel(Localizer.get().pack_unpack_game_folder_executable))
        self.decompile_exe_edit = LineEdit()
        self.decompile_exe_edit.setPlaceholderText(
            Localizer.get().pack_unpack_select_game_folder_project_root_launcher_exe
        )
        btn_browse = PushButton(Localizer.get().browse, icon=FluentIcon.FOLDER)
        btn_browse.clicked.connect(self._browse_decompile_exe)
        row1.addWidget(self.decompile_exe_edit, 1)
        row1.addWidget(btn_browse)
        layout.addLayout(row1)

        self.decompile_overwrite_check = CheckBox(
            Localizer.get().pack_unpack_overwrite_existing_rpy_files_unrpyc_clobber
        )
        self.decompile_overwrite_check.setChecked(False)
        layout.addWidget(self.decompile_overwrite_check)

        self.decompile_direct_check = CheckBox(
            Localizer.get().pack_unpack_direct_decompilation_unren_uses_game_s_python
        )
        self.decompile_direct_check.setToolTip(
            Localizer.get().pack_unpack_try_unren_first_then_fall_back_unrpyc
        )
        self.decompile_direct_check.setChecked(True)
        layout.addWidget(self.decompile_direct_check)

        btn_row = QHBoxLayout()
        self.decompile_button = PrimaryPushButton(Localizer.get().pack_unpack_decompile, icon=FluentIcon.CODE)
        self.decompile_button.setToolTip(
            Localizer.get().pack_unpack_try_unren_first_then_fall_back_unrpyc_2
        )
        self.decompile_button.clicked.connect(self._decompile)
        btn_row.addWidget(self.decompile_button)

        self.cleanup_rpyc_button = PushButton(
            Localizer.get().pack_unpack_clean_rpyc_files,
            icon=FluentIcon.DELETE,
        )
        self.cleanup_rpyc_button.setToolTip(
            Localizer.get().pack_unpack_delete_rpyc_files_have_matching_decompiled_rpy
        )
        self.cleanup_rpyc_button.clicked.connect(self.cleanup_rpyc_files)
        btn_row.addWidget(self.cleanup_rpyc_button)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        # 反编译进度（不确定进度）
        self.decompile_progress = ProgressBar(self)
        self.decompile_progress.setRange(0, 0)
        self.decompile_progress.setVisible(False)
        layout.addWidget(self.decompile_progress)

        self.decompile_status_label = QLabel("")
        self.decompile_status_label.setStyleSheet("color: gray; font-size: 11px;")
        self.decompile_status_label.setVisible(False)
        layout.addWidget(self.decompile_status_label)

        return card

    def _browse_unpack_dir(self):
        """浏览解包目录"""
        directory = QFileDialog.getExistingDirectory(
            self,
            Localizer.get().pack_unpack_select_game_folder,
            "",
        )
        if directory:
            self.unpack_game_dir_edit.setText(directory)

    def _browse_pack_src(self):
        """浏览打包源目录"""
        directory = QFileDialog.getExistingDirectory(
            self,
            Localizer.get().pack_unpack_select_folder_package_2,
            "",
        )
        if directory:
            self.pack_src_dir_edit.setText(directory)

    def _browse_pack_output(self):
        """选择打包输出文件"""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            Localizer.get().pack_unpack_select_rpa_output_base_file,
            "archive.rpa",
            Localizer.get().pack_unpack_rpa_files_rpa,
        )
        if file_path:
            self.pack_output_edit.setText(file_path)

    def _browse_decompile_exe(self):
        directory = QFileDialog.getExistingDirectory(
            self,
            Localizer.get().pack_unpack_select_game_folder_project_root,
            "",
        )
        if directory:
            self.decompile_exe_edit.setText(directory)

    def _unpack(self):
        """解包 RPA"""
        try:
            if self.unpack_worker and self.unpack_worker.isRunning():
                InfoBar.warning(
                    Localizer.get().notice,
                    Localizer.get().pack_unpack_unpacking_task_already_running,
                    parent=self,
                )
                return False

            game_dir = self.unpack_game_dir_edit.text().strip()
            if not game_dir:
                InfoBar.warning(
                    Localizer.get().notice,
                    Localizer.get().pack_unpack_select_game_folder_2,
                    parent=self,
                )
                return False

            if not Path(game_dir).exists():
                InfoBar.error(
                    Localizer.get().error,
                    Localizer.get().add_language_folder_does_not_exist,
                    parent=self,
                )
                return False

            LogManager.get().info(f"开始解包: {game_dir}")
            
            script_only = self.unpack_script_only_check.isChecked()
            direct = self.unpack_direct_check.isChecked()

            self._set_unpack_busy(True, Localizer.get().pack_unpack_preparing)
            self.unpack_worker = UnpackWorker(
                game_dir,
                direct=direct,
                script_only=script_only,
            )
            self.unpack_worker.progress.connect(self._on_unpack_progress)
            self.unpack_worker.finished.connect(self._on_unpack_finished)
            self.unpack_worker.start()
            return True

        except Exception as e:
            LogManager.get().error(f"解包失败: {e}")
            InfoBar.error(
                Localizer.get().error,
                Localizer.get().pack_unpack_unpacking_failed.format(e=e),
                parent=self,
            )
            return False

    def _on_unpack_progress(self, message: str) -> None:
        self.unpack_status_label.setText(message or "")

    def _on_unpack_finished(self, result: dict) -> None:
        self._set_unpack_busy(False)
        self.unpack_worker = None

        level = (result or {}).get("level", "info")
        title = (result or {}).get("title", Localizer.get().notice)
        message = (result or {}).get("message", "")

        if level == "success":
            LogManager.get().info(message or "解包完成")
            InfoBar.success(title, message, parent=self)
        elif level == "warning":
            LogManager.get().warning(message or "解包提示")
            InfoBar.warning(title, message, parent=self)
        elif level == "error":
            LogManager.get().error(message or "解包失败")
            InfoBar.error(title, message, parent=self)
        else:
            LogManager.get().info(message or "解包完成")
            InfoBar.info(title, message, parent=self)

    def _cleanup_unpack_artifacts(self):
        """清理解包/反编译可能遗留的临时文件（不影响正常文件）。"""
        try:
            if self.cleanup_worker and self.cleanup_worker.isRunning():
                InfoBar.warning(
                    Localizer.get().notice,
                    Localizer.get().pack_unpack_cleanup_task_already_running,
                    parent=self,
                )
                return

            if self.unpack_worker and self.unpack_worker.isRunning():
                InfoBar.warning(
                    Localizer.get().notice,
                    Localizer.get().pack_unpack_unpacking_task_already_running,
                    parent=self,
                )
                return

            if self.decompile_worker and self.decompile_worker.isRunning():
                InfoBar.warning(
                    Localizer.get().notice,
                    Localizer.get().pack_unpack_decompilation_task_already_running,
                    parent=self,
                )
                return

            game_dir = self.unpack_game_dir_edit.text().strip()
            if not game_dir:
                InfoBar.warning(
                    Localizer.get().notice,
                    Localizer.get().pack_unpack_select_game_folder_2,
                    parent=self,
                )
                return

            game_path = Path(game_dir)
            if not game_path.exists():
                InfoBar.error(
                    Localizer.get().error,
                    Localizer.get().add_language_folder_does_not_exist,
                    parent=self,
                )
                return

            self._set_unpack_busy(True, Localizer.get().pack_unpack_preparing_cleanup)
            self.cleanup_worker = CleanupWorker(game_dir)
            self.cleanup_worker.progress.connect(self._on_cleanup_progress)
            self.cleanup_worker.finished.connect(self._on_cleanup_finished)
            self.cleanup_worker.start()
        except Exception as e:
            LogManager.get().error(f"清理失败: {e}")
            InfoBar.error(
                Localizer.get().error,
                Localizer.get().pack_unpack_cleanup_failed.format(e=e),
                parent=self,
            )

    def _on_cleanup_progress(self, message: str) -> None:
        self.unpack_status_label.setText(message or "")

    def _on_cleanup_finished(self, result: dict) -> None:
        self._set_unpack_busy(False)
        self.cleanup_worker = None

        level = (result or {}).get("level", "info")
        title = (result or {}).get("title", Localizer.get().notice)
        message = (result or {}).get("message", "")

        if level == "success":
            LogManager.get().info(message or "反编译完成")
            InfoBar.success(title, message, parent=self)
        elif level == "warning":
            LogManager.get().warning(message or "反编译提示")
            InfoBar.warning(title, message, parent=self)
        elif level == "error":
            LogManager.get().error(message or "反编译失败")
            InfoBar.error(title, message, parent=self)
        else:
            LogManager.get().info(message or "反编译完成")
            InfoBar.info(title, message, parent=self)

    def _decompile(self, fallback_unren_options: str | None = None):
        """反编译 RPYC → RPY（unrpyc v2）"""
        try:
            if self.decompile_worker and self.decompile_worker.isRunning():
                InfoBar.warning(
                    Localizer.get().notice,
                    Localizer.get().pack_unpack_decompilation_task_already_running,
                    parent=self,
                )
                return

            exe_path = self.decompile_exe_edit.text().strip()
            if not exe_path:
                InfoBar.warning(
                    Localizer.get().notice,
                    Localizer.get().pack_unpack_select_game_folder_project_root_executable,
                    parent=self,
                )
                return

            if not Path(exe_path).exists():
                InfoBar.error(
                    Localizer.get().error,
                    Localizer.get().pack_unpack_path_does_not_exist,
                    parent=self,
                )
                return

            overwrite = self.decompile_overwrite_check.isChecked()
            use_unren = self.decompile_direct_check.isChecked()
            mode = "优先 UnRen" if use_unren else "unrpyc"
            LogManager.get().info(f"开始反编译: {exe_path} (覆盖: {overwrite}, {mode})")

            fallback_options = fallback_unren_options or "2x"
            self._set_decompile_busy(True, Localizer.get().pack_unpack_preparing)
            self.decompile_worker = DecompileWorker(
                exe_path,
                overwrite=overwrite,
                fallback_unren_options=fallback_options,
                use_unren=use_unren,
            )
            self.decompile_worker.progress.connect(self._on_decompile_progress)
            self.decompile_worker.finished.connect(self._on_decompile_finished)
            self.decompile_worker.start()

        except Exception as e:
            LogManager.get().error(f"反编译失败: {e}")
            InfoBar.error(
                Localizer.get().error,
                Localizer.get().pack_unpack_decompilation_failed.format(e=e),
                parent=self,
            )

    def _on_decompile_progress(self, message: str) -> None:
        self.decompile_status_label.setText(message or "")

    def _on_decompile_finished(self, result: dict) -> None:
        self._set_decompile_busy(False)
        self.decompile_worker = None

        level = (result or {}).get("level", "info")
        title = (result or {}).get("title", Localizer.get().notice)
        message = (result or {}).get("message", "")

        if level == "success":
            LogManager.get().info(message or "反编译完成")
            InfoBar.success(title, message, parent=self)
        elif level == "warning":
            LogManager.get().warning(message or "反编译提示")
            InfoBar.warning(title, message, parent=self)
        elif level == "error":
            LogManager.get().error(message or "反编译失败")
            InfoBar.error(title, message, parent=self)
        else:
            LogManager.get().info(message or "反编译完成")
            InfoBar.info(title, message, parent=self)

    def cleanup_rpyc_files(self) -> None:
        """清理 game 目录下已成功反编译的 RPYC 文件。"""
        try:
            if self.decompile_worker and self.decompile_worker.isRunning():
                InfoBar.warning(
                    Localizer.get().notice,
                    Localizer.get().pack_unpack_cleanup_task_already_running,
                    parent=self,
                )
                return

            if self.unpack_worker and self.unpack_worker.isRunning():
                InfoBar.warning(
                    Localizer.get().notice,
                    Localizer.get().pack_unpack_unpacking_task_already_running,
                    parent=self,
                )
                return

            if self.cleanup_worker and self.cleanup_worker.isRunning():
                InfoBar.warning(
                    Localizer.get().notice,
                    Localizer.get().pack_unpack_cleanup_task_already_running,
                    parent=self,
                )
                return

            target = self.decompile_exe_edit.text().strip()
            if not target:
                fallback = self.unpack_game_dir_edit.text().strip()
                if fallback:
                    self.decompile_exe_edit.setText(fallback)
                    target = fallback
            if not target:
                InfoBar.warning(
                    Localizer.get().notice,
                    Localizer.get().pack_unpack_select_game_folder_project_root_executable,
                    parent=self,
                )
                return

            if not Path(target).exists():
                InfoBar.error(
                    Localizer.get().error,
                    Localizer.get().pack_unpack_path_does_not_exist,
                    parent=self,
                )
                return

            LogManager.get().info(f"开始清理 RPYC: {target}")
            self._set_decompile_busy(True, Localizer.get().pack_unpack_preparing_cleanup)
            self.decompile_worker = RpycCleanupWorker(target)
            self.decompile_worker.progress.connect(self._on_decompile_progress)
            self.decompile_worker.finished.connect(self._on_decompile_finished)
            self.decompile_worker.start()
        except Exception as exc:
            LogManager.get().error("清理 RPYC 失败", exc)
            InfoBar.error(
                Localizer.get().error,
                Localizer.get().pack_unpack_cleanup_failed_2.format(exc=exc),
                parent=self,
            )

    def _set_unpack_busy(self, busy: bool, message: str = "") -> None:
        self.unpack_button.setEnabled(not busy)
        self.unpack_cleanup_button.setEnabled(not busy)
        self.unpack_progress.setVisible(busy)
        self.unpack_status_label.setVisible(busy)
        self.unpack_status_label.setText(message or "")

        # 避免同时触发反编译导致目录冲突
        self.decompile_button.setEnabled(not busy)
        self.cleanup_rpyc_button.setEnabled(not busy)

    def _set_decompile_busy(self, busy: bool, message: str = "") -> None:
        self.decompile_button.setEnabled(not busy)
        self.cleanup_rpyc_button.setEnabled(not busy)
        self.decompile_progress.setVisible(busy)
        self.decompile_status_label.setVisible(busy)
        self.decompile_status_label.setText(message or "")

        # 避免同时触发解包导致目录冲突
        self.unpack_button.setEnabled(not busy)
        self.unpack_cleanup_button.setEnabled(not busy)
        self.cleanup_rpyc_button.setEnabled(not busy)

    def _pack(self):
        """打包为 RPA（后台线程）"""
        src_dir = self.pack_src_dir_edit.text().strip()
        output_file = self.pack_output_edit.text().strip()

        if not src_dir:
            InfoBar.warning(
                Localizer.get().notice,
                Localizer.get().pack_unpack_select_source_folder,
                parent=self,
            )
            return

        if not Path(src_dir).exists():
            InfoBar.error(
                Localizer.get().error,
                Localizer.get().pack_unpack_source_folder_does_not_exist,
                parent=self,
            )
            return

        # 如果没有指定输出文件，默认使用源目录名.rpa，保存在源目录的父目录（通常是 game 目录）
        if not output_file:
            output_file = Path(src_dir).name + ".rpa"

        # 如果输出文件不是绝对路径，则放到源目录的父目录下（例如 images -> game/images.rpa）
        output_path = Path(output_file)
        if not output_path.is_absolute():
            output_file = str(Path(src_dir).parent / output_file)

        # 检查是否已有打包任务在运行
        if self.pack_worker and self.pack_worker.isRunning():
            InfoBar.warning(
                Localizer.get().notice,
                Localizer.get().pack_unpack_packaging_task_already_running,
                parent=self,
            )
            return

        max_part_size_bytes = None
        if self.pack_split_check.isChecked():
            try:
                max_part_size_bytes = _parse_rpa_size_limit(
                    self.pack_part_size_edit.text()
                )
            except ValueError as error:
                InfoBar.warning(Localizer.get().notice, str(error), parent=self)
                self.pack_part_size_edit.setFocus()
                return

        LogManager.get().info(f"开始打包: {src_dir} -> {output_file}")

        # 更新 UI 状态
        self.pack_button.setEnabled(False)
        self.pack_cancel_button.setEnabled(True)
        self.pack_progress.setVisible(True)
        self.pack_progress.setValue(0)
        self.pack_status_label.setVisible(True)
        self.pack_status_label.setText(Localizer.get().pack_unpack_scanning_files)

        # 创建并启动后台线程
        self.pack_worker = PackWorker(
            src_dir,
            output_file,
            max_part_size_bytes=max_part_size_bytes,
        )
        self.pack_worker.progress.connect(self._on_pack_progress)
        self.pack_worker.finished.connect(self._on_pack_finished)
        self.pack_worker.start()

    def _cancel_pack(self):
        """取消打包"""
        if self.pack_worker and self.pack_worker.isRunning():
            self.pack_worker.stop()
            self.pack_cancel_button.setEnabled(False)
            self.pack_status_label.setText(
                Localizer.get().pack_unpack_cancelling_after_current_part_finishes_writing
            )

    def _on_pack_progress(self, current: int, total: int, filename: str):
        """打包进度更新"""
        if total > 0:
            percent = int(current * 100 / total)
            self.pack_progress.setValue(percent)
        self.pack_status_label.setText(
            Localizer.get().pack_unpack_packing.format(current=current, total=total, filename=filename)
        )

    def _on_pack_finished(self, success: bool, message: str):
        """打包完成"""
        self.pack_button.setEnabled(True)
        self.pack_cancel_button.setEnabled(False)
        self.pack_progress.setVisible(False)
        self.pack_status_label.setText("")
        self.pack_status_label.setVisible(False)

        if success:
            InfoBar.success(Localizer.get().local_glossary_completed, message, parent=self)
        else:
            if message == Localizer.get().pack_unpack_cancelled:
                InfoBar.info(Localizer.get().pack_unpack_cancelled, message, parent=self)
            else:
                InfoBar.error(
                    Localizer.get().error,
                    Localizer.get().pack_unpack_packaging_failed.format(message=message),
                    parent=self,
                )

        self.pack_worker = None


