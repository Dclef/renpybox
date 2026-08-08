import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import qfluentwidgets
from PyQt5.QtWidgets import QApplication

from frontend.RenpyToolbox import OneKeyTranslatePage as page_module
from module.Config import Config
from module.Extract.ReplaceGenerator import (
    load_declined_candidates,
    record_declined_candidates,
)


APP = QApplication.instance() or QApplication([])


class _FakeMessageBox:
    def __init__(self, *args, **kwargs):
        self.yesButton = SimpleNamespace(setText=lambda value: None)
        self.cancelButton = SimpleNamespace(setText=lambda value: None)

    def exec(self):
        return True


def test_followup_options_are_created_with_current_defaults(monkeypatch):
    monkeypatch.setattr(Config, "load", lambda self: self)

    page = page_module.YiJianFanyiPage()

    assert page.verify_uppercase_chk.text() == (
        "对未翻译的大写缩写做二次确认（会额外消耗额度）"
    )
    assert page.verify_uppercase_chk.isChecked() is True
    assert page.clear_declined_btn.text() == "清除判定不译清单"
    page.deleteLater()


def test_verify_uppercase_option_saves_config(monkeypatch):
    saved = []
    config = SimpleNamespace(
        renpy_verify_uppercase_candidates=True,
        save=lambda: saved.append(True),
    )
    monkeypatch.setattr(
        "module.Config.Config",
        lambda: SimpleNamespace(load=lambda: config),
    )
    page = SimpleNamespace(
        logger=SimpleNamespace(warning=lambda *args, **kwargs: None)
    )

    page_module.YiJianFanyiPage._on_verify_uppercase_changed(page, 0)

    assert config.renpy_verify_uppercase_candidates is False
    assert saved == [True]


def test_clear_declined_candidates_reports_count_and_empty_state(tmp_path, monkeypatch):
    game_dir = tmp_path / "project"
    record_declined_candidates(game_dir, "chinese", {"TBD", "QUEST"})
    messages = []
    monkeypatch.setattr(qfluentwidgets, "MessageBox", _FakeMessageBox)
    monkeypatch.setattr(
        page_module,
        "InfoBar",
        SimpleNamespace(
            success=lambda title, message, **kwargs: messages.append(
                ("success", message)
            ),
            info=lambda title, message, **kwargs: messages.append(("info", message)),
            warning=lambda title, message, **kwargs: messages.append(
                ("warning", message)
            ),
        ),
    )
    page = SimpleNamespace(
        game_dir=str(game_dir),
        tl_folder_edit=SimpleNamespace(text=lambda: "chinese"),
    )

    page_module.YiJianFanyiPage._clear_declined_candidates(page)

    assert load_declined_candidates(game_dir, "chinese") == set()
    assert messages[-1] == ("success", "已清除 2 条判定不译记录")

    page_module.YiJianFanyiPage._clear_declined_candidates(page)

    assert messages[-1] == ("info", "当前没有判定不译记录")
