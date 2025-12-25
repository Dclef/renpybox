"""
翻译抽取到 TL 页面
简化版：一个主功能 + 可折叠的高级选项
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QFileDialog
from qfluentwidgets import (
    FluentIcon,
    PushButton,
    PrimaryPushButton,
    LineEdit,
    CheckBox,
    CardWidget,
    SubtitleLabel,
    BodyLabel,
    CaptionLabel,
    ProgressBar,
    InfoBar,
    InfoBarPosition,
    SingleDirectionScrollArea,
)

from base.LogManager import LogManager
from module.Config import Config
from module.Extract.UnifiedExtractor import UnifiedExtractor
from module.Extract.ReplaceGenerator import (
    scan_missing_and_update_glossary,
    check_miss_rpy_status,
    parse_miss_rpy,
    write_replace_script,
    sync_miss_rpy_with_glossary,
    archive_miss_file,
)
from widget.ThemeHelper import mark_toolbox_widget, mark_toolbox_scroll_area


class RenpyTranslationPage(QWidget):
    """翻译抽取到 TL - 简化版"""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent=parent)
        self.logger = LogManager.get()
        self.config = Config().load()
        self._miss_status_timer = QTimer(self)
        self._miss_status_timer.setSingleShot(True)
        self._miss_status_timer.timeout.connect(self._update_miss_status)
        # 保底：至少开启补充抽取，避免全关导致不会跑
        if not self.config.extract_use_official and not self.config.extract_use_custom:
            self.config.extract_use_custom = True
        self.unified_extractor = UnifiedExtractor()
        self._init_ui()

    def _init_ui(self) -> None:
        self.setObjectName("RenpyTranslationPage")
        mark_toolbox_widget(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        title = SubtitleLabel("翻译抽取")
        layout.addWidget(title)

        # 简单说明
        intro = CaptionLabel("从 Ren'Py 游戏中提取可翻译文本到 tl 目录")
        intro.setStyleSheet("color: gray;")
        layout.addWidget(intro)

        scroll_area = SingleDirectionScrollArea(orient=Qt.Orientation.Vertical)
        scroll_area.setWidgetResizable(True)
        mark_toolbox_scroll_area(scroll_area)
        scroll_widget = QWidget()
        mark_toolbox_widget(scroll_widget, "toolboxScroll")
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.setSpacing(12)

        # 主功能区
        scroll_layout.addWidget(self._create_main_card())
        
        # 高级功能（折叠）
        scroll_layout.addWidget(self._create_advanced_card())
        
        scroll_layout.addStretch(1)

        scroll_area.setWidget(scroll_widget)
        layout.addWidget(scroll_area)

        self.progress_bar = ProgressBar(self)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # 输入变化时自动刷新缺失状态（避免返回页面后还要手动点“扫描缺失”）
        try:
            self.game_dir_edit.textChanged.connect(self._schedule_miss_status_update)
            self.tl_name_edit.textChanged.connect(self._schedule_miss_status_update)
        except Exception:
            pass

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # 页面回到前台时刷新 miss 状态
        self._schedule_miss_status_update()

    def _schedule_miss_status_update(self) -> None:
        if not hasattr(self, "miss_status"):
            return
        # 轻量防抖：用户粘贴/输入路径时避免高频 IO
        self._miss_status_timer.start(200)

    def _create_main_card(self) -> CardWidget:
        """主功能卡片 - 极简"""
        card = CardWidget(self)
        mark_toolbox_widget(card)
        layout = QVBoxLayout(card)
        layout.setSpacing(10)

        # 游戏目录（最重要的输入）
        row1 = QHBoxLayout()
        row1.addWidget(BodyLabel("游戏目录:"))
        self.game_dir_edit = LineEdit()
        self.game_dir_edit.setPlaceholderText("选择游戏文件夹（包含 game 目录的那个）")
        if self.config.renpy_game_folder:
            self.game_dir_edit.setText(self.config.renpy_game_folder)
        btn_browse = PushButton(FluentIcon.FOLDER, "浏览")
        btn_browse.clicked.connect(self._browse_game_dir)
        row1.addWidget(self.game_dir_edit, 1)
        row1.addWidget(btn_browse)
        layout.addLayout(row1)

        # 语言名称（简化）
        row2 = QHBoxLayout()
        row2.addWidget(BodyLabel("语言名称:"))
        self.tl_name_edit = LineEdit()
        self.tl_name_edit.setText("chinese")
        self.tl_name_edit.setFixedWidth(120)
        self.tl_name_edit.setToolTip("翻译文件夹名称，如 chinese、schinese 等")
        row2.addWidget(self.tl_name_edit)
        row2.addStretch(1)
        
        # 主按钮
        self.extract_btn = PrimaryPushButton(FluentIcon.PLAY, "开始抽取")
        self.extract_btn.clicked.connect(self._do_extract)
        row2.addWidget(self.extract_btn)
        layout.addLayout(row2)

        # 快速提示
        tip = CaptionLabel("默认保留已有翻译（增量），未找到 exe 也能用补充抽取；官方抽取失败可仅用补充抽取。")
        tip.setStyleSheet("color: #888;")
        layout.addWidget(tip)

        return card

    def _create_advanced_card(self) -> CardWidget:
        """高级选项卡片 - 默认折叠"""
        card = CardWidget(self)
        mark_toolbox_widget(card)
        layout = QVBoxLayout(card)
        layout.setSpacing(8)

        # 标题行（可点击展开）
        header = QHBoxLayout()
        self.advanced_toggle = PushButton("▶ 高级选项")
        self.advanced_toggle.setFlat(True)
        self.advanced_toggle.clicked.connect(self._toggle_advanced)
        header.addWidget(self.advanced_toggle)
        header.addStretch(1)
        layout.addLayout(header)

        # 高级选项内容（默认隐藏）
        self.advanced_widget = QWidget()
        adv_layout = QVBoxLayout(self.advanced_widget)
        adv_layout.setContentsMargins(0, 8, 0, 0)
        adv_layout.setSpacing(8)

        # === 抽取方式选择 ===
        extract_row = QHBoxLayout()
        extract_row.addWidget(CaptionLabel("抽取方式:"))
        
        self.chk_official = CheckBox("官方抽取")
        self.chk_official.setChecked(self.config.extract_use_official)
        self.chk_official.setToolTip("调用游戏引擎的官方翻译抽取（需要 exe）")
        self.chk_official.stateChanged.connect(self._refresh_option_state)
        extract_row.addWidget(self.chk_official)
        
        self.chk_custom = CheckBox("补充抽取")
        self.chk_custom.setChecked(self.config.extract_use_custom)
        self.chk_custom.setToolTip("自定义 AST 解析，覆盖官方遗漏的文本")
        self.chk_custom.stateChanged.connect(self._refresh_option_state)
        extract_row.addWidget(self.chk_custom)
        
        extract_row.addStretch(1)
        adv_layout.addLayout(extract_row)

        # === 可选 exe ===
        exe_row = QHBoxLayout()
        exe_row.addWidget(CaptionLabel("游戏 exe (可选):"))
        self.exe_edit = LineEdit()
        self.exe_edit.setPlaceholderText("仅勾选官方抽取时需要，留空自动查找 .exe")
        btn_exe = PushButton(FluentIcon.FOLDER, "选择")
        btn_exe.clicked.connect(lambda: self._browse_exe(self.exe_edit))
        exe_row.addWidget(self.exe_edit, 1)
        exe_row.addWidget(btn_exe)
        adv_layout.addLayout(exe_row)

        # === 其他选项 ===
        opt_row = QHBoxLayout()
        self.chk_skip_hooks = CheckBox("跳过 Hook 文件")
        self.chk_skip_hooks.setChecked(self.config.extract_skip_hook_files)
        opt_row.addWidget(self.chk_skip_hooks)
        opt_row.addStretch(1)
        adv_layout.addLayout(opt_row)

        # === 缺失补丁工具 ===
        adv_layout.addWidget(self._create_miss_section())

        layout.addWidget(self.advanced_widget)
        self.advanced_widget.setVisible(False)  # 默认折叠
        self._refresh_option_state()

        return card

    def _create_miss_section(self) -> QWidget:
        """缺失补丁区域"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(6)

        # 分隔说明
        sep = CaptionLabel("── 缺失补丁工具 ──")
        sep.setStyleSheet("color: #888;")
        layout.addWidget(sep)

        desc = CaptionLabel("检测官方抽取遗漏的文本，生成 replace_text 钩子修复")
        desc.setStyleSheet("color: #666; font-size: 11px;")
        layout.addWidget(desc)

        # 状态
        self.miss_status = CaptionLabel("")
        layout.addWidget(self.miss_status)

        # 按钮
        btn_row = QHBoxLayout()
        self.scan_btn = PushButton(FluentIcon.SEARCH, "扫描缺失")
        self.scan_btn.clicked.connect(self._scan_missing)
        btn_row.addWidget(self.scan_btn)

        self.hook_btn = PushButton(FluentIcon.EDIT, "生成钩子")
        self.hook_btn.clicked.connect(self._generate_hook)
        self.hook_btn.setEnabled(False)
        btn_row.addWidget(self.hook_btn)

        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        return widget

    def _toggle_advanced(self):
        """切换高级选项显示"""
        try:
            visible = not self.advanced_widget.isVisible()
            self.advanced_widget.setVisible(visible)
            # 更新按钮文字来表示展开/折叠状态
            text = "▼ 高级选项" if visible else "▶ 高级选项"
            self.advanced_toggle.setText(text)
        except Exception as e:
            self.logger.error(f"切换高级选项失败: {e}")

    # ==================== 核心逻辑 ====================

    def _do_extract(self):
        """执行抽取（主按钮）"""
        try:
            game_dir = self.game_dir_edit.text().strip()
            if not game_dir:
                InfoBar.warning("提示", "请先选择游戏目录", parent=self)
                return

            root_path = Path(game_dir)
            if not root_path.exists():
                InfoBar.error("错误", f"目录不存在: {game_dir}", parent=self)
                return

            # 处理路径
            exe_path: Optional[Path] = None
            if root_path.is_file():
                exe_path = root_path
                root_path = root_path.parent

            if root_path.name.lower() == "game":
                project_root = root_path.parent
            else:
                project_root = root_path

            game_folder = project_root / "game"
            if not game_folder.exists():
                InfoBar.error("错误", f"未找到 game 目录", parent=self)
                return

            tl_name = self.tl_name_edit.text().strip() or "chinese"
            tl_dir = project_root / "game" / "tl" / tl_name
            if not tl_dir.exists():
                InfoBar.error("错误", f"未找到 tl 子目录: {tl_dir}", parent=self)
                return

            def _is_effective_tl_rpy(path: Path) -> bool:
                name = path.name.lower()
                try:
                    rel = path.relative_to(tl_dir)
                    if rel.parts and rel.parts[0].lower() in {"base_box", "fonts"}:
                        return False
                except Exception:
                    pass
                if name.startswith("miss_ready_replace"):
                    return False
                if name.startswith("hook_"):
                    return False
                if name == "choice_screen_fix_auto.rpy":
                    return False
                if name in {"replace_text_auto.rpy", "set_default_language_at_startup.rpy"}:
                    return False
                return True

            has_existing_tl = any(_is_effective_tl_rpy(p) for p in tl_dir.rglob("*.rpy"))

            # 编码预检：关闭自动检测时尝试读取一个文件
            if not self.config.renpy_auto_detect_encoding:
                sample_file = next(tl_dir.rglob("*.rpy"), None)
                if sample_file:
                    try:
                        sample_file.read_text(encoding=self.config.renpy_default_encoding)
                    except Exception as e:
                        InfoBar.error("错误", f"默认编码读取失败: {self.config.renpy_default_encoding}\n{e}", parent=self)
                        return

            # 获取选项
            use_official = self.chk_official.isChecked() if hasattr(self, 'chk_official') else self.config.extract_use_official
            use_custom = self.chk_custom.isChecked() if hasattr(self, 'chk_custom') else self.config.extract_use_custom

            if not use_official and not use_custom:
                use_custom = True  # 至少启用补充抽取

            # 自动查找 exe
            if use_official and not exe_path:
                exe_edit_text = self.exe_edit.text().strip() if hasattr(self, 'exe_edit') else ""
                if exe_edit_text:
                    exe_path = Path(exe_edit_text)
                else:
                    exe_path = self._auto_find_exe(project_root)

            if use_official and not exe_path:
                use_official = False
                # 未找到 exe 时自动回退到补充抽取，避免“官方开但补充关”时无法抽取
                if not use_custom:
                    use_custom = True
                    if hasattr(self, "chk_custom"):
                        try:
                            self.chk_custom.setChecked(True)
                        except Exception:
                            pass
                self.logger.info("未找到 exe，跳过官方抽取")
                InfoBar.info("提示", "未找到 exe，已自动关闭官方抽取，改用补充抽取", parent=self)

            # 保存配置
            self.config.renpy_game_folder = game_dir
            self.config.extract_use_official = use_official
            self.config.extract_use_custom = use_custom
            if hasattr(self, 'chk_skip_hooks'):
                self.config.extract_skip_hook_files = self.chk_skip_hooks.isChecked()
            self.config.save()

            # 执行抽取
            self._begin("正在抽取翻译文本…")

            if has_existing_tl:
                self.logger.info("检测到已有翻译，启用增量抽取以保留译文")
                InfoBar.info("增量模式", "检测到已有 tl，增量抽取会保留已翻译内容", parent=self)
                result = self.unified_extractor.extract_incremental(
                    project_root,
                    tl_name,
                    exe_path,
                    use_official=use_official
                )
            else:
                result = self.unified_extractor.extract_regular(
                    project_root,
                    tl_name,
                    exe_path,
                    use_official=use_official
                )

            self._end(result.success)
            
            if result.success:
                InfoBar.success("抽取完成", result.message, parent=self)
                # 更新缺失状态
                if hasattr(self, 'miss_status'):
                    self._update_miss_status()
            else:
                InfoBar.error("抽取失败", result.message, parent=self)

        except Exception as e:
            self.logger.error(f"抽取失败: {e}")
            InfoBar.error("错误", str(e), parent=self)
            self._end(False)

    def _scan_missing(self):
        """扫描缺失文本并反补角色名到术语库"""
        try:
            target, tl, _ = self._resolve_paths()
            self._begin("正在扫描…")

            miss_path, count, added_names = scan_missing_and_update_glossary(target, tl)
            self._update_miss_status()

            if count == 0:
                InfoBar.success(
                    "扫描完成",
                    "未发现缺失文本",
                    parent=self
                )
            else:
                msg = f"发现 {count} 条缺失文本"
                if added_names > 0:
                    msg += f"，已将 {added_names} 个角色名添加到术语库"
                InfoBar.success("扫描完成", msg, parent=self)
            self._end(True)
        except Exception as e:
            self.logger.error(f"扫描失败: {e}")
            InfoBar.error("错误", str(e), parent=self)
            self._end(False)

    def _generate_hook(self):
        """生成 replace 钩子"""
        try:
            target, tl, project_root = self._resolve_paths()
            self._begin("正在生成钩子…")

            tl_dir = project_root / "game" / "tl" / tl
            status = check_miss_rpy_status(target, tl)
            miss_path = status.get("path") if isinstance(status, dict) else None
            if not status.get("exists"):
                self.progress_bar.setVisible(False)
                InfoBar.warning(
                    "提示",
                    "请先点击「扫描缺失」生成 miss_ready_replace.rpy",
                    parent=self
                )
                return
            
            # 先同步术语库翻译到 miss_ready_replace.rpy
            synced = sync_miss_rpy_with_glossary(project_root / "game", tl)
            if synced > 0:
                self.logger.info(f"已从术语库同步 {synced} 条翻译到 miss_ready_replace.rpy")
            
            pairs = parse_miss_rpy(project_root / "game", tl)

            if not pairs:
                self.progress_bar.setVisible(False)
                InfoBar.warning(
                    "提示",
                    f"请先编辑 {miss_path or 'miss_ready_replace.rpy'}，将 new 字段改为译文",
                    parent=self
                )
                return

            output = tl_dir / "replace_text_auto.rpy"
            write_replace_script(output, pairs)

            archived = archive_miss_file(target, tl)

            self._end(True)
            self._update_miss_status()
            if archived:
                InfoBar.success("完成", f"已生成钩子 ({len(pairs)} 条)，并已归档 miss 文件", parent=self)
            else:
                InfoBar.success("完成", f"已生成钩子 ({len(pairs)} 条)", parent=self)

        except Exception as e:
            self.logger.error(f"生成钩子失败: {e}")
            InfoBar.error("错误", str(e), parent=self)
            self._end(False)

    def _update_miss_status(self):
        """更新缺失状态显示"""
        try:
            target, tl, _ = self._resolve_paths()
            status = check_miss_rpy_status(target, tl)

            if not status["exists"]:
                if status.get("hook_exists"):
                    self.miss_status.setText("状态: 已生成钩子（miss 已归档）")
                    self.miss_status.setStyleSheet("color: #20a050;")
                    self.hook_btn.setEnabled(False)
                elif status.get("archived_exists"):
                    self.miss_status.setText("状态: miss 已归档（可重新扫描）")
                    self.miss_status.setStyleSheet("color: #666;")
                    self.hook_btn.setEnabled(False)
                else:
                    self.miss_status.setText("状态: 尚未扫描")
                    self.miss_status.setStyleSheet("color: #666;")
                    self.hook_btn.setEnabled(False)
            else:
                total = status["total_count"]
                done = status["translated_count"]
                if done == 0:
                    self.miss_status.setText(f"状态: {total} 条待翻译")
                    self.miss_status.setStyleSheet("color: #e0a000;")
                    self.hook_btn.setEnabled(False)
                else:
                    self.miss_status.setText(f"状态: 已翻译 {done}/{total}")
                    self.miss_status.setStyleSheet("color: #20a050;")
                    self.hook_btn.setEnabled(True)
        except Exception:
            self.miss_status.setText("状态: 请先选择游戏")
            self.miss_status.setStyleSheet("color: #666;")
            self.hook_btn.setEnabled(False)

    # ==================== 工具方法 ====================

    def _resolve_paths(self) -> tuple[str, str, Path]:
        """解析路径"""
        game_dir = self.game_dir_edit.text().strip()
        if not game_dir:
            raise RuntimeError("请先选择游戏目录")

        path = Path(game_dir).resolve()
        if path.is_file():
            project_root = path.parent
        elif path.name.lower() == "game":
            project_root = path.parent
        else:
            project_root = path

        tl = self.tl_name_edit.text().strip() or "chinese"
        target = self.exe_edit.text().strip() if hasattr(self, 'exe_edit') and self.exe_edit.text().strip() else str(project_root)

        return target, tl, project_root

    def _auto_find_exe(self, root_dir: Path) -> Optional[Path]:
        """自动查找 exe"""
        for pattern in ("*.exe", "*.py"):
            for f in root_dir.glob(pattern):
                if f.is_file() and f.stat().st_size > 1024:
                    return f
        return None

    def _browse_game_dir(self):
        path = QFileDialog.getExistingDirectory(self, "选择游戏目录")
        if path:
            self.game_dir_edit.setText(path)
            self.config.renpy_game_folder = path
            self.config.save()
            if hasattr(self, 'miss_status'):
                self._update_miss_status()

    def _browse_exe(self, edit: LineEdit):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择游戏可执行文件", "", "可执行文件 (*.exe *.py)"
        )
        if path:
            edit.setText(path)

    def _begin(self, msg: str):
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.extract_btn.setEnabled(False)

    def _end(self, ok: bool):
        self.progress_bar.setVisible(False)
        self.extract_btn.setEnabled(True)
        # 根据选项状态更新可用性
        self._refresh_option_state()

    def _refresh_option_state(self):
        """根据勾选状态刷新控件可用性"""
        try:
            use_official = self.chk_official.isChecked() if hasattr(self, 'chk_official') else False
            use_custom = self.chk_custom.isChecked() if hasattr(self, 'chk_custom') else True

            if hasattr(self, 'exe_edit'):
                self.exe_edit.setEnabled(use_official)
                if not use_official:
                    self.exe_edit.setPlaceholderText("仅勾选官方抽取时需要，留空自动查找 .exe")
                else:
                    self.exe_edit.setPlaceholderText("留空自动查找 .exe")

            # 缺失补丁工具依赖官方抽取结果，未开启时禁用
            if hasattr(self, 'scan_btn') and hasattr(self, 'hook_btn'):
                enable_missing = use_official
                self.scan_btn.setEnabled(enable_missing)
                self.hook_btn.setEnabled(enable_missing and self.hook_btn.isEnabled())
                if not enable_missing:
                    self.miss_status.setText("状态: 需先开启官方抽取")
                    self.miss_status.setStyleSheet("color: #666;")

            # 至少保证有一种抽取方式
            if not use_official and not use_custom:
                self.chk_custom.setChecked(True)
        except Exception as e:
            self.logger.warning(f"刷新选项状态失败: {e}")
