import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

from frontend.RenpyToolbox.TranslationReusePage import TranslationReusePage
from module.Config import Config


APP = QApplication.instance() or QApplication([])


def test_translation_reuse_page_prefills_configured_target(tmp_path, monkeypatch):
    target = tmp_path / "game" / "tl" / "chinese"
    target.mkdir(parents=True)
    config = Config()
    config.renpy_tl_folder = str(target)
    monkeypatch.setattr(Config, "load", lambda self, path=None: config)

    page = TranslationReusePage("translation-reuse")

    assert page.target_edit.text() == str(target)
    assert not hasattr(page, "backup_check")
    assert page.preview_button.isEnabled()
    assert page.execute_button.isEnabled()
    page.close()


def test_filter_groups_marked_supplement_as_generated_hook():
    from module.Cache.CacheItem import CacheItem
    marked = CacheItem(src="补漏", dst="补漏译文", file_path="scripts/miss.rpy", file_type=CacheItem.FileType.RENPY)
    extra = {"renpy": {"replace_only": True}}
    marked.set_extra_field(extra)
    assert TranslationReusePage is not None
    from frontend.Proofreading.FilterDialog import FilterDialog
    assert FilterDialog.file_group_key(marked) == "replace_text_auto.rpy"
