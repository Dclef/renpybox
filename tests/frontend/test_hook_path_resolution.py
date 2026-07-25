from pathlib import Path
from types import SimpleNamespace

import pytest

from frontend.RenpyToolbox.HookSupplementPage import HookSupplementPage
from frontend.RenpyToolbox.HookTranslatePage import HookTranslatePage


@pytest.mark.parametrize(
    "resolver",
    (
        HookTranslatePage._resolve_tl_dir,
        HookSupplementPage._resolve_tl_dir,
    ),
)
def test_hook_pages_keep_explicit_custom_tl_directory_before_creation(
    tmp_path,
    resolver,
):
    project = tmp_path / "project"
    (project / "game").mkdir(parents = True)
    custom_tl = project / "tl" / "chinese"
    assert custom_tl.exists() is False

    config = SimpleNamespace(
        renpy_project_path = str(project),
        renpy_game_folder = str(project),
        renpy_tl_folder = str(custom_tl),
        input_folder = str(custom_tl),
        output_folder = str(custom_tl),
    )
    page = SimpleNamespace(
        config = config,
        tl_name_edit = SimpleNamespace(text = lambda: "chinese"),
        _resolve_project_root = lambda: project.resolve(),
    )

    assert resolver(page) == custom_tl.resolve()


@pytest.mark.parametrize(
    "resolver",
    (
        HookTranslatePage._resolve_tl_dir,
        HookSupplementPage._resolve_tl_dir,
    ),
)
def test_hook_pages_ignore_custom_tl_directory_from_another_project(
    tmp_path,
    resolver,
):
    current = tmp_path / "current"
    previous = tmp_path / "previous"
    (current / "game").mkdir(parents = True)
    (previous / "game").mkdir(parents = True)
    stale_tl = previous / "tl" / "chinese"

    config = SimpleNamespace(
        renpy_project_path = str(previous),
        renpy_game_folder = str(previous),
        renpy_tl_folder = str(stale_tl),
        input_folder = str(stale_tl),
        output_folder = str(stale_tl),
    )
    page = SimpleNamespace(
        config = config,
        tl_name_edit = SimpleNamespace(text = lambda: "chinese"),
        _resolve_project_root = lambda: current.resolve(),
    )

    assert resolver(page) == Path(current / "game" / "tl" / "chinese")
