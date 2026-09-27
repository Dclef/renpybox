"""分类规则通过真实读取和写回链路验证。"""
import pytest

from base.Base import Base
from module.Config import Config
from module.Extract import GameExtractionRules as rules
from module.Extract.RpyExtractionSettings import context_for_path, ProfileTlExtractor
from module.File.RENPY import RENPY
from module.File.RENPYSOURCE import RENPYSOURCE
from module.Renpy.renpy_tl_core import parse_tl_document
from module.Renpy.renpy_tl_io import RenpyTlItemExtractor


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


def test_selected_source_files_do_not_walk_game(tmp_path, monkeypatch):
    game = tmp_path / 'game'
    game.mkdir()
    selected = game / 'scene.rpy'
    selected.write_text('e "Hello"', encoding='utf-8')
    backup = game / 'backup.rpy'
    backup.write_text('e "Ignored"', encoding='utf-8')
    outside = tmp_path / 'outside.rpy'
    outside.write_text('e "Outside"', encoding='utf-8')
    rule = rules.new_rule()
    monkeypatch.setattr(rules.os, 'walk', lambda *a, **k: pytest.fail('不应遍历整个 game'))
    manifest = rules.source_manifest(tmp_path, [rule], paths=[selected, backup, outside])
    assert [entry[0] for entry in manifest] == ['scene.rpy']


def test_tl_scope_matches_once_per_file(monkeypatch):
    import module.Extract.RpyExtractionSettings as settings
    rule = rules.new_rule()
    rule.update(enabled=True, pattern=r'old\s+(?P<text>"Hello")')
    profile = rules.new_profile('tl')
    profile['rules'] = [rule]
    doc = parse_tl_document(['translate chinese strings:'] + ['    old "Hello"', '    new ""'] * 500)
    calls = []
    original = settings._matches_scope
    def counted(path, pattern):
        calls.append(path)
        return original(path, pattern)
    monkeypatch.setattr(settings, '_matches_scope', counted)
    extractor = ProfileTlExtractor('custom', profile)
    assert len(extractor.extract(doc, 'scene.rpy')) == 500
    assert len(calls) == 1
    assert len(extractor.extract(doc, 'other.txt')) == 0


@pytest.mark.parametrize('second_location', [
    '# game/places/graveyard.rpy:328',
    '# game/places/graveyard.rpy:347',
])
def test_tl_extractor_preserves_distinct_labels_and_writeback(second_location):
    doc = parse_tl_document([
        '# places/graveyard.rpyc:328',
        'translate chinese scene_a:',
        '    # e "Same line"',
        '    e "相同对白"',
        '',
        second_location,
        'translate chinese scene_a_1:',
        '    # e "Same line"',
        '    e "相同对白"',
    ])
    items = RenpyTlItemExtractor().extract(doc, 'places/graveyard.rpy')
    assert [item.get_src() for item in items] == ['Same line', 'Same line']
    assert [item.get_extra_field()['renpy']['block']['label'] for item in items] == ['scene_a', 'scene_a_1']
    # 相同对白的两个剧情位置必须分别写回，不能丢失其中的译文。
    from module.Renpy.renpy_tl_io import RenpyTlLineUpdater
    items[0].set_dst('第一次施法')
    items[1].set_dst('第二次施法')
    lines = list(doc.lines)
    applied, _ = RenpyTlLineUpdater().apply_items_to_lines(lines, items)
    assert applied == 2
    assert lines[3] == '    e "第一次施法"'
    assert lines[8] == '    e "第二次施法"'
