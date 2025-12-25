"""
ItemCard - 工具卡片组件
类似 LinguaGacha 的卡片设计，用于工具箱页面
"""
from typing import Callable

from PyQt5.QtGui import QColor, QPainter
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout
from qfluentwidgets import (
    CardWidget,
    SubtitleLabel,
    CaptionLabel,
    TransparentToolButton,
    FluentIcon,
    isDarkTheme,
    qconfig,
    themeColor,
)
from qfluentwidgets.common.style_sheet import FluentStyleSheet

from widget.Separator import Separator


class ItemCard(CardWidget):
    """工具卡片组件 - 支持主题切换"""

    def __init__(
        self,
        parent: QWidget,
        title: str,
        description: str,
        init: Callable = None,
        clicked: Callable = None,
    ) -> None:
        super().__init__(parent)

        # 设置容器
        self.setFixedSize(300, 150)
        self.setBorderRadius(4)
        
        # 设置初始背景色
        self._update_background()
        
        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(16, 16, 16, 16)  # 左、上、右、下

        # 添加标题
        self.head_hbox_container = QWidget(self)
        self.head_hbox_container.setStyleSheet("background: transparent;")
        self.head_hbox = QHBoxLayout(self.head_hbox_container)
        self.head_hbox.setSpacing(0)
        self.head_hbox.setContentsMargins(0, 0, 0, 0)
        self.root.addWidget(self.head_hbox_container)

        self.title_label = SubtitleLabel(title, self)
        self.title_label.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents
        )
        self.head_hbox.addWidget(self.title_label)
        self.head_hbox.addStretch(1)
        self.title_button = TransparentToolButton(FluentIcon.PAGE_RIGHT)
        self.head_hbox.addWidget(self.title_button)

        # 添加分割线
        self.root.addWidget(Separator(self))

        # 添加描述
        self.description_label = CaptionLabel(description, self)
        self.description_label.setWordWrap(True)
        self._update_description_color()
        self.description_label.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents
        )
        self.root.addWidget(self.description_label, 1)

        # 监听主题变化
        qconfig.themeChanged.connect(self._on_theme_changed)

        if callable(init):
            init(self)

        if callable(clicked):
            self.clicked.connect(lambda: clicked(self))
            self.title_button.clicked.connect(lambda: clicked(self))

    def _update_background(self):
        """更新卡片背景色"""
        if isDarkTheme():
            # 暗色主题：深色卡片背景
            self.setStyleSheet("""
                ItemCard {
                    background-color: rgb(39, 39, 39);
                    border: 1px solid rgb(55, 55, 55);
                    border-radius: 4px;
                }
                ItemCard:hover {
                    background-color: rgb(45, 45, 45);
                    border: 1px solid rgb(65, 65, 65);
                }
            """)
        else:
            # 亮色主题：白色卡片背景
            self.setStyleSheet("""
                ItemCard {
                    background-color: rgb(255, 255, 255);
                    border: 1px solid rgb(229, 229, 229);
                    border-radius: 4px;
                }
                ItemCard:hover {
                    background-color: rgb(249, 249, 249);
                    border: 1px solid rgb(219, 219, 219);
                }
            """)

    def _update_description_color(self):
        """根据当前主题更新描述文字颜色"""
        if isDarkTheme():
            self.description_label.setTextColor(
                QColor(160, 160, 160), QColor(160, 160, 160)
            )
        else:
            self.description_label.setTextColor(
                QColor(96, 96, 96), QColor(96, 96, 96)
            )

    def _on_theme_changed(self):
        """主题切换时更新样式"""
        self._update_background()
        self._update_description_color()
