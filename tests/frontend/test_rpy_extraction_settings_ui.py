"""抽取设置入口、分类切换及预览生命周期。"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt5.QtWidgets import QApplication
from frontend.RenpyToolbox import RpyExtractionPage as page_module
from frontend.RenpyToolbox.GameExtractionRulesDialog import GameExtractionRulesDialog
from frontend.RenpyToolbox.DirectRpyTranslatePage import DirectRpyTranslatePage
from frontend.RenpyToolbox.SourceTranslatePage import SourceTranslatePage
from module.Config import Config
from module.Extract.GameExtractionRules import RuleStore, RuleScan
from tests.frontend.test_game_extraction_rules_dialog import wait_until

APP = QApplication.instance() or QApplication([])


def test_builtin_templates_preview_and_categories_stay_separate(tmp_path, monkeypatch):
    root = tmp_path / 'project'
    game = root / 'game'
    tl = game / 'tl' / 'chinese'
    tl.mkdir(parents=True)
    (game / 'scene.rpy').write_text('e "Hello."\n"Continue":\ntext "Start"\n', encoding='utf-8')
    (tl / 'scene.rpy').write_text('translate chinese strings:\n    old "Hello."\n    new ""\n', encoding='utf-8')
    store = RuleStore(tmp_path / 'rules.json')
    monkeypatch.setattr(page_module, 'RuleStore', lambda: store)
    monkeypatch.setattr(Config, 'load', lambda self: self)
    source_profile = page_module.starter_profile('source')
    scan = RuleScan(root, source_profile)
    scan.advance()
    assert {c.text for c in scan.candidates} == {'Hello.', 'Continue', 'Start'}
    store.save(source_profile, root, bind=True, proof=scan)
    store.select(root, 'source', 'custom', source_profile['id'])
    page = page_module.RpyExtractionPage()
    page.path.setText(str(root))
    page.refresh()
    assert page.settings.mode.currentData() == 'custom'
    assert page.settings.profile.count() == 2
    page.category.setCurrentIndex(1)
    assert page.settings.mode.currentData() == 'builtin'
    assert page.settings.profile.count() == 1
    dialog = GameExtractionRulesDialog(root, 'chinese', store=store, category='tl', base=tl)
    dialog._add_rule()
    dialog._preview()
    wait_until(lambda: dialog.job is None)
    assert dialog.scan and dialog.scan.completed, dialog.status.text()
    assert dialog.results.rowCount() == 1
    dialog._save()
    wait_until(lambda: dialog.job is None)
    assert store.selection(root, 'tl')[0] == 'combined'
    assert store.selection(root, 'source')[0] == 'custom'
    dialog._dirty = False
    dialog.close()
    page.close()
    dialog.deleteLater()
    page.deleteLater()
    APP.processEvents()


def test_source_and_tl_pages_expose_matching_settings(monkeypatch):
    monkeypatch.setattr(Config, 'load', lambda self: self)
    source = SourceTranslatePage('test-source')
    tl = DirectRpyTranslatePage('test-tl')
    assert source.rpy_settings.category == 'source'
    assert tl.rpy_settings.category == 'tl'
    assert not source.rpy_settings.button.isHidden()
    assert not tl.rpy_settings.button.isHidden()
    source.deleteLater()
    tl.deleteLater()
    APP.processEvents()


def test_beginner_view_hides_rule_editor_until_needed(monkeypatch):
    monkeypatch.setattr(Config, 'load', lambda self: self)
    page = page_module.RpyExtractionPage()
    settings = page.settings
    assert settings.mode.currentData() == 'builtin'
    assert not settings.apply_button_simple.isHidden()
    assert not settings.advanced_actions.isVisible()
    assert not settings.profile.isVisible()
    settings.mode.setCurrentIndex(settings.mode.findData('combined'))
    assert not settings.profile.isHidden()
    assert settings.advanced_toggle.isChecked()
    assert not settings.advanced_actions.isHidden()
    page.deleteLater()
    APP.processEvents()
