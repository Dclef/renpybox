"""规则管理窗口：后台预览、保存绑定及取消生命周期。"""
import os
import threading
import time

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QApplication

from base.BaseLanguage import BaseLanguage
from frontend.RenpyToolbox.GameExtractionRulesDialog import GameExtractionRulesDialog
from module.Extract.GameExtractionRules import RuleStore, RuleScan
from module.Localizer.Localizer import Localizer

APP = QApplication.instance() or QApplication([])


def wait_until(predicate):
    deadline = time.monotonic() + 8
    while not predicate() and time.monotonic() < deadline:
        APP.processEvents()
        time.sleep(0.005)
    assert predicate()


def test_edit_preview_save_restart_and_stale_edit(tmp_path, monkeypatch):
    root = tmp_path / 'project'
    (root / 'game').mkdir(parents=True)
    (root / 'game' / 'phone.rpy').write_text('call reply_message("Try again.")', encoding='utf-8')
    store = RuleStore(tmp_path / 'storage' / 'rules.json')
    monkeypatch.setattr(Localizer, 'APP_LANGUAGE', BaseLanguage.Enum.EN)
    dialog = GameExtractionRulesDialog(root, 'chinese', store=store)
    try:
        dialog._add_rule()
        assert not dialog.save_btn.isEnabled()
        dialog._preview()
        assert not dialog.content.isEnabled()
        wait_until(lambda: dialog.job is None)
        assert dialog.scan is not None, dialog.status.text()
        assert dialog.scan.completed
        assert dialog.results.rowCount() == 1
        assert dialog.save_btn.isEnabled()
        dialog._save()
        wait_until(lambda: dialog.job is None)
        assert store.bound_profile(root)['rules'][0]['enabled']
        assert dialog.status.text() == Localizer.get().game_rules_saved
        dialog.pattern.setPlainText('[')
        assert not dialog.save_btn.isEnabled()
        dialog._preview()
        wait_until(lambda: dialog.job is None)
        assert dialog.status.text() == Localizer.get().game_rules_error_pattern
        dialog._save_draft()
        wait_until(lambda: dialog.job is None)
        assert not store.bound_profile(root)['rules'][0]['enabled']
        assert dialog.status.text() == Localizer.get().game_rules_draft_saved
        reopened = GameExtractionRulesDialog(root, 'japanese', store=RuleStore(store.path))
        assert reopened.profile['id'] == dialog.profile['id']
        reopened.deleteLater()
    finally:
        if dialog.job:
            dialog.job.requestInterruption()
            wait_until(lambda: dialog.job is None)
        dialog._dirty = False
        dialog.close()
        dialog.deleteLater()
        APP.processEvents()


def test_preview_keeps_gui_alive_and_close_cancels(tmp_path, monkeypatch):
    (tmp_path / 'game').mkdir()
    dialog = GameExtractionRulesDialog(tmp_path, 'chinese', store=RuleStore(tmp_path / 'rules.json'))
    dialog._add_rule()
    entered = threading.Event()
    threads = []
    original = RuleScan.advance
    def delayed(self, cancel=None, **kwargs):
        threads.append(threading.get_ident())
        entered.set()
        deadline = time.monotonic() + 5
        while not cancel() and time.monotonic() < deadline:
            time.sleep(0.005)
        return original(self, cancel, **kwargs)
    monkeypatch.setattr(RuleScan, 'advance', delayed)
    dialog._preview()
    assert entered.wait(2)
    heartbeat = []
    QTimer.singleShot(0, lambda: heartbeat.append(True))
    wait_until(lambda: bool(heartbeat))
    assert threads != [threading.get_ident()]
    dialog.reject()
    wait_until(lambda: dialog.job is None)
    assert not dialog.save_btn.isEnabled()
    assert not (tmp_path / 'rules.json').exists()
    dialog.deleteLater()
    APP.processEvents()



def test_project_switch_invalidates_preview(tmp_path):
    from base.Base import Base
    root = tmp_path / 'first'
    (root / 'game').mkdir(parents=True)
    dialog = GameExtractionRulesDialog(root, 'chinese', store=RuleStore(tmp_path / 'rules.json'))
    dialog._add_rule()
    dialog._preview()
    wait_until(lambda: dialog.job is None)
    assert dialog.scan.completed
    dialog._on_project_changed(Base.Event.PROJECT_CHANGED, {'project_root': str(tmp_path / 'second')})
    assert dialog.scan is None
    assert not dialog.content.isEnabled()
    dialog._dirty = False
    dialog.close()
    dialog.deleteLater()
    APP.processEvents()
