"""项目设置页选择目录后不得改写用户的显式选择。"""

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt5.QtWidgets import QApplication
from PyQt5.QtWidgets import QWidget

import frontend.Project.ProjectPage as page_module
from base.BaseLanguage import BaseLanguage
from module.Config import Config
from module.Project.ProjectStore import ProjectStore
from module.Renpy.ProjectPaths import RenpyProjectPaths


APP = QApplication.instance() or QApplication([])


def _build_project(root: Path, language: str = "chinese") -> Path:
    tl_dir = root / "game" / "tl" / language
    tl_dir.mkdir(parents=True)
    (tl_dir / "a.rpy").write_text("x", encoding="utf-8")
    return tl_dir


@pytest.fixture
def project_page(monkeypatch, tmp_path):
    config = Config()
    config.renpy_project_path = ""
    config.renpy_game_folder = ""
    config.renpy_tl_folder = ""
    config.input_folder = ""
    config.output_folder = ""
    config.target_language = BaseLanguage.Enum.ZH
    monkeypatch.setattr(Config, "load", lambda self, path=None: config)
    monkeypatch.setattr(Config, "save", lambda self: None)
    monkeypatch.setattr(ProjectStore, "_emit_changed", lambda *args: None)
    window = QWidget()
    page = page_module.ProjectPage("project", window)
    try:
        yield page, config, window
    finally:
        page.deleteLater()
        window.close()


def _select(page, path: Path) -> None:
    """模拟用户点击输入文件夹卡片上的选择按钮。"""
    original = page_module.QFileDialog.getExistingDirectory
    page_module.QFileDialog.getExistingDirectory = staticmethod(
        lambda *args, **kwargs: str(path)
    )
    try:
        page.input_folder_card.get_push_button().click()
    finally:
        page_module.QFileDialog.getExistingDirectory = original


def test_user_chosen_input_folder_is_kept_as_is(project_page, tmp_path):
    """用户自建目录就是最终输入目录，项目身份不被改写成 game/tl/<lang>。"""
    page, config, _window = project_page
    root = tmp_path / "MyGame"
    tl_dir = _build_project(root)
    paths = RenpyProjectPaths.from_path(root)
    config.renpy_project_path = str(paths.project_root)
    config.renpy_game_folder = str(paths.project_root)
    config.renpy_tl_folder = str(tl_dir)
    config.input_folder = str(root / "MyOwnFolder")
    config.output_folder = str(root / "RenpyBox_Translation" / "chinese")
    my_input = root / "MyOwnFolder" / "trans"
    my_input.mkdir(parents=True)

    _select(page, my_input)

    assert config.input_folder == str(my_input)
    assert config.renpy_project_path == str(paths.project_root)
    assert config.renpy_tl_folder == str(tl_dir)
    assert page.input_folder_card.get_description_label().toolTip() == str(my_input)


def test_standard_tl_folder_still_syncs_project_identity(project_page, tmp_path):
    """选中真正的 game/tl/<lang> 时仍要同步项目身份，语言推断照旧生效。"""
    page, config, _window = project_page
    root = tmp_path / "OtherGame"
    _build_project(root, "japanese")
    tl_dir = root / "game" / "tl" / "japanese"
    config.target_language = BaseLanguage.Enum.ZH

    _select(page, tl_dir)

    paths = RenpyProjectPaths.from_path(root)
    assert config.renpy_project_path == str(paths.project_root)
    assert config.renpy_tl_folder == str(paths.tl_language_dir)
    assert config.input_folder == str(tl_dir)
    assert config.target_language == BaseLanguage.Enum.JA
