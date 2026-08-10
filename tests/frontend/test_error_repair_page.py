import importlib
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

from frontend.RenpyToolbox.ErrorRepairPage import ErrorRepairPage


APP = QApplication.instance() or QApplication([])
error_page_module = importlib.import_module(
    "frontend.RenpyToolbox.ErrorRepairPage"
)


class _DeferredThread:
    instances = []

    def __init__(self, *, target, daemon: bool) -> None:
        self.target = target
        self.daemon = daemon
        self.started = False
        self.__class__.instances.append(self)

    def start(self) -> None:
        self.started = True

    def finish(self) -> None:
        self.target()
        APP.processEvents()


def _silence_info_bars(monkeypatch):
    messages = []

    def record(level):
        def callback(*args, **kwargs):
            messages.append((level, args, kwargs))
        return callback

    for level in ("info", "success", "warning", "error"):
        monkeypatch.setattr(error_page_module.InfoBar, level, record(level))
    return messages


def _new_page(monkeypatch) -> ErrorRepairPage:
    _silence_info_bars(monkeypatch)
    _DeferredThread.instances = []
    monkeypatch.setattr(error_page_module.threading, "Thread", _DeferredThread)
    return ErrorRepairPage("error-repair-test")


def test_page_removes_dead_encoding_option_and_gates_report_export(monkeypatch) -> None:
    messages = _silence_info_bars(monkeypatch)
    page = ErrorRepairPage("error-repair-test")

    assert not hasattr(page, "fix_encoding_check")
    assert not page.fix_quotes_check.isChecked()
    assert not page.fix_dialogue_quotes_check.isChecked()
    assert not page.export_report_button.isEnabled()

    page._export_report()

    assert messages[-1][0] == "warning"
    assert "先扫描" in messages[-1][1][1]
    page.close()


def test_scan_runs_in_worker_saves_report_and_blocks_duplicate_actions(
    tmp_path, monkeypatch
) -> None:
    game_dir = tmp_path / "game"
    game_dir.mkdir()
    report = {str(game_dir / "script.rpy"): [{"line": 3, "type": "quotes"}]}
    calls = []

    class FakeRepairer:
        def check_folder(self, path, **kwargs):
            calls.append((path, kwargs))
            return report

    page = _new_page(monkeypatch)
    monkeypatch.setattr(error_page_module, "ErrorRepairer", FakeRepairer)
    page.game_dir_edit.setText(str(game_dir))

    page._scan_errors()
    page._scan_errors()

    assert len(_DeferredThread.instances) == 1
    worker = _DeferredThread.instances[0]
    assert worker.started is True
    assert worker.daemon is True
    assert calls == []
    assert page._running_operation == "scan"
    assert not page.scan_button.isEnabled()
    assert not page.repair_button.isEnabled()
    assert not page.lint_check_button.isEnabled()
    assert not page.export_report_button.isEnabled()

    worker.finish()

    assert calls == [(
        str(game_dir),
        {
            "check_indent": True,
            "check_indent_level": False,
            "check_quotes": True,
            "check_dialogue_quotes": True,
            "encoding": "utf-8",
        },
    )]
    assert page._last_scan_report == report
    assert page._running_operation is None
    assert page.scan_button.isEnabled()
    assert page.repair_button.isEnabled()
    assert page.lint_check_button.isEnabled()
    assert page.export_report_button.isEnabled()
    page.close()


def test_auto_repair_runs_in_worker_with_snapshotted_options(tmp_path, monkeypatch) -> None:
    game_dir = tmp_path / "game"
    game_dir.mkdir()
    first = game_dir / "first.rpy"
    second = game_dir / "second.rpy"
    first.write_text("label start:\n", encoding="utf-8")
    second.write_text("label end:\n", encoding="utf-8")
    calls = []

    class FakeRepairer:
        def auto_fix_file(self, path, **kwargs):
            calls.append((Path(path).name, kwargs))
            return (True, 2) if Path(path).name == "first.rpy" else (False, 0)

    page = _new_page(monkeypatch)
    monkeypatch.setattr(error_page_module, "ErrorRepairer", FakeRepairer)
    page.game_dir_edit.setText(str(game_dir))
    page.fix_indent_check.setChecked(False)
    page.fix_indent_level_check.setChecked(True)
    page.fix_quotes_check.setChecked(True)
    page.fix_dialogue_quotes_check.setChecked(True)

    page._repair_errors()

    assert calls == []
    assert page._running_operation == "repair"
    assert len(_DeferredThread.instances) == 1

    # Later UI changes must not alter the options already handed to the task.
    page.fix_quotes_check.setChecked(False)
    _DeferredThread.instances[0].finish()

    assert {name for name, _ in calls} == {"first.rpy", "second.rpy"}
    assert all(kwargs == {
        "fix_indent": False,
        "fix_indent_level": True,
        "fix_quotes": True,
        "fix_dialogue_quotes": True,
        "encoding": "utf-8",
    } for _, kwargs in calls)
    assert page._running_operation is None
    assert page.repair_button.isEnabled()
    page.close()


def test_lint_runs_in_worker_and_parses_output_off_main_path(tmp_path, monkeypatch) -> None:
    game_exe = tmp_path / "game.exe"
    game_exe.write_bytes(b"")
    calls = []

    class FakeRepairer:
        def exec_renpy_lint(self, path):
            calls.append(("exec", path))
            return "lint output"

        def parse_lint_errors(self, output):
            calls.append(("parse", output))
            return [{"line": 7}]

    page = _new_page(monkeypatch)
    monkeypatch.setattr(error_page_module, "ErrorRepairer", FakeRepairer)
    page.game_exe_edit.setText(str(game_exe))

    page._run_lint_check()

    assert calls == []
    assert page._running_operation == "lint"
    assert len(_DeferredThread.instances) == 1
    _DeferredThread.instances[0].finish()

    assert calls == [("exec", str(game_exe)), ("parse", "lint output")]
    assert page._running_operation is None
    assert page.lint_check_button.isEnabled()
    page.close()


def test_lint_execution_failure_uses_error_path(tmp_path, monkeypatch) -> None:
    game_exe = tmp_path / "game.exe"
    game_exe.write_bytes(b"")
    messages = []

    class FakeRepairer:
        def exec_renpy_lint(self, path):
            del path
            return None

    page = _new_page(monkeypatch)
    monkeypatch.setattr(error_page_module, "ErrorRepairer", FakeRepairer)
    monkeypatch.setattr(
        error_page_module.InfoBar,
        "error",
        lambda *args, **kwargs: messages.append((args, kwargs)),
    )
    page.game_exe_edit.setText(str(game_exe))

    page._run_lint_check()
    _DeferredThread.instances[0].finish()

    assert page._running_operation is None
    assert page.lint_check_button.isEnabled()
    assert messages
    assert "Lint 执行失败" in messages[-1][0][1]
    page.close()


def test_export_uses_last_scan_report(tmp_path, monkeypatch) -> None:
    report = {"script.rpy": [{"line": 1, "message": "broken"}]}
    export_path = tmp_path / "report"
    calls = []

    class FakeRepairer:
        def export_error_report(self, value, output_path):
            calls.append((value, output_path))
            Path(output_path).write_bytes(b"xlsx")

    page = _new_page(monkeypatch)
    monkeypatch.setattr(error_page_module, "ErrorRepairer", FakeRepairer)
    monkeypatch.setattr(
        error_page_module.QFileDialog,
        "getSaveFileName",
        lambda *args, **kwargs: (str(export_path), "Excel 文件 (*.xlsx)"),
    )
    page._last_scan_report = report
    page._set_running_operation(None)

    assert page.export_report_button.isEnabled()
    page._export_report()

    expected_path = str(export_path) + ".xlsx"
    assert calls == [(report, expected_path)]
    assert Path(expected_path).read_bytes() == b"xlsx"
    page.close()


def test_worker_failure_restores_actions_and_preserves_previous_report(
    tmp_path, monkeypatch
) -> None:
    game_dir = tmp_path / "game"
    game_dir.mkdir()
    previous_report = {"old.rpy": [{"line": 1}]}

    class FakeRepairer:
        def check_folder(self, path, **kwargs):
            raise RuntimeError("scan exploded")

    page = _new_page(monkeypatch)
    monkeypatch.setattr(error_page_module, "ErrorRepairer", FakeRepairer)
    page._last_scan_report = previous_report
    page._set_running_operation(None)
    page.game_dir_edit.setText(str(game_dir))

    page._scan_errors()
    _DeferredThread.instances[0].finish()

    assert page._running_operation is None
    assert page._last_scan_report == previous_report
    assert page.scan_button.isEnabled()
    assert page.repair_button.isEnabled()
    assert page.lint_check_button.isEnabled()
    assert page.export_report_button.isEnabled()
    page.close()
