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
    QLabel#translationStatusPill {
        background-color: #242C36;
        border: none;
        border-radius: 4px;
        padding: 2px 3px;
        font-size: 10px;
    }
    QWidget#onekeySurface {
        background-color: #1B212A;
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 8px;
    }
    QWidget#onekeySection {
        background-color: #12161D;
        border: 1px solid rgba(255, 255, 255, 0.06);
        border-radius: 8px;
    }
    QMainWindow {
        background-color: #12161D;
    }

    /* Renpy Toolbox 背景 */
    QWidget[toolboxPage="true"],
    QWidget[toolboxScroll="true"],
    QWidget[toolboxFlow="true"],
    QWidget#toolboxPage,
    QWidget#toolboxScrollArea,
    QWidget#toolboxScrollContent,
    QWidget#toolboxScrollViewport,
    QWidget#toolboxFlow,
    QWidget#RenpyTranslationPage,
    QWidget[appPage="true"] {
        background-color: #12161D;
    }

    QWidget[toolboxPage="true"] QLabel,
    QWidget[toolboxScroll="true"] QLabel,
    QWidget[toolboxFlow="true"] QLabel,
    QWidget#toolboxPage QLabel,
    QWidget#toolboxScrollArea QLabel,
    QWidget#toolboxScrollContent QLabel,
    QWidget#toolboxScrollViewport QLabel,
    QWidget#toolboxFlow QLabel,
    QWidget#RenpyTranslationPage QLabel,
    QWidget[appPage="true"] QLabel {
        color: #E8ECF0;
        background: transparent;
    }

    /* CardWidget 统一背景 */
    CardWidget {
        background-color: #1B212A;
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 8px;
    }
    CardWidget:hover {
        background-color: #242C36;
        border-color: rgba(255, 255, 255, 0.12);
    }
    CardWidget:pressed {
        background-color: #303B47;
    }

    /* 任务监控看板的速览与流水层级 */
    CardWidget#translationKpiCard,
    CardWidget#translationMetricCard {
        background-color: #1B212A;
        border: 1px solid rgba(255, 255, 255, 0.08);
    }
    QFrame#translationThroughputStat,
    QFrame#translationFeedItem {
        background-color: rgba(18, 22, 29, 0.55);
        border: 1px solid rgba(255, 255, 255, 0.06);
        border-radius: 6px;
    }

    /* 校对页单层表面和顶部筛选条 */
    CardWidget#proofreadingSurface {
        background-color: #1B212A;
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 8px;
    }
    QWidget#workbenchSummarySurface,
    QWidget#workbenchStatusSurface {
        background-color: #12161D;
        border: 1px solid rgba(255, 255, 255, 0.06);
        border-radius: 6px;
    }
    QFrame#workbenchSummaryRow {
        background: transparent;
        border-bottom: 1px dashed rgba(255, 255, 255, 0.10);
    }
    QWidget#proofreadingFilterBar {
        background-color: #1B212A;
        border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    }

    /* 工具箱入口卡片 */
    ItemCard[toolCard="true"] {
        background-color: #1B212A;
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 8px;
    }
    ItemCard[toolCard="true"]:hover {
        background-color: #242C36;
        border-color: rgba(255, 255, 255, 0.12);
    }
    ItemCard[toolCard="true"]:pressed,
    ItemCard[toolCard="true"][pressed="true"] {
        background-color: #303B47;
    }
    ItemCard[toolCard="true"][projectReady="false"]:hover,
    ItemCard[toolCard="true"][projectReady="false"]:pressed,
    ItemCard[toolCard="true"][projectReady="false"][pressed="true"] {
        background-color: #1B212A;
        border-color: rgba(255, 255, 255, 0.08);
    }
    ItemCard[toolCard="true"]:focus {
        border-color: #9DAFBE;
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
        color: #B9C7D4;
        background-color: rgba(157, 175, 190, 0.18);
        border: 1px solid rgba(157, 175, 190, 0.35);
        border-radius: 11px;
    }

    /* 原生 QTableWidget 样式 */
    QTableWidget {
        background-color: #1B212A;
        alternate-background-color: #242C36;
        color: #E8ECF0;
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 8px;
        gridline-color: rgba(255, 255, 255, 0.08);
        selection-background-color: #303B47;
    }
    QTableWidget::item {
        padding: 6px;
        border: none;
    }
    QTableWidget::item:selected {
        background-color: #303B47;
        color: rgb(255, 255, 255);
    }
    QTableWidget::item:hover {
        background-color: #242C36;
    }
    QHeaderView::section {
        background-color: #242C36;
        color: #E8ECF0;
        padding: 8px;
        border: none;
        border-bottom: 1px solid rgba(255, 255, 255, 0.08);
        font-weight: bold;
    }
    QTableCornerButton::section {
        background-color: #242C36;
        border: none;
    }
    
    /* 原生 QScrollBar 样式 */
    QScrollBar:vertical {
        background-color: #1B212A;
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
        background-color: #1B212A;
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
        color: #E8ECF0;
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
    QLabel#translationStatusPill {
        background-color: #EDF0F3;
        border: none;
        border-radius: 4px;
        padding: 2px 3px;
        font-size: 10px;
    }
    QWidget#onekeySurface {
        background-color: #FFFFFF;
        border: 1px solid rgba(32, 38, 46, 0.10);
        border-radius: 8px;
    }
    QWidget#onekeySection {
        background-color: #F5F6F8;
        border: 1px solid rgba(32, 38, 46, 0.06);
        border-radius: 8px;
    }
    QMainWindow {
        background-color: #F5F6F8;
    }

    /* Renpy Toolbox 背景 */
    QWidget[toolboxPage="true"],
    QWidget[toolboxScroll="true"],
    QWidget[toolboxFlow="true"],
    QWidget#toolboxPage,
    QWidget#toolboxScrollArea,
    QWidget#toolboxScrollContent,
    QWidget#toolboxScrollViewport,
    QWidget#toolboxFlow,
    QWidget#RenpyTranslationPage,
    QWidget[appPage="true"] {
        background-color: #F5F6F8;
    }

    QWidget[toolboxPage="true"] QLabel,
    QWidget[toolboxScroll="true"] QLabel,
    QWidget[toolboxFlow="true"] QLabel,
    QWidget#toolboxPage QLabel,
    QWidget#toolboxScrollArea QLabel,
    QWidget#toolboxScrollContent QLabel,
    QWidget#toolboxScrollViewport QLabel,
    QWidget#toolboxFlow QLabel,
    QWidget#RenpyTranslationPage QLabel,
    QWidget[appPage="true"] QLabel {
        color: #20262E;
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
        background-color: #F5F6F8;
        border-color: rgba(0, 0, 0, 0.12);
    }
    CardWidget:pressed {
        background-color: #EDF0F3;
    }

    /* 任务监控看板的速览与流水层级 */
    CardWidget#translationKpiCard,
    CardWidget#translationMetricCard {
        background-color: #FFFFFF;
        border: 1px solid rgba(0, 0, 0, 0.08);
    }
    QFrame#translationThroughputStat,
    QFrame#translationFeedItem {
        background-color: #F5F6F8;
        border: 1px solid rgba(32, 38, 46, 0.06);
        border-radius: 6px;
    }

    /* 校对页单层表面和顶部筛选条 */
    CardWidget#proofreadingSurface {
        background-color: #FFFFFF;
        border: 1px solid rgba(32, 38, 46, 0.08);
        border-radius: 8px;
    }
    QWidget#workbenchSummarySurface,
    QWidget#workbenchStatusSurface {
        background-color: #F5F6F8;
        border: 1px solid rgba(32, 38, 46, 0.06);
        border-radius: 6px;
    }
    QFrame#workbenchSummaryRow {
        background: transparent;
        border-bottom: 1px dashed rgba(32, 38, 46, 0.14);
    }
    QWidget#proofreadingFilterBar {
        background-color: #FFFFFF;
        border-bottom: 1px solid rgba(32, 38, 46, 0.08);
    }

    /* 工具箱入口卡片 */
    ItemCard[toolCard="true"] {
        background-color: #FFFFFF;
        border: 1px solid rgba(0, 0, 0, 0.08);
        border-radius: 8px;
    }
    ItemCard[toolCard="true"]:hover {
        background-color: #F5F6F8;
        border-color: rgba(0, 0, 0, 0.12);
    }
    ItemCard[toolCard="true"]:pressed,
    ItemCard[toolCard="true"][pressed="true"] {
        background-color: #EDF0F3;
    }
    ItemCard[toolCard="true"][projectReady="false"]:hover,
    ItemCard[toolCard="true"][projectReady="false"]:pressed,
    ItemCard[toolCard="true"][projectReady="false"][pressed="true"] {
        background-color: #FFFFFF;
        border-color: rgba(0, 0, 0, 0.08);
    }
    ItemCard[toolCard="true"]:focus {
        border-color: #53697F;
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
        color: #53697F;
        background-color: rgba(83, 105, 127, 0.1);
        border: 1px solid rgba(83, 105, 127, 0.25);
        border-radius: 11px;
    }

    /* 原生 QTableWidget 样式 */
    QTableWidget {
        background-color: #FFFFFF;
        alternate-background-color: #F5F6F8;
        color: #20262E;
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
        color: #20262E;
    }
    QTableWidget::item:hover {
        background-color: #F5F6F8;
    }
    QHeaderView::section {
        background-color: #F5F6F8;
        color: #20262E;
        padding: 8px;
        border: none;
        border-bottom: 1px solid rgba(0, 0, 0, 0.08);
        font-weight: bold;
    }
    QTableCornerButton::section {
        background-color: #F5F6F8;
        border: none;
    }
    
    /* 原生 QScrollBar 样式 */
    QScrollBar:vertical {
        background-color: #F5F6F8;
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
        background-color: #A8B4C1;
    }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        height: 0px;
    }
    QScrollBar:horizontal {
        background-color: #F5F6F8;
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
        background-color: #A8B4C1;
    }
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
        width: 0px;
    }
    
    /* QGroupBox 样式 */
    QGroupBox {
        color: #20262E;
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


def get_navigation_stylesheet() -> str:
    """获取与页面表面一致的导航栏样式，覆盖 QFluent 默认灰色表面。"""
    if isDarkTheme():
        return """
            NavigationPanel[menu="true"] {
                background-color: #181D25;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-top-right-radius: 8px;
                border-bottom-right-radius: 8px;
            }
            NavigationPanel[menu="false"] {
                background-color: transparent;
                border: 1px solid transparent;
            }
            NavigationPanel[transparent="true"] {
                background-color: transparent;
            }
            QScrollArea, #scrollWidget {
                border: none;
                background-color: transparent;
            }
        """
    return """
        NavigationPanel[menu="true"] {
            background-color: #EDF0F3;
            border: 1px solid rgba(32, 38, 46, 0.08);
            border-top-right-radius: 8px;
            border-bottom-right-radius: 8px;
        }
        NavigationPanel[menu="false"] {
            background-color: transparent;
            border: 1px solid transparent;
        }
        NavigationPanel[transparent="true"] {
            background-color: transparent;
        }
        QScrollArea, #scrollWidget {
            border: none;
            background-color: transparent;
        }
    """


def get_theme_accent_color() -> QColor:
    """获取随明暗主题变化的应用主色。"""
    return ThemeColor.PRIMARY.color()


def get_theme_active_card_background_color() -> QColor:
    """获取激活卡片的低对比度主题色表面。"""
    return (
        QColor(157, 175, 190, 31)
        if isDarkTheme()
        else QColor(83, 105, 127, 20)
    )


def get_theme_active_card_border_color() -> QColor:
    """获取激活卡片的弱主题色边框。"""
    return (
        QColor(157, 175, 190, 92)
        if isDarkTheme()
        else QColor(83, 105, 127, 64)
    )


def get_theme_active_card_indicator_color() -> QColor:
    """获取激活卡片左侧强调线颜色。"""
    return QColor("#9DAFBE") if isDarkTheme() else QColor("#53697F")


def get_theme_active_card_foreground_color() -> QColor:
    """获取激活卡片的高对比度标题色。"""
    return QColor("#E8ECF0") if isDarkTheme() else QColor("#20262E")


def mark_toolbox_widget(widget: QWidget | None, prop: str = "toolboxPage") -> None:
    """为指定控件打上工具箱主题标记，确保样式表生效"""
    if widget is None:
        return

    widget.setProperty(prop, True)
    widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)


def mark_app_page(widget: QWidget | None) -> None:
    """为非工具箱主页面启用统一的浅色/深色背景。"""
    mark_toolbox_widget(widget, "appPage")


def mark_toolbox_scroll_area(scroll_area: QAbstractScrollArea | None) -> None:
    """额外处理滚动区域及其 viewport"""
    if scroll_area is None:
        return

    mark_toolbox_widget(scroll_area, "toolboxScroll")

    viewport = scroll_area.viewport()
    if viewport is not None:
        mark_toolbox_widget(viewport, "toolboxScroll")
