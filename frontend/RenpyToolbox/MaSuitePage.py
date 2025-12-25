# -*- coding: utf-8 -*-
"""前端页面 - 终极结构导出（哈基米修正版）。"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFileDialog,
)
from qfluentwidgets import (
    CardWidget,
    SubtitleLabel,
    BodyLabel,
    CaptionLabel,
    LineEdit,
    ComboBox,
    PushButton,
    PrimaryPushButton,
    CheckBox,
    InfoBar,
    FluentIcon,
)

from base.Base import Base
from base.LogManager import LogManager
from module.Config import Config
from module.Extract.HakimiSuiteRunner import HakimiSuiteRunner
from module.Extract.EmojiReplacer import (
    load_default_mapping,
    apply_replacements_dir,
    backup_folder,
)
from widget.ThemeHelper import mark_toolbox_widget


class MaSuitePage(Base, QWidget):
    """调用 MaSuiteRunner，生成 Excel 与终极结构文件。"""

    def __init__(self, object_name: str, parent=None):
        Base.__init__(self)
        QWidget.__init__(self, parent)
        self.setObjectName(object_name)
        mark_toolbox_widget(self)

        self.logger = LogManager.get()
        self.config = Config().load()
        self.hakimi_runner = HakimiSuiteRunner(self.logger)

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = SubtitleLabel("翻译套件（结构优化版）")
        layout.addWidget(title)

        desc = CaptionLabel("将游戏源码提取为 Excel、生成终极结构翻译文件（translate_names/others.rpy + replace.rpy）。")
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #666;")
        layout.addWidget(desc)

        layout.addWidget(self._create_form_card())
        layout.addWidget(self._create_emoji_card())
        layout.addStretch(1)

    def _create_form_card(self) -> CardWidget:
        card = CardWidget(self)
        mark_toolbox_widget(card)
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(10)

        # 游戏路径
        path_row = QHBoxLayout()
        path_row.addWidget(BodyLabel("游戏路径:"))
        self.path_edit = LineEdit()
        self.path_edit.setPlaceholderText("选择游戏目录（包含 game 的上级）或 exe")
        if self.config.renpy_game_folder:
            self.path_edit.setText(self.config.renpy_game_folder)
        btn_browse_dir = PushButton(FluentIcon.FOLDER, "选目录")
        btn_browse_dir.clicked.connect(self._browse_dir)
        btn_browse_exe = PushButton("选exe")
        btn_browse_exe.clicked.connect(self._browse_exe_into_path)
        path_row.addWidget(self.path_edit, 1)
        path_row.addWidget(btn_browse_dir)
        path_row.addWidget(btn_browse_exe)
        card_layout.addLayout(path_row)

        # 语言与官方提取
        tl_row = QHBoxLayout()
        tl_row.addWidget(BodyLabel("语言名称:"))
        self.tl_edit = LineEdit()
        self.tl_edit.setText("chinese")
        self.tl_edit.setFixedWidth(150)
        self.tl_edit.setToolTip("tl/<language> 目录名，例如 chinese / schinese / tchinese")
        tl_row.addWidget(self.tl_edit)

        self.chk_official = CheckBox("先执行官方提取（默认关闭）")
        self.chk_official.setChecked(False)
        self.chk_official.stateChanged.connect(self._toggle_official_state)
        tl_row.addWidget(self.chk_official)
        tl_row.addStretch(1)
        card_layout.addLayout(tl_row)

        # 模式（老猫套件 v7.5 多模式版）
        mode_row = QHBoxLayout()
        mode_row.addWidget(BodyLabel("提取模式:"))
        self.mode_combo = ComboBox()
        self.mode_combo.addItems([
            "仅标准模式(稳)",
            "标准+外部文件(.json/.yml)",
            "标准+外部+疯狗模式(慎用)",
        ])
        self.mode_combo.setCurrentIndex(0)
        self.mode_combo.setToolTip("对应老猫套件 v7.5：1=标准 2=外部文件 3=外部+疯狗")
        mode_row.addWidget(self.mode_combo, 1)
        mode_row.addStretch(1)
        card_layout.addLayout(mode_row)

        opt_row = QHBoxLayout()
        self.chk_emoji = CheckBox("生成 Emoji 替换表")
        self.chk_emoji.setChecked(False)
        self.chk_emoji.setToolTip("扫描 tl/<lang> 中的特效标记（{} / []），生成译前/译后替换表")
        opt_row.addWidget(self.chk_emoji)
        opt_row.addStretch(1)
        card_layout.addLayout(opt_row)

        # 可选 exe
        exe_row = QHBoxLayout()
        exe_row.addWidget(BodyLabel("官方提取 exe (可选):"))
        self.exe_edit = LineEdit()
        self.exe_edit.setPlaceholderText("仅勾选官方提取时需要，留空自动查找")
        self.exe_edit.setEnabled(False)
        btn_exe = PushButton(FluentIcon.FOLDER, "选择")
        btn_exe.clicked.connect(self._browse_exe)
        exe_row.addWidget(self.exe_edit, 1)
        exe_row.addWidget(btn_exe)
        card_layout.addLayout(exe_row)

        # 状态 + 按钮
        status_row = QHBoxLayout()
        self.status_label = CaptionLabel("等待操作…")
        self.status_label.setStyleSheet("color: #666;")
        status_row.addWidget(self.status_label)
        status_row.addStretch(1)
        card_layout.addLayout(status_row)

        action_row = QHBoxLayout()
        self.run_btn = PrimaryPushButton(FluentIcon.PLAY, "生成终极结构")
        self.run_btn.clicked.connect(self._run_suite)
        action_row.addStretch(1)
        action_row.addWidget(self.run_btn)
        card_layout.addLayout(action_row)

        return card

    def _create_emoji_card(self) -> CardWidget:
        card = CardWidget(self)
        mark_toolbox_widget(card)
        layout = QVBoxLayout(card)
        layout.setSpacing(8)

        layout.addWidget(BodyLabel("Emoji 替换助手（目录批量）"))
        tip = CaptionLabel("基于哈基米/旧版生成的映射表，对选定目录下所有 .rpy 做译前/译后替换。")
        tip.setStyleSheet("color: #666;")
        tip.setWordWrap(True)
        layout.addWidget(tip)

        path_row = QHBoxLayout()
        path_row.addWidget(BodyLabel("目标目录:"))
        self.emoji_dir_edit = LineEdit()
        self.emoji_dir_edit.setPlaceholderText("选择需要处理的目录（如 game/tl/Chinese）")
        btn_browse = PushButton(FluentIcon.FOLDER, "选择")
        btn_browse.clicked.connect(self._browse_emoji_dir)
        path_row.addWidget(self.emoji_dir_edit, 1)
        path_row.addWidget(btn_browse)
        layout.addLayout(path_row)

        btn_row = QHBoxLayout()
        self.btn_emoji_prepare = PushButton("译前加密 (目录)")
        self.btn_emoji_prepare.clicked.connect(lambda: self._run_emoji_dir("prepare"))
        self.btn_emoji_restore = PushButton("译后还原 (目录)")
        self.btn_emoji_restore.clicked.connect(lambda: self._run_emoji_dir("restore"))
        btn_row.addWidget(self.btn_emoji_prepare)
        btn_row.addWidget(self.btn_emoji_restore)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        return card

    # -------------------- UI handlers -------------------- #
    def _toggle_official_state(self):
        enabled = self.chk_official.isChecked()
        self.exe_edit.setEnabled(enabled)
        if not enabled:
            self.exe_edit.clear()

    def _browse_emoji_dir(self):
        path = QFileDialog.getExistingDirectory(self, "选择需要处理的目录（含 .rpy）")
        if path:
            self.emoji_dir_edit.setText(path)

    def _browse_dir(self):
        path = QFileDialog.getExistingDirectory(self, "选择游戏目录")
        if path:
            self.path_edit.setText(path)

    def _browse_exe_into_path(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择游戏可执行文件",
            "",
            "可执行文件 (*.exe *.py);;所有文件 (*)",
        )
        if path:
            self.path_edit.setText(path)

    def _browse_exe(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择官方提取用的 exe",
            "",
            "可执行文件 (*.exe *.py);;所有文件 (*)",
        )
        if path:
            self.exe_edit.setText(path)
            if not self.chk_official.isChecked():
                self.chk_official.setChecked(True)

    def _set_running(self, running: bool, message: Optional[str] = None):
        self.run_btn.setEnabled(not running)
        if message is not None:
            self.status_label.setText(message)
            self.status_label.setStyleSheet("color: #0078d4;" if running else "color: #666;")

    def _run_suite(self):
        game_path = self.path_edit.text().strip()
        if not game_path:
            InfoBar.warning("提示", "请先选择游戏目录或 exe", parent=self)
            return

        tl_name = self.tl_edit.text().strip() or "chinese"
        use_official = self.chk_official.isChecked()
        gen_emoji = self.chk_emoji.isChecked()
        exe_path = self.exe_edit.text().strip() if use_official and self.exe_edit.text().strip() else None
        mode = str(self.mode_combo.currentIndex() + 1) if hasattr(self, "mode_combo") else "1"

        self._set_running(True, "正在生成终极结构…")
        try:
            result = self.hakimi_runner.run(
                game_path,
                tl_name,
                use_official=use_official,
                exe_path=exe_path,
                gen_emoji=gen_emoji,
                mode=mode,
            )
            if result is None:
                InfoBar.info("完成", "未生成任何结果，请检查路径或 tl 目录", parent=self)
                self.status_label.setText("未生成结果")
                self.status_label.setStyleSheet("color: #e67e22;")
                return

            result_path = ""
            if hasattr(result, "result_dir") and isinstance(result.result_dir, Path):
                result_path = str(result.result_dir)
            elif hasattr(result, "base_dir") and getattr(result, "base_dir", None):
                result_path = str(result.base_dir)

            extra = ""
            emoji_count = getattr(result, "emoji_replacements", 0)
            emoji_dir = getattr(result, "emoji_output_dir", None) or getattr(result, "emoji_dir", None)
            if gen_emoji and emoji_count:
                extra = f"\nEmoji/Tag 对照: {emoji_count} 条 → {emoji_dir}"

            summary = f"角色名 {result.names_count} 条，其他 {result.others_count} 条，替换 {result.replace_count} 条"
            if hasattr(result, "deleted_count"):
                summary += f"；删除 {result.deleted_count} 条"

            default_out = "translate_output"
            detail = f"{summary}\n输出目录: {result_path or default_out}{extra}"
            InfoBar.success("完成", detail, parent=self)
            self.status_label.setText(f"完成：{result_path or '已写入输出目录'}")
            self.status_label.setStyleSheet("color: #107c10;")

            # 记住路径
            self.config.renpy_game_folder = game_path
            self.config.save()
        except Exception as e:
            self.logger.error(f"翻译套件执行失败: {e}")
            InfoBar.error("错误", str(e), parent=self)
            self.status_label.setText("执行失败")
            self.status_label.setStyleSheet("color: #c50f1f;")
        finally:
            self._set_running(False)

    def _run_emoji_dir(self, mode: str):
        folder_path = self.emoji_dir_edit.text().strip()
        if not folder_path:
            InfoBar.warning("提示", "请选择需要处理的目录", parent=self)
            return
        target = Path(folder_path)
        if not target.exists():
            InfoBar.error("错误", f"目录不存在: {target}", parent=self)
            return

        try:
            project_root = self._resolve_project_root()
            mapping = load_default_mapping(project_root, mode)

            # 备份
            backup_path = backup_folder(target)
            self.logger.info(f"已备份到: {backup_path}")

            success, failed = apply_replacements_dir(target, mapping, is_restore=(mode == "restore"))

            InfoBar.success(
                "完成",
                f"已处理目录: {target}\n成功 {success} 个文件，失败 {failed} 个\n备份: {backup_path}",
                parent=self,
            )
        except Exception as e:
            self.logger.error(f"Emoji 替换失败: {e}")
            InfoBar.error("错误", str(e), parent=self)

    def _resolve_project_root(self) -> Path:
        base_path = self.path_edit.text().strip() or self.config.renpy_game_folder
        if not base_path:
            raise RuntimeError("请先在上方选择游戏目录或 exe")
        path = Path(base_path).expanduser().resolve()
        project_root = path.parent if path.is_file() else path
        if project_root.name.lower() == "game":
            project_root = project_root.parent
        if not (project_root / "game").exists():
            raise FileNotFoundError(f"未找到 game 目录: {project_root / 'game'}")
        return project_root


__all__ = ["MaSuitePage"]
