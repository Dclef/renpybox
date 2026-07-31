import importlib
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import Qt
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication, QWidget

from frontend.RenpyToolbox.RenpyToolboxPage import RenpyToolboxPage
from frontend.RenpyToolbox.ToolRegistry import TOOL_SPECS
from module.Config import Config
from widget.ItemCard import ItemCard


APP = QApplication.instance() or QApplication([])
toolbox_page_module = importlib.import_module(
    "frontend.RenpyToolbox.RenpyToolboxPage"
)


PROJECT_TOOLS = {
    "proofreading",
    "apply_translation",
    "font_replace",
    "add_language",
    "set_default_language",
    "hook_translate",
    "source_translate",
    "hook_supplement",
    "name_extraction",
    "android_build",
}


def _create_toolbox(monkeypatch, width: int = 1180) -> tuple[QWidget, RenpyToolboxPage]:
    clean_config = Config()
    clean_config.input_folder = ""
    clean_config.output_folder = ""
    clean_config.renpy_project_path = ""
    clean_config.renpy_game_folder = ""
    clean_config.renpy_tl_folder = ""
    monkeypatch.setattr(Config, "load", lambda self, path=None: clean_config)

    window = QWidget()
    window.resize(width, 760)
    toolbox = RenpyToolboxPage("renpy_toolbox_page", window)
    toolbox.setGeometry(window.rect())
    window.show()
    APP.processEvents()
    QTest.qWait(120)
    return window, toolbox


def test_toolbox_search_shows_empty_state_and_matches_keywords(monkeypatch) -> None:
    window, toolbox = _create_toolbox(monkeypatch)

    toolbox.search_edit.setText("zzz")
    QTest.qWait(10)
    assert toolbox.empty_state.isVisible()
    assert not any(card.isVisible() for card in toolbox._cards.values())
    assert not any(title.isVisible() for title in toolbox._section_titles.values())

    toolbox.search_edit.setText("反编译")
    QTest.qWait(10)
    assert not toolbox.empty_state.isVisible()
    assert [key for key, card in toolbox._cards.items() if card.isVisible()] == [
        "pack_unpack"
    ]

    toolbox.search_edit.clear()
    QTest.qWait(10)
    assert not toolbox.empty_state.isVisible()
    assert all(card.isVisible() for card in toolbox._cards.values())

    window.close()


def test_project_tools_are_explained_without_being_disabled(monkeypatch) -> None:
    assert {spec.key for spec in TOOL_SPECS if spec.requires_project} == PROJECT_TOOLS
    window, toolbox = _create_toolbox(monkeypatch)

    for key, card in toolbox._cards.items():
        if key in PROJECT_TOOLS:
            assert card.project_requirement_label.isVisible()
            assert card.toolTip() == "需先选择游戏目录"
            assert card.title_container.toolTip() == "需先选择游戏目录"
            assert card.isEnabled()
            assert card.graphicsEffect() is None
            description_layout = card.root.itemAt(2).layout()
            assert card.root.count() == 3
            assert description_layout.indexOf(card.description_label) == 0
            assert description_layout.indexOf(card.project_requirement_label) == 1
            assert (
                card.description_label.height()
                == card.description_label.maximumHeight()
            )
            assert (
                card.description_label.geometry().right()
                < card.project_requirement_label.geometry().left()
            )
            assert (
                card.description_label.geometry().top()
                <= card.project_requirement_label.geometry().top()
            )
            assert (
                card.project_requirement_label.geometry().bottom()
                <= card.description_label.geometry().bottom()
            )
        else:
            assert not card.project_requirement_label.isVisible()

    window.close()


def test_project_requirement_is_checked_before_custom_handler(monkeypatch) -> None:
    window, toolbox = _create_toolbox(monkeypatch)
    apply_spec = next(spec for spec in TOOL_SPECS if spec.key == "apply_translation")
    handled = []
    warnings = []
    monkeypatch.setattr(toolbox, "_has_project", lambda: False)
    monkeypatch.setattr(
        toolbox,
        "_open_apply_translation",
        lambda card: handled.append(card),
    )
    monkeypatch.setattr(
        toolbox_page_module.InfoBar,
        "warning",
        lambda *args, **kwargs: warnings.append((args, kwargs)),
    )

    toolbox._open_tool(apply_spec, toolbox._cards[apply_spec.key])

    assert handled == []
    assert len(warnings) == 1
    window.close()


def test_item_card_supports_keyboard_activation() -> None:
    parent = QWidget()
    activated = []
    card = ItemCard(
        parent,
        "测试工具",
        "测试描述",
        clicked=lambda widget: activated.append(widget),
    )
    parent.show()
    card.show()
    card.setFocus()
    APP.processEvents()

    assert card.focusPolicy() == Qt.FocusPolicy.StrongFocus
    assert card.title_button.focusPolicy() == Qt.FocusPolicy.NoFocus
    QTest.keyClick(card, Qt.Key.Key_Return)
    QTest.keyClick(card, Qt.Key.Key_Space)
    assert activated == [card, card]

    QTest.mousePress(card, Qt.MouseButton.LeftButton)
    assert card.property("pressed") is True
    QTest.mouseRelease(card, Qt.MouseButton.LeftButton)
    assert card.property("pressed") is False

    parent.close()


def test_flow_continue_card_reserves_step_space_only_in_numbered_group(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        RenpyToolboxPage,
        "_check_pending_translation",
        lambda self: True,
    )
    window, toolbox = _create_toolbox(monkeypatch)

    continue_card = toolbox._cards["continue_translation"]
    numbered_card = toolbox._cards["one_key_translate"]
    unnumbered_card = toolbox._cards["extract_to_tl"]
    continue_layout = continue_card.title_container.layout()
    numbered_layout = numbered_card.title_container.layout()
    unnumbered_layout = unnumbered_card.title_container.layout()

    assert continue_layout.itemAt(0).spacerItem().sizeHint().width() == 22 + 9
    assert numbered_layout.itemAt(0).widget().property("toolStep") is True
    assert unnumbered_layout.itemAt(0).widget() is unnumbered_card.icon_widget
    assert continue_card.icon_widget.x() == numbered_card.icon_widget.x()
    assert continue_card.title_label.x() == numbered_card.title_label.x()
    assert unnumbered_card.icon_widget.x() < continue_card.icon_widget.x()

    window.close()


def test_toolbox_cards_fill_available_width(monkeypatch) -> None:
    window, toolbox = _create_toolbox(monkeypatch, width=1280)

    def expected_width() -> int:
        width = toolbox.scroll_area.viewport().contentsRect().width()
        columns = max(1, (width + 12) // 272)
        return max(1, (width - 12 * (columns - 1) - 1) // columns)

    def assert_first_row_uses_expected_columns() -> None:
        width = toolbox.scroll_area.viewport().contentsRect().width()
        columns = max(1, (width + 12) // 272)
        flow_cards = [
            card
            for key, card in toolbox._cards.items()
            if toolbox._spec_by_key[key].group == "flow"
        ]
        first_row_y = min(card.y() for card in flow_cards)
        assert sum(card.y() == first_row_y for card in flow_cards) == min(
            columns, len(flow_cards)
        )

    assert {card.width() for card in toolbox._cards.values()} == {expected_width()}
    assert {card.height() for card in toolbox._cards.values()} == {132}
    assert_first_row_uses_expected_columns()

    window.resize(1920, 760)
    toolbox.setGeometry(window.rect())
    QTest.qWait(200)
    assert {card.width() for card in toolbox._cards.values()} == {expected_width()}
    assert {card.height() for card in toolbox._cards.values()} == {132}
    assert_first_row_uses_expected_columns()

    window.close()
