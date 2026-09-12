"""一键翻译在页面往返和工程切换时保持正确的运行目录。"""

import os
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt5.QtWidgets import QApplication

from base.Base import Base
from base.BaseLanguage import BaseLanguage
import frontend.RenpyToolbox.OneKeyTranslatePage as page_module
from module.Cache.CacheManager import CacheManager
from module.Config import Config


APP = QApplication.instance() or QApplication([])


@pytest.fixture
def project_page(monkeypatch, tmp_path):
    config = Config()
    config.renpy_project_path = ""
    config.renpy_game_folder = ""
    config.input_folder = ""
    config.output_folder = ""
    config.platforms = []
    monkeypatch.setattr(Config, "load", lambda self, path=None: config)
    monkeypatch.setattr(Config, "save", lambda self: None)
    monkeypatch.setattr(page_module.ProjectStore, "_emit_changed", lambda *args: None)
    monkeypatch.setattr(page_module.InfoBar, "success", lambda *args, **kwargs: None)
    monkeypatch.setattr(page_module.InfoBar, "warning", lambda *args, **kwargs: None)
    page = page_module.YiJianFanyiPage()
    root = tmp_path / "A"
    (root / "game" / "tl" / "chinese").mkdir(parents=True)
    page.game_path_edit.setText(str(root))
    try:
        yield page, config, root
    finally:
        page.close()
        page.deleteLater()


def test_incremental_paths_survive_workbench_and_translation_preflight(project_page, monkeypatch):
    page, config, root = project_page
    delta_input = root / "game" / "tl" / "chinese_new"
    delta_input.mkdir()
    monkeypatch.setattr(page, "_extract_character_names", lambda: None)
    page._on_extract_finished(True, "完成", SimpleNamespace(incremental_dir=delta_input))
    delta_output = root / "RenpyBox_Translation" / "chinese_new"
    visited = []
    workbench = SimpleNamespace(refresh_from_config=lambda: visited.append(config.input_folder))
    page.window = SimpleNamespace(renpy_workbench_page=workbench, navigate_to_page=lambda _: None)

    page._open_workbench_from_onekey()

    assert visited == [str(delta_input)]
    assert Path(config.input_folder) == delta_input
    assert Path(config.output_folder) == delta_output
    config.input_folder = str(root / "game" / "tl" / "chinese")
    config.output_folder = str(root / "RenpyBox_Translation" / "chinese")
    checked = []
    monkeypatch.setattr(page, "_refresh_step4_ready", lambda: checked.append(
        (Path(config.input_folder), Path(config.output_folder))
    ) or False)
    page._on_start_translate_clicked()
    assert checked == [(delta_input, delta_output)]


@pytest.mark.parametrize("change", ["project", "language"])
def test_new_project_or_language_drops_old_incremental_state(project_page, change):
    page, config, root = project_page
    page._incremental_dir = root / "game" / "tl" / "chinese_new"
    page._incremental_output_dir = root / "RenpyBox_Translation" / "chinese_new"
    page._apply_target_dir = root / "game" / "tl" / "chinese"
    page._onekey_translation_completed = True
    page._onekey_translation_started = True
    page._onekey_run_id = 7
    if change == "project":
        target = root.parent / "B"
        (target / "game").mkdir(parents=True)
        page.game_path_edit.setText(str(target))
        expected = target / "RenpyBox_Translation" / "chinese"
    else:
        (root / "game" / "tl" / "japanese").mkdir()
        page.tl_folder_edit.setText("japanese")
        expected = root / "RenpyBox_Translation" / "japanese"

    assert Path(config.output_folder) == expected
    assert page._incremental_dir is None
    assert page._incremental_output_dir is None
    assert page._apply_target_dir is None
    assert not page._onekey_translation_completed
    assert not page._onekey_translation_started
    assert page._onekey_run_id is None


def test_completed_cache_from_other_project_does_not_complete_wizard(project_page):
    page, config, root = project_page
    other_output = root.parent / "B" / "RenpyBox_Translation" / "chinese"
    manager = CacheManager(service=False)
    manager.get_project().set_status(Base.TranslationStatus.TRANSLATED)
    manager.save_to_file(manager.get_project(), [], str(other_output))
    config.output_folder = str(other_output)

    assert page._translation_output_completed() is False


def test_language_choices_update_the_actual_translation_config(project_page):
    page, config, _root = project_page
    page.src_lang_combo.setCurrentIndex(1)
    page.tgt_lang_combo.setCurrentIndex(1)

    assert config.source_language == BaseLanguage.Enum.JA
    assert config.target_language == BaseLanguage.Enum.ZH
    assert config.traditional_chinese_enable is True

    page.tgt_lang_combo.setCurrentIndex(2)
    assert config.target_language == BaseLanguage.Enum.JA
    assert config.traditional_chinese_enable is False


def test_language_choices_reload_current_settings_when_page_reopens(project_page):
    page, config, _root = project_page
    config.source_language = BaseLanguage.Enum.KO
    config.target_language = BaseLanguage.Enum.EN
    page.show()
    APP.processEvents()

    assert page.src_lang_combo.currentData() == BaseLanguage.Enum.KO
    assert page.tgt_lang_combo.currentData() == (BaseLanguage.Enum.EN, False)
