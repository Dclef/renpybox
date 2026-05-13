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

from base.Base import Base
from base.BaseLanguage import BaseLanguage
from module.Config import Config
from module.Localizer.Localizer import Localizer
from widget.ComboBoxCard import ComboBoxCard
from widget.PushButtonCard import PushButtonCard
from widget.SwitchButtonCard import SwitchButtonCard

class ProjectPage(QWidget, Base):

    def __init__(self, text: str, window: FluentWindow) -> None:
        super().__init__(window)
        self.setObjectName(text.replace(" ", "-"))

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

        # 添加控件
        self.add_widget_source_language(self.vbox, config, window)
        self.add_widget_target_language(self.vbox, config, window)
        self.add_widget_input_folder(self.vbox, config, window)
        self.add_widget_output_folder(self.vbox, config, window)
        self.add_widget_output_folder_open_on_finish(self.vbox, config, window)
        self.add_widget_traditional_chinese(self.vbox, config, window)

        # 填充
        self.vbox.addStretch(1)

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

    def _pick_tl_language_dir(self, tl_root: Path) -> Path | None:
        """从 tl 根目录中选择一个语言目录。"""
        if tl_root.exists() is False or tl_root.is_dir() is False:
            return None

        for preferred in ("chinese", "schinese", "tchinese", "english", "japanese", "korean"):
            candidate = tl_root / preferred
            if candidate.is_dir():
                return candidate

        children = sorted(
            [child for child in tl_root.iterdir() if child.is_dir()],
            key = lambda item: item.name.lower(),
        )
        return children[0] if children else None

    def _infer_renpy_layout(self, raw_path: str) -> tuple[Path | None, Path | None, Path | None]:
        """根据用户选择的目录推断项目根目录、game 目录与 tl 语言目录。"""
        if not raw_path:
            return None, None, None

        try:
            path = Path(raw_path).expanduser().resolve()
        except Exception:
            path = Path(raw_path)

        if path.exists() is False:
            return None, None, None

        if path.is_file():
            path = path.parent

        project_root: Path | None = None
        game_dir: Path | None = None
        tl_dir: Path | None = None

        # 直接选择的是 game/tl/<lang>
        if path.parent.name.lower() == "tl" and path.is_dir():
            tl_dir = path
            if path.parent.parent.name.lower() == "game":
                game_dir = path.parent.parent
                project_root = game_dir.parent
            else:
                game_dir = path.parent.parent
                project_root = game_dir
            return project_root, game_dir, tl_dir

        # 直接选择的是 game/tl
        if path.name.lower() == "tl" and path.is_dir():
            tl_dir = self._pick_tl_language_dir(path)
            if path.parent.name.lower() == "game":
                game_dir = path.parent
                project_root = game_dir.parent
            else:
                game_dir = path.parent
                project_root = game_dir
            return project_root, game_dir, tl_dir

        # 直接选择的是 game 目录
        if path.name.lower() == "game" and path.is_dir():
            game_dir = path
            project_root = path.parent
            tl_dir = self._pick_tl_language_dir(path / "tl")
            return project_root, game_dir, tl_dir

        # 选择的是项目根目录
        game_child = path / "game"
        if game_child.is_dir():
            project_root = path
            game_dir = game_child
            tl_dir = self._pick_tl_language_dir(game_child / "tl")
            return project_root, game_dir, tl_dir

        # 兜底：允许把当前目录当作源码目录处理
        return path, path, None

    def _looks_like_renpy_path(self, raw_path: str) -> bool:
        """判断路径是否明显包含 Ren'Py 项目结构。"""
        if not raw_path:
            return False

        try:
            path = Path(raw_path).expanduser().resolve()
        except Exception:
            path = Path(raw_path)

        if path.exists() is False:
            return False

        if path.is_file():
            path = path.parent

        return (
            path.name.lower() in {"game", "tl"}
            or path.parent.name.lower() == "tl"
            or (path / "game").is_dir()
        )

    def _sync_renpy_paths_from_selection(self, config: Config, raw_path: str) -> None:
        """把项目页选择的路径同步到 Ren'Py 专用配置，避免工具页继续读取旧项目。"""
        project_root, game_dir, tl_dir = self._infer_renpy_layout(raw_path)
        if project_root is None or game_dir is None:
            return

        config.renpy_project_path = str(project_root)
        # 这里统一保存项目根目录，工具页内部会自动兼容 project_root / game 两种形式。
        config.renpy_game_folder = str(project_root)

        if tl_dir is not None and tl_dir.exists():
            config.renpy_tl_folder = str(tl_dir)

            guessed = self._guess_lang_from_path(tl_dir)
            if guessed is not None:
                config.target_language = guessed

    def _auto_fill_by_renpy_config(self, config: Config) -> Config:
        """
        当已选择 Ren'Py 项目后，自动用 tl 目录填充输入/输出目录，并尝试推断目标语言。
        """
        changed = False

        tl_folder = config.renpy_tl_folder.strip() if config.renpy_tl_folder else ""
        if tl_folder:
            tl_path = Path(tl_folder)
            if tl_path.exists():
                # 自动设置输入目录
                if not config.input_folder or config.input_folder in ("./input", "input"):
                    config.input_folder = str(tl_path)
                    changed = True

                # 自动设置输出目录（与输入目录不同）
                desired_out = tl_path.parent / "out"
                if (
                    not config.output_folder
                    or config.output_folder in ("./output", "output")
                    or Path(config.output_folder).resolve() == tl_path.resolve()
                ):
                    config.output_folder = str(desired_out)
                    Path(config.output_folder).mkdir(parents=True, exist_ok=True)
                    changed = True

                # 推断目标语言
                guessed = self._guess_lang_from_path(tl_path)
                if guessed is not None and guessed != config.target_language:
                    config.target_language = guessed
                    changed = True

        if changed:
            config.save()
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
            self._sync_renpy_paths_from_selection(config, path.strip())
            config.save()

        parent.addWidget(
            PushButtonCard(
                title = Localizer.get().project_page_input_folder_title,
                description = "",
                init = init,
                clicked = clicked,
            )
        )

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
                self._sync_renpy_paths_from_selection(config, path.strip())
            config.save()

        parent.addWidget(
            PushButtonCard(
                title = Localizer.get().project_page_output_folder_title,
                description = "",
                init = init,
                clicked = clicked,
            )
        )

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
