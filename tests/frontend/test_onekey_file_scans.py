import os
import threading
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QApplication, QPushButton

import frontend.RenpyToolbox.OneKeyTranslatePage as page_module
from module.Config import Config


APP = QApplication.instance() or QApplication([])


def wait_until(predicate):
    deadline = time.monotonic() + 5
    while not predicate() and time.monotonic() < deadline:
        APP.processEvents()
        time.sleep(0.005)
    assert predicate()


@pytest.fixture
def scan_page(tmp_path, monkeypatch):
    config = Config()
    config.renpy_project_path = config.renpy_game_folder = ""
    config.input_folder = config.output_folder = ""
    config.platforms = []
    monkeypatch.setattr(Config, "load", lambda *args, **kwargs: config)
    monkeypatch.setattr(Config, "save", lambda *args: None)
    monkeypatch.setattr(page_module.ProjectStore, "_emit_changed", lambda *args: None)
    for level in ("warning", "error", "success"):
        monkeypatch.setattr(page_module.InfoBar, level, lambda *args, **kwargs: None)
    page = page_module.YiJianFanyiPage()
    root = tmp_path / "project"
    tl = root / "game" / "tl" / "chinese"
    tl.mkdir(parents=True)
    (tl / "old.rpy").touch()
    page.game_path_edit.setText(str(root))
    page._old_translation_scan_timer.stop()
    try:
        yield page, root
    finally:
        page._invalidate_old_translation_scan()
        for worker in (page._old_translation_scan_worker, page._apply_scan_worker):
            if worker is not None:
                worker.requestInterruption()
                assert worker.wait(5000)
        APP.processEvents()
        page.close()
        page.deleteLater()
        APP.processEvents()


def hold_scan(monkeypatch):
    entered, release = threading.Event(), threading.Event()
    caller_threads = []
    real_walk = os.walk

    def delayed_walk(*args, **kwargs):
        caller_threads.append(threading.get_ident())
        entered.set()
        assert release.wait(5), "test must release the background scan"
        yield from real_walk(*args, **kwargs)

    monkeypatch.setattr("frontend.RenpyToolbox.OneKeyWorkers.os.walk", delayed_walk)
    return entered, release, caller_threads


def test_game_status_scan_keeps_gui_responsive(tmp_path, monkeypatch):
    from frontend.RenpyToolbox.OneKeyWorkers import GameStatusWorker

    root = tmp_path / "project"
    game = root / "game"
    game.mkdir(parents=True)
    (game / "script.rpy").write_text("label start:\n    pass\n", encoding="utf-8")
    entered, release, threads = hold_scan(monkeypatch)
    results = []
    worker = GameStatusWorker(str(root), "chinese")
    worker.result_ready.connect(results.append)
    try:
        worker.start()
        assert entered.wait(2)
        heartbeat = []
        QTimer.singleShot(0, lambda: heartbeat.append(True))
        wait_until(lambda: bool(heartbeat))
        assert threads[0] != threading.get_ident()
        release.set()
        wait_until(lambda: bool(results))
        assert len(results) == 1
        assert results[0]["status"] == "ready"
    finally:
        release.set()
        if worker.isRunning():
            worker.requestInterruption()
        assert worker.wait(5000)
        worker.deleteLater()


def test_game_status_scan_can_be_cancelled_without_result(tmp_path, monkeypatch):
    from frontend.RenpyToolbox.OneKeyWorkers import GameStatusWorker

    root = tmp_path / "project"
    (root / "game").mkdir(parents=True)
    entered, release, _threads = hold_scan(monkeypatch)
    results = []
    worker = GameStatusWorker(str(root), "chinese")
    worker.result_ready.connect(results.append)
    try:
        worker.start()
        assert entered.wait(2)
        worker.requestInterruption()
        release.set()
        assert worker.wait(5000)
        APP.processEvents()
        assert results == [{"status": "cancelled", "message": ""}]
    finally:
        release.set()
        if worker.isRunning():
            worker.requestInterruption()
            assert worker.wait(5000)
        worker.deleteLater()


def test_old_translation_count_keeps_gui_responsive(scan_page, monkeypatch):
    page, root = scan_page
    tl = root / "game" / "tl" / "chinese"
    nested = tl / "chapter"
    nested.mkdir()
    (nested / "extra.rpy").touch()
    (nested / "cached.rpyc").touch()
    entered, release, threads = hold_scan(monkeypatch)
    heartbeat = []
    try:
        page._start_old_translation_scan()
        assert entered.wait(2)
        QTimer.singleShot(0, lambda: heartbeat.append(True))
        wait_until(lambda: bool(heartbeat))
        assert page.has_old_translation
        assert page.incremental_rb.isChecked()
        assert threads[0] != threading.get_ident()
        # A late count must not reset a user's full-extraction selection.
        page.full_extract_rb.setChecked(True)
        release.set()
        wait_until(lambda: page._old_translation_scan_worker is None)
        assert "2" in page.old_trans_title.text()
        assert page.full_extract_rb.isChecked()
    finally:
        release.set()


@pytest.mark.parametrize("change", ["empty", "language"])
def test_old_translation_count_drops_stale_results(scan_page, monkeypatch, change):
    page, _root = scan_page
    entered, release, _threads = hold_scan(monkeypatch)
    try:
        page._start_old_translation_scan()
        assert entered.wait(2)
        if change == "empty":
            page.game_path_edit.clear()
        else:
            page.tl_folder_edit.setText("japanese")
        page.old_trans_title.setText("current project")
        release.set()
        wait_until(lambda: page._old_translation_scan_worker is None)
        assert page.old_trans_title.text() == "current project"
        assert not page.has_old_translation
        assert page.skip_extract_btn.isHidden()
    finally:
        release.set()


@pytest.mark.parametrize("action", ["complete", "cancel", "switch", "empty"])
def test_apply_preflight_scans_off_thread_and_rejects_stale_results(
    scan_page, monkeypatch, action,
):
    page, root = scan_page
    output = root / "RenpyBox_Translation" / "chinese"
    output.mkdir(parents=True, exist_ok=True)
    translated = output / "result.rpy"
    translated.touch()
    confirmed = []
    monkeypatch.setattr(page, "_confirm_apply_translation", lambda context, files: confirmed.append((context, files)))
    entered, release, threads = hold_scan(monkeypatch)
    card = QPushButton()
    try:
        page._tool_apply_translation(card)
        worker = page._apply_scan_worker
        assert entered.wait(2)
        assert not card.isEnabled()
        heartbeat = []
        QTimer.singleShot(0, lambda: heartbeat.append(True))
        wait_until(lambda: bool(heartbeat))
        page._tool_apply_translation(card)
        assert page._apply_scan_worker is worker
        assert len(threads) == 1 and threads[0] != threading.get_ident()
        if action == "cancel":
            worker.scan_dialog.cancel()
        elif action == "switch":
            page._onekey_project_key = "another-project"
        elif action == "empty":
            page.game_path_edit.clear()
        release.set()
        wait_until(lambda: not page._apply_preflight_running)
        assert card.isEnabled()
        assert page._apply_scan_worker is None
        if action == "complete":
            assert len(confirmed) == 1
            assert confirmed[0][1] == [translated]
            assert confirmed[0][0]["input_dir"] == root / "game" / "tl" / "chinese"
        else:
            assert not confirmed
    finally:
        release.set()


def test_scan_error_is_not_reported_as_empty_success(tmp_path, monkeypatch):
    from frontend.RenpyToolbox.OneKeyWorkers import TranslationFileScanWorker

    def denied(directory, *, onerror):
        onerror(PermissionError("directory unavailable"))
        return iter(())

    monkeypatch.setattr("frontend.RenpyToolbox.OneKeyWorkers.os.walk", denied)
    worker = TranslationFileScanWorker(tmp_path, collect_files=True)
    worker.run()
    assert worker.error == "directory unavailable"
    assert worker.files == []
    worker.deleteLater()
