from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QWidget
from qfluentwidgets import FluentIcon, IconWidget, qconfig

from widget.FlowCard import FlowCard


class PlatformGroupCard(FlowCard):
    """接口分组卡片。"""

    def __init__(
        self,
        parent: QWidget,
        title: str,
        description: str,
        icon: FluentIcon,
    ) -> None:
        super().__init__(parent, title, description)

        self.icon_widget = IconWidget(icon, self)
        self.icon_widget.setFixedSize(26, 26)
        self.icon_widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.head_hbox.insertWidget(0, self.icon_widget)
        qconfig.themeChanged.connect(lambda _theme: self.icon_widget.update())

    def set_count_visible(self) -> None:
        """组内没有接口时隐藏整张卡片。"""
        self.setVisible(self.flow_layout.count() > 0)
