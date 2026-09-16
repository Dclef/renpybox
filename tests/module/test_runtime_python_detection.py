from types import SimpleNamespace

from utils import call_game_python


def test_detect_python_major_uses_interpreter_output(tmp_path, monkeypatch):
    interpreter = tmp_path / "python.exe"
    interpreter.write_bytes(b"")
    monkeypatch.setattr(
        call_game_python.subprocess, "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="3\n"),
    )
    assert call_game_python.detect_python_major(str(interpreter)) == 3


def test_detect_python_major_reports_unknown_for_missing_interpreter():
    assert call_game_python.detect_python_major(None) is None


def test_get_py_path_uses_unsuffixed_script_for_32_64_bit_launcher(tmp_path):
    exe = tmp_path / "DarkMagic-32.exe"
    script = tmp_path / "DarkMagic.py"
    exe.write_bytes(b"")
    script.write_text("", encoding="utf-8")

    assert call_game_python.get_py_path(str(exe)) == str(script)
