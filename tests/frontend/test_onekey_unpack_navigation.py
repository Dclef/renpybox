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
    navigated_pages = []
    window = SimpleNamespace(
        pack_unpack_page = unpack_page,
        navigate_to_page = navigated_pages.append,
    )
    page = SimpleNamespace(
        window = window,
        game_dir = str(tmp_path),
    )

    YiJianFanyiPage._open_rpa_unpack(page)

    assert received_paths == [str(tmp_path)]
    assert navigated_pages == [unpack_page]
