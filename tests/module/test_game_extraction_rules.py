"""自定义规则的持久化、严格捕获和有界扫描回归。"""
import copy
import time

import pytest

from module.Extract import GameExtractionRules as rules


def profile():
    value = rules.new_profile()
    value['name'] = '手机规则'
    rule = rules.new_rule()
    rule.update(name='手机消息', enabled=True)
    value['rules'] = [rule]
    return value


def source(tmp_path, text='call reply_message("Try again.")\n', name='phone.rpy'):
    target = tmp_path / 'game' / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding='utf-8')
    return target


def complete(root, value):
    scan = rules.RuleScan(root, value)
    for _ in range(100):
        scan.advance()
        if scan.completed:
            return scan
    raise AssertionError('扫描未完成')


def test_persistence_binding_language_independent_clone_and_delete(tmp_path):
    root = tmp_path / 'game_project'
    source(root)
    value = profile()
    store = rules.RuleStore(tmp_path / 'storage' / 'rules.json')
    store.save(value, root, bind=True, proof=complete(root, value))
    restored = rules.RuleStore(store.path)
    assert restored.bound_profile(root) == value
    assert list(restored.load()['bindings']) == [rules.project_key(root)]
    assert 'chinese' not in next(iter(restored.load()['bindings']))
    with pytest.raises(rules.RuleError, match='bound'):
        restored.delete(value['id'])
    moved = tmp_path / 'moved'
    source(moved)
    assert restored.bound_profile(moved) is None
    restored.save(value, moved, bind=True, proof=complete(moved, value))
    restored.unbind(root)
    assert restored.bound_profile(root) is None
    assert restored.bound_profile(moved) == value
    restored.unbind(moved)
    restored.delete(value['id'])
    assert restored.load()['profiles'] == []


@pytest.mark.parametrize('payload', ['{broken', '{"schema_version":2}', '{"schema_version":1,"profiles":[],"bindings":{"game":"missing"}}'])
def test_corrupt_store_never_overwritten(tmp_path, payload):
    path = tmp_path / 'rules.json'
    path.write_text(payload, encoding='utf-8')
    store = rules.RuleStore(path)
    value = profile()
    value['rules'][0]['enabled'] = False
    with pytest.raises(rules.RuleError):
        store.save(value, tmp_path, bind=False)
    assert path.read_text(encoding='utf-8') == payload


def test_failed_atomic_save_preserves_existing(tmp_path, monkeypatch):
    store = rules.RuleStore(tmp_path / 'rules.json')
    value = profile()
    value['rules'][0]['enabled'] = False
    store.save(value, tmp_path, bind=False)
    original = store.path.read_bytes()
    def fail(*args, **kwargs):
        raise PermissionError('只读目录')
    monkeypatch.setattr('module.File.AtomicWrite.os.replace', fail)
    value['name'] = '新名字'
    with pytest.raises(rules.RuleError, match='storage'):
        store.save(value, tmp_path, bind=False)
    assert store.path.read_bytes() == original


@pytest.mark.parametrize('line,expected', [
    ('call reply_message("你好 [name] {b}100%{/b}")', '你好 [name] {b}100%{/b}'),
    (r'''call reply_message('It\'s ok.')''', "It's ok."),
    (r'''call reply_message("a\\b\nc\"d")''', 'a\\b\nc"d'),
])
def test_strict_literals_roundtrip(tmp_path, line, expected):
    value = profile()
    value['rules'][0]['pattern'] = r"reply_message\((?P<text>\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*')\)"
    source(tmp_path, line)
    assert [c.text for c in complete(tmp_path, value).candidates] == [expected]


@pytest.mark.parametrize('line', [
    'call reply_message(f"Score: {score}")',
    'call reply_message(r"raw")',
    'call reply_message(b"bytes")',
    'call reply_message("one" "two")',
    'call reply_message("one" + variable)',
    'call reply_message(variable + "one")',
    'call reply_message("one".format(x))',
    'call reply_message("one" % x)',
    'call reply_message("one" if x else "two")',
    '# call reply_message("comment")',
    'call reply_message("""multiline""")',
])
def test_unsafe_capture_is_rejected(tmp_path, line):
    value = profile()
    value['rules'][0]['pattern'] = r'(?P<text>"[^"\n]*")'
    source(tmp_path, line)
    assert complete(tmp_path, value).candidates == []


def test_multiline_string_contents_not_scanned(tmp_path):
    source(tmp_path, 'default example = """\ncall reply_message("not code")\n"""\ncall reply_message("Real text")\n')
    assert [c.text for c in complete(tmp_path, profile()).candidates] == ['Real text']


@pytest.mark.parametrize('scope', ['../*.rpy', 'C:/*.rpy', '/abs/*.rpy', 'phone\\*.rpy', '', 'a/**b.rpy'])
def test_invalid_scope(scope):
    value = profile()
    value['rules'][0]['include_globs'] = [scope]
    with pytest.raises(rules.RuleError):
        rules.validate_profile(value)


def test_excluded_sources_and_outside_links(tmp_path):
    source(tmp_path)
    for name in ['tl/chinese/source.rpy', 'fonts_backup/font.rpy', 'tl_backup_1/a.rpy', 'cache/a.rpy', 'saves/a.rpy', 'miss/a.rpy', 'zz_renpybox_hook.rpy', 'replace_text_auto.rpy', '.hidden/a.rpy']:
        source(tmp_path, name=name)
    outside = tmp_path / 'outside.rpy'
    outside.write_text('call reply_message("outside")', encoding='utf-8')
    try:
        (tmp_path / 'game' / 'link.rpy').symlink_to(outside)
    except OSError:
        pass
    scan = complete(tmp_path, profile())
    assert [(c.path, c.line) for c in scan.candidates] == [('phone.rpy', 1)]


def test_preview_must_complete_and_sources_must_stay_current(tmp_path):
    source(tmp_path, name='a.rpy')
    source(tmp_path, name='b.rpy')
    value = profile()
    store = rules.RuleStore(tmp_path / 'rules.json')
    scan = rules.RuleScan(tmp_path, value)
    scan.advance(max_files=1)
    assert not scan.completed
    with pytest.raises(rules.RuleError, match='preview_required'):
        store.save(value, tmp_path, bind=True, proof=scan)
    scan.advance(max_files=1)
    assert scan.completed and len(scan.candidates) == 2
    changed = copy.deepcopy(value)
    changed['rules'][0]['pattern'] += ' '
    with pytest.raises(rules.RuleError, match='preview_required'):
        store.save(changed, tmp_path, bind=True, proof=scan)
    source(tmp_path, name='new.rpy')
    with pytest.raises(rules.RuleError, match='stale'):
        store.save(value, tmp_path, bind=True, proof=scan)


def test_changed_file_invalidates_continuation(tmp_path):
    path = source(tmp_path, name='a.rpy')
    source(tmp_path, name='b.rpy')
    scan = rules.RuleScan(tmp_path, profile())
    scan.advance(max_files=1)
    path.write_text('changed', encoding='utf-8')
    with pytest.raises(rules.RuleError, match='stale'):
        scan.advance()


def test_cancel_and_hard_timeout(tmp_path, monkeypatch):
    source(tmp_path)
    scan = rules.RuleScan(tmp_path, profile())
    with pytest.raises(rules.RuleError, match='cancelled'):
        scan.advance(lambda: True)
    assert not scan.completed
    value = profile()
    value['rules'][0].update(pattern=r'(?:call reply_message\((?P<text>"[^"]*")\)|(?:a+)+$)')
    source(tmp_path, 'a' * 30000 + '!')
    monkeypatch.setattr(rules, 'MATCH_TIMEOUT', 0.002)
    start = time.monotonic()
    with pytest.raises(rules.RuleError, match='timeout'):
        rules.RuleScan(tmp_path, value).advance()
    assert time.monotonic() - start < 2


def test_invalid_pattern_and_samples(tmp_path):
    value = profile()
    value['rules'][0]['pattern'] = '['
    with pytest.raises(rules.RuleError, match='pattern'):
        rules.RuleScan(tmp_path, value)
    value = profile()
    value['rules'][0]['negative_samples'] = value['rules'][0]['positive_samples']
    with pytest.raises(rules.RuleError, match='samples'):
        rules.RuleScan(tmp_path, value)


def test_byte_budget_resumes_without_duplicate_lines(tmp_path):
    source(tmp_path, 'call reply_message("First")\ncall reply_message("Second")\n')
    scan = rules.RuleScan(tmp_path, profile())
    scan.advance(max_bytes=1)
    assert not scan.completed
    scan.advance()
    assert scan.completed
    assert [(c.text, c.line) for c in scan.candidates] == [('First', 1), ('Second', 2)]


@pytest.mark.parametrize('text', [
    'call reply_message("one"\n "two")',
    'call reply_message(("one") + variable)',
    'call reply_message(\n "one"\n "two"\n)',
])
def test_cross_line_or_parenthesized_expression_is_not_a_literal(tmp_path, text):
    value = profile()
    value['rules'][0]['pattern'] = r'(?P<text>"[^"\n]*")'
    source(tmp_path, text)
    assert not complete(tmp_path, value).candidates


def test_overlapping_rules_keep_origins(tmp_path):
    value = profile()
    value['rules'].append(copy.deepcopy(value['rules'][0]))
    value['rules'][1]['id'] = 'second-rule'
    source(tmp_path)
    scan = complete(tmp_path, value)
    assert len(scan.candidates) == 2
    assert {c.rule_id for c in scan.candidates} == {value['rules'][0]['id'], 'second-rule'}


def test_compiled_dependency_has_real_timeout_support():
    compiled = rules.regex.compile('(a+)+$')
    with pytest.raises(TimeoutError):
        compiled.search('a' * 30000 + '!', timeout=0.001)
