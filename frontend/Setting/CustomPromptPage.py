from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QWidget
from PyQt5.QtWidgets import QLayout
from PyQt5.QtWidgets import QVBoxLayout
from qfluentwidgets import FluentWindow
from qfluentwidgets import SingleDirectionScrollArea
from qfluentwidgets import PlainTextEdit

from base.Base import Base
from module.Config import Config
from module.Localizer.Localizer import Localizer
from widget.GroupCard import GroupCard
from widget.SwitchButtonCard import SwitchButtonCard


class CustomPromptPage(QWidget, Base):

    def __init__(self, text: str, window: FluentWindow) -> None:
        super().__init__(window)
        self.setObjectName(text.replace(" ", "-"))

        # 载入配置
        config = Config().load().save()

        # 容器
        self.root = QVBoxLayout(self)
        self.root.setSpacing(8)
        self.root.setContentsMargins(24, 24, 24, 24)

        # 滚动区域
        scroll_area_vbox_widget = QWidget()
        scroll_area_vbox = QVBoxLayout(scroll_area_vbox_widget)
        scroll_area_vbox.setContentsMargins(0, 0, 0, 0)

        scroll_area = SingleDirectionScrollArea(orient=Qt.Orientation.Vertical)
        scroll_area.setWidget(scroll_area_vbox_widget)
        scroll_area.setWidgetResizable(True)
        scroll_area.enableTransparentBackground()
        self.root.addWidget(scroll_area)

        # 自定义中文提示词
        self.add_widget_custom_prompt_zh(scroll_area_vbox, config, window)
        # 自定义英文提示词
        self.add_widget_custom_prompt_en(scroll_area_vbox, config, window)

        # 填充
        scroll_area_vbox.addStretch(1)

    # 自定义中文提示词
    def add_widget_custom_prompt_zh(self, parent: QLayout, config: Config, window: FluentWindow) -> None:

        def init_switch(widget: SwitchButtonCard) -> None:
            widget.get_switch_button().setChecked(config.custom_prompt_zh_enable)

        def checked_changed(widget: SwitchButtonCard) -> None:
            cfg = Config().load()
            cfg.custom_prompt_zh_enable = widget.get_switch_button().isChecked()
            cfg.save()

        def init_group(widget: GroupCard) -> None:
            edit = PlainTextEdit(widget)
            edit.setPlainText(config.custom_prompt_zh_data or "")
            edit.setPlaceholderText("在此粘贴或编写中文提示词主体（不含前缀/后缀）")

            def on_changed():
                cfg = Config().load()
                cfg.custom_prompt_zh_data = edit.toPlainText()
                cfg.save()

            edit.textChanged.connect(on_changed)
            widget.add_widget(edit)

        parent.addWidget(
            SwitchButtonCard(
                title=Localizer.get().custom_prompt_zh_page_head,
                description=Localizer.get().custom_prompt_zh_page_head_desc,
                init=init_switch,
                checked_changed=checked_changed,
            )
        )
        parent.addWidget(
            GroupCard(
                parent=self,
                title=Localizer.get().app_custom_prompt_zh_page,
                description="仅在目标语言为中文时使用本自定义提示词主体。",
                init=init_group,
            )
        )

    # 自定义英文提示词
    def add_widget_custom_prompt_en(self, parent: QLayout, config: Config, window: FluentWindow) -> None:

        def init_switch(widget: SwitchButtonCard) -> None:
            widget.get_switch_button().setChecked(config.custom_prompt_en_enable)

        def checked_changed(widget: SwitchButtonCard) -> None:
            cfg = Config().load()
            cfg.custom_prompt_en_enable = widget.get_switch_button().isChecked()
            cfg.save()

        def init_group(widget: GroupCard) -> None:
            edit = PlainTextEdit(widget)
            edit.setPlainText(config.custom_prompt_en_data or "")
            edit.setPlaceholderText("Write English prompt body here (without prefix/suffix)")

            def on_changed():
                cfg = Config().load()
                cfg.custom_prompt_en_data = edit.toPlainText()
                cfg.save()

            edit.textChanged.connect(on_changed)
            widget.add_widget(edit)

        parent.addWidget(
            SwitchButtonCard(
                title=Localizer.get().custom_prompt_en_page_head,
                description=Localizer.get().custom_prompt_en_page_head_desc,
                init=init_switch,
                checked_changed=checked_changed,
            )
        )
        parent.addWidget(
            GroupCard(
                parent=self,
                title=Localizer.get().app_custom_prompt_en_page,
                description="Used only when target language is not Chinese.",
                init=init_group,
            )
        )

