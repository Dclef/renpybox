"""Theme helpers for native Qt controls and the application shell."""

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QAbstractScrollArea, QWidget
from qfluentwidgets import ThemeColor

from widget.ThemeTokens import DARK, LIGHT, ThemePalette, current_palette


def _build_stylesheet(palette: ThemePalette) -> str:
    """Build the small native-control layer that sits below QFluentWidgets."""
    return f"""
        QMainWindow {{
            background-color: {palette.background};
        }}

        QWidget[toolboxPage="true"],
        QWidget[toolboxScroll="true"],
        QWidget[toolboxFlow="true"],
        QWidget#toolboxPage,
        QWidget#toolboxScrollArea,
        QWidget#toolboxScrollContent,
        QWidget#toolboxScrollViewport,
        QWidget#toolboxFlow,
        QWidget#RenpyTranslationPage,
        QWidget[appPage="true"] {{
            background-color: {palette.background};
        }}

        QWidget[toolboxPage="true"] QLabel,
        QWidget[toolboxScroll="true"] QLabel,
        QWidget[toolboxFlow="true"] QLabel,
        QWidget#toolboxPage QLabel,
        QWidget#toolboxScrollArea QLabel,
        QWidget#toolboxScrollContent QLabel,
        QWidget#toolboxScrollViewport QLabel,
        QWidget#toolboxFlow QLabel,
        QWidget#RenpyTranslationPage QLabel,
        QWidget[appPage="true"] QLabel {{
            color: {palette.text_primary};
            background: transparent;
        }}

        QLabel#translationStatusPill {{
            color: {palette.text_secondary};
            background-color: {palette.surface_subtle};
            border: 1px solid {palette.border};
            border-radius: 4px;
            padding: 2px 4px;
            font-size: 10px;
        }}

        QWidget#onekeySurface {{
            background-color: {palette.surface};
            border: 1px solid {palette.border};
            border-radius: 8px;
        }}
        QWidget#onekeySection {{
            background-color: {palette.surface_subtle};
            border: 1px solid {palette.border};
            border-radius: 6px;
        }}

        CardWidget {{
            background-color: {palette.surface};
            border: 1px solid {palette.border};
            border-radius: 8px;
        }}
        CardWidget:hover {{
            background-color: {palette.surface_hover};
            border-color: {palette.border_strong};
        }}
        CardWidget:pressed {{
            background-color: {palette.surface_pressed};
        }}

        CardWidget#translationKpiCard,
        CardWidget#translationMetricCard,
        CardWidget#proofreadingSurface {{
            background-color: {palette.surface};
            border: 1px solid {palette.border};
            border-radius: 8px;
        }}
        QFrame#translationThroughputStat,
        QFrame#translationFeedHeader,
        QFrame#translationFeedItem,
        QWidget#workbenchSummarySurface,
        QWidget#workbenchStatusSurface {{
            background-color: {palette.surface_subtle};
            border: 1px solid {palette.border};
            border-radius: 6px;
        }}
        QFrame#translationFeedHeader {{
            background-color: {palette.surface};
            border-color: {palette.divider};
        }}
        QFrame#workbenchSummaryRow {{
            background: transparent;
            border-bottom: 1px solid {palette.divider};
        }}
        QWidget#proofreadingFilterBar {{
            background-color: {palette.surface};
            border-bottom: 1px solid {palette.divider};
        }}

        ItemCard[toolCard="true"] {{
            background-color: {palette.surface};
            border: 1px solid {palette.border};
            border-radius: 8px;
        }}
        ItemCard[toolCard="true"]:hover {{
            background-color: {palette.surface_hover};
            border-color: {palette.border_strong};
        }}
        ItemCard[toolCard="true"]:pressed,
        ItemCard[toolCard="true"][pressed="true"] {{
            background-color: {palette.surface_pressed};
        }}
        ItemCard[toolCard="true"][projectReady="false"]:hover,
        ItemCard[toolCard="true"][projectReady="false"]:pressed,
        ItemCard[toolCard="true"][projectReady="false"][pressed="true"] {{
            background-color: {palette.surface};
            border-color: {palette.border};
        }}
        ItemCard[toolCard="true"]:focus {{
            border-color: {palette.accent};
        }}
        ItemCard[toolCard="true"] QLabel[toolCardDescription="true"],
        ItemCard[toolCard="true"][projectReady="false"] QLabel[toolCardTitle="true"],
        ItemCard[toolCard="true"][projectReady="false"] QLabel[projectRequirement="true"] {{
            color: {palette.text_secondary};
            background: transparent;
        }}
        ItemCard[toolCard="true"][projectReady="false"] QLabel[toolCardDescription="true"] {{
            color: {palette.text_disabled};
        }}
        ItemCard[toolCard="true"] QLabel[toolStep="true"] {{
            color: {palette.accent};
            background-color: {palette.accent_surface};
            border: 1px solid {palette.accent};
            border-radius: 11px;
        }}

        QTableWidget,
        QTableView {{
            background-color: {palette.surface};
            alternate-background-color: {palette.surface_subtle};
            color: {palette.text_primary};
            border: 1px solid {palette.border};
            border-radius: 8px;
            gridline-color: {palette.divider};
            selection-background-color: {palette.accent_surface};
            selection-color: {palette.text_primary};
        }}
        QTableWidget::item,
        QTableView::item {{
            padding: 6px;
            border: none;
        }}
        QTableWidget::item:selected,
        QTableView::item:selected {{
            background-color: {palette.accent_surface};
            color: {palette.text_primary};
        }}
        QTableWidget::item:hover,
        QTableView::item:hover {{
            background-color: {palette.surface_hover};
        }}
        QHeaderView::section {{
            background-color: {palette.surface_subtle};
            color: {palette.text_primary};
            padding: 8px;
            border: none;
            border-bottom: 1px solid {palette.divider};
            font-weight: 600;
        }}
        QTableCornerButton::section {{
            background-color: {palette.surface_subtle};
            border: none;
        }}

        QScrollBar:vertical {{
            background: transparent;
            width: 10px;
            margin: 0;
        }}
        QScrollBar::handle:vertical {{
            background-color: {palette.scrollbar};
            min-height: 30px;
            border-radius: 4px;
            margin: 2px;
        }}
        QScrollBar::handle:vertical:hover {{
            background-color: {palette.scrollbar_hover};
        }}
        QScrollBar::add-line:vertical,
        QScrollBar::sub-line:vertical {{
            height: 0;
        }}
        QScrollBar:horizontal {{
            background: transparent;
            height: 10px;
            margin: 0;
        }}
        QScrollBar::handle:horizontal {{
            background-color: {palette.scrollbar};
            min-width: 30px;
            border-radius: 4px;
            margin: 2px;
        }}
        QScrollBar::handle:horizontal:hover {{
            background-color: {palette.scrollbar_hover};
        }}
        QScrollBar::add-line:horizontal,
        QScrollBar::sub-line:horizontal {{
            width: 0;
        }}

        QGroupBox {{
            color: {palette.text_primary};
            border: 1px solid {palette.border};
            border-radius: 8px;
            margin-top: 12px;
            padding-top: 8px;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 5px;
        }}

        QLabel[semanticStatus="success"] {{ color: {palette.success}; }}
        QLabel[semanticStatus="warning"] {{ color: {palette.warning}; }}
        QLabel[semanticStatus="error"] {{ color: {palette.error}; }}
        QLabel[semanticStatus="info"] {{ color: {palette.info}; }}
        QLabel[textRole="secondary"] {{ color: {palette.text_secondary}; }}
        QLabel[textRole="disabled"] {{ color: {palette.text_disabled}; }}
    """


DARK_STYLESHEET = _build_stylesheet(DARK)
LIGHT_STYLESHEET = _build_stylesheet(LIGHT)


def get_current_stylesheet() -> str:
    """Return the native Qt stylesheet for the active theme."""
    return DARK_STYLESHEET if current_palette() is DARK else LIGHT_STYLESHEET


def get_navigation_stylesheet() -> str:
    """Return a neutral NavigationView surface matching Windows 11."""
    palette = current_palette()
    return f"""
        NavigationPanel[menu="true"],
        NavigationPanel[menu="false"] {{
            background-color: {palette.chrome};
            border-right: 1px solid {palette.divider};
        }}
        NavigationPanel[transparent="true"] {{
            background-color: transparent;
            border: none;
        }}
        QScrollArea, #scrollWidget {{
            border: none;
            background-color: transparent;
        }}
    """


def get_theme_accent_color() -> QColor:
    return ThemeColor.PRIMARY.color()


def _refresh_dynamic_style(widget: QWidget) -> None:
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    widget.update()


def set_text_role(
    widget: QWidget,
    role: str = "secondary",
    pixel_size: int | None = None,
) -> None:
    """Apply a theme-aware text role without an inline color stylesheet."""
    token = "text_disabled" if role == "disabled" else "text_secondary"
    if pixel_size is not None and hasattr(widget, "font") and hasattr(widget, "setFont"):
        font = widget.font()
        font.setPixelSize(pixel_size)
        widget.setFont(font)
    if hasattr(widget, "setTextColor"):
        widget.setTextColor(QColor(getattr(LIGHT, token)), QColor(getattr(DARK, token)))
    if hasattr(widget, "setProperty"):
        widget.setProperty("semanticStatus", "")
        widget.setProperty("textRole", role)
    if isinstance(widget, QWidget):
        _refresh_dynamic_style(widget)


def set_semantic_status(widget: QWidget, status: str | None) -> None:
    """Apply a shared success, warning, error, or info color."""
    if not status:
        set_text_role(widget)
        return
    if hasattr(widget, "setTextColor"):
        widget.setTextColor(QColor(getattr(LIGHT, status)), QColor(getattr(DARK, status)))
    if hasattr(widget, "setProperty"):
        widget.setProperty("textRole", "")
        widget.setProperty("semanticStatus", status)
    if isinstance(widget, QWidget):
        _refresh_dynamic_style(widget)


def get_theme_active_card_background_color() -> QColor:
    color = ThemeColor.PRIMARY.color()
    color.setAlpha(28 if current_palette() is DARK else 18)
    return color


def get_theme_active_card_border_color() -> QColor:
    color = ThemeColor.PRIMARY.color()
    color.setAlpha(92 if current_palette() is DARK else 64)
    return color


def get_theme_active_card_indicator_color() -> QColor:
    return ThemeColor.PRIMARY.color()


def get_theme_active_card_foreground_color() -> QColor:
    return QColor(current_palette().text_primary)


def mark_toolbox_widget(widget: QWidget | None, prop: str = "toolboxPage") -> None:
    """Mark a widget as a themed surface."""
    if widget is None:
        return
    widget.setProperty(prop, True)
    widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)


def mark_app_page(widget: QWidget | None) -> None:
    mark_toolbox_widget(widget, "appPage")


def mark_toolbox_scroll_area(scroll_area: QAbstractScrollArea | None) -> None:
    if scroll_area is None:
        return
    mark_toolbox_widget(scroll_area, "toolboxScroll")
    mark_toolbox_widget(scroll_area.viewport(), "toolboxScroll")
