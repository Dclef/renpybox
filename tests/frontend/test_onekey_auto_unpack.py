import os
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt5.QtGui import QHideEvent
from PyQt5.QtWidgets import QApplication

import frontend.RenpyToolbox.OneKeyTranslatePage as page_module
from frontend.RenpyToolbox.OneKeyTranslatePage import YiJianFanyiPage
from module.Config import Config
from module.Renpy.ProjectPaths import RenpyProjectPaths, apply_to_config


APP = QApplication.instance() or QApplication([])


class _SignalStub:
    def __init__(self) -> None:
        self.connections = []

    def connect(self, fn) -> None:
        self.connections.append(fn)

    def emit(self, *args) -> None:
        for callback in list(self.connections):
            callback(*args)


class _UnpackWorkerStub:
    started: list["_UnpackWorkerStub"] = []

    def __init__(self, game_dir: str, *, direct: bool, script_only: bool):
        self.progress = _SignalStub()
        self.finished = _SignalStub()
        self.game_dir = game_dir
        self.direct = direct
        self.script_only = script_only
        self.running = False

    def start(self) -> None:
        self.running = True
        self.started.append(self)

    def isRunning(self) -> bool:
        return self.running

    def complete(self, result: dict) -> None:
        self.running = False
        self.finished.emit(result)


class _DecompileWorkerStub:
    started: list["_DecompileWorkerStub"] = []

    def __init__(
        self,
        target: str,
        *,
        overwrite: bool,
        fallback_unren_options: str | None,
        use_unren: bool,
    ):
        self.progress = _SignalStub()
        self.finished = _SignalStub()
        self.target = target
        self.overwrite = overwrite
        self.fallback_unren_options = fallback_unren_options
        self.use_unren = use_unren
        self.running = False

    def start(self) -> None:
        self.running = True
        self.started.append(self)

    def isRunning(self) -> bool:
        return self.running

    def complete(self, result: dict) -> None:
        self.running = False
        self.finished.emit(result)


class _GameStatusWorkerStub:
    started: list["_GameStatusWorkerStub"] = []

    def __init__(self, game_dir: str, tl_name: str):
        self.result_ready = _SignalStub()
        self.finished = _SignalStub()
        self.game_dir = game_dir
        self.tl_name = tl_name
        self.running = False
        self.interrupted = False

    def start(self) -> None:
        self.running = True
        self.started.append(self)

    def isRunning(self) -> bool:
        return self.running

    def requestInterruption(self) -> None:
        self.interrupted = True

    def isInterruptionRequested(self) -> bool:
        return self.interrupted

    def deleteLater(self) -> None:
        pass

    def complete(self, status: str, message: str) -> None:
        self.running = False
        self.result_ready.emit({"status": status, "message": message})


class _ExtractionWorkerStub:
    started: list["_ExtractionWorkerStub"] = []

    def __init__(self, extractor, game_dir, tl_name, exe_path, incremental=False):
        self.progress = _SignalStub()
        self.finished = _SignalStub()
        self.game_dir = game_dir
        self.tl_name = tl_name
        self.exe_path = exe_path
        self.incremental = incremental
        self.running = False

    def start(self) -> None:
        self.running = True
        self.started.append(self)

    def isRunning(self) -> bool:
        return self.running


def _config_for(root: Path, language: str = "chinese") -> Config:
    paths = RenpyProjectPaths.from_path(root, language)
    assert paths is not None
    config = Config()
    apply_to_config(config, paths)
    return config


def _make_page(root: Path, language: str = "chinese") -> YiJianFanyiPage:
    page = YiJianFanyiPage()
    page.tl_folder_edit.setText(language)
    page.game_dir = str(root)
    page.game_path = str(root)
    return page


def _patch_workers(monkeypatch) -> None:
    for worker_type in (
        _UnpackWorkerStub,
        _DecompileWorkerStub,
        _GameStatusWorkerStub,
        _ExtractionWorkerStub,
    ):
        worker_type.started.clear()
    monkeypatch.setattr(page_module, "UnpackWorker", _UnpackWorkerStub)
    monkeypatch.setattr(page_module, "DecompileWorker", _DecompileWorkerStub)
    monkeypatch.setattr(page_module, "GameStatusWorker", _GameStatusWorkerStub)
    monkeypatch.setattr(page_module, "ExtractionWorker", _ExtractionWorkerStub)


def _quiet_info_bars(monkeypatch) -> list[str]:
    messages: list[str] = []
    monkeypatch.setattr(
        page_module,
        "InfoBar",
        SimpleNamespace(
            success=lambda *args, **kwargs: messages.append("success"),
            info=lambda *args, **kwargs: messages.append("info"),
            warning=lambda *args, **kwargs: messages.append("warning"),
            error=lambda *args, **kwargs: messages.append("error"),
        ),
    )
    return messages


def _success(message: str) -> dict:
    return {"level": "success", "title": "完成", "message": message}


def _failure(message: str) -> dict:
    return {"level": "error", "title": "错误", "message": message}


def test_detect_game_status_ignores_translated_rpy_files(tmp_path) -> None:
    root = tmp_path / "Project"
    (root / "game" / "tl" / "chinese").mkdir(parents=True)
    (root / "game" / "tl" / "chinese" / "script.rpy").write_text(
        "translate chinese start:\n    pass\n",
        encoding="utf-8",
    )
    (root / "game" / "script.rpa").write_bytes(b"RPA-3.0")
    page = _make_page(root)
    try:
        status, _message = page._detect_game_status(str(root))
    finally:
        page.deleteLater()

    assert status == "need_unpack"


@pytest.mark.parametrize(
    ("suffix", "expected"),
    [
        (".rpy", "ready"),
        (".rpyc", "need_decompile"),
    ],
)
def test_detect_game_status_uses_only_source_scripts(
    tmp_path,
    suffix,
    expected,
) -> None:
    root = tmp_path / "Project"
    (root / "game").mkdir(parents=True)
    (root / "game" / f"script{suffix}").write_bytes(b"script")
    (root / "game" / "script.rpa").write_bytes(b"RPA-3.0")
    page = _make_page(root)
    try:
        status, _message = page._detect_game_status(str(root))
    finally:
        page.deleteLater()

    assert status == expected


def test_detect_game_status_decompiles_mixed_source_scripts(tmp_path) -> None:
    root = tmp_path / "Project"
    (root / "game").mkdir(parents=True)
    (root / "game" / "script.rpy").write_text("label start:\n    pass\n", encoding="utf-8")
    (root / "game" / "extra.rpyc").write_bytes(b"compiled")
    page = _make_page(root)
    try:
        status, _message = page._detect_game_status(str(root))
    finally:
        page.deleteLater()

    assert status == "need_decompile"


def test_go_step2_starts_unpack_in_background_then_extracts(monkeypatch, tmp_path) -> None:
    root = tmp_path / "Project"
    (root / "game").mkdir(parents=True)
    config = _config_for(root)
    monkeypatch.setattr(page_module.Config, "load", lambda self, path=None: config)
    _patch_workers(monkeypatch)
    messages = _quiet_info_bars(monkeypatch)

    page = _make_page(root)
    try:
        page._go_step2()
        generation = page._extraction_generation

        assert len(_GameStatusWorkerStub.started) == 1
        assert _UnpackWorkerStub.started == []
        _GameStatusWorkerStub.started[0].complete("need_unpack", "有 RPA")
        assert len(_UnpackWorkerStub.started) == 1
        assert _ExtractionWorkerStub.started == []
        unpack = _UnpackWorkerStub.started[0]
        assert unpack.game_dir == str(root / "game")
        assert unpack.direct is True
        assert unpack.script_only is False

        unpack.complete(_success("已解包"))

        assert len(_GameStatusWorkerStub.started) == 2
        _GameStatusWorkerStub.started[1].complete("ready", "有 RPY")
        assert page._extraction_generation == generation
        assert len(_ExtractionWorkerStub.started) == 1
        extraction = _ExtractionWorkerStub.started[0]
        assert extraction.game_dir == str(root)
        assert extraction.tl_name == "chinese"
        assert extraction.incremental is False
        assert messages == []
    finally:
        page.deleteLater()


def test_go_step2_chains_unpack_decompile_and_extract(monkeypatch, tmp_path) -> None:
    root = tmp_path / "Project"
    (root / "game").mkdir(parents=True)
    config = _config_for(root)
    monkeypatch.setattr(page_module.Config, "load", lambda self, path=None: config)
    _patch_workers(monkeypatch)
    _quiet_info_bars(monkeypatch)

    page = _make_page(root)
    try:
        page._go_step2()
        generation = page._extraction_generation
        _GameStatusWorkerStub.started[0].complete("need_unpack", "有 RPA")
        _UnpackWorkerStub.started[0].complete(_success("已解包"))

        _GameStatusWorkerStub.started[1].complete("need_decompile", "有 RPYC")
        assert len(_DecompileWorkerStub.started) == 1
        assert _ExtractionWorkerStub.started == []
        decompile = _DecompileWorkerStub.started[0]
        assert decompile.target == str(root)
        assert decompile.overwrite is False
        assert decompile.fallback_unren_options == "2x"
        assert decompile.use_unren is True

        decompile.complete(_success("反编译完成"))

        _GameStatusWorkerStub.started[2].complete("ready", "有 RPY")
        assert page._extraction_generation == generation
        assert len(_ExtractionWorkerStub.started) == 1
    finally:
        page.deleteLater()


def test_go_step2_shows_manual_fallback_when_unpack_fails(monkeypatch, tmp_path) -> None:
    root = tmp_path / "Project"
    (root / "game").mkdir(parents=True)
    config = _config_for(root)
    monkeypatch.setattr(page_module.Config, "load", lambda self, path=None: config)
    _patch_workers(monkeypatch)
    messages = _quiet_info_bars(monkeypatch)

    page = _make_page(root)
    try:
        page._go_step2()
        _GameStatusWorkerStub.started[0].complete("need_unpack", "有 RPA")
        _UnpackWorkerStub.started[0].complete(_failure("boom"))

        assert _ExtractionWorkerStub.started == []
        assert not page.step2_unpack_btn.isHidden()
        assert page.step2_unpack_btn.isEnabled()
        assert not page.step2_retry_btn.isHidden()
        assert not page.step2_skip_btn.isHidden()
        assert "boom" in page.step2_desc.text()
        assert messages == ["warning"]
    finally:
        page.deleteLater()


def test_go_step2_shows_retry_when_decompile_fails(monkeypatch, tmp_path) -> None:
    root = tmp_path / "Project"
    (root / "game").mkdir(parents=True)
    config = _config_for(root)
    monkeypatch.setattr(page_module.Config, "load", lambda self, path=None: config)
    _patch_workers(monkeypatch)
    messages = _quiet_info_bars(monkeypatch)

    page = _make_page(root)
    try:
        page._go_step2()
        _GameStatusWorkerStub.started[0].complete("need_decompile", "有 RPYC")
        _DecompileWorkerStub.started[0].complete(_failure("boom"))

        assert _ExtractionWorkerStub.started == []
        assert not page.step2_retry_btn.isHidden()
        assert not page.step2_skip_btn.isHidden()
        assert "boom" in page.step2_desc.text()
        assert messages == ["warning"]
    finally:
        page.deleteLater()


def test_go_step2_fails_when_unpack_leaves_no_scripts(monkeypatch, tmp_path) -> None:
    root = tmp_path / "Project"
    (root / "game").mkdir(parents=True)
    config = _config_for(root)
    monkeypatch.setattr(page_module.Config, "load", lambda self, path=None: config)
    _patch_workers(monkeypatch)
    messages = _quiet_info_bars(monkeypatch)

    page = _make_page(root)
    try:
        page._go_step2()
        _GameStatusWorkerStub.started[0].complete("need_unpack", "有 RPA")
        _UnpackWorkerStub.started[0].complete(_success("已解包"))

        _GameStatusWorkerStub.started[1].complete("empty", "没有脚本")
        assert _ExtractionWorkerStub.started == []
        assert not page.step2_unpack_btn.isHidden()
        assert not page.step2_retry_btn.isHidden()
        assert not page.step2_skip_btn.isHidden()
        assert ".rpy" in page.step2_desc.text()
        assert messages == ["warning"]
    finally:
        page.deleteLater()


def test_old_preprocess_result_is_ignored_after_page_leaves(monkeypatch, tmp_path) -> None:
    root = tmp_path / "Project"
    (root / "game").mkdir(parents=True)
    config = _config_for(root)
    monkeypatch.setattr(page_module.Config, "load", lambda self, path=None: config)
    _patch_workers(monkeypatch)
    _quiet_info_bars(monkeypatch)

    page = _make_page(root)
    try:
        page._go_step2()
        status_worker = _GameStatusWorkerStub.started[0]
        page.hideEvent(QHideEvent())
        assert status_worker.interrupted is True
        status_worker.complete("need_unpack", "有 RPA")

        assert _UnpackWorkerStub.started == []
        assert _DecompileWorkerStub.started == []
        assert _ExtractionWorkerStub.started == []
    finally:
        page.deleteLater()


def test_status_scan_is_cancelled_when_language_changes(monkeypatch, tmp_path) -> None:
    root = tmp_path / "Project"
    (root / "game").mkdir(parents=True)
    config = _config_for(root)
    monkeypatch.setattr(page_module.Config, "load", lambda self, path=None: config)
    _patch_workers(monkeypatch)
    _quiet_info_bars(monkeypatch)

    page = _make_page(root)
    try:
        page._go_step2()
        status_worker = _GameStatusWorkerStub.started[0]
        page.tl_folder_edit.setText("japanese")
        assert status_worker.interrupted is True
        status_worker.complete("need_unpack", "旧项目结果")

        assert _UnpackWorkerStub.started == []
        assert _ExtractionWorkerStub.started == []
    finally:
        page.deleteLater()


def test_cancel_status_scan_restores_retry_state(monkeypatch, tmp_path) -> None:
    root = tmp_path / "Project"
    (root / "game").mkdir(parents=True)
    config = _config_for(root)
    monkeypatch.setattr(page_module.Config, "load", lambda self, path=None: config)
    _patch_workers(monkeypatch)
    _quiet_info_bars(monkeypatch)

    page = _make_page(root)
    try:
        page._go_step2()
        status_worker = _GameStatusWorkerStub.started[0]
        page._cancel_extraction()

        assert status_worker.interrupted is True
        assert page.step2_cancel_btn.isEnabled() is False
        status_worker.complete("cancelled", "")

        assert page.step2_page.progress_ring.isHidden()
        assert page.step2_cancel_btn.isHidden()
        assert page.step2_cancel_btn.isEnabled() is True
        assert not page.step2_retry_btn.isHidden()
        assert not page.step2_skip_btn.isHidden()
    finally:
        page.deleteLater()


@pytest.mark.parametrize("navigate", ["previous", "indicator"])
def test_navigation_waits_for_status_scan(monkeypatch, tmp_path, navigate) -> None:
    root = tmp_path / "Project"
    (root / "game").mkdir(parents=True)
    config = _config_for(root)
    monkeypatch.setattr(page_module.Config, "load", lambda self, path=None: config)
    _patch_workers(monkeypatch)
    messages = _quiet_info_bars(monkeypatch)

    page = _make_page(root)
    try:
        page._go_step2()
        status_worker = _GameStatusWorkerStub.started[0]
        if navigate == "previous":
            page._go_previous_step(2)
        else:
            page._on_step_indicator_clicked(1)

        assert page.current_step == 2
        assert status_worker.interrupted is False
        assert messages == ["warning"]
    finally:
        page.hideEvent(QHideEvent())
        page.deleteLater()


def test_late_status_result_from_replaced_worker_is_ignored(monkeypatch, tmp_path) -> None:
    root = tmp_path / "Project"
    (root / "game").mkdir(parents=True)
    config = _config_for(root)
    paths = RenpyProjectPaths.from_path(root, "chinese")
    assert paths is not None
    monkeypatch.setattr(page_module.Config, "load", lambda self, path=None: config)
    _patch_workers(monkeypatch)
    _quiet_info_bars(monkeypatch)

    page = _make_page(root)
    try:
        page._go_step2()
        first = _GameStatusWorkerStub.started[0]
        first.running = False
        context = {
            "game_dir": str(root),
            "language": "chinese",
            "project_key": paths.project_key,
            "exe_path": root,
            "incremental": False,
        }
        page._start_status_scan(page._extraction_generation, context)
        second = _GameStatusWorkerStub.started[1]

        first.complete("need_unpack", "旧扫描结果")
        assert _UnpackWorkerStub.started == []
        second.complete("ready", "当前扫描结果")
        assert len(_ExtractionWorkerStub.started) == 1
    finally:
        page.hideEvent(QHideEvent())
        page.deleteLater()


def test_old_preprocess_result_is_ignored_after_config_switch(monkeypatch, tmp_path) -> None:
    root = tmp_path / "ProjectA"
    other = tmp_path / "ProjectB"
    (root / "game").mkdir(parents=True)
    (other / "game").mkdir(parents=True)
    current = {"config": _config_for(root)}
    monkeypatch.setattr(
        page_module.Config,
        "load",
        lambda self, path=None: current["config"],
    )
    _patch_workers(monkeypatch)
    _quiet_info_bars(monkeypatch)

    page = _make_page(root)
    try:
        page._go_step2()
        _GameStatusWorkerStub.started[0].complete("need_unpack", "有 RPA")
        unpack = _UnpackWorkerStub.started[0]
        current["config"] = _config_for(other)
        unpack.complete(_success("旧项目已解包"))

        assert _DecompileWorkerStub.started == []
        assert _ExtractionWorkerStub.started == []
    finally:
        page.deleteLater()


def test_old_preprocess_result_is_ignored_after_page_project_switch(
    monkeypatch,
    tmp_path,
) -> None:
    root = tmp_path / "ProjectA"
    other = tmp_path / "ProjectB"
    (root / "game").mkdir(parents=True)
    (other / "game").mkdir(parents=True)
    config = _config_for(root)
    monkeypatch.setattr(page_module.Config, "load", lambda self, path=None: config)
    _patch_workers(monkeypatch)
    _quiet_info_bars(monkeypatch)

    page = _make_page(root)
    try:
        page._go_step2()
        _GameStatusWorkerStub.started[0].complete("need_unpack", "有 RPA")
        unpack = _UnpackWorkerStub.started[0]
        page.game_dir = str(other)
        page.game_path = str(other)
        unpack.complete(_success("旧项目已解包"))

        assert _DecompileWorkerStub.started == []
        assert _ExtractionWorkerStub.started == []
    finally:
        page.deleteLater()
