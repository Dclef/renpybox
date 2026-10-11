"""安卓打包页面 - 安装 SDK / 生成签名 / 构建 APK。"""

from __future__ import annotations

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
from module.Localizer.Localizer import Localizer
from module.Project.ProjectStore import ProjectStore
from module.Tool.AndroidBuilder import AndroidBuilder
from module.Tool.AndroidProjectTools import (
    AndroidProjectToolsError,
    DEFAULT_DETECT_HINTS,
    detect_resource_dirs,
    make_shell_archive,
    merge_items,
    preflight_shell_archive,
    sanitize_android_dist_assets,
    split_items,
)
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

        layout.addWidget(TitleLabel(Localizer.get().android_build_android_build))

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

        layout.addWidget(StrongBodyLabel(Localizer.get().android_build_paths))
        note = QLabel(
            Localizer.get().android_build_android_shell_projects_download_modified_sdk_qq
        )
        layout.addWidget(note)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Ren'Py SDK:"))
        self.sdk_path_edit = LineEdit()
        self.sdk_path_edit.setPlaceholderText(
            Localizer.get().android_build_select_renpy_sdk_folder
        )
        btn_sdk = PushButton(Localizer.get().browse, icon=FluentIcon.FOLDER)
        btn_sdk.clicked.connect(self._browse_sdk_path)
        row1.addWidget(self.sdk_path_edit, 1)
        row1.addWidget(btn_sdk)
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel(Localizer.get().android_build_project_folder))
        self.project_path_edit = LineEdit()
        self.project_path_edit.setPlaceholderText(
            Localizer.get().android_build_select_ren_py_project_root_folder
        )
        btn_project = PushButton(
            Localizer.get().browse, icon=FluentIcon.FOLDER
        )
        btn_project.clicked.connect(self._browse_project_path)
        row2.addWidget(self.project_path_edit, 1)
        row2.addWidget(btn_project)
        layout.addLayout(row2)

        return card

    def _create_android_config_card(self) -> CardWidget:
        card = CardWidget(self)
        layout = QVBoxLayout(card)
        layout.setSpacing(12)

        layout.addWidget(
            StrongBodyLabel(
                Localizer.get().android_build_android_configuration_android_json
            )
        )

        row1 = QHBoxLayout()
        row1.addWidget(QLabel(Localizer.get().android_build_app_name))
        self.app_name_edit = LineEdit()
        self.app_name_edit.setPlaceholderText(
            Localizer.get().android_build_display_name
        )
        row1.addWidget(self.app_name_edit, 1)
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel(Localizer.get().android_build_package_name))
        self.package_name_edit = LineEdit()
        self.package_name_edit.setPlaceholderText(
            Localizer.get().android_build_e_g_com_example_game
        )
        row2.addWidget(self.package_name_edit, 1)
        layout.addLayout(row2)

        row3 = QHBoxLayout()
        row3.addWidget(QLabel(Localizer.get().android_build_version))
        self.version_edit = LineEdit()
        self.version_edit.setPlaceholderText(
            Localizer.get().android_build_e_g_1_0_0
        )
        row3.addWidget(self.version_edit, 1)
        layout.addLayout(row3)

        self.update_always_check = CheckBox(
            Localizer.get().android_build_automatically_update_java_code,
            card,
        )
        self.update_always_check.setVisible(False)
        self.update_icons_check = CheckBox(
            Localizer.get().android_build_automatically_update_icons, card
        )
        self.update_icons_check.setVisible(False)

        hint = QLabel(
            Localizer.get().android_build_icons_place_android_icon_foreground_png_android
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        row7 = QHBoxLayout()
        self.dname_label = QLabel(Localizer.get().android_build_signing_name)
        self.dname_label.setVisible(False)
        row7.addWidget(self.dname_label)
        self.dname_edit = LineEdit()
        self.dname_edit.setPlaceholderText(
            Localizer.get().android_build_organization_name_used_generate_keystore_optional
        )
        self.dname_edit.setVisible(False)
        row7.addWidget(self.dname_edit, 1)
        layout.addLayout(row7)

        btn_row = QHBoxLayout()
        self.write_json_button = PrimaryPushButton(
            Localizer.get().android_build_write_android_json,
            icon=FluentIcon.SAVE,
        )
        self.write_json_button.clicked.connect(self._write_android_json)
        btn_row.addWidget(self.write_json_button)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        return card

    def _create_env_card(self) -> CardWidget:
        card = CardWidget(self)
        layout = QVBoxLayout(card)
        layout.setSpacing(12)

        layout.addWidget(
            StrongBodyLabel(
                Localizer.get().android_build_environment_signing
            )
        )

        btn_row = QHBoxLayout()
        self.check_env_button = PushButton(
            Localizer.get().android_build_check_environment, icon=FluentIcon.SEARCH
        )
        self.check_env_button.clicked.connect(self._check_env)
        self.install_sdk_button = PrimaryPushButton(
            Localizer.get().android_build_install_sdk, icon=FluentIcon.DOWNLOAD
        )
        self.install_sdk_button.clicked.connect(self._install_sdk)
        self.generate_keys_button = PushButton(
            Localizer.get().android_build_generate_signing_key,
            icon=FluentIcon.SAVE,
        )
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

        layout.addWidget(StrongBodyLabel(Localizer.get().android_build_build))

        hint = QLabel(
            Localizer.get().android_build_generates_apk_only_opens_rapt_bin_when
        )
        layout.addWidget(hint)

        btn_row = QHBoxLayout()
        self.build_button = PrimaryPushButton(
            Localizer.get().android_build_start_build, icon=FluentIcon.PLAY
        )
        self.build_button.clicked.connect(self._build_android)
        self.open_bin_button = PushButton(
            Localizer.get().android_build_open_rapt_bin,
            icon=FluentIcon.FOLDER,
        )
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

        layout.addWidget(
            StrongBodyLabel(Localizer.get().android_build_shell_package)
        )
        layout.addWidget(
            QLabel(
                Localizer.get().android_build_pack_selected_folders_archive_rpa_project_root
            )
        )

        row1 = QHBoxLayout()
        row1.addWidget(QLabel(Localizer.get().android_build_package_folders))
        self.archive_source_edit = LineEdit()
        self.archive_source_edit.setPlaceholderText(
            Localizer.get().android_build_separate_multiple_folders_semicolons_new_lines_leave
        )
        btn_browse_archive = PushButton(
            Localizer.get().android_build_add, icon=FluentIcon.FOLDER
        )
        btn_browse_archive.clicked.connect(self._browse_archive_source_dir)
        self.detect_archive_button = PushButton(
            Localizer.get().android_build_detect, icon=FluentIcon.SEARCH
        )
        self.detect_archive_button.clicked.connect(self._detect_archive_dirs)
        row1.addWidget(self.archive_source_edit, 1)
        row1.addWidget(btn_browse_archive)
        row1.addWidget(self.detect_archive_button)
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        self.shell_backup_check = CheckBox(
            Localizer.get().android_build_back_up_package_folders_zip_file_project
        )
        row2.addWidget(self.shell_backup_check)
        row2.addStretch(1)
        layout.addLayout(row2)

        row3 = QHBoxLayout()
        row3.addWidget(QLabel(Localizer.get().android_build_cleanup_folders))
        self.shell_remove_dirs_edit = LineEdit()
        default_dirs = (self.config.android_shell_remove_dirs or "").strip()
        if default_dirs:
            placeholder = Localizer.get().android_build_separate_folders_commas_semicolons_leave_blank_delete.format(default_dirs=default_dirs)
        else:
            placeholder = Localizer.get().android_build_separate_folders_commas_semicolons_leave_blank_delete_2
        self.shell_remove_dirs_edit.setPlaceholderText(placeholder)
        row3.addWidget(self.shell_remove_dirs_edit, 1)
        self.detect_remove_button = PushButton(
            Localizer.get().android_build_detect, icon=FluentIcon.SEARCH
        )
        self.detect_remove_button.clicked.connect(self._detect_remove_dirs)
        row3.addWidget(self.detect_remove_button)
        layout.addLayout(row3)

        btn_row = QHBoxLayout()
        self.make_shell_button = PrimaryPushButton(
            Localizer.get().android_build_generate_archive_rpa_clean_resources,
            icon=FluentIcon.ZIP_FOLDER,
        )
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
        ProjectStore.get().set_project_path(
            self.config,
            self.project_path_edit.text().strip(),
        )
        self.config.android_app_name = self.app_name_edit.text().strip()
        self.config.android_package_name = self.package_name_edit.text().strip()
        self.config.android_version = self.version_edit.text().strip()
        self.config.android_archive_source_dir = self.archive_source_edit.text().strip()
        self.config.android_shell_backup_enable = self.shell_backup_check.isChecked()
        self.config.android_shell_remove_dirs = self.shell_remove_dirs_edit.text().strip()
        self.config.android_update_always = self.update_always_check.isChecked()
        self.config.android_update_icons = self.update_icons_check.isChecked()
        self.config.android_dname = self.dname_edit.text().strip()
        ProjectStore.get().persist(self.config)

    def _browse_sdk_path(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self,
            Localizer.get().android_build_select_ren_py_sdk_folder,
        )
        if folder:
            self.sdk_path_edit.setText(folder)

    def _browse_project_path(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self,
            Localizer.get().android_build_select_ren_py_project_folder,
        )
        if folder:
            self.project_path_edit.setText(folder)

    def _browse_archive_source_dir(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self,
            Localizer.get().android_build_select_package_folder,
        )
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
            InfoBar.warning(
                Localizer.get().notice,
                Localizer.get().android_build_select_ren_py_sdk_folder_first,
                parent=self,
            )
            return None
        if not project_path:
            InfoBar.warning(
                Localizer.get().notice,
                Localizer.get().android_build_select_project_folder_first,
                parent=self,
            )
            return None

        builder = AndroidBuilder(sdk_path, project_path)
        errors = builder.validate_paths()
        if errors:
            InfoBar.error(
                Localizer.get().error, "\n".join(errors), parent=self
            )
            for err in errors:
                self._log(err)
            return None
        return builder

    def _get_project_dir(self) -> Path | None:
        project_path = self.project_path_edit.text().strip()
        if not project_path:
            InfoBar.warning(
                Localizer.get().notice,
                Localizer.get().android_build_select_project_folder_first,
                parent=self,
            )
            return None
        project_dir = Path(project_path)
        if not project_dir.exists():
            InfoBar.error(
                Localizer.get().error,
                Localizer.get().android_build_project_folder_does_not_exist.format(project_dir=project_dir),
                parent=self,
            )
            return None
        game_dir = project_dir / "game"
        if not game_dir.exists():
            InfoBar.error(
                Localizer.get().error,
                Localizer.get().android_build_game_folder_not_found.format(game_dir=game_dir),
                parent=self,
            )
            return None
        return project_dir

    def _get_detect_hints(self) -> list[str]:
        text = self.shell_remove_dirs_edit.text().strip()
        if not text:
            text = (self.config.android_shell_remove_dirs or DEFAULT_DETECT_HINTS).strip()
        return split_items(text)

    def _apply_detected_items(self, line_edit: LineEdit, items: list[str], *, replace: bool) -> bool:
        if not items:
            if replace:
                line_edit.clear()
            return False
        if replace:
            line_edit.setText(";".join(items))
            return True
        existing = split_items(line_edit.text().strip())
        merged = merge_items(existing, items)
        line_edit.setText(";".join(merged))
        return True

    def _detect_archive_dirs(self) -> None:
        project_dir = self._get_project_dir()
        if not project_dir:
            return
        game_dir = project_dir / "game"
        try:
            detected = detect_resource_dirs(game_dir, hints=self._get_detect_hints())
        except AndroidProjectToolsError as exc:
            InfoBar.error(Localizer.get().error, str(exc), parent=self)
            return
        if not self._apply_detected_items(self.archive_source_edit, detected, replace=True):
            InfoBar.warning(
                Localizer.get().notice,
                Localizer.get().android_build_no_resource_folders_detected_field_cleared,
                parent=self,
            )
            return
        InfoBar.success(
            Localizer.get().android_build_done,
            Localizer.get().android_build_detected_folder_s_replaced_current_list.format(detected_count=len(detected)),
            parent=self,
        )

    def _detect_remove_dirs(self) -> None:
        project_dir = self._get_project_dir()
        if not project_dir:
            return
        game_dir = project_dir / "game"
        try:
            detected = detect_resource_dirs(game_dir, hints=self._get_detect_hints())
        except AndroidProjectToolsError as exc:
            InfoBar.error(Localizer.get().error, str(exc), parent=self)
            return
        if not self._apply_detected_items(self.shell_remove_dirs_edit, detected, replace=True):
            InfoBar.warning(
                Localizer.get().notice,
                Localizer.get().android_build_no_resource_folders_detected_field_cleared,
                parent=self,
            )
            return
        InfoBar.success(
            Localizer.get().android_build_done,
            Localizer.get().android_build_detected_folder_s_replaced_current_list.format(detected_count=len(detected)),
            parent=self,
        )

    def _write_android_json(self) -> None:
        builder = self._get_builder()
        if not builder:
            return

        package = self.package_name_edit.text().strip()
        app_name = self.app_name_edit.text().strip()
        version = self.version_edit.text().strip()
        if not package or not app_name or not version:
            InfoBar.warning(
                Localizer.get().notice,
                Localizer.get().android_build_enter_app_name_package_name_version,
                parent=self,
            )
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
        InfoBar.success(
            Localizer.get().android_build_done,
            Localizer.get().android_build_android_json_updated,
            parent=self,
        )

    def _check_env(self) -> None:
        builder = self._get_builder()
        if not builder:
            return
        self._open_bin_after_build = False

        def task(output):
            output("开始检查环境...")
            ok = builder.check_env(on_output=output)
            return ok, (
                Localizer.get().android_build_environment_check_completed
                if ok
                else Localizer.get().android_build_environment_check_failed
            )

        self._start_worker(
            task, Localizer.get().android_build_checking_environment
        )

    def _install_sdk(self) -> None:
        builder = self._get_builder()
        if not builder:
            return
        self._open_bin_after_build = False

        def task(output):
            output("开始安装 Android SDK...")
            ok = builder.install_sdk(on_output=output)
            return ok, (
                Localizer.get().android_build_sdk_installation_completed
                if ok
                else Localizer.get().android_build_sdk_installation_failed
            )

        self._start_worker(
            task, Localizer.get().android_build_installing_sdk
        )

    def _generate_keys(self) -> None:
        builder = self._get_builder()
        if not builder:
            return
        self._open_bin_after_build = False

        dname = self.dname_edit.text().strip() or None

        def task(output):
            output("开始生成签名文件...")
            ok = builder.generate_keys(dname=dname, on_output=output)
            return ok, (
                Localizer.get().android_build_signing_key_generated
                if ok
                else Localizer.get().android_build_signing_key_generation_failed
            )

        self._start_worker(
            task,
            Localizer.get().android_build_generating_signing_key,
        )

    def _build_android(self) -> None:
        builder = self._get_builder()
        if not builder:
            return

        package = self.package_name_edit.text().strip()
        app_name = self.app_name_edit.text().strip()
        version = self.version_edit.text().strip()
        if not package or not app_name or not version:
            InfoBar.warning(
                Localizer.get().notice,
                Localizer.get().android_build_enter_app_name_package_name_version,
                parent=self,
            )
            return

        keystore = Path(builder.project_dir) / "android.keystore"
        if not keystore.exists():
            InfoBar.warning(
                Localizer.get().notice,
                Localizer.get().android_build_no_signing_key_found_generate_one_first,
                parent=self,
            )
            return

        dist_dir = str(builder.project_dist_dir())
        update_always = self.update_always_check.isChecked()
        update_icons = self.update_icons_check.isChecked()

        def task(output):
            output("更新 android.json...")
            builder.write_android_json(
                package_name=package,
                app_name=app_name,
                version=version,
                update_always=update_always,
                update_icons=update_icons,
            )
            output(f"准备分发目录: {dist_dir}")
            if not builder.run_distribute(dist_dir=dist_dir, on_output=output):
                return False, Localizer.get().android_build_failed_create_distribution_folder
            try:
                sanitize_android_dist_assets(
                    builder.project_dir,
                    dist_dir,
                    on_output=output,
                )
            except AndroidProjectToolsError as exc:
                return False, str(exc)

            output("开始构建 Android 包...")
            ok = builder.build_android(
                dist_dir=dist_dir,
                install=False,
                launch=False,
                on_output=output,
            )
            if not ok:
                return False, Localizer.get().android_build_build_failed

            outputs = builder.list_outputs()
            if outputs:
                output("产物: " + ", ".join(p.name for p in outputs[:3]))

            return True, Localizer.get().android_build_build_completed

        self._save_config()
        self._open_bin_after_build = True
        self._start_worker(task, Localizer.get().android_build_building)

    def _make_shell_only(self) -> None:
        reply = MessageBox(
            Localizer.get().android_build_confirm_shell_processing,
            Localizer.get().android_build_build_archive_rpa_project_root_clean_configured,
            self,
        ).exec()
        if not reply:
            return

        project_dir = self._get_project_dir()
        if not project_dir:
            return

        self._open_bin_after_build = False
        source_text = self.archive_source_edit.text().strip()
        remove_text = self.shell_remove_dirs_edit.text().strip()
        backup = self.shell_backup_check.isChecked()

        # 与 API 同一 preflight：非法路径/联接在 save 之前拒绝
        try:
            plan = preflight_shell_archive(
                project_dir,
                source_text=source_text,
                remove_text=remove_text,
                backup=backup,
            )
        except AndroidProjectToolsError as exc:
            InfoBar.error(Localizer.get().error, str(exc), parent=self)
            return

        def task(output):
            try:
                result = make_shell_archive(
                    project_dir,
                    source_text=source_text,
                    remove_text=remove_text,
                    backup=backup,
                    on_output=output,
                    plan=plan,
                )
            except AndroidProjectToolsError as exc:
                return False, str(exc)
            ok = bool(result.get("success"))
            message = result.get("message") or (
                Localizer.get().android_build_shell_package_completed
                if ok
                else Localizer.get().android_build_task_failed
            )
            if ok and result.get("partial"):
                failed = result.get("failed") or []
                if failed:
                    message = f"{message}: {'; '.join(failed[:3])}"
            return ok, message

        self._save_config()
        self._start_worker(
            task, Localizer.get().android_build_processing_shell_package
        )

    def _open_bin_dir(self) -> None:
        builder = self._get_builder()
        if not builder:
            return
        bin_dir = builder.rapt_bin
        if not bin_dir.exists():
            InfoBar.warning(
                Localizer.get().notice,
                Localizer.get().android_build_rapt_bin_not_found_run_build_first,
                parent=self,
            )
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(bin_dir)))

    def _start_worker(self, task, status: str) -> None:
        if self.worker and self.worker.isRunning():
            InfoBar.warning(
                Localizer.get().notice,
                Localizer.get().android_build_task_already_running,
                parent=self,
            )
            return
        self._set_busy(True, status)
        self.worker = AndroidTaskWorker(task)
        self.worker.output.connect(self._log)
        self.worker.finished.connect(self._on_worker_finished)
        self.worker.start()

    def _on_worker_finished(self, ok: bool, message: str) -> None:
        self._set_busy(False)
        if ok:
            InfoBar.success(
                Localizer.get().android_build_done,
                message
                or Localizer.get().android_build_task_completed,
                parent=self,
            )
        else:
            InfoBar.error(
                Localizer.get().android_build_failed,
                message or Localizer.get().android_build_task_failed,
                parent=self,
            )
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
