'''Resume tests use only fake requesters and isolated tmp_path storage.'''
from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest
import module.Extract.ExtractionCheckpoint as checkpoint
import module.Extract.GlossaryCandidateService as module
from module.Extract.GlossaryCandidateService import GlossaryCandidateService

PLATFORM = {'api_format': 'OpenAI', 'api_url': 'https://fake.invalid', 'model': 'fake',
            'thinking': {'level': 'HIGH'}, 'api_key': 'NEVER-WRITE-THIS-API-KEY'}


def row(name='Alice', line=1):
    return {'src': name, 'type': '角色', 'source': 'story.rpy', 'line': line, 'evidence': name}


def store(tmp_path, count=3, **kwargs):
    return checkpoint.ExtractionCheckpoint(project=tmp_path / 'game', mode=kwargs.pop('mode', 'glossary'),
        model_hash=kwargs.pop('model_hash', 'model'), chunk_keys=[checkpoint.digest(i) for i in range(count)],
        root=tmp_path / 'cache', **kwargs)


@pytest.fixture(autouse=True)
def isolate_every_run(tmp_path, monkeypatch):
    monkeypatch.setattr(GlossaryCandidateService, 'info', lambda *args, **kwargs: None)
    monkeypatch.setattr(checkpoint, 'default_checkpoint_root', lambda: tmp_path / 'private-cache')
    class ForbiddenRequester:
        def __init__(self, *args, **kwargs):
            raise AssertionError('No real model requests are allowed in this test module')
    monkeypatch.setattr(module, 'AgentRequester', ForbiddenRequester)


def make_service(tmp_path, monkeypatch, *, count=4, behavior=None, calls=None, events=None,
                 platform=None, suffix='', game='game', names=None, prefix='', **kwargs):
    game_path = tmp_path / game
    game_path.mkdir(exist_ok=True)
    names = names or {}
    rows = [{'id': i, 'text': '{}{} spoke.{}'.format(prefix, names.get(i, 'Name' + str(i)), suffix), 'source': 'story.rpy', 'line': i + 11}
            for i in range(count)]
    calls = calls if calls is not None else []
    behavior = behavior or {}
    class FakeRequester:
        def __init__(self, config, platform, **kwargs):
            pass
        def request_text(self, messages, **_kwargs):
            data = [json.loads(line) for line in messages[0]['content'].split('输入：' + chr(10), 1)[1].splitlines()]
            index = data[0]['id']
            calls.append(index)
            value = behavior.get(index, 'candidate')
            if callable(value):
                value = value()
            if value == 'fail':
                return SimpleNamespace(success=False, text='', error_code='fake', error_message='fake failure')
            text = '[]' if value == 'empty' else json.dumps({'src': names.get(index, 'Name' + str(index)), 'type': '角色', 'line': index})
            return SimpleNamespace(success=True, text=text, error_code='', error_message='')
        def cancel(self):
            pass
        def close(self):
            pass
    monkeypatch.setattr(module, 'AgentRequester', FakeRequester)
    service = GlossaryCandidateService(config=SimpleNamespace(), target_path=game_path,
        platform=copy.deepcopy(platform or PLATFORM), checkpoint_root=tmp_path / 'service-cache',
        event_callback=events, **kwargs)
    service._collect_corpus = lambda: (copy.deepcopy(rows), [])
    service._build_chunks = lambda items: [[item] for item in items]
    service.CHUNK_CONCURRENCY = 1
    service.CHUNK_TIMEOUT_SECONDS = 5.0
    service.CLOSE_TIMEOUT_SECONDS = 0.03
    return service


def test_empty_success_is_restored_and_completion_starts_fresh(tmp_path):
    first = store(tmp_path, count=2)
    assert first.begin() == {}
    assert first.save(0, []) == []
    assert first.metadata()['resume_available'] is True
    second = store(tmp_path, count=2)
    assert second.begin() == {0: []}
    assert second.save(1, [row()]) == [row()]
    second.finish()
    assert second.metadata()['checkpoint_status'] == 'complete'
    assert second.metadata()['resume_available'] is False
    third = store(tmp_path, count=2)
    assert third.begin() == {}
    assert third.generation != first.generation
    assert first.save(1, []) is None
    assert first.status == 'superseded'


@pytest.mark.parametrize('damage', ['syntax', 'version', 'identity', 'record', 'type', 'source', 'digest', 'complete'])
def test_corrupt_or_incompatible_checkpoint_never_skips_chunks(tmp_path, damage):
    first = store(tmp_path)
    first.begin()
    first.save(0, [row()])
    data = json.loads(first.path.read_text(encoding='utf-8'))
    if damage == 'version':
        data['schema_version'] = 999
    elif damage == 'identity':
        data['identity'] = 'other'
    elif damage == 'record':
        data['successes']['0'] = []
    elif damage == 'type':
        data['successes']['0']['entries'][0]['src'] = 7
    elif damage == 'source':
        del data['successes']['0']['entries'][0]['source']
    elif damage == 'digest':
        data['successes']['0']['digest'] = 'wrong'
    elif damage == 'complete':
        data['complete'] = True
    first.path.write_text('{' if damage == 'syntax' else json.dumps(data), encoding='utf-8')
    next_run = store(tmp_path)
    assert next_run.begin() == {}
    assert next_run.status == ('incompatible' if damage in {'version', 'identity'} else 'corrupt')
    assert next_run.metadata()['resume_available'] is False
    assert next_run.diagnostics
    next_run.save(1, [])
    assert next_run.status == 'new' and next_run.metadata()['resume_available']


def test_parallel_writes_merge_and_force_fences_old_generation(tmp_path):
    writers = [store(tmp_path, count=20) for _ in range(4)]
    for writer in writers:
        writer.begin()
    assert len({writer.generation for writer in writers}) == 1
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(writers[index % 4].save, index, []) for index in range(20)]
        assert all(future.result() == [] for future in futures)
    assert set(store(tmp_path, count=20).begin()) == set(range(20))
    forced = store(tmp_path, count=20)
    assert forced.begin(force=True) == {}
    assert writers[0].save(0, [row()]) is None
    assert forced.save(0, [row()]) == [row()]
    assert store(tmp_path, count=20).begin() == {0: [row()]}
    assert not list(forced.path.parent.glob('*.tmp'))


def test_first_concurrent_success_is_canonical(tmp_path):
    a, b = store(tmp_path), store(tmp_path)
    a.begin()
    b.begin()
    assert a.save(0, [row('Alice')]) == [row('Alice')]
    assert b.save(0, [row('Bob')]) == [row('Alice')]
    assert store(tmp_path).begin()[0] == [row('Alice')]


def test_committed_success_survives_process_exit_and_lock_is_released(tmp_path):
    code = '''
import os, sys
import importlib.util
spec = importlib.util.spec_from_file_location('checkpoint_test_child', sys.argv[-1])
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
ExtractionCheckpoint, digest = module.ExtractionCheckpoint, module.digest
_file_lock = module._file_lock
s = ExtractionCheckpoint(project=sys.argv[2], mode='glossary', model_hash='model', chunk_keys=[digest(i) for i in range(3)], root=sys.argv[1])
s.begin()
s.save(0, [])
lock = _file_lock(s.lock_path)
lock.__enter__()
os._exit(23)
'''
    result = subprocess.run([sys.executable, '-c', code, str(tmp_path / 'cache'), str(tmp_path / 'game'), str(checkpoint.__file__)],
        cwd=str(Path(__file__).resolve().parents[2]), capture_output=True, timeout=10)
    assert result.returncode == 23, result.stderr.decode(errors='replace')
    resumed = store(tmp_path)
    assert resumed.begin() == {0: []}
    assert resumed.save(1, [row()]) == [row()]


def test_atomic_replace_failure_preserves_previous_success(tmp_path, monkeypatch):
    original = store(tmp_path)
    original.begin()
    original.save(0, [])
    before = original.path.read_bytes()
    def broken_replace(*args):
        raise OSError('simulated disk failure with private data')
    with monkeypatch.context() as patch:
        patch.setattr(checkpoint.os, 'replace', broken_replace)
        assert original.save(1, [row()]) is None
    assert original.path.read_bytes() == before
    assert original.metadata()['resume_available'] is False
    assert original.diagnostics == ['io_error']
    assert store(tmp_path).begin() == {0: []}
    assert not list(original.path.parent.glob('*.tmp'))


def test_cache_refuses_game_owned_paths(tmp_path):
    cache = checkpoint.ExtractionCheckpoint(project=tmp_path / 'game', mode='glossary', model_hash='m',
        chunk_keys=['a'], root=tmp_path / 'game' / 'cache')
    assert cache.begin() == {}
    assert cache.diagnostics == ['unsafe_root']
    assert not (tmp_path / 'game').exists()


def test_same_project_alias_normalizes_identity(tmp_path):
    path = tmp_path / 'game'
    assert checkpoint.normalized_project(path / '..' / 'game') == checkpoint.normalized_project(path)


def test_partial_resume_uses_exact_success_indices_including_empty(tmp_path, monkeypatch):
    first_calls, events = [], []
    first = make_service(tmp_path, monkeypatch, calls=first_calls, behavior={0: 'fail', 2: 'empty', 3: 'fail'}, events=events.append)
    result = first.run()
    assert result['status'] == 'partial' and result['resume_available']
    assert set(first_calls) == {0, 1, 2, 3}
    second_calls, resumed_events = [], []
    second = make_service(tmp_path, monkeypatch, calls=second_calls, events=resumed_events.append)
    result = second.run()
    assert second_calls == [0, 3], 'never infer the first N blocks from completed count'
    assert result['reused_chunks'] == 2 and result['requested_chunks'] == 2
    assert result['llm_chunks_pending'] == 0 and result['coverage_percent'] == 100
    assert {entry['src'] for entry in result['entries']} == {'Name0', 'Name1', 'Name3'}
    for event in resumed_events:
        assert event['completed_chunks'] + len(event['active_chunks']) + event['pending_chunks'] == event['total_chunks']
        assert event['reused_chunks'] <= event['successful_chunks']
    third_calls = []
    make_service(tmp_path, monkeypatch, calls=third_calls).run()
    assert third_calls == [0, 1, 2, 3]


def test_more_than_twenty_full_results_resume_past_chunk_cap(tmp_path, monkeypatch):
    first = make_service(tmp_path, monkeypatch, count=30)
    first.MAX_LLM_CHUNKS = 25
    first_result = first.run()
    assert first_result['status'] == 'partial' and len(first_result['entries']) == 25
    assert len(first.progress.snapshot()['candidates']) == 20
    calls = []
    second = make_service(tmp_path, monkeypatch, count=30, calls=calls)
    second.MAX_LLM_CHUNKS = 25
    final = second.run()
    assert calls == list(range(25, 30))
    assert final['reused_chunks'] == 25 and final['requested_chunks'] == 5
    assert len(final['entries']) == 30 and final['status'] == 'completed'


@pytest.mark.parametrize('change', ['source', 'model', 'endpoint', 'thinking', 'mode', 'project', 'semantics'])
def test_request_model_mode_or_project_mismatch_never_reuses(tmp_path, monkeypatch, change):
    first = make_service(tmp_path, monkeypatch)
    first.MAX_LLM_CHUNKS = 1
    first.run()
    kwargs, platform = {}, copy.deepcopy(PLATFORM)
    if change == 'source':
        kwargs['suffix'] = ' Changed source.'
    elif change == 'model':
        platform['model'] = 'other'
    elif change == 'endpoint':
        platform['api_url'] = 'https://another.invalid'
    elif change == 'thinking':
        platform['thinking'] = {'level': 'LOW'}
    elif change == 'mode':
        kwargs['character_only'] = True
    elif change == 'project':
        kwargs['game'] = 'second-game'
    elif change == 'semantics':
        monkeypatch.setattr(checkpoint, 'SEMANTICS_VERSION', 999)
    calls = []
    result = make_service(tmp_path, monkeypatch, calls=calls, platform=platform, **kwargs).run()
    assert calls == [0, 1, 2, 3] and result['reused_chunks'] == 0


@pytest.mark.parametrize('options', [{'force': True}, {'resume': False}])
def test_force_or_resume_false_starts_from_scratch(tmp_path, monkeypatch, options):
    first = make_service(tmp_path, monkeypatch)
    first.MAX_LLM_CHUNKS = 1
    first.run()
    calls = []
    result = make_service(tmp_path, monkeypatch, calls=calls, **options).run()
    assert calls == [0, 1, 2, 3] and result['reused_chunks'] == 0


def test_forged_cached_source_is_revalidated_against_current_chunk(tmp_path, monkeypatch):
    first = make_service(tmp_path, monkeypatch)
    first.MAX_LLM_CHUNKS = 1
    first.run()
    path = first._checkpoint.path
    data = json.loads(path.read_text(encoding='utf-8'))
    record = data['successes']['0']
    record['entries'][0]['source'] = '../forged.rpy'
    record['digest'] = checkpoint.digest(record['entries'])
    path.write_text(json.dumps(data), encoding='utf-8')
    calls, events = [], []
    final = make_service(tmp_path, monkeypatch, calls=calls, events=events.append).run()
    assert calls == [0, 1, 2, 3] and final['reused_chunks'] == 0
    assert 'invalid_results' in final['checkpoint_diagnostics']
    assert any(event.get('checkpoint_status') == 'corrupt' and not event['resume_available'] for event in events)


def test_cancellation_retains_only_coordinator_committed_successes(tmp_path, monkeypatch):
    cancelled, events = threading.Event(), []
    def progress(event):
        events.append(copy.deepcopy(event))
        if event['completed_chunks'] >= 1:
            cancelled.set()
    first = make_service(tmp_path, monkeypatch, events=progress, cancel_callback=cancelled.is_set)
    with pytest.raises(InterruptedError):
        first.run()
    frozen = copy.deepcopy(events)
    data = json.loads(first._checkpoint.path.read_text(encoding='utf-8'))
    assert set(data['successes']) == {'0'}
    calls = []
    second = make_service(tmp_path, monkeypatch, calls=calls)
    final = second.run()
    assert calls == [1, 2, 3] and final['reused_chunks'] == 1
    assert events == frozen


def test_timeout_and_late_result_cannot_modify_resumed_checkpoint(tmp_path, monkeypatch):
    release = threading.Event()
    def blocked():
        release.wait(2)
        return 'candidate'
    first = make_service(tmp_path, monkeypatch, count=2, behavior={0: blocked})
    first.CHUNK_CONCURRENCY = 2
    first.CHUNK_TIMEOUT_SECONDS = 0.08
    try:
        result = first.run()
        assert result['status'] == 'partial' and result['resume_available']
        calls = []
        second = make_service(tmp_path, monkeypatch, count=2, calls=calls)
        final = second.run()
        assert calls == [0] and final['reused_chunks'] == 1
        snapshot = second._checkpoint.path.read_bytes()
        release.set()
        time.sleep(0.12)
        assert second._checkpoint.path.read_bytes() == snapshot
    finally:
        release.set()


def test_only_coordinator_saves_and_no_prompt_or_credential_is_written(tmp_path, monkeypatch):
    owner = threading.get_ident()
    observed = []
    original = checkpoint.ExtractionCheckpoint.save
    def save(self, index, entries):
        observed.append(threading.get_ident())
        return original(self, index, entries)
    monkeypatch.setattr(checkpoint.ExtractionCheckpoint, 'save', save)
    service = make_service(tmp_path, monkeypatch)
    service.CHUNK_CONCURRENCY = 3
    service.run()
    assert observed and set(observed) == {owner}
    text = service._checkpoint.path.read_text(encoding='utf-8')
    assert PLATFORM['api_key'] not in text and PLATFORM['api_url'] not in text
    assert '你是' not in text and '输入：' not in text and 'reasoning' not in text
    assert str(tmp_path) not in text


def test_api_key_rotation_does_not_invalidate_semantic_fingerprint():
    other = {**PLATFORM, 'api_key': 'ROTATED-SECRET'}
    assert checkpoint.semantic_fingerprint(PLATFORM, 100) == checkpoint.semantic_fingerprint(other, 100)


def test_default_direct_service_does_not_create_global_cache(tmp_path, monkeypatch):
    configured = make_service(tmp_path, monkeypatch)
    service = GlossaryCandidateService(config=SimpleNamespace(), target_path=tmp_path / 'game', platform=PLATFORM)
    service._collect_corpus = configured._collect_corpus
    service._build_chunks = configured._build_chunks
    assert service.checkpoint_enabled is False
    def forbidden():
        raise AssertionError('Default direct calls must not resolve software storage')
    monkeypatch.setattr(checkpoint, 'default_checkpoint_root', forbidden)
    result = service.run()
    assert result['status'] == 'completed'
    assert result['resume_available'] is False and result['checkpoint_diagnostics'] == ['disabled']


def test_independent_processes_merge_successes_without_lost_updates(tmp_path):
    original = store(tmp_path, count=4)
    original.begin()
    code = '''
import sys
import importlib.util
spec = importlib.util.spec_from_file_location('checkpoint_test_child', sys.argv[-1])
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
ExtractionCheckpoint, digest = module.ExtractionCheckpoint, module.digest
_file_lock = module._file_lock
s = ExtractionCheckpoint(project=sys.argv[2], mode='glossary', model_hash='model', chunk_keys=[digest(i) for i in range(4)], root=sys.argv[1])
s.begin()
assert s.save(int(sys.argv[3]), []) == []
'''
    children = [subprocess.Popen([sys.executable, '-c', code, str(tmp_path / 'cache'), str(tmp_path / 'game'), str(index), str(checkpoint.__file__)],
        cwd=str(Path(__file__).resolve().parents[2]), stdout=subprocess.PIPE, stderr=subprocess.PIPE) for index in range(4)]
    try:
        for child in children:
            out, err = child.communicate(timeout=10)
            assert child.returncode == 0, err.decode(errors='replace')
    finally:
        for child in children:
            if child.poll() is None:
                child.kill()
                child.communicate(timeout=5)
    assert store(tmp_path, count=4).begin() == {0: [], 1: [], 2: [], 3: []}


def test_busy_checkpoint_lock_falls_back_with_bounded_wait(tmp_path, monkeypatch):
    cache = store(tmp_path)
    cache.begin()
    monkeypatch.setattr(checkpoint, 'LOCK_TIMEOUT_SECONDS', 0.05)
    lock = checkpoint._LOCKS[str(cache.lock_path.resolve())]
    lock.acquire()
    started = time.monotonic()
    try:
        assert cache.save(0, []) is None
    finally:
        lock.release()
    assert time.monotonic() - started < 0.5
    assert cache.status == 'unavailable' and cache.diagnostics == ['busy']
    assert cache.metadata()['resume_available'] is False



@pytest.mark.parametrize('field,value', [
    ('src', ' '), ('src', chr(9)), ('src', ' Name0'), ('src', 'Name0 '),
    ('src', chr(34) + 'Name0' + chr(34)), ('src', '{i}Name0{/i}'), ('src', 'Name0.'),
    ('src', 'Name0  spoke.'), ('evidence', ''), ('evidence', ' '), ('evidence', 'spoke.'),
])
def test_noncanonical_cache_rows_are_retried_as_whole_chunks(tmp_path, monkeypatch, field, value):
    suffix = ' ' + chr(34) + 'Name0' + chr(34) + ' {i}Name0{/i} Name0. Name0  spoke.'
    first = make_service(tmp_path, monkeypatch, count=2, suffix=suffix)
    first.MAX_LLM_CHUNKS = 1
    first.run()
    data = json.loads(first._checkpoint.path.read_text(encoding='utf-8'))
    record = data['successes']['0']
    record['entries'][0][field] = value
    record['digest'] = checkpoint.digest(record['entries'])
    first._checkpoint.path.write_text(json.dumps(data), encoding='utf-8')
    calls, events = [], []
    final = make_service(tmp_path, monkeypatch, count=2, suffix=suffix, calls=calls, events=events.append).run()
    assert calls == [0, 1] and final['reused_chunks'] == 0
    assert final['status'] == 'completed'
    assert {entry['src'] for entry in final['entries']} == {'Name0', 'Name1'}
    assert final['checkpoint_diagnostics']
    assert any(event.get('checkpoint_status') == 'corrupt' and not event['resume_available'] for event in events)


@pytest.mark.parametrize('name', ['N' * 35, 'N' * 50, '[Archivist]'])
def test_legal_grounded_names_keep_truncated_evidence_on_resume(tmp_path, monkeypatch, name):
    names, prefix = {0: name}, 'An unrelated sufficiently long prefix '
    first = make_service(tmp_path, monkeypatch, count=2, names=names, prefix=prefix)
    first.MAX_LLM_CHUNKS = 1
    first.run()
    data = json.loads(first._checkpoint.path.read_text(encoding='utf-8'))
    evidence = data['successes']['0']['entries'][0]['evidence']
    if len(name) >= 35:
        assert name not in evidence and len(evidence) <= 40
    calls = []
    final = make_service(tmp_path, monkeypatch, count=2, names=names, prefix=prefix, calls=calls).run()
    assert calls == [1] and final['reused_chunks'] == 1
    assert {entry['src'] for entry in final['entries']} == {name, 'Name1'}
    assert final['checkpoint_diagnostics'] == []


def test_invalid_fresh_rows_never_become_successful_empty_checkpoint(tmp_path, monkeypatch):
    first = make_service(tmp_path, monkeypatch, count=1)
    first._request_chunk = lambda index, chunk, requester: (True, [row('Name0', 11), row(' ', 11)])
    result = first.run()
    data = json.loads(first._checkpoint.path.read_text(encoding='utf-8'))
    assert result['status'] == 'failed' and result['llm_chunks_failed'] == 1
    assert data['successes'] == {} and not data['complete']
    calls = []
    final = make_service(tmp_path, monkeypatch, count=1, calls=calls).run()
    assert calls == [0] and final['reused_chunks'] == 0
    assert [entry['src'] for entry in final['entries']] == ['Name0']


def test_unknown_checkpoint_fields_are_not_carried_into_new_writes(tmp_path):
    first = store(tmp_path)
    first.begin()
    first.save(0, [])
    data = json.loads(first.path.read_text(encoding='utf-8'))
    data['prompt'] = 'Unexpected source or secret content'
    first.path.write_text(json.dumps(data), encoding='utf-8')
    second = store(tmp_path)
    assert second.begin() == {} and second.status == 'corrupt'
    assert 'Unexpected source or secret content' not in second.path.read_text(encoding='utf-8')

