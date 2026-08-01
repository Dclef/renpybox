"""
ThemeHelper - 主题样式辅助工具
统一处理所有页面的主题切换问题

注意：此样式仅针对原生 Qt 控件 (QTableWidget, QLineEdit 等)
qfluentwidgets 的控件会自动处理主题，不需要在此设置
"""
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QWidget, QTableWidget, QLabel, QAbstractScrollArea
from qfluentwidgets import ThemeColor, isDarkTheme


# 暗色主题的全局样式表 - 仅针对原生 Qt 控件
DARK_STYLESHEET = """
    /* Renpy Toolbox 背景 */
    QWidget[toolboxPage="true"],
    QWidget[toolboxScroll="true"],
    QWidget[toolboxFlow="true"],
    QWidget#toolboxPage,
    QWidget#toolboxScrollArea,
    QWidget#toolboxScrollContent,
    QWidget#toolboxScrollViewport,
    QWidget#toolboxFlow,
    QWidget#RenpyTranslationPage {
        background-color: rgb(20, 20, 20);
    }

    QWidget[toolboxPage="true"] QLabel,
    QWidget[toolboxScroll="true"] QLabel,
    QWidget[toolboxFlow="true"] QLabel,
    QWidget#toolboxPage QLabel,
    QWidget#toolboxScrollArea QLabel,
    QWidget#toolboxScrollContent QLabel,
    QWidget#toolboxScrollViewport QLabel,
    QWidget#toolboxFlow QLabel,
    QWidget#RenpyTranslationPage QLabel {
        color: rgb(235, 235, 235);
        background: transparent;
    }

    /* CardWidget 统一背景 */
    CardWidget {
        background-color: rgb(32, 32, 32);
        border: 1px solid rgb(55, 55, 55);
        border-radius: 8px;
    }
    CardWidget:hover {
        background-color: rgb(38, 38, 38);
    }

    /* 工具箱入口卡片 */
    ItemCard[toolCard="true"] {
        background-color: rgb(32, 32, 32);
        border: 1px solid rgb(55, 55, 55);
        border-radius: 8px;
    }
    ItemCard[toolCard="true"]:hover {
        background-color: rgb(38, 38, 38);
        border-color: rgb(70, 70, 70);
    }
    ItemCard[toolCard="true"]:pressed,
    ItemCard[toolCard="true"][pressed="true"] {
        background-color: rgb(45, 45, 45);
    }
    ItemCard[toolCard="true"][projectReady="false"]:hover,
    ItemCard[toolCard="true"][projectReady="false"]:pressed,
    ItemCard[toolCard="true"][projectReady="false"][pressed="true"] {
        background-color: rgb(32, 32, 32);
        border-color: rgb(55, 55, 55);
    }
    ItemCard[toolCard="true"]:focus {
        border-color: #BCA483;
    }
    ItemCard[toolCard="true"] QLabel[toolCardDescription="true"] {
        color: rgb(160, 160, 160);
        background: transparent;
    }
    ItemCard[toolCard="true"][projectReady="false"] QLabel[toolCardTitle="true"],
    ItemCard[toolCard="true"][projectReady="false"] QLabel[projectRequirement="true"] {
        color: rgb(160, 160, 160);
        background: transparent;
    }
    ItemCard[toolCard="true"][projectReady="false"] QLabel[toolCardDescription="true"] {
        color: rgb(120, 120, 120);
    }
    ItemCard[toolCard="true"] QLabel[toolStep="true"] {
        color: rgb(235, 225, 211);
        background-color: rgb(74, 65, 53);
        border: 1px solid rgb(103, 89, 70);
        border-radius: 11px;
    }

    /* 原生 QTableWidget 样式 */
    QTableWidget {
        background-color: rgb(39, 39, 39);
        alternate-background-color: rgb(45, 45, 45);
        color: rgb(200, 200, 200);
        border: 1px solid rgb(55, 55, 55);
        border-radius: 4px;
        gridline-color: rgb(55, 55, 55);
        selection-background-color: rgb(60, 60, 60);
    }
    QTableWidget::item {
        padding: 6px;
        border: none;
    }
    QTableWidget::item:selected {
        background-color: rgb(70, 70, 70);
        color: rgb(255, 255, 255);
    }
    QTableWidget::item:hover {
        background-color: rgb(50, 50, 50);
    }
    QHeaderView::section {
        background-color: rgb(50, 50, 50);
        color: rgb(200, 200, 200);
        padding: 8px;
        border: none;
        border-bottom: 1px solid rgb(65, 65, 65);
        font-weight: bold;
    }
    QTableCornerButton::section {
        background-color: rgb(50, 50, 50);
        border: none;
    }
    
    /* 原生 QScrollBar 样式 */
    QScrollBar:vertical {
        background-color: rgb(39, 39, 39);
        width: 12px;
        margin: 0px;
    }
    QScrollBar::handle:vertical {
        background-color: rgb(80, 80, 80);
        min-height: 30px;
        border-radius: 6px;
        margin: 2px;
    }
    QScrollBar::handle:vertical:hover {
        background-color: rgb(100, 100, 100);
    }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        height: 0px;
    }
    QScrollBar:horizontal {
        background-color: rgb(39, 39, 39);
        height: 12px;
        margin: 0px;
    }
    QScrollBar::handle:horizontal {
        background-color: rgb(80, 80, 80);
        min-width: 30px;
        border-radius: 6px;
        margin: 2px;
    }
    QScrollBar::handle:horizontal:hover {
        background-color: rgb(100, 100, 100);
    }
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
        width: 0px;
    }
    
    /* QGroupBox 样式 */
    QGroupBox {
        color: rgb(200, 200, 200);
        border: 1px solid rgb(55, 55, 55);
        border-radius: 4px;
        margin-top: 12px;
        padding-top: 8px;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        left: 10px;
        padding: 0 5px;
    }
"""

# 亮色主题的全局样式表 - 仅针对原生 Qt 控件
LIGHT_STYLESHEET = """
    /* Renpy Toolbox 背景 */
    QWidget[toolboxPage="true"],
    QWidget[toolboxScroll="true"],
    QWidget[toolboxFlow="true"],
    QWidget#toolboxPage,
    QWidget#toolboxScrollArea,
    QWidget#toolboxScrollContent,
    QWidget#toolboxScrollViewport,
    QWidget#toolboxFlow,
    QWidget#RenpyTranslationPage {
        background-color: rgb(250, 250, 250);
    }

    QWidget[toolboxPage="true"] QLabel,
    QWidget[toolboxScroll="true"] QLabel,
    QWidget[toolboxFlow="true"] QLabel,
    QWidget#toolboxPage QLabel,
    QWidget#toolboxScrollArea QLabel,
    QWidget#toolboxScrollContent QLabel,
    QWidget#toolboxScrollViewport QLabel,
    QWidget#toolboxFlow QLabel,
    QWidget#RenpyTranslationPage QLabel {
        color: rgb(32, 32, 32);
        padding: 0px;
    }

    /* CardWidget 统一背景 */
    CardWidget {
        background-color: rgb(255, 255, 255);
        border: 1px solid rgb(230, 230, 230);
        border-radius: 8px;
    }
    CardWidget:hover {
        background-color: rgb(248, 248, 248);
    }

    /* 工具箱入口卡片 */
    ItemCard[toolCard="true"] {
        background-color: rgb(255, 255, 255);
        border: 1px solid rgb(230, 230, 230);
        border-radius: 8px;
    }
    ItemCard[toolCard="true"]:hover {
        background-color: rgb(248, 248, 248);
        border-color: rgb(214, 214, 214);
    }
    ItemCard[toolCard="true"]:pressed,
    ItemCard[toolCard="true"][pressed="true"] {
        background-color: rgb(240, 240, 240);
    }
    ItemCard[toolCard="true"][projectReady="false"]:hover,
    ItemCard[toolCard="true"][projectReady="false"]:pressed,
    ItemCard[toolCard="true"][projectReady="false"][pressed="true"] {
        background-color: rgb(255, 255, 255);
        border-color: rgb(230, 230, 230);
    }
    ItemCard[toolCard="true"]:focus {
        border-color: #BCA483;
    }
    ItemCard[toolCard="true"] QLabel[toolCardDescription="true"] {
        color: rgb(96, 96, 96);
        background: transparent;
    }
    ItemCard[toolCard="true"][projectReady="false"] QLabel[toolCardTitle="true"],
    ItemCard[toolCard="true"][projectReady="false"] QLabel[projectRequirement="true"] {
        color: rgb(96, 96, 96);
        background: transparent;
    }
    ItemCard[toolCard="true"][projectReady="false"] QLabel[toolCardDescription="true"] {
        color: rgb(150, 150, 150);
    }
    ItemCard[toolCard="true"] QLabel[toolStep="true"] {
        color: rgb(88, 70, 48);
        background-color: rgb(239, 232, 221);
        border: 1px solid rgb(216, 202, 183);
        border-radius: 11px;
    }

    /* 原生 QTableWidget 样式 */
    QTableWidget {
        background-color: rgb(255, 255, 255);
        alternate-background-color: rgb(248, 248, 248);
        color: rgb(32, 32, 32);
        border: 1px solid rgb(220, 220, 220);
        border-radius: 4px;
        gridline-color: rgb(230, 230, 230);
        selection-background-color: rgb(230, 230, 230);
    }
    QTableWidget::item {
        padding: 6px;
        border: none;
    }
    QTableWidget::item:selected {
        background-color: rgb(210, 210, 210);
        color: rgb(0, 0, 0);
    }
    QTableWidget::item:hover {
        background-color: rgb(245, 245, 245);
    }
    QHeaderView::section {
        background-color: rgb(245, 245, 245);
        color: rgb(32, 32, 32);
        padding: 8px;
        border: none;
        border-bottom: 1px solid rgb(220, 220, 220);
        font-weight: bold;
    }
    QTableCornerButton::section {
        background-color: rgb(245, 245, 245);
        border: none;
    }
    
    /* 原生 QScrollBar 样式 */
    QScrollBar:vertical {
        background-color: rgb(245, 245, 245);
        width: 12px;
        margin: 0px;
    }
    QScrollBar::handle:vertical {
        background-color: rgb(200, 200, 200);
        min-height: 30px;
        border-radius: 6px;
        margin: 2px;
    }
    QScrollBar::handle:vertical:hover {
        background-color: rgb(180, 180, 180);
    }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        height: 0px;
    }
    QScrollBar:horizontal {
        background-color: rgb(245, 245, 245);
        height: 12px;
        margin: 0px;
    }
    QScrollBar::handle:horizontal {
        background-color: rgb(200, 200, 200);
        min-width: 30px;
        border-radius: 6px;
        margin: 2px;
    }
    QScrollBar::handle:horizontal:hover {
        background-color: rgb(180, 180, 180);
    }
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
        width: 0px;
    }
    
    /* QGroupBox 样式 */
    QGroupBox {
        color: rgb(32, 32, 32);
        border: 1px solid rgb(220, 220, 220);
        border-radius: 4px;
        margin-top: 12px;
        padding-top: 8px;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        left: 10px;
        padding: 0 5px;
    }
"""


def get_current_stylesheet() -> str:
    """获取当前主题对应的样式表"""
    return DARK_STYLESHEET if isDarkTheme() else LIGHT_STYLESHEET


def get_theme_accent_color() -> QColor:
    """获取随明暗主题变化的应用主色。"""
    return ThemeColor.PRIMARY.color()


def get_theme_active_card_background_color() -> QColor:
    """获取与主按钮一致的激活卡片背景色。"""
    return get_theme_accent_color()


def get_theme_active_card_border_color() -> QColor:
    """获取与主按钮一致的激活卡片边框色。"""
    return ThemeColor.LIGHT_1.color()


def get_theme_active_card_indicator_color() -> QColor:
    """获取激活卡片左侧强调线颜色。"""
    return ThemeColor.DARK_1.color()


def get_theme_active_card_foreground_color() -> QColor:
    """获取与主按钮一致的激活卡片前景色。"""
    return QColor(0, 0, 0) if isDarkTheme() else QColor(255, 255, 255)


def mark_toolbox_widget(widget: QWidget | None, prop: str = "toolboxPage") -> None:
    """为指定控件打上工具箱主题标记，确保样式表生效"""
    if widget is None:
        return

    widget.setProperty(prop, True)
    widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)


def mark_toolbox_scroll_area(scroll_area: QAbstractScrollArea | None) -> None:
    """额外处理滚动区域及其 viewport"""
    if scroll_area is None:
        return

    mark_toolbox_widget(scroll_area, "toolboxScroll")

    viewport = scroll_area.viewport()
    if viewport is not None:
        mark_toolbox_widget(viewport, "toolboxScroll")
