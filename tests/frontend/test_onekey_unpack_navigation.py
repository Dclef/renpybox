from pathlib import Path
from types import SimpleNamespace

from frontend.RenpyToolbox.OneKeyTranslatePage import YiJianFanyiPage
from frontend.RenpyToolbox.PackUnpackPage import PackUnpackPage


class _LineEditStub:
    def __init__(self) -> None:
        self.value = ""

    def setText(self, value: str) -> None:
        self.value = value


def test_pack_unpack_accepts_project_root_and_fills_game_directory(tmp_path) -> None:
    game_dir = tmp_path / "game"
    game_dir.mkdir()
    page = SimpleNamespace(unpack_game_dir_edit = _LineEditStub())

    assert PackUnpackPage.set_game_directory(page, tmp_path) is True
    assert Path(page.unpack_game_dir_edit.value) == game_dir


def test_onekey_unpack_navigation_reuses_page_and_passes_project_path(
    tmp_path,
) -> None:
    received_paths = []
    unpack_page = SimpleNamespace(
        set_game_directory = lambda path: received_paths.append(path) or True,
    )
    requested_keys = []
    toolbox_page = SimpleNamespace(
        get_tool_page = lambda key: requested_keys.append(key) or unpack_page,
    )
    navigated_pages = []
    window = SimpleNamespace(
        renpy_toolbox_page = toolbox_page,
        navigate_to_page = navigated_pages.append,
    )
    page = SimpleNamespace(
        window = window,
        game_dir = str(tmp_path),
    )
    page._get_tool_page = lambda key: YiJianFanyiPage._get_tool_page(page, key)

    YiJianFanyiPage._open_rpa_unpack(page)

    assert requested_keys == ["pack_unpack"]
    assert received_paths == [str(tmp_path)]
    assert navigated_pages == [unpack_page]
