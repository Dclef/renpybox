from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QLayout
from PyQt5.QtWidgets import QVBoxLayout
from PyQt5.QtWidgets import QWidget
from qfluentwidgets import FluentWindow
from qfluentwidgets import PlainTextEdit
from qfluentwidgets import SingleDirectionScrollArea

from base.Base import Base
from base.BaseLanguage import BaseLanguage
from frontend.Setting.TranslationSettingsBinding import PROMPT_MODE_VALUES
from frontend.Setting.TranslationSettingsBinding import WRITING_STYLE_VALUES
from frontend.Setting.TranslationSettingsBinding import choice_index
from frontend.Setting.TranslationSettingsBinding import get_custom_prompt
from frontend.Setting.TranslationSettingsBinding import set_custom_prompt
from frontend.Setting.TranslationSettingsBinding import set_prompt_mode
from frontend.Setting.TranslationSettingsBinding import set_writing_style
from module.Config import Config
from module.Localizer.Localizer import Localizer
from widget.ComboBoxCard import ComboBoxCard
from widget.GroupCard import GroupCard


class CustomPromptPage(QWidget, Base):

    def __init__(self, text: str, window: FluentWindow) -> None:
        super().__init__(window)
        self.setObjectName(text.replace(" ", "-"))
        self.custom_prompt_groups: list[GroupCard] = []
        self.custom_style_group: GroupCard | None = None

        config = Config().load().save()

        self.root = QVBoxLayout(self)
        self.root.setSpacing(8)
        self.root.setContentsMargins(24, 24, 24, 24)

        scroll_area_vbox_widget = QWidget()
        scroll_area_vbox = QVBoxLayout(scroll_area_vbox_widget)
        scroll_area_vbox.setSpacing(8)
        scroll_area_vbox.setContentsMargins(0, 0, 0, 0)

        scroll_area = SingleDirectionScrollArea(orient = Qt.Orientation.Vertical)
        scroll_area.setWidget(scroll_area_vbox_widget)
        scroll_area.setWidgetResizable(True)
        scroll_area.enableTransparentBackground()
        self.root.addWidget(scroll_area)

        self.add_widget_prompt_mode(scroll_area_vbox, config)
        self.add_widget_custom_prompt(
            scroll_area_vbox,
            config,
            BaseLanguage.Enum.ZH,
        )
        self.add_widget_custom_prompt(
            scroll_area_vbox,
            config,
            BaseLanguage.Enum.EN,
        )
        self.add_widget_writing_style(scroll_area_vbox, config)
        self.add_widget_custom_style(scroll_area_vbox, config)
        self.refresh_conditional_visibility(config)

        scroll_area_vbox.addStretch(1)

    @staticmethod
    def prompt_mode_labels() -> tuple[str, ...]:
        localizer = Localizer.get()
        return (
            localizer.translation_prompt_mode_common,
            localizer.translation_prompt_mode_cot,
            localizer.translation_prompt_mode_think,
            localizer.translation_prompt_mode_local,
            localizer.translation_prompt_mode_custom,
        )

    @staticmethod
    def writing_style_labels() -> tuple[str, ...]:
        localizer = Localizer.get()
        return (
            localizer.translation_writing_style_none,
            localizer.translation_writing_style_literary,
            localizer.translation_writing_style_classical,
            localizer.translation_writing_style_r18,
            localizer.translation_writing_style_custom,
        )

    def refresh_conditional_visibility(self, config: Config) -> None:
        custom_prompt_visible = (
            config.translation_prompt_mode == Config.PROMPT_MODE_CUSTOM
        )
        for group in self.custom_prompt_groups:
            group.setVisible(custom_prompt_visible)

        if self.custom_style_group is not None:
            self.custom_style_group.setVisible(
                config.translation_style_id == Config.STYLE_CUSTOM
            )

    def add_widget_prompt_mode(self, parent: QLayout, config: Config) -> None:
        def init(widget: ComboBoxCard) -> None:
            widget.get_combo_box().setCurrentIndex(
                choice_index(config.translation_prompt_mode, PROMPT_MODE_VALUES)
            )

        def current_changed(widget: ComboBoxCard) -> None:
            current = Config().load()
            set_prompt_mode(
                current,
                PROMPT_MODE_VALUES[widget.get_combo_box().currentIndex()],
            )
            current.save()
            self.refresh_conditional_visibility(current)

        parent.addWidget(
            ComboBoxCard(
                title = Localizer.get().translation_prompt_mode_title,
                description = Localizer.get().translation_prompt_mode_desc,
                items = list(self.prompt_mode_labels()),
                init = init,
                current_changed = current_changed,
            )
        )

    def add_widget_custom_prompt(
        self,
        parent: QLayout,
        config: Config,
        language: BaseLanguage.Enum,
    ) -> None:
        is_chinese = language == BaseLanguage.Enum.ZH

        def init(widget: GroupCard) -> None:
            edit = PlainTextEdit(widget)
            edit.setMinimumHeight(180)
            edit.setPlainText(get_custom_prompt(config, language))
            edit.setPlaceholderText(
                Localizer.get().translation_custom_prompt_zh_placeholder
                if is_chinese
                else Localizer.get().translation_custom_prompt_en_placeholder
            )

            def text_changed() -> None:
                current = Config().load()
                set_custom_prompt(current, language, edit.toPlainText())
                current.save()

            edit.textChanged.connect(text_changed)
            widget.add_widget(edit)

        group = GroupCard(
            parent = self,
            title = (
                Localizer.get().translation_custom_prompt_zh_title
                if is_chinese
                else Localizer.get().translation_custom_prompt_en_title
            ),
            description = (
                Localizer.get().translation_custom_prompt_zh_desc
                if is_chinese
                else Localizer.get().translation_custom_prompt_en_desc
            ),
            init = init,
        )
        self.custom_prompt_groups.append(group)
        parent.addWidget(group)

    def add_widget_writing_style(self, parent: QLayout, config: Config) -> None:
        def init(widget: ComboBoxCard) -> None:
            widget.get_combo_box().setCurrentIndex(
                choice_index(config.translation_style_id, WRITING_STYLE_VALUES)
            )

        def current_changed(widget: ComboBoxCard) -> None:
            current = Config().load()
            set_writing_style(
                current,
                WRITING_STYLE_VALUES[widget.get_combo_box().currentIndex()],
            )
            current.save()
            self.refresh_conditional_visibility(current)

        parent.addWidget(
            ComboBoxCard(
                title = Localizer.get().translation_writing_style_title,
                description = Localizer.get().translation_writing_style_desc,
                items = list(self.writing_style_labels()),
                init = init,
                current_changed = current_changed,
            )
        )

    def add_widget_custom_style(self, parent: QLayout, config: Config) -> None:
        def init(widget: GroupCard) -> None:
            edit = PlainTextEdit(widget)
            edit.setMinimumHeight(140)
            edit.setPlainText(config.translation_custom_style or "")
            edit.setPlaceholderText(
                Localizer.get().translation_custom_writing_style_placeholder
            )

            def text_changed() -> None:
                current = Config().load()
                current.translation_custom_style = edit.toPlainText()
                current.save()

            edit.textChanged.connect(text_changed)
            widget.add_widget(edit)

        self.custom_style_group = GroupCard(
            parent = self,
            title = Localizer.get().translation_custom_writing_style_title,
            description = Localizer.get().translation_custom_writing_style_desc,
            init = init,
        )
        parent.addWidget(self.custom_style_group)
