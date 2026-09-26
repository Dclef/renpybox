"""分类规则通过真实读取和写回链路验证。"""
import pytest

from base.Base import Base
from module.Config import Config
from module.Extract import GameExtractionRules as rules
from module.Extract.RpyExtractionSettings import context_for_path, ProfileTlExtractor
from module.File.RENPY import RENPY
from module.File.RENPYSOURCE import RENPYSOURCE
from module.Renpy.renpy_tl_core import parse_tl_document


def bind(tmp_path, monkeypatch, root, category, pattern, sample, *, mode='custom', base=None):
    store = rules.RuleStore(tmp_path / 'rules.json')
    profile = rules.new_profile(category)
    rule = rules.new_rule()
    rule.update(name='测试', enabled=True, pattern=pattern, positive_samples=[sample], negative_samples=['jump next_label'])
    profile.update(name='测试方案', rules=[rule])
    scan = rules.RuleScan(root, profile, base=base)
    scan.advance()
    assert scan.completed
    store.save(profile, root, bind=True, proof=scan)
    store.select(root, category, mode, profile['id'])
    monkeypatch.setattr(rules, 'RuleStore', lambda: store)
    return store, profile


def test_source_custom_only_exact_literal_and_writeback(tmp_path, monkeypatch):
    root = tmp_path / 'project'
    source = root / 'game' / 'sub' / 'phone.rpy'
    source.parent.mkdir(parents=True)
    original = 'e "Built-in dialogue"\n$ reply_message("key", "Try again.", "Try again.")\n'
    source.write_text(original, encoding='utf-8')
    store, profile = bind(tmp_path, monkeypatch, root, 'source',
        r'reply_message\("key", (?P<text>"(?:\\.|[^"\\])*"),',
        '$ reply_message("key", "Try again.", "Try again.")')
    config = Config()
    config.input_folder = str(source)
    config.output_folder = str(tmp_path / 'out')
    reader = RENPYSOURCE(config)
    items = reader.read_from_path([str(source)])
    assert [i.get_src() for i in items] == ['Try again.']
    assert items[0].get_extra_field()['renpy_source']['literal_slot'] == 1
    items[0].set_dst('重试。')
    items[0].set_status(Base.TranslationStatus.TRANSLATED)
    reader.write_to_path(items)
    assert (tmp_path / 'out' / source.name).read_text(encoding='utf-8') == original.replace('"Try again.",', '"重试。",', 1)
    assert source.read_text(encoding='utf-8') == original
    store.select(root, 'source', 'builtin', profile['id'])
    assert any(i.get_src() == 'Built-in dialogue' for i in reader.read_from_path([str(source)]))


def test_tl_custom_bypasses_text_filter_but_preserves_pair(tmp_path, monkeypatch):
    root = tmp_path / 'project'
    base = root / 'game' / 'tl' / 'japanese'
    base.mkdir(parents=True)
    path = base / 'test.rpy'
    original = 'translate japanese strings:\n    old "images/icon.png"\n    new ""\n    old "Ordinary text"\n    new ""\n'
    path.write_text(original, encoding='utf-8')
    assert context_for_path(path, 'tl')[1] == base
    store, profile = bind(tmp_path, monkeypatch, root, 'tl', r'^\s*old\s+(?P<text>"images/icon.png")', 'old "images/icon.png"', base=base)
    config = Config()
    config.input_folder = str(base)
    config.output_folder = str(tmp_path / 'out')
    reader = RENPY(config)
    items = reader.read_from_path([str(path)])
    assert [i.get_src() for i in items] == ['images/icon.png']
    store.select(root, 'tl', 'builtin', profile['id'])
    items[0].set_dst('自定义文本')
    items[0].set_status(Base.TranslationStatus.TRANSLATED)
    reader.write_to_path(items)
    result = (tmp_path / 'out' / 'test.rpy').read_text(encoding='utf-8')
    assert 'old "images/icon.png"\n    new "自定义文本"' in result
    assert 'old "Ordinary text"\n    new ""' in result
    assert path.read_text(encoding='utf-8') == original
    store.select(root, 'tl', 'combined', profile['id'])
    assert {i.get_src() for i in reader.read_from_path([str(path)])} == {'images/icon.png', 'Ordinary text'}
    assert store.selection(root, 'source') == ('builtin', None)


def test_tl_dialogue_custom_selection():
    profile = rules.new_profile('tl')
    rule = rules.new_rule()
    rule.update(name='对白', enabled=True, pattern=r'^\s*e\s+(?P<text>"Hello")')
    profile.update(name='测试', rules=[rule])
    doc = parse_tl_document(['translate chinese scene_1:', '    # e "Hello"', '    e ""', '    # f "Other"', '    f ""'])
    items = ProfileTlExtractor('custom', profile).extract(doc, 'scene.rpy')
    assert [i.get_src() for i in items] == ['Hello']
    assert items[0].get_extra_field()['renpy']['pair']['target_line'] == 3


def test_missing_custom_profile_fails_before_read(tmp_path, monkeypatch):
    root = tmp_path / 'project'
    (root / 'game').mkdir(parents=True)
    store = rules.RuleStore(tmp_path / 'rules.json')
    store.select(root, 'source', 'custom')
    monkeypatch.setattr(rules, 'RuleStore', lambda: store)
    config = Config()
    config.input_folder = str(root / 'game')
    with pytest.raises(rules.RuleError, match='binding'):
        RENPYSOURCE(config).read_from_path([])


def test_tl_scopes_remain_relative_to_language_folder(tmp_path, monkeypatch):
    root = tmp_path / 'project'
    base = root / 'game' / 'tl' / 'chinese'
    nested = base / 'phone'
    nested.mkdir(parents=True)
    path = nested / 'message.rpy'
    path.write_text('translate chinese strings:\n    old "Hello"\n    new ""\n', encoding='utf-8')
    store, profile = bind(tmp_path, monkeypatch, root, 'tl', r'old\s+(?P<text>"Hello")', 'old "Hello"', base=base)
    profile['rules'][0]['include_globs'] = ['phone/*.rpy']
    scan = rules.RuleScan(root, profile, base=base)
    scan.advance()
    store.save(profile, root, bind=True, proof=scan)
    config = Config()
    config.input_folder = str(nested)
    items = RENPY(config).read_from_path([str(path)])
    assert [i.get_src() for i in items] == ['Hello']
    assert items[0].get_file_path() == 'message.rpy'
    store.unbind(root, 'tl')
    assert store.selection(root, 'tl') == ('builtin', None)
