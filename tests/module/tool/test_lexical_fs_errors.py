from pathlib import Path

import pytest

from module.Tool import LexicalFs
from module.Tool.ErrorRepairer import ErrorRepairer


@pytest.mark.parametrize("denied_directory", [".", "unreadable"])
def test_scan_does_not_report_success_after_directory_read_failure(tmp_path, monkeypatch, denied_directory):
    unreadable = tmp_path / "unreadable"
    unreadable.mkdir()
    script = unreadable / "script.rpy"
    original = b'\tnew "text"\n'
    script.write_bytes(original)
    denied = tmp_path / denied_directory
    real_scandir = LexicalFs.os.scandir

    def scandir(path):
        if Path(path) == denied:
            raise PermissionError(13, "Permission denied", str(path))
        return real_scandir(path)

    monkeypatch.setattr(LexicalFs.os, "scandir", scandir)
    with pytest.raises(RuntimeError, match="Permission denied") as failure:
        ErrorRepairer().scan_folder(str(tmp_path))
    assert isinstance(failure.value.__cause__, PermissionError)
    assert script.read_bytes() == original
