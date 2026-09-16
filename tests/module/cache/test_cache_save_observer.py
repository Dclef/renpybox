import threading

import pytest

from module.Cache.CacheItem import CacheItem
from module.Cache.CacheManager import CacheManager
from module.Cache.CacheProject import CacheProject


@pytest.mark.parametrize("use_sqlite", [False, True])
def test_successful_save_reports_only_cost_and_outcome(tmp_path, use_sqlite):
    manager = CacheManager(service = False)
    manager.cache_use_sqlite = use_sqlite
    observations = []
    manager.set_save_observer(observations.append)

    assert manager.save_to_file(
        CacheProject(), [CacheItem(src = "private source")], str(tmp_path), strict = True,
    ) is True

    assert len(observations) == 1
    assert observations[0].keys() == {
        "cache_save_count", "cache_save_error_count", "cache_save_ms",
    }
    assert observations[0]["cache_save_count"] == 1
    assert observations[0]["cache_save_error_count"] == 0
    assert observations[0]["cache_save_ms"] >= 0


def test_failed_save_reports_failure_without_changing_false_result():
    manager = CacheManager(service = False)
    observations = []
    manager.set_save_observer(observations.append)

    assert manager.save_to_file(CacheProject(), [], "") is False

    assert observations[0]["cache_save_error_count"] == 1


def test_strict_save_reports_failure_and_preserves_original_exception():
    manager = CacheManager(service = False)
    observations = []
    manager.set_save_observer(observations.append)

    with pytest.raises(ValueError):
        manager.save_to_file(CacheProject(), [], "", strict = True)

    assert observations[0]["cache_save_count"] == 1
    assert observations[0]["cache_save_error_count"] == 1


@pytest.mark.parametrize("strict", [False, True])
def test_observer_failure_does_not_replace_save_outcome(tmp_path, strict):
    manager = CacheManager(service = False)
    manager.cache_use_sqlite = False

    def broken_observer(payload):
        raise RuntimeError("observer failed")

    manager.set_save_observer(broken_observer)
    if strict:
        with pytest.raises(ValueError):
            manager.save_to_file(CacheProject(), [], "", strict = True)
    else:
        assert manager.save_to_file(CacheProject(), [], str(tmp_path)) is True


def test_old_save_uses_observer_captured_before_lock_wait(monkeypatch):
    manager = CacheManager(service = False)
    old_observations = []
    new_observations = []
    manager.set_save_observer(old_observations.append)
    entered = threading.Event()
    errors = []
    results = []

    def blocked_save(*args, **kwargs):
        entered.set()
        with manager.LOCK:
            return True

    monkeypatch.setattr(manager, "_save_to_file_impl", blocked_save)

    def save():
        try:
            results.append(manager.save_to_file(CacheProject(), [], "unused"))
        except BaseException as exc:
            errors.append(exc)

    with manager.LOCK:
        worker = threading.Thread(target = save)
        worker.start()
        assert entered.wait(timeout = 2)
        manager.set_save_observer(new_observations.append)
    worker.join(timeout = 2)

    assert not worker.is_alive()
    assert not errors
    assert results == [True]
    assert len(old_observations) == 1
    assert new_observations == []

    assert manager.save_to_file(CacheProject(), [], "unused") is True
    assert len(new_observations) == 1
    manager.set_save_observer(None)
    assert manager.save_to_file(CacheProject(), [], "unused") is True
    assert len(new_observations) == 1


def test_timing_includes_entire_save_impl_and_preserves_arguments(monkeypatch):
    manager = CacheManager(service = False)
    observations = []
    manager.set_save_observer(observations.append)
    clock_values = iter([10.0, 10.125])
    monkeypatch.setattr("module.Cache.CacheManager.time.perf_counter", lambda: next(clock_values))
    project = CacheProject()
    items = [CacheItem(src = "source")]
    calls = []

    def save_impl(actual_project, actual_items, actual_folder, *, strict = False):
        calls.append((actual_project, actual_items, actual_folder, strict))
        return True

    monkeypatch.setattr(manager, "_save_to_file_impl", save_impl)

    assert manager.save_to_file(project, items, " target ", strict = True) is True

    assert calls == [(project, items, " target ", True)]
    assert observations == [{
        "cache_save_count": 1,
        "cache_save_error_count": 0,
        "cache_save_ms": 125.0,
    }]
