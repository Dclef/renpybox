"""后台读取目标行附近的内容，避免大脚本阻塞校对界面。"""
import threading
from pathlib import Path

from PyQt5.QtCore import QUrl, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QDesktopServices, QTextCursor, QTextFormat
from PyQt5.QtWidgets import QDialog, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QTextEdit, QVBoxLayout

from module.Localizer.Localizer import Localizer
from widget.ThemeHelper import mark_app_dialog


def read_line_context(path, row, cancel=None, radius=20):
    """只保留目标行附近的文本，并限制超长物理行的显示长度。"""
    if row < 1:
        raise ValueError(Localizer.get().target_line_invalid)
    start = max(1, row - radius)
    lines = []
    found = False
    with Path(path).open(encoding="utf-8-sig", errors="replace") as stream:
        for number, line in enumerate(stream, 1):
            if cancel and cancel():
                return []
            if number >= start:
                lines.append((number, line.rstrip("\r\n")[:2000]))
            if number == row:
                found = True
            if number >= row + radius:
                break
    if not found:
        raise ValueError(Localizer.get().target_line_missing)
    return lines


class TargetLocationDialog(QDialog):
    loaded = pyqtSignal(object, str)

    def __init__(self, path, row, parent=None):
        super().__init__(parent)
        mark_app_dialog(self)
        self.setWindowTitle(Localizer.get().target_line_title)
        self.resize(850, 520)
        self._cancel = threading.Event()
        self.row = row
        self.path = Path(path).resolve()
        layout = QVBoxLayout(self)
        self.location = QLabel(f"{path}:{row}", self)
        self.location.setTextFormat(Qt.PlainText)
        self.location.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.location.setWordWrap(True)
        layout.addWidget(self.location)
        self.status = QLabel(Localizer.get().target_line_loading, self)
        layout.addWidget(self.status)
        self.preview = QPlainTextEdit(self)
        self.preview.setReadOnly(True)
        self.preview.setLineWrapMode(QPlainTextEdit.NoWrap)
        layout.addWidget(self.preview)
        buttons = QHBoxLayout()
        self.open_file_button = QPushButton(Localizer.get().target_line_open_file, self)
        self.open_file_button.clicked.connect(self._open_file)
        buttons.addWidget(self.open_file_button)
        buttons.addStretch()
        close = QPushButton(Localizer.get().target_line_close, self)
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        layout.addLayout(buttons)
        self.finished.connect(lambda _: self._cancel.set())
        self.loaded.connect(self._show_context)

        def task():
            try:
                lines = read_line_context(path, row, self._cancel.is_set)
                self.loaded.emit(lines, "")
            except (OSError, ValueError) as exc:
                self.loaded.emit([], str(exc))

        threading.Thread(target=task, daemon=True).start()

    def _open_file(self):
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.path))):
            self.status.setText(Localizer.get().target_line_open_failed)

    def _show_context(self, lines, error):
        if self._cancel.is_set():
            return
        if error:
            self.status.setText(error)
            return
        self.status.setText(Localizer.get().target_line_context.format(row=self.row))
        self.preview.setPlainText("\n".join(f"{number:>6}  {text}" for number, text in lines))
        index = next((i for i, (number, _) in enumerate(lines) if number == self.row), 0)
        cursor = QTextCursor(self.preview.document().findBlockByNumber(index))
        self.preview.setTextCursor(cursor)
        selection = QTextEdit.ExtraSelection()
        selection.cursor = cursor
        selection.format.setBackground(QColor(255, 200, 60, 100))
        selection.format.setProperty(QTextFormat.FullWidthSelection, True)
        self.preview.setExtraSelections([selection])
        self.preview.centerCursor()
