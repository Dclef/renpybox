from PyQt5.QtGui import QIcon
from qfluentwidgets import PushButton, TogglePushButton, setCustomStyleSheet


class QuietPillButton(TogglePushButton):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        styles = []
        for text, muted, selected, hover, accent in (
            ("#20262E", "#75808B", "#E4E9EE", "#EDF0F3", "#53697F"),
            ("#E8ECF0", "#84909D", "#303B47", "#242C36", "#9DAFBE"),
        ):
            styles.append(
                f"QuietPillButton {{ color: {text}; background: transparent;"
                " border: 1px solid transparent; border-radius: 14px; }"
                f"QuietPillButton:hover {{ color: {text}; background: {hover}; }}"
                f"QuietPillButton:checked, QuietPillButton:checked:hover {{"
                f" color: {text}; background: {selected}; border: 1px solid transparent;"
                f" border-bottom: 2px solid {accent}; }}"
                f"QuietPillButton:pressed, QuietPillButton:checked:pressed {{"
                f" color: {text}; background: {selected}; }}"
                f"QuietPillButton:focus {{ border: 1px solid {accent}; }}"
                f"QuietPillButton:disabled, QuietPillButton:checked:disabled {{"
                f" color: {muted}; background: transparent; border: 1px solid transparent; }}"
            )
        setCustomStyleSheet(self, *styles)

    def _drawIcon(self, icon, painter, rect, state=QIcon.Off):
        PushButton._drawIcon(self, icon, painter, rect, state)
