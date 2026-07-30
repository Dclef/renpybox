import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication, QStackedWidget, QWidget

from frontend.RenpyToolbox.RenpyToolboxPage import RenpyToolboxPage
from module.Config import Config


def _assert_visible_cards_inside_sections(toolbox: RenpyToolboxPage) -> None:
    for key, card in toolbox._cards.items():
        if not card.isVisible():
            continue
        group = toolbox._spec_by_key[key].group
        container = toolbox._section_containers[group]
        assert container.rect().contains(card.geometry())


def test_toolbox_cards_survive_page_round_trip(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    clean_config = Config()
    clean_config.input_folder = ""
    clean_config.output_folder = ""
    clean_config.renpy_project_path = ""
    clean_config.renpy_game_folder = ""
    clean_config.renpy_tl_folder = ""
    monkeypatch.setattr(Config, "load", lambda self, path=None: clean_config)

    window = QWidget()
    window.resize(1180, 760)
    stack = QStackedWidget(window)
    stack.setGeometry(0, 0, 1180, 760)
    toolbox = RenpyToolboxPage("renpy_toolbox_page", window)
    placeholder = QWidget()
    stack.addWidget(toolbox)
    stack.addWidget(placeholder)
    stack.setCurrentWidget(toolbox)
    window.show()
    QTest.qWait(30)

    card_count = len(toolbox._cards)
    assert sum(card.isVisible() for card in toolbox._cards.values()) == card_count
    _assert_visible_cards_inside_sections(toolbox)

    stack.setCurrentWidget(placeholder)
    stack.setCurrentWidget(toolbox)
    QTest.qWait(30)
    assert sum(card.isVisible() for card in toolbox._cards.values()) == card_count

    toolbox.search_edit.setText("HTML")
    QTest.qWait(10)
    assert [key for key, card in toolbox._cards.items() if card.isVisible()] == [
        "html_import"
    ]

    stack.setCurrentWidget(placeholder)
    stack.setCurrentWidget(toolbox)
    QTest.qWait(30)
    assert [key for key, card in toolbox._cards.items() if card.isVisible()] == [
        "html_import"
    ]

    toolbox.search_edit.clear()
    QTest.qWait(10)
    assert sum(card.isVisible() for card in toolbox._cards.values()) == card_count
    _assert_visible_cards_inside_sections(toolbox)

    window.close()
    app.processEvents()
