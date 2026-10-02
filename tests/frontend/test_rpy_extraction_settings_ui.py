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


def _bound_page(tmp_path, monkeypatch, mode='builtin', category='source'):
    """建一个带项目目录的页面，方案设置已落盘，返回页面。

    总是先存一个带启用规则的方案：没有方案时切到 combined/custom 会走进
    apply() 的 binding 错误分支，而 QMessageBox.warning 在 offscreen 下会
    直接 access violation 崩掉解释器（不是本次改动引入的）。
    存方案要带 RuleScan 证明，save() 在规则启用时强制要求。
    """
    root = tmp_path / 'project'
    game = root / 'game'
    game.mkdir(parents=True)
    (game / 'scene.rpy').write_text('e "Hello."\n"Continue":\ntext "Start"\n', encoding='utf-8')
    store = RuleStore(tmp_path / 'rules.json')
    monkeypatch.setattr(page_module, 'RuleStore', lambda: store)
    monkeypatch.setattr(Config, 'load', lambda self: self)
    page = page_module.RpyExtractionPage()
    page.path.setText(str(root))
    page.category.setCurrentIndex(page.category.findData(category))
    page.refresh()
    assert page.settings.root is not None
    profile = page_module.starter_profile(category)
    scan = RuleScan(root, profile)
    scan.advance()
    assert scan.completed
    # bind=False：builtin 模式要保持"没有绑定方案"，这样摘要才显示
    # rpy_rules_no_profile，测试才能区分 builtin/combined 两种摘要。
    store.save(profile, root, bind=False, proof=scan)
    if mode != 'builtin':
        store.select(root, category, mode, profile['id'])
    page.refresh()
    return page, store, root, profile


def test_summary_marks_unsaved_choice_until_it_is_applied(tmp_path, monkeypatch):
    from module.Localizer.Localizer import Localizer
    page, store, root, profile = _bound_page(tmp_path, monkeypatch)
    l = Localizer.get()
    settings = page.settings
    assert settings.summary.text() == l.rpy_rules_current.format(
        mode=l.rpy_rules_builtin, name=l.rpy_rules_no_profile)

    # 只改下拉不点应用：摘要必须变成"未保存"，而不是继续显示已生效值。
    # builtin 模式没有绑定方案，切到 combined 后必须自己选一个，
    # 否则 apply() 会按设计报 binding（QMessageBox 在 offscreen 下会崩）。
    settings.mode.setCurrentIndex(settings.mode.findData('combined'))
    settings.profile.setCurrentIndex(settings.profile.findData(profile['id']))
    assert settings.summary.text().startswith(l.rpy_rules_pending.split('{')[0])
    assert l.rpy_rules_builtin not in settings.summary.text()
    assert store.selection(root, 'source')[0] == 'builtin', '下拉不该自己落盘'

    # 应用后回到"已生效"，并且磁盘上确实改了。
    settings.apply()
    assert store.selection(root, 'source')[0] == 'combined'
    applied_text = l.rpy_rules_current.format(
        mode=l.rpy_rules_combined, name=profile['name'])
    assert settings.summary.text() == applied_text

    # 重新打开页面（模拟切换标签页）后仍显示已生效，不是未保存。
    page.refresh()
    assert page.settings.summary.text() == applied_text
    page.deleteLater()
    APP.processEvents()


def test_advanced_panel_cannot_be_collapsed_while_a_profile_is_required(tmp_path, monkeypatch):
    page, store, root, _ = _bound_page(tmp_path, monkeypatch, mode='custom')
    settings = page.settings
    assert settings.mode.currentData() == 'custom'
    assert settings.advanced_toggle.isChecked()
    assert not settings.advanced_actions.isHidden()

    # 收起高级区会把"管理自定义方案"一起藏掉，勾选必须被弹回去。
    settings.advanced_toggle.setChecked(False)
    assert settings.advanced_toggle.isChecked()
    assert not settings.advanced_actions.isHidden()

    # 回到 builtin 后可以自由折叠。
    settings.mode.setCurrentIndex(settings.mode.findData('builtin'))
    settings.advanced_toggle.setChecked(False)
    assert not settings.advanced_toggle.isChecked()
    assert not settings.advanced_actions.isVisible()
    page.deleteLater()
    APP.processEvents()


def test_category_names_describe_syntax_and_scope_note_tracks_the_selection(monkeypatch):
    from module.Localizer.Localizer import Localizer
    l = Localizer.get()
    monkeypatch.setattr(Config, 'load', lambda self: self)
    # 分类名按"读哪个目录的语法"命名；功能名只出现在适用范围说明里。
    assert 'game/' in l.rpy_rules_source
    assert 'tl/' in l.rpy_rules_tl
    assert '一键翻译' not in l.rpy_rules_source
    assert '源码翻译' not in l.rpy_rules_source
    assert 'TL 翻译' not in l.rpy_rules_tl
    assert '一键翻译' in l.rpy_rules_source_scope
    assert '一键翻译' in l.rpy_rules_tl_scope

    page = page_module.RpyExtractionPage()
    assert page.category_scope.text() == l.rpy_rules_source_scope
    page.category.setCurrentIndex(page.category.findData('tl'))
    assert page.category_scope.text() == l.rpy_rules_tl_scope
    page.deleteLater()
    APP.processEvents()


def test_settings_panel_stays_below_the_category_selector(monkeypatch):
    """_SETTINGS_INDEX 是具名常量：插入位置写错时布局顺序要立刻能看出来。"""
    monkeypatch.setattr(Config, 'load', lambda self: self)
    page = page_module.RpyExtractionPage()
    layout = page.layout()
    # 用 indexOf 直接钉住位置：几何比较在控件没被 layout 分配过时恒成立，
    # 索引写错也会全绿。settings 是普通 QWidget 子类，indexOf 能认出它。
    assert layout.indexOf(page.settings) == page._SETTINGS_INDEX
    # 设置区必须排在分类下拉和适用范围说明之后。
    # language 被包在 QHBoxLayout 里（indexOf 返回 -1），所以只断言设置区
    # 不在最后一个位置——真正挡在它前面的是后面那行展开说明。
    assert layout.indexOf(page.category) < layout.indexOf(page.settings)
    assert layout.indexOf(page.category_scope) < layout.indexOf(page.settings)
    assert page.layout().indexOf(page.hint) > page.layout().indexOf(page.settings)
    page.deleteLater()
    APP.processEvents()
