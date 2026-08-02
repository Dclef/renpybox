from PyQt5.QtWidgets import QWidget
from qfluentwidgets import FluentIcon, PrimaryDropDownPushButton

from module.Localizer.Localizer import Localizer
from widget.EmptyCard import EmptyCard


class PlatformHeaderCard(EmptyCard):
    """接口管理页顶部说明卡。"""

    def __init__(self, parent: QWidget) -> None:
        localizer = Localizer.get()
        super().__init__(
            localizer.platform_page_widget_add_title,
            localizer.platform_page_active_none,
        )
        self.setParent(parent)

        self.add_button = PrimaryDropDownPushButton(localizer.add, self)
        self.add_button.setIcon(FluentIcon.ADD_TO)
        self.add_button.setFixedWidth(128)
        self.add_button.setContentsMargins(4, 0, 4, 0)
        self.add_widget(self.add_button)

    def set_active_name(self, name: str | None) -> None:
        localizer = Localizer.get()
        text = (
            localizer.platform_page_active_hint.replace("{NAME}", name)
            if name is not None
            else localizer.platform_page_active_none
        )
        self.description_label.setText(text)
