from PyQt5.QtGui import QIcon
from qfluentwidgets import PushButton, TogglePushButton, setCustomStyleSheet

from widget.ThemeTokens import DARK, LIGHT


class QuietPillButton(TogglePushButton):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        styles = []
        for palette in (LIGHT, DARK):
            styles.append(
                f"QuietPillButton {{ color: {palette.text_primary}; background: transparent;"
                " border: 1px solid transparent; border-radius: 6px; }"
                f"QuietPillButton:hover {{ color: {palette.text_primary};"
                f" background: {palette.surface_hover}; }}"
                f"QuietPillButton:checked, QuietPillButton:checked:hover {{"
                f" color: {palette.text_primary}; background: {palette.surface_pressed};"
                f" border: 1px solid transparent; border-bottom: 2px solid {palette.accent}; }}"
                f"QuietPillButton:pressed, QuietPillButton:checked:pressed {{"
                f" color: {palette.text_primary}; background: {palette.surface_pressed}; }}"
                f"QuietPillButton:focus {{ border: 1px solid {palette.accent}; }}"
                f"QuietPillButton:disabled, QuietPillButton:checked:disabled {{"
                f" color: {palette.text_disabled}; background: transparent;"
                " border: 1px solid transparent; }"
            )
        setCustomStyleSheet(self, *styles)

    def _drawIcon(self, icon, painter, rect, state=QIcon.Off):
        PushButton._drawIcon(self, icon, painter, rect, state)
