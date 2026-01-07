"""
解包/反编译/打包页面 - 通过 Hook 注入优先解包 RPA、封装 unrpyc 反编译，以及 rpatool 打包能力。
"""
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
from module.Tool.Packer import Packer
from module.Tool.RenpyDecompiler import RenpyDecompiler
from widget.ThemeHelper import mark_toolbox_widget, mark_toolbox_scroll_area


class PackWorker(QThread):
    """后台打包工作线程"""
    progress = pyqtSignal(int, int, str)  # current, total, message
    finished = pyqtSignal(bool, str)  # success, message

    def __init__(self, src_dir: str, output_file: str):
        super().__init__()
        self.src_dir = src_dir
        self.output_file = output_file
        self.should_stop = False

    def run(self):
        try:
            from module.Tool.Packer import Packer
            packer = Packer()
            packer.pack_from_dir(
                self.src_dir,
                self.output_file,
                progress_callback=self._on_progress,
                stop_check=lambda: self.should_stop,
            )
            if self.should_stop:
                self.finished.emit(False, "打包已取消")
            else:
                self.finished.emit(True, "打包完成")
        except Exception as e:
            LogManager.get().error(f"打包失败: {e}")
            self.finished.emit(False, str(e))

    def _on_progress(self, current: int, total: int, filename: str):
        self.progress.emit(current, total, filename)

    def stop(self):
        self.should_stop = True


class PackUnpackPage(Base, QWidget):
    """解包/打包页面"""

    def __init__(self, object_name: str, parent=None):
        Base.__init__(self)
        QWidget.__init__(self, parent)
        self.setObjectName(object_name)
        mark_toolbox_widget(self)
        
        self.window = parent
        self.pack_worker = None
        self._init_ui()

    def _init_ui(self):
        """初始化界面"""
        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        layout.setContentsMargins(24, 24, 24, 24)

        # 标题
        layout.addWidget(TitleLabel("📦 解包 / 反编译 / 打包"))

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

        layout.addWidget(StrongBodyLabel("📂 解包 RPA 文件"))

        # game 目录
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("game 目录:"))
        self.unpack_game_dir_edit = LineEdit()
        self.unpack_game_dir_edit.setPlaceholderText("选择包含 .rpa 文件的 game 目录")
        btn_browse_unpack = PushButton("浏览", icon=FluentIcon.FOLDER)
        btn_browse_unpack.clicked.connect(self._browse_unpack_dir)
        row1.addWidget(self.unpack_game_dir_edit, 1)
        row1.addWidget(btn_browse_unpack)
        layout.addLayout(row1)

        # 选项
        self.unpack_direct_check = CheckBox("直接解包（UnRen：使用游戏自带 python，无需启动游戏）")
        self.unpack_direct_check.setChecked(True)
        layout.addWidget(self.unpack_direct_check)

        self.unpack_script_only_check = CheckBox("仅解包脚本（.rpy/.rpyc）")
        self.unpack_script_only_check.setChecked(True)
        layout.addWidget(self.unpack_script_only_check)

        # 按钮
        btn_row = QHBoxLayout()
        self.unpack_button = PrimaryPushButton("解包", icon=FluentIcon.FOLDER_ADD)
        self.unpack_button.clicked.connect(self._unpack)
        self.unpack_cleanup_button = PushButton("清理临时文件", icon=FluentIcon.DELETE)
        self.unpack_cleanup_button.clicked.connect(self._cleanup_unpack_artifacts)
        btn_row.addWidget(self.unpack_button)
        btn_row.addWidget(self.unpack_cleanup_button)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        return card

    def _create_pack_card(self) -> CardWidget:
        """创建打包卡片"""
        card = CardWidget(self)
        layout = QVBoxLayout(card)
        layout.setSpacing(12)

        layout.addWidget(StrongBodyLabel("📦 打包为 RPA 文件"))

        # 源目录
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("源目录:"))
        self.pack_src_dir_edit = LineEdit()
        self.pack_src_dir_edit.setPlaceholderText("选择要打包的目录")
        btn_browse_pack_src = PushButton("浏览", icon=FluentIcon.FOLDER)
        btn_browse_pack_src.clicked.connect(self._browse_pack_src)
        row1.addWidget(self.pack_src_dir_edit, 1)
        row1.addWidget(btn_browse_pack_src)
        layout.addLayout(row1)

        # 输出文件
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("输出文件:"))
        self.pack_output_edit = LineEdit()
        self.pack_output_edit.setPlaceholderText("留空则使用目录名.rpa，保存在源目录内")
        btn_browse_pack_out = PushButton("选择", icon=FluentIcon.SAVE)
        btn_browse_pack_out.clicked.connect(self._browse_pack_output)
        row2.addWidget(self.pack_output_edit, 1)
        row2.addWidget(btn_browse_pack_out)
        layout.addLayout(row2)

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
        self.pack_button = PrimaryPushButton("打包", icon=FluentIcon.ZIP_FOLDER)
        self.pack_button.clicked.connect(self._pack)
        self.pack_cancel_button = PushButton("取消", icon=FluentIcon.CANCEL)
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

        layout.addWidget(StrongBodyLabel("🧩 反编译 RPYC → RPY"))

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("游戏根目录/可执行文件:"))
        self.decompile_exe_edit = LineEdit()
        self.decompile_exe_edit.setPlaceholderText("选择游戏根目录或启动程序 (.exe)")
        btn_browse = PushButton("浏览", icon=FluentIcon.FOLDER)
        btn_browse.clicked.connect(self._browse_decompile_exe)
        row1.addWidget(self.decompile_exe_edit, 1)
        row1.addWidget(btn_browse)
        layout.addLayout(row1)

        self.decompile_overwrite_check = CheckBox("覆盖已存在的 .rpy (unrpyc --clobber)")
        self.decompile_overwrite_check.setChecked(False)
        layout.addWidget(self.decompile_overwrite_check)

        btn_row = QHBoxLayout()
        self.decompile_button = PrimaryPushButton("反编译 (经典)", icon=FluentIcon.CODE)
        self.decompile_button.clicked.connect(lambda: self._decompile("unrpyc_python"))
        btn_row.addWidget(self.decompile_button)

        self.decompile_button_v2 = PushButton("反编译 (unrpyc v2)", icon=FluentIcon.CODE)
        self.decompile_button_v2.setToolTip("使用新版本 unrpyc 适配 Ren'Py 8 系列")
        self.decompile_button_v2.clicked.connect(lambda: self._decompile("unrpyc_python_v2"))
        btn_row.addWidget(self.decompile_button_v2)

        self.unpack_and_decompile_button = PushButton("解包 + 反编译", icon=FluentIcon.PLAY)
        self.unpack_and_decompile_button.setToolTip("按解包设置先解包归档，然后执行 unrpyc（自动尝试经典/v2）")
        self.unpack_and_decompile_button.clicked.connect(self._unpack_and_decompile)
        btn_row.addWidget(self.unpack_and_decompile_button)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        return card

    def _browse_unpack_dir(self):
        """浏览解包目录"""
        directory = QFileDialog.getExistingDirectory(self, "选择 game 目录", "")
        if directory:
            self.unpack_game_dir_edit.setText(directory)

    def _browse_pack_src(self):
        """浏览打包源目录"""
        directory = QFileDialog.getExistingDirectory(self, "选择要打包的目录", "")
        if directory:
            self.pack_src_dir_edit.setText(directory)

    def _browse_pack_output(self):
        """选择打包输出文件"""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "保存 RPA 文件", "archive.rpa", "RPA 文件 (*.rpa)"
        )
        if file_path:
            self.pack_output_edit.setText(file_path)

    def _browse_decompile_exe(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择 Ren'Py 游戏可执行文件",
            "",
            "可执行文件 (*.exe)",
        )
        if file_path:
            self.decompile_exe_edit.setText(file_path)

    def _unpack(self):
        """解包 RPA"""
        try:
            game_dir = self.unpack_game_dir_edit.text().strip()
            if not game_dir:
                InfoBar.warning("提示", "请选择 game 目录", parent=self)
                return

            if not Path(game_dir).exists():
                InfoBar.error("错误", "目录不存在", parent=self)
                return

            LogManager.get().info(f"开始解包: {game_dir}")
            
            packer = Packer()
            script_only = self.unpack_script_only_check.isChecked()

            # 1) UnRen：使用游戏自带 python 直接解包（不启动游戏）
            if self.unpack_direct_check.isChecked():
                try:
                    count, messages = packer.unpack_all_unren(
                        game_dir,
                        script_only=script_only,
                    )
                    for msg in messages:
                        LogManager.get().info(msg)
                    if count > 0:
                        InfoBar.success("完成", f"已直接解包 {count} 个归档文件", parent=self)
                        return
                    InfoBar.info("提示", "未找到可解包的归档文件", parent=self)
                    return
                except Exception as e:
                    LogManager.get().error(f"直接解包失败: {e}")
                    InfoBar.warning("提示", "直接解包失败，尝试使用外部工具继续解包", parent=self)

            # 2) 外部工具：unrpa / rpatool
            count, messages = packer.unpack_all(
                game_dir,
                script_only=script_only,
                prefer_hook=False,
                allow_external_fallback=True,
                output_root=game_dir,
            )

            for msg in messages:
                LogManager.get().info(msg)

            if count > 0:
                InfoBar.success("完成", f"已解包 {count} 个 RPA 文件", parent=self)
                return

            InfoBar.info("提示", "未找到 RPA 文件，或外部工具不可用", parent=self)
            
        except Exception as e:
            LogManager.get().error(f"解包失败: {e}")
            InfoBar.error("错误", f"解包失败: {e}", parent=self)

    def _cleanup_unpack_artifacts(self):
        """清理解包/反编译可能遗留的临时文件（不影响正常文件）。"""
        try:
            game_dir = self.unpack_game_dir_edit.text().strip()
            if not game_dir:
                InfoBar.warning("提示", "请选择 game 目录", parent=self)
                return

            game_path = Path(game_dir)
            if not game_path.exists():
                InfoBar.error("错误", "目录不存在", parent=self)
                return

            root_dir = game_path.parent

            to_delete = [
                game_path / "__pycache__",
                game_path / "unpacked_rpa",
                game_path / "hook_unrpa.rpy",
                game_path / "hook_unrpa.rpyc",
                game_path / "hook_extract.rpy",
                game_path / "hook_extract.rpyc",
                game_path / "hook_add_change_language_entrance.rpy",
                game_path / "hook_add_change_language_entrance.rpyc",
                root_dir / "unpack.finish",
                root_dir / "game.pid",
                root_dir / "common_backup.zip",
                root_dir / "unrpyc.complete",
            ]

            removed = []
            for p in to_delete:
                try:
                    if not p.exists():
                        continue
                    if p.is_dir():
                        import shutil
                        shutil.rmtree(p, ignore_errors=True)
                    else:
                        p.unlink(missing_ok=True)
                    removed.append(str(p))
                except Exception:
                    continue

            if removed:
                InfoBar.success("完成", f"已清理 {len(removed)} 个临时项", parent=self)
                for item in removed:
                    LogManager.get().info(f"已清理: {item}")
            else:
                InfoBar.info("提示", "未发现需要清理的临时文件", parent=self)
        except Exception as e:
            LogManager.get().error(f"清理失败: {e}")
            InfoBar.error("错误", f"清理失败: {e}", parent=self)

    def _decompile(self, variant: str = "unrpyc_python"):
        """反编译 RPYC，variant 控制使用哪个 unrpyc 版本"""
        try:
            exe_path = self.decompile_exe_edit.text().strip()
            if not exe_path:
                InfoBar.warning("提示", "请选择游戏根目录或可执行文件", parent=self)
                return

            if not Path(exe_path).exists():
                InfoBar.error("错误", "路径不存在", parent=self)
                return

            overwrite = self.decompile_overwrite_check.isChecked()
            LogManager.get().info(f"开始反编译: {exe_path} (覆盖: {overwrite}, variant={variant})")

            decompiler = RenpyDecompiler(variant)
            decompiler.decompile(exe_path, overwrite=overwrite)

            variant_label = "unrpyc v2" if variant == "unrpyc_python_v2" else "经典 unrpyc"
            InfoBar.success("完成", f"{variant_label} 反编译完成，已生成 .rpy 文件", parent=self)

        except Exception as e:
            LogManager.get().error(f"反编译失败: {e}")
            InfoBar.error("错误", f"反编译失败: {e}", parent=self)

    def _unpack_and_decompile(self):
        """一键：按解包设置解包后，执行 unrpyc 反编译。"""
        game_dir = self.unpack_game_dir_edit.text().strip()
        if not game_dir:
            InfoBar.warning("提示", "请选择 game 目录", parent=self)
            return
        if not Path(game_dir).exists():
            InfoBar.error("错误", "目录不存在", parent=self)
            return

        # 先解包（UnRen / 外部工具）
        self._unpack()

        # 自动填充反编译目标（未填写时使用 game 的上级目录）
        if not self.decompile_exe_edit.text().strip():
            try:
                self.decompile_exe_edit.setText(str(Path(game_dir).parent))
            except Exception:
                pass

        # 默认优先 v2（内部会自动 fallback 到另一个版本）
        self._decompile("unrpyc_python_v2")

    def _pack(self):
        """打包为 RPA（后台线程）"""
        src_dir = self.pack_src_dir_edit.text().strip()
        output_file = self.pack_output_edit.text().strip()

        if not src_dir:
            InfoBar.warning("提示", "请选择源目录", parent=self)
            return

        if not Path(src_dir).exists():
            InfoBar.error("错误", "源目录不存在", parent=self)
            return

        # 如果没有指定输出文件，默认使用源目录名.rpa，保存在源目录的父目录（通常是 game 目录）
        if not output_file:
            output_file = Path(src_dir).name + ".rpa"

        # 如果输出文件不是绝对路径，则放到源目录的父目录下（例如 images -> game/images.rpa）
        output_path = Path(output_file)
        if not output_path.is_absolute():
            output_file = str(Path(src_dir).parent / output_file)

        # 打包前删除 game 目录下的 hook 文件
        game_dir = Path(src_dir).parent
        packer = Packer()
        removed = packer.remove_hook_files(str(game_dir))
        if removed:
            for f in removed:
                LogManager.get().info(f"打包前已删除 Hook 文件: {f}")

        # 检查是否已有打包任务在运行
        if self.pack_worker and self.pack_worker.isRunning():
            InfoBar.warning("提示", "打包任务正在进行中", parent=self)
            return

        LogManager.get().info(f"开始打包: {src_dir} -> {output_file}")

        # 更新 UI 状态
        self.pack_button.setEnabled(False)
        self.pack_cancel_button.setEnabled(True)
        self.pack_progress.setVisible(True)
        self.pack_progress.setValue(0)
        self.pack_status_label.setVisible(True)
        self.pack_status_label.setText("正在扫描文件...")

        # 创建并启动后台线程
        self.pack_worker = PackWorker(src_dir, output_file)
        self.pack_worker.progress.connect(self._on_pack_progress)
        self.pack_worker.finished.connect(self._on_pack_finished)
        self.pack_worker.start()

    def _cancel_pack(self):
        """取消打包"""
        if self.pack_worker and self.pack_worker.isRunning():
            self.pack_worker.stop()
            self.pack_cancel_button.setEnabled(False)
            self.pack_status_label.setText("正在取消...")

    def _on_pack_progress(self, current: int, total: int, filename: str):
        """打包进度更新"""
        if total > 0:
            percent = int(current * 100 / total)
            self.pack_progress.setValue(percent)
        self.pack_status_label.setText(f"打包中: {current}/{total} - {filename}")

    def _on_pack_finished(self, success: bool, message: str):
        """打包完成"""
        self.pack_button.setEnabled(True)
        self.pack_cancel_button.setEnabled(False)
        self.pack_progress.setVisible(False)
        self.pack_status_label.setText("")
        self.pack_status_label.setVisible(False)

        if success:
            InfoBar.success("完成", message, parent=self)
        else:
            if "未找到 rpatool" in message:
                InfoBar.warning("未实现", message, parent=self)
            elif "取消" in message:
                InfoBar.info("已取消", message, parent=self)
            else:
                InfoBar.error("错误", f"打包失败: {message}", parent=self)

        self.pack_worker = None
