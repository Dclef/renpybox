"""安卓打包页面 - 安装 SDK / 生成签名 / 构建 APK。"""

from __future__ import annotations

import os
import re
import shutil
import zipfile
from datetime import datetime
from pathlib import Path

from PyQt5.QtCore import Qt, QThread, pyqtSignal, QUrl
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFileDialog
from qfluentwidgets import (
    CardWidget,
    PushButton,
    PrimaryPushButton,
    LineEdit,
    CheckBox,
    InfoBar,
    MessageBox,
    FluentIcon,
    SingleDirectionScrollArea,
    TitleLabel,
    StrongBodyLabel,
    ProgressBar,
)

from base.Base import Base
from base.LogManager import LogManager
from module.Config import Config
from module.Tool.AndroidBuilder import AndroidBuilder
from widget.ThemeHelper import mark_toolbox_widget, mark_toolbox_scroll_area


class AndroidTaskWorker(QThread):
    output = pyqtSignal(str)
    finished = pyqtSignal(bool, str)

    def __init__(self, task):
        super().__init__()
        self._task = task

    def run(self):
        try:
            ok, message = self._task(self._emit_output)
            self.finished.emit(bool(ok), message or "")
        except Exception as exc:
            LogManager.get().error(f"安卓任务失败: {exc}")
            self.output.emit(str(exc))
            self.finished.emit(False, str(exc))

    def _emit_output(self, line: str) -> None:
        if line:
            self.output.emit(line)


class AndroidBuildPage(Base, QWidget):
    """安卓打包页面"""

    RESOURCE_EXTENSIONS = {
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
        ".gif",
        ".bmp",
        ".mp3",
        ".ogg",
        ".wav",
        ".flac",
        ".m4a",
        ".aac",
        ".opus",
        ".mp4",
        ".webm",
        ".mkv",
        ".avi",
        ".mov",
    }

    def __init__(self, object_name: str, parent=None):
        Base.__init__(self)
        QWidget.__init__(self, parent)
        self.setObjectName(object_name)
        mark_toolbox_widget(self)

        self.window = parent
        self.config = Config().load()
        self.worker: AndroidTaskWorker | None = None
        self._open_bin_after_build = False

        self._init_ui()
        self._load_config()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        layout.setContentsMargins(24, 24, 24, 24)

        layout.addWidget(TitleLabel("安卓打包"))

        scroll_area = SingleDirectionScrollArea(orient=Qt.Orientation.Vertical)
        scroll_area.setWidgetResizable(True)
        scroll_area.enableTransparentBackground()
        mark_toolbox_scroll_area(scroll_area)

        scroll_widget = QWidget()
        mark_toolbox_widget(scroll_widget, "toolboxScroll")
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.setSpacing(12)

        scroll_layout.addWidget(self._create_path_card())
        scroll_layout.addWidget(self._create_android_config_card())
        scroll_layout.addWidget(self._create_env_card())
        scroll_layout.addWidget(self._create_shell_card())
        scroll_layout.addWidget(self._create_build_card())
        scroll_layout.addStretch(1)
        scroll_area.setWidget(scroll_widget)
        layout.addWidget(scroll_area)

        self.progress = ProgressBar(self)
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

    def _create_path_card(self) -> CardWidget:
        card = CardWidget(self)
        layout = QVBoxLayout(card)
        layout.setSpacing(12)

        layout.addWidget(StrongBodyLabel("路径设置"))
        note = QLabel("如果制作安卓壳子，请在群：821152470 下载魔改 SDK。")
        layout.addWidget(note)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Ren'Py SDK:"))
        self.sdk_path_edit = LineEdit()
        self.sdk_path_edit.setPlaceholderText("选择 renpy-sdk 目录")
        btn_sdk = PushButton("浏览", icon=FluentIcon.FOLDER)
        btn_sdk.clicked.connect(self._browse_sdk_path)
        row1.addWidget(self.sdk_path_edit, 1)
        row1.addWidget(btn_sdk)
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("项目目录:"))
        self.project_path_edit = LineEdit()
        self.project_path_edit.setPlaceholderText("选择 Ren'Py 项目根目录")
        btn_project = PushButton("浏览", icon=FluentIcon.FOLDER)
        btn_project.clicked.connect(self._browse_project_path)
        row2.addWidget(self.project_path_edit, 1)
        row2.addWidget(btn_project)
        layout.addLayout(row2)

        return card

    def _create_android_config_card(self) -> CardWidget:
        card = CardWidget(self)
        layout = QVBoxLayout(card)
        layout.setSpacing(12)

        layout.addWidget(StrongBodyLabel("Android 配置 (android.json)"))

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("应用名:"))
        self.app_name_edit = LineEdit()
        self.app_name_edit.setPlaceholderText("显示名称")
        row1.addWidget(self.app_name_edit, 1)
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("包名:"))
        self.package_name_edit = LineEdit()
        self.package_name_edit.setPlaceholderText("例如 com.example.game")
        row2.addWidget(self.package_name_edit, 1)
        layout.addLayout(row2)

        row3 = QHBoxLayout()
        row3.addWidget(QLabel("版本:"))
        self.version_edit = LineEdit()
        self.version_edit.setPlaceholderText("例如 1.0.0")
        row3.addWidget(self.version_edit, 1)
        layout.addLayout(row3)

        self.update_always_check = CheckBox("自动更新 Java 代码", card)
        self.update_always_check.setVisible(False)
        self.update_icons_check = CheckBox("自动更新图标", card)
        self.update_icons_check.setVisible(False)

        hint = QLabel(
            "图标替换：项目根目录放 android-icon_foreground.png 与 android-icon_background.png（PNG，建议 1024x1024）。\n"
            "启动图：android-presplash.png/jpg、android-downloading.png/jpg（建议 930x580 或保持同比例）。"
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        row7 = QHBoxLayout()
        self.dname_label = QLabel("签名名称:")
        self.dname_label.setVisible(False)
        row7.addWidget(self.dname_label)
        self.dname_edit = LineEdit()
        self.dname_edit.setPlaceholderText("生成 keystore 时的组织/名称 (可选)")
        self.dname_edit.setVisible(False)
        row7.addWidget(self.dname_edit, 1)
        layout.addLayout(row7)

        btn_row = QHBoxLayout()
        self.write_json_button = PrimaryPushButton("写入 android.json", icon=FluentIcon.SAVE)
        self.write_json_button.clicked.connect(self._write_android_json)
        btn_row.addWidget(self.write_json_button)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        return card

    def _create_env_card(self) -> CardWidget:
        card = CardWidget(self)
        layout = QVBoxLayout(card)
        layout.setSpacing(12)

        layout.addWidget(StrongBodyLabel("环境与签名"))

        btn_row = QHBoxLayout()
        self.check_env_button = PushButton("检查环境", icon=FluentIcon.SEARCH)
        self.check_env_button.clicked.connect(self._check_env)
        self.install_sdk_button = PrimaryPushButton("安装 SDK", icon=FluentIcon.DOWNLOAD)
        self.install_sdk_button.clicked.connect(self._install_sdk)
        self.generate_keys_button = PushButton("生成签名", icon=FluentIcon.SAVE)
        self.generate_keys_button.clicked.connect(self._generate_keys)
        btn_row.addWidget(self.check_env_button)
        btn_row.addWidget(self.install_sdk_button)
        btn_row.addWidget(self.generate_keys_button)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        return card

    def _create_build_card(self) -> CardWidget:
        card = CardWidget(self)
        layout = QVBoxLayout(card)
        layout.setSpacing(12)

        layout.addWidget(StrongBodyLabel("构建"))

        hint = QLabel("仅生成 APK。构建完成后自动打开 rapt/bin。")
        layout.addWidget(hint)

        btn_row = QHBoxLayout()
        self.build_button = PrimaryPushButton("开始构建", icon=FluentIcon.PLAY)
        self.build_button.clicked.connect(self._build_android)
        self.open_bin_button = PushButton("打开 rapt/bin", icon=FluentIcon.FOLDER)
        self.open_bin_button.clicked.connect(self._open_bin_dir)
        btn_row.addWidget(self.build_button)
        btn_row.addWidget(self.open_bin_button)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        self.build_status_label = QLabel("")
        self.build_status_label.setVisible(False)
        layout.addWidget(self.build_status_label)

        return card

    def _create_shell_card(self) -> CardWidget:
        card = CardWidget(self)
        layout = QVBoxLayout(card)
        layout.setSpacing(12)

        layout.addWidget(StrongBodyLabel("壳子制作"))
        layout.addWidget(QLabel("将指定目录打包为 archive.rpa（保存到项目根目录），并清理大体积资源目录。"))

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("打包目录:"))
        self.archive_source_edit = LineEdit()
        self.archive_source_edit.setPlaceholderText("多个目录用分号或换行分隔，留空默认使用 game")
        btn_browse_archive = PushButton("添加", icon=FluentIcon.FOLDER)
        btn_browse_archive.clicked.connect(self._browse_archive_source_dir)
        self.detect_archive_button = PushButton("检测", icon=FluentIcon.SEARCH)
        self.detect_archive_button.clicked.connect(self._detect_archive_dirs)
        row1.addWidget(self.archive_source_edit, 1)
        row1.addWidget(btn_browse_archive)
        row1.addWidget(self.detect_archive_button)
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        self.shell_backup_check = CheckBox("备份打包目录并压缩为 zip（保存到项目根目录）")
        row2.addWidget(self.shell_backup_check)
        row2.addStretch(1)
        layout.addLayout(row2)

        row3 = QHBoxLayout()
        row3.addWidget(QLabel("清理目录:"))
        self.shell_remove_dirs_edit = LineEdit()
        default_dirs = (self.config.android_shell_remove_dirs or "").strip()
        if default_dirs:
            placeholder = f"多个目录用逗号/分号分隔，留空不删除（默认: {default_dirs}）"
        else:
            placeholder = "多个目录用逗号/分号分隔，留空不删除"
        self.shell_remove_dirs_edit.setPlaceholderText(placeholder)
        row3.addWidget(self.shell_remove_dirs_edit, 1)
        self.detect_remove_button = PushButton("检测", icon=FluentIcon.SEARCH)
        self.detect_remove_button.clicked.connect(self._detect_remove_dirs)
        row3.addWidget(self.detect_remove_button)
        layout.addLayout(row3)

        btn_row = QHBoxLayout()
        self.make_shell_button = PrimaryPushButton("生成 archive.rpa + 清理资源", icon=FluentIcon.ZIP_FOLDER)
        self.make_shell_button.clicked.connect(self._make_shell_only)
        btn_row.addWidget(self.make_shell_button)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        return card

    def _load_config(self) -> None:
        self.sdk_path_edit.setText(self.config.renpy_sdk_path or "")
        if self.config.renpy_project_path:
            self.project_path_edit.setText(self.config.renpy_project_path)

        self.app_name_edit.setText(self.config.android_app_name or "")
        self.package_name_edit.setText(self.config.android_package_name or "")
        self.version_edit.setText(self.config.android_version or "")
        self.archive_source_edit.setText(self.config.android_archive_source_dir or "")
        self.shell_backup_check.setChecked(bool(self.config.android_shell_backup_enable))
        self.shell_remove_dirs_edit.setText(self.config.android_shell_remove_dirs or "")
        self.update_always_check.setChecked(bool(self.config.android_update_always))
        self.update_icons_check.setChecked(bool(self.config.android_update_icons))
        self.dname_edit.setText(self.config.android_dname or "")

    def _save_config(self) -> None:
        self.config.renpy_sdk_path = self.sdk_path_edit.text().strip()
        self.config.renpy_project_path = self.project_path_edit.text().strip()
        self.config.android_app_name = self.app_name_edit.text().strip()
        self.config.android_package_name = self.package_name_edit.text().strip()
        self.config.android_version = self.version_edit.text().strip()
        self.config.android_archive_source_dir = self.archive_source_edit.text().strip()
        self.config.android_shell_backup_enable = self.shell_backup_check.isChecked()
        self.config.android_shell_remove_dirs = self.shell_remove_dirs_edit.text().strip()
        self.config.android_update_always = self.update_always_check.isChecked()
        self.config.android_update_icons = self.update_icons_check.isChecked()
        self.config.android_dname = self.dname_edit.text().strip()
        self.config.save()

    def _browse_sdk_path(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "选择 Ren'Py SDK 目录")
        if folder:
            self.sdk_path_edit.setText(folder)

    def _browse_project_path(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "选择 Ren'Py 项目目录")
        if folder:
            self.project_path_edit.setText(folder)

    def _browse_archive_source_dir(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "选择打包目录")
        if folder:
            existing = self.archive_source_edit.text().strip()
            if existing:
                self.archive_source_edit.setText(existing + ";" + folder)
            else:
                self.archive_source_edit.setText(folder)

    def _get_builder(self) -> AndroidBuilder | None:
        sdk_path = self.sdk_path_edit.text().strip()
        project_path = self.project_path_edit.text().strip()
        if not sdk_path:
            InfoBar.warning("提示", "请先选择 Ren'Py SDK 目录", parent=self)
            return None
        if not project_path:
            InfoBar.warning("提示", "请先选择项目目录", parent=self)
            return None

        builder = AndroidBuilder(sdk_path, project_path)
        errors = builder.validate_paths()
        if errors:
            InfoBar.error("错误", "\n".join(errors), parent=self)
            for err in errors:
                self._log(err)
            return None
        return builder

    def _get_project_dir(self) -> Path | None:
        project_path = self.project_path_edit.text().strip()
        if not project_path:
            InfoBar.warning("提示", "请先选择项目目录", parent=self)
            return None
        project_dir = Path(project_path)
        if not project_dir.exists():
            InfoBar.error("错误", f"项目目录不存在: {project_dir}", parent=self)
            return None
        game_dir = project_dir / "game"
        if not game_dir.exists():
            InfoBar.error("错误", f"未找到 game 目录: {game_dir}", parent=self)
            return None
        return project_dir

    def _split_items(self, text: str) -> list[str]:
        if not text:
            return []
        return [item.strip() for item in re.split(r"[;,\n\r]+", text) if item.strip()]

    def _get_detect_hints(self) -> list[str]:
        text = self.shell_remove_dirs_edit.text().strip()
        if not text:
            text = (self.config.android_shell_remove_dirs or "").strip()
        return self._split_items(text)

    def _merge_items(self, existing: list[str], items: list[str]) -> list[str]:
        merged = list(existing)
        seen = {item.lower() if os.name == "nt" else item: True for item in existing}
        for item in items:
            key = item.lower() if os.name == "nt" else item
            if key in seen:
                continue
            merged.append(item)
            seen[key] = True
        return merged

    def _detect_resource_dirs(self, game_dir: Path) -> list[str]:
        detected: list[str] = []
        seen = set()
        ignored = {"gui"}

        for name in self._get_detect_hints():
            if name.lower() in ignored:
                continue
            path = game_dir / name
            if path.exists():
                key = name.lower() if os.name == "nt" else name
                if key not in seen:
                    detected.append(name)
                    seen.add(key)

        for child in game_dir.iterdir():
            if not child.is_dir():
                continue
            if child.name.lower() in ignored:
                continue
            key = child.name.lower() if os.name == "nt" else child.name
            if key in seen:
                continue
            if self._dir_has_resource_files(child):
                detected.append(child.name)
                seen.add(key)

        return detected

    def _dir_has_resource_files(self, folder: Path) -> bool:
        checked = 0
        for entry in folder.rglob("*"):
            if entry.is_file():
                if entry.suffix.lower() in self.RESOURCE_EXTENSIONS:
                    return True
                checked += 1
                if checked >= 20000:
                    break
        return False

    def _apply_detected_items(self, line_edit: LineEdit, items: list[str], *, replace: bool) -> bool:
        if not items:
            if replace:
                line_edit.clear()
            return False
        if replace:
            line_edit.setText(";".join(items))
            return True
        existing = self._split_items(line_edit.text().strip())
        merged = self._merge_items(existing, items)
        line_edit.setText(";".join(merged))
        return True

    def _detect_archive_dirs(self) -> None:
        project_dir = self._get_project_dir()
        if not project_dir:
            return
        game_dir = project_dir / "game"
        detected = self._detect_resource_dirs(game_dir)
        if not self._apply_detected_items(self.archive_source_edit, detected, replace=True):
            InfoBar.warning("提示", "未检测到资源目录，已清空", parent=self)
            return
        InfoBar.success("完成", f"已检测到 {len(detected)} 个目录，已覆盖", parent=self)

    def _detect_remove_dirs(self) -> None:
        project_dir = self._get_project_dir()
        if not project_dir:
            return
        game_dir = project_dir / "game"
        detected = self._detect_resource_dirs(game_dir)
        if not self._apply_detected_items(self.shell_remove_dirs_edit, detected, replace=True):
            InfoBar.warning("提示", "未检测到资源目录，已清空", parent=self)
            return
        InfoBar.success("完成", f"已检测到 {len(detected)} 个目录，已覆盖", parent=self)

    def _get_external_archive_dir(self, project_dir: Path) -> Path:
        return project_dir


    def _sanitize_android_dist_assets(self, dist_dir: Path, output) -> None:
        assets_dir = dist_dir / "assets"
        android_prefix = "android-"
        if assets_dir.exists():
            target_dir = assets_dir
            keep_dirs = {"game", "renpy"}
            keep_names = {"android.json"}
            keep_py = False
            keep_hint = "game/renpy/android-*/android.json"
        else:
            target_dir = dist_dir
            keep_dirs = {"game", "renpy", "lib"}
            keep_names = {"android.json"}
            keep_py = True
            keep_hint = "game/renpy/lib/.py/android-*/android.json"

        if not target_dir.exists():
            output(f"未找到分发目录，跳过清理: {target_dir}")
            return

        output(f"清理分发目录: {target_dir}")
        removed = []
        for path in target_dir.iterdir():
            name_lower = path.name.lower()
            if name_lower.startswith(android_prefix):
                continue
            if path.is_dir() and name_lower in keep_dirs:
                continue
            if path.is_file() and name_lower in keep_names:
                continue
            if keep_py and path.is_file() and path.suffix.lower() == ".py":
                continue
            try:
                if path.is_dir():
                    shutil.rmtree(path, ignore_errors=True)
                else:
                    path.unlink()
                removed.append(path)
            except Exception:
                continue
        if removed:
            output(f"已清理 {len(removed)} 个文件（保留 {keep_hint}）")
        else:
            output("未发现需要清理的文件")

    def _resolve_archive_source_dirs(self, project_dir: Path) -> list[Path]:
        game_dir = project_dir / "game"
        tokens = self._split_items(self.archive_source_edit.text().strip())
        if not tokens:
            return [game_dir]

        resolved: list[Path] = []
        for token in tokens:
            path = Path(token)
            if not path.is_absolute():
                path = (game_dir / token).resolve()
            else:
                path = path.resolve()
            resolved.append(path)

        unique: list[Path] = []
        seen = set()
        for path in resolved:
            key = str(path).lower() if os.name == "nt" else str(path)
            if key in seen:
                continue
            seen.add(key)
            unique.append(path)
        return unique

    def _parse_remove_dirs(self) -> list[str]:
        text = self.shell_remove_dirs_edit.text().strip()
        if not text:
            return []
        return [item.strip() for item in re.split(r"[;,\s]+", text) if item.strip()]

    def _to_long_path(self, path: Path) -> str:
        if os.name != "nt":
            return str(path)
        path_str = str(path)
        if path_str.startswith("\\\\?\\"):
            return path_str
        if path_str.startswith("\\\\"):
            return "\\\\?\\UNC\\" + path_str[2:]
        return "\\\\?\\" + path_str

    def _write_android_json(self) -> None:
        builder = self._get_builder()
        if not builder:
            return

        package = self.package_name_edit.text().strip()
        app_name = self.app_name_edit.text().strip()
        version = self.version_edit.text().strip()
        if not package or not app_name or not version:
            InfoBar.warning("提示", "请填写应用名、包名和版本", parent=self)
            return

        json_path = builder.write_android_json(
            package_name=package,
            app_name=app_name,
            version=version,
            update_always=self.update_always_check.isChecked(),
            update_icons=self.update_icons_check.isChecked(),
        )
        self._log(f"已写入: {json_path}")
        self._save_config()
        InfoBar.success("完成", "android.json 已更新", parent=self)

    def _check_env(self) -> None:
        builder = self._get_builder()
        if not builder:
            return
        self._open_bin_after_build = False

        def task(output):
            output("开始检查环境...")
            ok = builder.check_env(on_output=output)
            return ok, "环境检查完成" if ok else "环境检查失败"

        self._start_worker(task, "检查环境中...")

    def _install_sdk(self) -> None:
        builder = self._get_builder()
        if not builder:
            return
        self._open_bin_after_build = False

        def task(output):
            output("开始安装 Android SDK...")
            ok = builder.install_sdk(on_output=output)
            return ok, "SDK 安装完成" if ok else "SDK 安装失败"

        self._start_worker(task, "安装 SDK 中...")

    def _generate_keys(self) -> None:
        builder = self._get_builder()
        if not builder:
            return
        self._open_bin_after_build = False

        dname = self.dname_edit.text().strip() or None

        def task(output):
            output("开始生成签名文件...")
            ok = builder.generate_keys(dname=dname, on_output=output)
            return ok, "签名生成完成" if ok else "签名生成失败"

        self._start_worker(task, "生成签名中...")

    def _build_android(self) -> None:
        builder = self._get_builder()
        if not builder:
            return
        project_dir = Path(builder.project_dir)

        package = self.package_name_edit.text().strip()
        app_name = self.app_name_edit.text().strip()
        version = self.version_edit.text().strip()
        if not package or not app_name or not version:
            InfoBar.warning("提示", "请填写应用名、包名和版本", parent=self)
            return

        keystore = Path(builder.project_dir) / "android.keystore"
        if not keystore.exists():
            InfoBar.warning("提示", "未检测到签名文件，请先生成签名", parent=self)
            return

        dist_dir = str(Path(builder.project_dir) / "android.dist")

        def task(output):
            output("更新 android.json...")
            builder.write_android_json(
                package_name=package,
                app_name=app_name,
                version=version,
                update_always=self.update_always_check.isChecked(),
                update_icons=self.update_icons_check.isChecked(),
            )
            output(f"准备分发目录: {dist_dir}")
            if not builder.run_distribute(dist_dir=dist_dir, on_output=output):
                return False, "分发目录生成失败"
            self._sanitize_android_dist_assets(Path(dist_dir), output)

            output("开始构建 Android 包...")
            ok = builder.build_android(dist_dir=dist_dir, on_output=output)
            if not ok:
                return False, "构建失败"

            outputs = builder.list_outputs()
            if outputs:
                output("产物: " + ", ".join(p.name for p in outputs[:3]))

            return True, "构建完成"

        self._save_config()
        self._open_bin_after_build = True
        self._start_worker(task, "构建中...")

    def _make_shell_only(self) -> None:
        reply = MessageBox(
            "确认壳子处理",
            "将打包 archive.rpa（保存到项目根目录），并清理配置的资源目录。\n"
            "此操作会修改工程文件，建议先备份。",
            self,
        ).exec()
        if not reply:
            return

        project_dir = self._get_project_dir()
        if not project_dir:
            return

        self._open_bin_after_build = False

        def task(output):
            ok, message = self._make_shell_archive(project_dir, output)
            return ok, message

        self._save_config()
        self._start_worker(task, "壳子处理中...")

    def _make_shell_archive(self, project_dir: Path, output) -> tuple[bool, str]:
        game_dir = project_dir / "game"
        if not game_dir.exists():
            return False, f"未找到 game 目录: {game_dir}"

        source_dirs = self._resolve_archive_source_dirs(project_dir)
        for source_dir in source_dirs:
            if not source_dir.exists():
                return False, f"打包目录不存在: {source_dir}"
            if not source_dir.is_dir():
                return False, f"打包目录不是文件夹: {source_dir}"

        external_dir = self._get_external_archive_dir(project_dir)
        external_dir.mkdir(parents=True, exist_ok=True)
        archive_path = external_dir / "archive.rpa"
        internal_archive = game_dir / "archive.rpa"
        exclude_paths = {archive_path.resolve(), internal_archive.resolve()}

        if self.shell_backup_check.isChecked():
            try:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_path = external_dir / f"archive_backup_{timestamp}.zip"
                exclude_paths.add(backup_path.resolve())
                output(f"正在备份打包目录: {backup_path}")
                with zipfile.ZipFile(backup_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                    seen_arc = set()
                    for source_dir in source_dirs:
                        try:
                            prefix = source_dir.relative_to(project_dir).as_posix()
                        except ValueError:
                            prefix = source_dir.name
                        if not prefix:
                            prefix = source_dir.name
                        for entry in source_dir.rglob("*"):
                            if entry.is_dir():
                                continue
                            if entry.resolve() in exclude_paths:
                                continue
                            rel = entry.relative_to(source_dir)
                            arcname = f"{prefix}/{rel.as_posix()}"
                            if arcname in seen_arc:
                                continue
                            seen_arc.add(arcname)
                            zf.write(entry, arcname)
                output("备份完成")
            except Exception as exc:
                return False, f"备份失败: {exc}"

        output(f"开始打包 archive.rpa: {archive_path}")
        ok, message = self._pack_archive_from_dirs(
            source_dirs,
            game_dir,
            archive_path,
            exclude_paths,
            output,
        )
        if not ok:
            return False, message

        output("archive.rpa 打包完成，开始清理资源目录...")
        remove_dirs = self._parse_remove_dirs()
        removed = []
        for name in remove_dirs:
            target = game_dir / name
            if not target.exists():
                continue
            try:
                if target.is_dir():
                    shutil.rmtree(target, ignore_errors=True)
                else:
                    target.unlink(missing_ok=True)
                removed.append(name)
            except Exception as exc:
                output(f"清理失败 {target}: {exc}")

        if removed:
            output("已删除目录: " + ", ".join(removed))
        else:
            if remove_dirs:
                output("未发现需要删除的目录")
            else:
                output("未配置清理目录，已跳过删除")

        if internal_archive.exists():
            try:
                internal_archive.unlink()
                output("已移除 game/archive.rpa，避免打进 APK")
            except Exception as exc:
                output(f"移除 game/archive.rpa 失败: {exc}")

        return True, "壳子制作完成"

    def _pack_archive_from_dirs(
        self,
        source_dirs: list[Path],
        game_dir: Path,
        archive_path: Path,
        exclude_paths: set[Path],
        output,
    ) -> tuple[bool, str]:
        from module.Tool.rpatool_core import RenPyArchive

        seen = set()

        out_path = archive_path.resolve()
        if os.name == "nt" and not str(out_path).startswith("\\\\?\\"):
            out_path = Path(self._to_long_path(out_path))

        out_path.parent.mkdir(parents=True, exist_ok=True)
        if out_path.exists():
            out_path.unlink()

        archive = RenPyArchive(version=3, verbose=False)
        added = 0
        for source_dir in source_dirs:
            try:
                prefix = source_dir.relative_to(game_dir).as_posix()
            except ValueError:
                prefix = source_dir.name
            if prefix == ".":
                prefix = ""

            for entry in source_dir.rglob("*"):
                if entry.is_dir():
                    continue
                entry_resolved = entry.resolve()
                if entry_resolved in exclude_paths:
                    continue
                rel = entry.relative_to(source_dir).as_posix()
                archive_name = f"{prefix}/{rel}" if prefix else rel
                if archive_name in seen:
                    continue
                seen.add(archive_name)
                path_str = self._to_long_path(entry_resolved)
                archive.add_file_path(archive_name, path_str)
                added += 1
                if added % 500 == 0:
                    output(f"已加入 {added} 个文件...")

        if added == 0:
            return False, "未找到可打包的文件"

        output(f"已加入 {added} 个文件，正在写入 RPA 文件...")
        archive.save(str(out_path))
        output("RPA 写入完成")
        return True, "archive.rpa 打包完成"

    def _open_bin_dir(self) -> None:
        builder = self._get_builder()
        if not builder:
            return
        bin_dir = builder.rapt_bin
        if not bin_dir.exists():
            InfoBar.warning("提示", "未找到 rapt/bin，请先构建", parent=self)
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(bin_dir)))

    def _start_worker(self, task, status: str) -> None:
        if self.worker and self.worker.isRunning():
            InfoBar.warning("提示", "任务正在进行中", parent=self)
            return
        self._set_busy(True, status)
        self.worker = AndroidTaskWorker(task)
        self.worker.output.connect(self._log)
        self.worker.finished.connect(self._on_worker_finished)
        self.worker.start()

    def _on_worker_finished(self, ok: bool, message: str) -> None:
        self._set_busy(False)
        if ok:
            InfoBar.success("完成", message or "任务完成", parent=self)
        else:
            InfoBar.error("失败", message or "任务失败", parent=self)
        if ok and self._open_bin_after_build:
            self._open_bin_after_build = False
            self._open_bin_dir()
        else:
            self._open_bin_after_build = False
        self.worker = None

    def _set_busy(self, busy: bool, status: str = "") -> None:
        self.progress.setVisible(busy)
        self.build_button.setEnabled(not busy)
        self.make_shell_button.setEnabled(not busy)
        self.detect_archive_button.setEnabled(not busy)
        self.detect_remove_button.setEnabled(not busy)
        self.check_env_button.setEnabled(not busy)
        self.install_sdk_button.setEnabled(not busy)
        self.generate_keys_button.setEnabled(not busy)
        self.write_json_button.setEnabled(not busy)
        self.build_status_label.setVisible(busy)
        self.build_status_label.setText(status or "")

    def _log(self, message: str) -> None:
        if not message:
            return
        LogManager.get().info(message)
