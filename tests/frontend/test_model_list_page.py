import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication, QWidget

from base.Base import Base
from frontend.Project.ModelListPage import ModelListPage
from module.Config import Config


APP = QApplication.instance() or QApplication([])


def test_model_list_filter_is_realtime_case_insensitive_and_preserves_items(monkeypatch) -> None:
    config = Config()
    config.platforms = [
        {
            "id": 7,
            "name": "聚合接口",
            "api_format": Base.APIFormat.OPENAI,
            "api_url": "https://example.invalid/v1",
            "api_key": ["test-key"],
        }
    ]
    config.save = lambda: config
    monkeypatch.setattr(Config, "load", lambda self, path=None: config)
    monkeypatch.setattr(
        ModelListPage,
        "get_models",
        lambda self, api_url, api_key, api_format: [
            "GPT-4o",
            "text-embedding-3-small",
            "Claude-3.5-Sonnet",
        ],
    )

    window = QWidget()
    page = ModelListPage(7, window)
    page.show()
    QApplication.processEvents()
    original_buttons = list(page.model_buttons)

    assert len(original_buttons) == 3
    assert all(not button.isHidden() for button in original_buttons)
    assert page.no_match_label.isHidden()

    page.filter_edit.setText("embedding")
    QApplication.processEvents()
    assert [button.text() for button in original_buttons if not button.isHidden()] == [
        "text-embedding-3-small"
    ]

    page.filter_edit.setText("cLaUd")
    QApplication.processEvents()
    assert [button.text() for button in original_buttons if not button.isHidden()] == [
        "Claude-3.5-Sonnet"
    ]

    page.filter_edit.setText("not-a-model")
    QApplication.processEvents()
    assert all(button.isHidden() for button in original_buttons)
    assert not page.no_match_label.isHidden()

    page.filter_edit.clear()
    QApplication.processEvents()
    assert all(not button.isHidden() for button in original_buttons)
    assert page.no_match_label.isHidden()
    assert page.model_buttons == original_buttons

    page.deleteLater()
    window.deleteLater()
