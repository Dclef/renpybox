import os
import webbrowser
from pathlib import Path

from PyQt5.QtWidgets import QWidget
from PyQt5.QtWidgets import QLayout
from PyQt5.QtWidgets import QFileDialog
from PyQt5.QtWidgets import QVBoxLayout
from qfluentwidgets import PushButton
from qfluentwidgets import FluentIcon
from qfluentwidgets import FluentWindow
from qfluentwidgets import CaptionLabel
from qfluentwidgets import TitleLabel

from base.Base import Base
from base.BaseLanguage import BaseLanguage
from module.Config import Config
from module.Localizer.Localizer import Localizer
from module.Renpy.ProjectPaths import (
    RenpyProjectPaths,
    looks_like_renpy_path,
)
from module.Project.ProjectStore import ProjectStore
from widget.ComboBoxCard import ComboBoxCard
from widget.PushButtonCard import PushButtonCard
from widget.SwitchButtonCard import SwitchButtonCard
from widget.ThemeHelper import mark_app_page

class ProjectPage(QWidget, Base):

    def __init__(self, text: str, window: FluentWindow) -> None:
        super().__init__(window)
        self.setObjectName(text.replace(" ", "-"))
        mark_app_page(self)

        # 载入并保存默认配置
        config = Config().load()
        config = self._auto_fill_by_renpy_config(config)
        config.save()

        # 根据应用语言构建语言列表
        if Localizer.get_app_language() == BaseLanguage.Enum.ZH:
            self.languages = [BaseLanguage.get_name_zh(v) for v in BaseLanguage.get_languages()]
        else:
            self.languages = [BaseLanguage.get_name_en(v) for v in BaseLanguage.get_languages()]

        # 设置主容器
        self.vbox = QVBoxLayout(self)
        self.vbox.setSpacing(8)
        self.vbox.setContentsMargins(24, 24, 24, 24) # 左、上、右、下

        header = QWidget(self)
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 4)
        header_layout.setSpacing(2)
        header_layout.addWidget(TitleLabel(Localizer.get().app_project_page, header))
        header_layout.addWidget(
            CaptionLabel(Localizer.get().project_page_header_description, header)
        )
        self.vbox.addWidget(header)

        # 添加控件
        self.add_widget_source_language(self.vbox, config, window)
        self.add_widget_target_language(self.vbox, config, window)
        self.add_widget_input_folder(self.vbox, config, window)
        self.add_widget_output_folder(self.vbox, config, window)
        self.add_widget_output_folder_open_on_finish(self.vbox, config, window)
        self.add_widget_traditional_chinese(self.vbox, config, window)

        # 填充
        self.vbox.addStretch(1)

    def showEvent(self, event) -> None:
        """页面重新显示时刷新路径，避免沿用旧页面创建时的配置快照。"""
        super().showEvent(event)
        config = self._auto_fill_by_renpy_config(Config().load())
        input_card = getattr(self, "input_folder_card", None)
        output_card = getattr(self, "output_folder_card", None)
        if input_card is not None:
            input_card.get_description_label().setText(
                f"{Localizer.get().project_page_input_folder_content} {config.input_folder}"
            )
        if output_card is not None:
            output_card.get_description_label().setText(
                f"{Localizer.get().project_page_output_folder_content} {config.output_folder}"
            )

    def _guess_lang_from_path(self, path: Path) -> BaseLanguage.Enum | None:
        lower = str(path).lower()
        if any(key in lower for key in ["chinese", "schinese", "tchinese", "zh"]):
            return BaseLanguage.Enum.ZH
        if any(key in lower for key in ["japanese", "ja", "jp"]):
            return BaseLanguage.Enum.JA
        if any(key in lower for key in ["korean", "kr", "ko"]):
            return BaseLanguage.Enum.KO
        if any(key in lower for key in ["english", "en"]):
            return BaseLanguage.Enum.EN
        if any(key in lower for key in ["russian", "ru"]):
            return BaseLanguage.Enum.RU
        return None

    def _looks_like_renpy_path(self, raw_path: str) -> bool:
        """判断路径是否明显包含 Ren'Py 项目结构。"""
        return looks_like_renpy_path(raw_path)

    def _sync_renpy_paths_from_selection(self, config: Config, raw_path: str) -> bool:
        """把项目页选择的路径同步到 Ren'Py 专用配置，避免工具页继续读取旧项目。"""
        paths = RenpyProjectPaths.from_path(raw_path)
        if paths is None:
            return False

        def mutate(current: Config) -> None:
            guessed = self._guess_lang_from_path(paths.tl_language_dir)
            if guessed is not None:
                current.target_language = guessed

        ProjectStore.get().apply_resolved(
            config,
            paths,
            persist = False,
            mutate = mutate,
        )
        return True

    def _auto_fill_by_renpy_config(self, config: Config) -> Config:
        """
        当已选择 Ren'Py 项目后，自动用 tl 目录填充输入/输出目录，并尝试推断目标语言。
        """
        changed = False

        paths = RenpyProjectPaths.from_config(config)
        if paths is not None and paths.tl_language_dir.exists():
            def keep_current_path(value: str) -> str | None:
                """保留本项目内的显式运行目录（增量/Hook/自定义输出）。"""
                text = str(value or "").strip()
                if text == "":
                    return None
                try:
                    candidate = Path(text).expanduser().resolve(strict = False)
                    candidate.relative_to(paths.project_root)
                except Exception:
                    return None
                if candidate == paths.project_root:
                    return None
                return str(candidate)

            current_input = keep_current_path(getattr(config, "input_folder", ""))
            current_output = keep_current_path(getattr(config, "output_folder", ""))
            before = (
                config.input_folder,
                config.output_folder,
                config.renpy_project_path,
                config.renpy_game_folder,
                config.renpy_tl_folder,
                config.target_language,
            )
            # 页面重新显示时不能把一键翻译的 <lang>_new 或 Hook 临时目录
            # 改回规范主目录；项目专用字段仍统一到当前项目。
            ProjectStore.get().apply_resolved(
                config,
                paths,
                input_folder = current_input or paths.tl_language_dir,
                output_folder = current_output or paths.translation_output_dir,
                persist = False,
            )
            guessed = self._guess_lang_from_path(paths.tl_language_dir)
            if guessed is not None:
                config.target_language = guessed
            changed = before != (
                config.input_folder,
                config.output_folder,
                config.renpy_project_path,
                config.renpy_game_folder,
                config.renpy_tl_folder,
                config.target_language,
            )
            Path(config.output_folder).mkdir(parents = True, exist_ok = True)

        if changed:
            ProjectStore.get().persist(config)
        return config

    # 原文语言
    def add_widget_source_language(self, parent: QLayout, config: Config, windows: FluentWindow) -> None:
        def init(widget: ComboBoxCard) -> None:
            if config.source_language in BaseLanguage.get_languages():
                widget.get_combo_box().setCurrentIndex(
                    BaseLanguage.get_languages().index(config.source_language)
                )

        def current_changed(widget: ComboBoxCard) -> None:
            config = Config().load()
            config.source_language = BaseLanguage.get_languages()[widget.get_combo_box().currentIndex()]
            config.save()

        parent.addWidget(
            ComboBoxCard(
                Localizer.get().project_page_source_language_title,
                Localizer.get().project_page_source_language_content,
                items = self.languages,
                init = init,
                current_changed = current_changed,
            )
        )

    # 译文语言
    def add_widget_target_language(self, parent: QLayout, config: Config, windows: FluentWindow) -> None:

        def init(widget: ComboBoxCard) -> None:
            if config.target_language in BaseLanguage.get_languages():
                widget.get_combo_box().setCurrentIndex(
                    BaseLanguage.get_languages().index(config.target_language)
                )

        def current_changed(widget: ComboBoxCard) -> None:
            config = Config().load()
            config.target_language = BaseLanguage.get_languages()[widget.get_combo_box().currentIndex()]
            config.save()

        parent.addWidget(
            ComboBoxCard(
                Localizer.get().project_page_target_language_title,
                Localizer.get().project_page_target_language_content,
                items = self.languages,
                init = init,
                current_changed = current_changed,
            )
        )

    # 输入文件夹
    def add_widget_input_folder(self, parent: QLayout, config: Config, windows: FluentWindow) -> None:

        def open_btn_clicked(widget: PushButton) -> None:
            webbrowser.open(os.path.abspath(Config().load().input_folder))

        def init(widget: PushButtonCard) -> None:
            open_btn = PushButton(FluentIcon.FOLDER, Localizer.get().open, self)
            open_btn.clicked.connect(open_btn_clicked)
            widget.add_spacing(4)
            widget.add_widget(open_btn)

            widget.get_description_label().setText(f"{Localizer.get().project_page_input_folder_content} {config.input_folder}")
            widget.get_push_button().setText(Localizer.get().select)
            widget.get_push_button().setIcon(FluentIcon.ADD_TO)

        def clicked(widget: PushButtonCard) -> None:
            # 选择文件夹
            path = QFileDialog.getExistingDirectory(None, Localizer.get().select, "")
            if path == None or path == "":
                return

            # 更新UI
            widget.get_description_label().setText(f"{Localizer.get().project_page_input_folder_content} {path.strip()}")

            # 更新并保存配置
            config = Config().load()
            config.input_folder = path.strip()
            resolved = self._sync_renpy_paths_from_selection(config, path.strip())
            ProjectStore.get().persist(config, emit = resolved)

        card = PushButtonCard(
                title = Localizer.get().project_page_input_folder_title,
                description = "",
                init = init,
                clicked = clicked,
            )
        self.input_folder_card = card
        parent.addWidget(card)

    # 输出文件夹
    def add_widget_output_folder(self, parent: QLayout, config: Config, windows: FluentWindow) -> None:

        def open_btn_clicked(widget: PushButton) -> None:
            webbrowser.open(os.path.abspath(Config().load().output_folder))

        def init(widget: PushButtonCard) -> None:
            open_btn = PushButton(FluentIcon.FOLDER, Localizer.get().open, self)
            open_btn.clicked.connect(open_btn_clicked)
            widget.add_spacing(4)
            widget.add_widget(open_btn)

            widget.get_description_label().setText(f"{Localizer.get().project_page_output_folder_content} {config.output_folder}")
            widget.get_push_button().setText(Localizer.get().select)
            widget.get_push_button().setIcon(FluentIcon.ADD_TO)

        def clicked(widget: PushButtonCard) -> None:
            # 选择文件夹
            path = QFileDialog.getExistingDirectory(None, Localizer.get().select, "")
            if path == None or path == "":
                return

            # 更新UI
            widget.get_description_label().setText(f"{Localizer.get().project_page_output_folder_content} {path.strip()}")

            # 更新并保存配置
            config = Config().load()
            config.output_folder = path.strip()
            if self._looks_like_renpy_path(path.strip()):
                resolved = self._sync_renpy_paths_from_selection(config, path.strip())
            else:
                resolved = False
            ProjectStore.get().persist(config, emit = resolved)

        card = PushButtonCard(
                title = Localizer.get().project_page_output_folder_title,
                description = "",
                init = init,
                clicked = clicked,
            )
        self.output_folder_card = card
        parent.addWidget(card)

    # 任务完成后自动打开输出文件夹
    def add_widget_output_folder_open_on_finish(self, parent: QLayout, config: Config, windows: FluentWindow) -> None:

        def init(widget: SwitchButtonCard) -> None:
            widget.get_switch_button().setChecked(
                config.output_folder_open_on_finish
            )

        def checked_changed(widget: SwitchButtonCard) -> None:
            # 更新并保存配置
            config = Config().load()
            config.output_folder_open_on_finish = widget.get_switch_button().isChecked()
            config.save()

        parent.addWidget(
            SwitchButtonCard(
                title = Localizer.get().project_page_output_folder_open_on_finish_title,
                description = Localizer.get().project_page_output_folder_open_on_finish_content,
                init = init,
                checked_changed = checked_changed,
            )
        )

    # 繁体输出
    def add_widget_traditional_chinese(self, parent: QLayout, config: Config, windows: FluentWindow) -> None:

        def init(widget: SwitchButtonCard) -> None:
            widget.get_switch_button().setChecked(
                config.traditional_chinese_enable
            )

        def checked_changed(widget: SwitchButtonCard) -> None:
            # 更新并保存配置
            config = Config().load()
            config.traditional_chinese_enable = widget.get_switch_button().isChecked()
            config.save()

        parent.addWidget(
            SwitchButtonCard(
                Localizer.get().project_page_traditional_chinese_title,
                Localizer.get().project_page_traditional_chinese_content,
                init = init,
                checked_changed = checked_changed,
            )
        )
