"""
ThemeHelper - 主题样式辅助工具
统一处理所有页面的主题切换问题

注意：此样式仅针对原生 Qt 控件 (QTableWidget, QLineEdit 等)
qfluentwidgets 的控件会自动处理主题，不需要在此设置
"""
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QWidget, QAbstractScrollArea
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
        background-color: #0B0F17;
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
        color: #E5E7EB;
        background: transparent;
    }

    /* CardWidget 统一背景 */
    CardWidget {
        background-color: #141B2A;
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 8px;
    }
    CardWidget:hover {
        background-color: #1A2234;
        border-color: rgba(255, 255, 255, 0.12);
    }
    CardWidget:pressed {
        background-color: #1E273D;
    }

    /* 工具箱入口卡片 */
    ItemCard[toolCard="true"] {
        background-color: #141B2A;
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 8px;
    }
    ItemCard[toolCard="true"]:hover {
        background-color: #1A2234;
        border-color: rgba(255, 255, 255, 0.12);
    }
    ItemCard[toolCard="true"]:pressed,
    ItemCard[toolCard="true"][pressed="true"] {
        background-color: #1E273D;
    }
    ItemCard[toolCard="true"][projectReady="false"]:hover,
    ItemCard[toolCard="true"][projectReady="false"]:pressed,
    ItemCard[toolCard="true"][projectReady="false"][pressed="true"] {
        background-color: #141B2A;
        border-color: rgba(255, 255, 255, 0.08);
    }
    ItemCard[toolCard="true"]:focus {
        border-color: #6366F1;
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
        color: #818CF8;
        background-color: rgba(99, 102, 241, 0.18);
        border: 1px solid rgba(99, 102, 241, 0.35);
        border-radius: 11px;
    }

    /* 原生 QTableWidget 样式 */
    QTableWidget {
        background-color: #141B2A;
        alternate-background-color: #1A2234;
        color: #E5E7EB;
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 8px;
        gridline-color: rgba(255, 255, 255, 0.08);
        selection-background-color: #1E273D;
    }
    QTableWidget::item {
        padding: 6px;
        border: none;
    }
    QTableWidget::item:selected {
        background-color: #1E273D;
        color: rgb(255, 255, 255);
    }
    QTableWidget::item:hover {
        background-color: #1A2234;
    }
    QHeaderView::section {
        background-color: #1A2234;
        color: #E5E7EB;
        padding: 8px;
        border: none;
        border-bottom: 1px solid rgba(255, 255, 255, 0.08);
        font-weight: bold;
    }
    QTableCornerButton::section {
        background-color: #1A2234;
        border: none;
    }
    
    /* 原生 QScrollBar 样式 */
    QScrollBar:vertical {
        background-color: #141B2A;
        width: 12px;
        margin: 0px;
    }
    QScrollBar::handle:vertical {
        background-color: #374151;
        min-height: 30px;
        border-radius: 6px;
        margin: 2px;
    }
    QScrollBar::handle:vertical:hover {
        background-color: #4B5563;
    }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        height: 0px;
    }
    QScrollBar:horizontal {
        background-color: #141B2A;
        height: 12px;
        margin: 0px;
    }
    QScrollBar::handle:horizontal {
        background-color: #374151;
        min-width: 30px;
        border-radius: 6px;
        margin: 2px;
    }
    QScrollBar::handle:horizontal:hover {
        background-color: #4B5563;
    }
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
        width: 0px;
    }
    
    /* QGroupBox 样式 */
    QGroupBox {
        color: #E5E7EB;
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 8px;
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
        background-color: #F8FAFC;
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
        color: #0F172A;
        padding: 0px;
        background: transparent;
    }

    /* CardWidget 统一背景 */
    CardWidget {
        background-color: #FFFFFF;
        border: 1px solid rgba(0, 0, 0, 0.08);
        border-radius: 8px;
    }
    CardWidget:hover {
        background-color: #F8FAFC;
        border-color: rgba(0, 0, 0, 0.12);
    }
    CardWidget:pressed {
        background-color: #F1F5F9;
    }

    /* 工具箱入口卡片 */
    ItemCard[toolCard="true"] {
        background-color: #FFFFFF;
        border: 1px solid rgba(0, 0, 0, 0.08);
        border-radius: 8px;
    }
    ItemCard[toolCard="true"]:hover {
        background-color: #F8FAFC;
        border-color: rgba(0, 0, 0, 0.12);
    }
    ItemCard[toolCard="true"]:pressed,
    ItemCard[toolCard="true"][pressed="true"] {
        background-color: #F1F5F9;
    }
    ItemCard[toolCard="true"][projectReady="false"]:hover,
    ItemCard[toolCard="true"][projectReady="false"]:pressed,
    ItemCard[toolCard="true"][projectReady="false"][pressed="true"] {
        background-color: #FFFFFF;
        border-color: rgba(0, 0, 0, 0.08);
    }
    ItemCard[toolCard="true"]:focus {
        border-color: #4F46E5;
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
        color: #4F46E5;
        background-color: rgba(79, 70, 229, 0.1);
        border: 1px solid rgba(79, 70, 229, 0.25);
        border-radius: 11px;
    }

    /* 原生 QTableWidget 样式 */
    QTableWidget {
        background-color: #FFFFFF;
        alternate-background-color: #F8FAFC;
        color: #0F172A;
        border: 1px solid rgba(0, 0, 0, 0.08);
        border-radius: 8px;
        gridline-color: rgba(0, 0, 0, 0.08);
        selection-background-color: #E2E8F0;
    }
    QTableWidget::item {
        padding: 6px;
        border: none;
    }
    QTableWidget::item:selected {
        background-color: #E2E8F0;
        color: #0F172A;
    }
    QTableWidget::item:hover {
        background-color: #F8FAFC;
    }
    QHeaderView::section {
        background-color: #F8FAFC;
        color: #0F172A;
        padding: 8px;
        border: none;
        border-bottom: 1px solid rgba(0, 0, 0, 0.08);
        font-weight: bold;
    }
    QTableCornerButton::section {
        background-color: #F8FAFC;
        border: none;
    }
    
    /* 原生 QScrollBar 样式 */
    QScrollBar:vertical {
        background-color: #F8FAFC;
        width: 12px;
        margin: 0px;
    }
    QScrollBar::handle:vertical {
        background-color: #CBD5E1;
        min-height: 30px;
        border-radius: 6px;
        margin: 2px;
    }
    QScrollBar::handle:vertical:hover {
        background-color: #94A3B8;
    }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        height: 0px;
    }
    QScrollBar:horizontal {
        background-color: #F8FAFC;
        height: 12px;
        margin: 0px;
    }
    QScrollBar::handle:horizontal {
        background-color: #CBD5E1;
        min-width: 30px;
        border-radius: 6px;
        margin: 2px;
    }
    QScrollBar::handle:horizontal:hover {
        background-color: #94A3B8;
    }
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
        width: 0px;
    }
    
    /* QGroupBox 样式 */
    QGroupBox {
        color: #0F172A;
        border: 1px solid rgba(0, 0, 0, 0.08);
        border-radius: 8px;
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
    return QColor("#6366F1") if isDarkTheme() else QColor("#4F46E5")


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
