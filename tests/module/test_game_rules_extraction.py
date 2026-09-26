"""规则候选通过真实常规/增量事务落盘，不覆盖旧译文。"""

import pytest

from module.Config import Config
from module.Extract import GameExtractionRules as rules
from module.Extract.UnifiedExtractor import UnifiedExtractor
from module.Renpy.renpy_tl_core import RENPYBOX_REPLACE_ONLY_MARKER


def setup_game(tmp_path, monkeypatch, *, bound=True):
    game = tmp_path / 'project'
    (game / 'game').mkdir(parents=True)
    (game / 'game' / 'phone.rpy').write_text('call reply_message("Shared text")\ncall reply_message("New phone message")\n', encoding='utf-8')
    value = rules.new_profile()
    value.update(name='手机', rules=[rules.new_rule()])
    value['rules'][0].update(name='消息', enabled=True)
    store = rules.RuleStore(tmp_path / 'storage' / 'rules.json')
    if bound:
        scan = rules.RuleScan(game, value)
        scan.advance()
        store.save(value, game, bind=True, proof=scan)
    monkeypatch.setattr(rules, 'RuleStore', lambda: store)
    config = Config()
    config.extract_use_custom = True
    config.extract_use_official = False
    config.onekey_inject_base_box = False
    config.renpy_incremental_include_untranslated = False
    monkeypatch.setattr(Config, 'load', lambda self: config)
    # 内置扫描不制造本用例的候选，自定义规则必须自己进入真实写入链。
    monkeypatch.setattr('module.Extract.UnifiedExtractor.rx.ExtractAllFilesInDir', lambda *a, **k: None)
    monkeypatch.setattr('module.Extract.UnifiedExtractor.rx.collect_static_source_strings', lambda *a, **k: {})
    monkeypatch.setattr('module.Extract.UnifiedExtractor.rx.collect_static_menu_strings', lambda *a, **k: set())
    extractor = UnifiedExtractor()
    return game, store, extractor, config


def test_regular_writes_rule_locations_and_preserves_existing_translation(tmp_path, monkeypatch):
    root, store, extractor, config = setup_game(tmp_path, monkeypatch)
    tl = root / 'game' / 'tl' / 'chinese'
    tl.mkdir(parents=True)
    (tl / 'old.rpy').write_text('translate chinese strings:\n    old "Shared text"\n    new "已有译文"\n', encoding='utf-8')
    source_before = (root / 'game' / 'phone.rpy').read_bytes()
    result = extractor.extract_regular(root, 'chinese', use_official=False)
    assert result.success, result.message
    assert result.game_rule_candidates == 2
    assert extractor._get_existing_string_translations(tl)['Shared text'] == '已有译文'
    content = (tl / 'phone.rpy').read_text(encoding='utf-8')
    assert '# game/phone.rpy:2' in content
    assert RENPYBOX_REPLACE_ONLY_MARKER in content
    assert (root / 'game' / 'phone.rpy').read_bytes() == source_before
    again = extractor.extract_regular(root, 'chinese', use_official=False)
    assert again.success, again.message
    assert (tl / 'phone.rpy').read_text(encoding='utf-8').count('old "New phone message"') == 1


@pytest.mark.parametrize('separate', [True, False])
def test_incremental_rules_keep_same_text_as_dialogue_and_preserve_tl(tmp_path, monkeypatch, separate):
    root, store, extractor, config = setup_game(tmp_path, monkeypatch)
    tl = root / 'game' / 'tl' / 'chinese'
    tl.mkdir(parents=True)
    old = tl / 'phone.rpy'
    old.write_text('translate chinese scene_1:\n    # narrator "Shared text"\n    narrator "对白译文"\n', encoding='utf-8')
    old_bytes = old.read_bytes()
    def official(exe, language):
        tl.mkdir(parents=True, exist_ok=True)
        old.write_bytes(old_bytes)
    extractor._run_official_extract = official
    config.extract_use_official = True
    result = extractor.extract_incremental(root, 'chinese', root / 'game.exe', output_to_separate_folder=separate)
    assert result.success, result.message
    target = result.incremental_dir if separate else tl
    assert {'Shared text', 'New phone message'} <= extractor._get_string_originals(target)
    if separate:
        assert old.read_bytes() == old_bytes
        merge = extractor.merge_incremental_folder(root, 'chinese', result.incremental_dir)
        assert merge.success, merge.message
    again = extractor.extract_incremental(root, 'chinese', root / 'game.exe', output_to_separate_folder=True)
    assert again.success, again.message
    assert again.new_strings == 0


@pytest.mark.parametrize('kind', ['disabled', 'unbound', 'all_disabled'])
def test_rules_only_run_when_explicitly_enabled(tmp_path, monkeypatch, kind):
    root, store, extractor, config = setup_game(tmp_path, monkeypatch, bound=kind != 'unbound')
    if kind == 'disabled':
        store.select(root, 'source', 'builtin', store.bound_profile(root)['id'])
    if kind == 'all_disabled':
        value = store.bound_profile(root)
        value['rules'][0]['enabled'] = False
        store.save(value, root, bind=True)
    result = extractor.extract_regular(root, 'chinese', use_official=False)
    assert result.game_rule_candidates == 0
    assert not list((root / 'game' / 'tl').rglob('phone.rpy'))


@pytest.mark.parametrize('incremental', [False, True])
def test_rule_failure_before_tl_mutation(tmp_path, monkeypatch, incremental):
    root, store, extractor, config = setup_game(tmp_path, monkeypatch)
    tl = root / 'game' / 'tl' / 'chinese'
    tl.mkdir(parents=True)
    old = tl / 'keep.rpy'
    old.write_text('translate chinese strings:\n    old "keep"\n    new "保留"\n', encoding='utf-8')
    before = old.read_bytes()
    data = store.load()
    data['profiles'][0]['rules'][0]['pattern'] = '['
    store._write(data)
    method = extractor.extract_incremental if incremental else extractor.extract_regular
    result = method(root, 'chinese', use_official=False)
    assert not result.success
    assert old.read_bytes() == before
    assert not list(root.glob('_temp_extract_*'))


def test_declined_and_global_coverage_skip_rules(tmp_path, monkeypatch):
    from module.Extract.ReplaceGenerator import record_declined_candidates
    root, store, extractor, config = setup_game(tmp_path, monkeypatch)
    tl = root / 'game' / 'tl' / 'chinese'
    tl.mkdir(parents=True)
    (tl / 'old.rpy').write_text('translate chinese strings:\n    old "Shared text"\n    new "已有全局译文"\n', encoding='utf-8')
    record_declined_candidates(root, 'chinese', {'New phone message'})
    result = extractor.extract_incremental(root, 'chinese', use_official=False)
    assert result.success, result.message
    assert result.new_strings == 0



def test_official_failure_stays_visible_with_successful_rules(tmp_path, monkeypatch):
    from base.BaseLanguage import BaseLanguage
    from module.Localizer.Localizer import Localizer
    from frontend.RenpyToolbox.OneKeyWorkers import _localize_extraction_result
    root, store, extractor, config = setup_game(tmp_path, monkeypatch)
    config.extract_use_official = True
    def fail(*args):
        raise RuntimeError('官方失败')
    extractor._run_official_extract = fail
    result = extractor.extract_regular(root, 'chinese', root / 'game.exe')
    assert result.success
    assert result.official_status == 'failed'
    assert result.game_rule_candidates == 2
    monkeypatch.setattr(Localizer, 'APP_LANGUAGE', BaseLanguage.Enum.EN)
    message = _localize_extraction_result(result, False)
    assert 'Official extraction failed' in message
    assert '2 unique texts matched' in message

@pytest.mark.parametrize('incremental', [False, True])
def test_custom_only_never_calls_builtin_extractors(tmp_path, monkeypatch, incremental):
    root, store, extractor, config = setup_game(tmp_path, monkeypatch)
    store.select(root, 'source', 'custom', store.bound_profile(root)['id'])
    config.extract_use_custom = False
    config.extract_use_official = True
    config.onekey_inject_base_box = True
    tl = root / 'game' / 'tl' / 'chinese'
    tl.mkdir(parents=True)
    (tl / 'previous.rpy').write_text('translate chinese strings:\n    old "Previous text"\n    new "已有译文"\n', encoding='utf-8')
    def forbidden(*args, **kwargs):
        raise AssertionError('仅自定义模式调用了内置抽取')
    monkeypatch.setattr('module.Extract.UnifiedExtractor.rx.ExtractAllFilesInDir', forbidden)
    monkeypatch.setattr('module.Extract.UnifiedExtractor.rx.collect_static_source_strings', forbidden)
    monkeypatch.setattr('module.Extract.UnifiedExtractor.rx.collect_static_menu_strings', forbidden)
    extractor._run_official_extract = forbidden
    extractor._deploy_builtin_ui_pack = forbidden
    run = extractor.extract_incremental if incremental else extractor.extract_regular
    result = run(root, 'chinese', root / 'game.exe')
    assert result.success, result.message
    assert result.official_status == 'not_run'
    assert result.game_rule_candidates == 2
    target = result.incremental_dir if incremental else tl
    assert {'Shared text', 'New phone message'} <= extractor._get_string_originals(target)
