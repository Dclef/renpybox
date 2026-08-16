import os
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import QRect
from PyQt5.QtWidgets import QApplication

APP = QApplication.instance() or QApplication(sys.argv)


def _fake_screen(width, height):
    return SimpleNamespace(availableGeometry=lambda: QRect(0, 0, width, height))


def test_window_size_clamps_to_small_screen(monkeypatch) -> None:
    from frontend.AppFluentWindow import AppFluentWindow

    monkeypatch.setattr(QApplication, "primaryScreen", lambda: _fake_screen(1000, 680))
    assert AppFluentWindow._resolve_window_size() == (1000, 680)


def test_window_size_keeps_design_size_on_large_screen(monkeypatch) -> None:
    from frontend.AppFluentWindow import AppFluentWindow

    monkeypatch.setattr(QApplication, "primaryScreen", lambda: _fake_screen(1920, 1040))
    assert AppFluentWindow._resolve_window_size() == (1280, 800)


def test_window_size_without_screen(monkeypatch) -> None:
    from frontend.AppFluentWindow import AppFluentWindow

    monkeypatch.setattr(QApplication, "primaryScreen", lambda: None)
    assert AppFluentWindow._resolve_window_size() == (1280, 800)
