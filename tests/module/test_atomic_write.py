import importlib
import os
import stat
from pathlib import Path

import pytest

from module.File.AtomicWrite import atomic_write_text

atomic_write_module = importlib.import_module("module.File.AtomicWrite")


def test_atomic_write_preserves_existing_file_when_validation_fails(tmp_path):
    target = tmp_path / "fictional.rpy"
    target.write_text("stable constellation\n", encoding="utf-8")

    def reject(_text: str) -> None:
        raise ValueError("fictional validation failure")

    with pytest.raises(ValueError, match="fictional validation failure"):
        atomic_write_text(target, "broken constellation\n", validator=reject)

    assert target.read_text(encoding="utf-8") == "stable constellation\n"
    assert list(tmp_path.glob("*.tmp")) == []


def test_atomic_write_copies_existing_file_mode(tmp_path, monkeypatch):
    target = tmp_path / "fictional.rpy"
    target.write_text("old orbit\n", encoding="utf-8")
    copied: list[tuple[object, object]] = []
    real_copymode = atomic_write_module.shutil.copymode

    def record_copymode(source, destination):
        copied.append((source, destination))
        return real_copymode(source, destination)

    monkeypatch.setattr(atomic_write_module.shutil, "copymode", record_copymode)

    atomic_write_text(target, "new orbit\n")

    assert len(copied) == 1
    assert copied[0][0] == target


@pytest.mark.skipif(os.name != "posix", reason="POSIX permission semantics")
def test_atomic_write_preserves_posix_permissions(tmp_path):
    target = tmp_path / "fictional.rpy"
    target.write_text("old eclipse\n", encoding="utf-8")
    target.chmod(0o640)

    atomic_write_text(target, "new eclipse\n")

    assert stat.S_IMODE(target.stat().st_mode) == 0o640


@pytest.mark.skipif(os.name != "posix", reason="POSIX permission semantics")
def test_atomic_write_new_file_honors_process_umask(tmp_path):
    target = tmp_path / "new_fictional_orbit.rpy"
    previous_umask = os.umask(0o027)
    try:
        atomic_write_text(target, "new fictional orbit\n")
    finally:
        os.umask(previous_umask)

    assert stat.S_IMODE(target.stat().st_mode) == 0o640


def test_atomic_write_preserves_symlink_and_updates_referent(tmp_path):
    shared = tmp_path / "shared"
    output = tmp_path / "output"
    shared.mkdir()
    output.mkdir()
    referent = shared / "fictional_linked.rpy"
    link = output / "fictional_linked.rpy"
    referent.write_text("old fictional linked text\n", encoding="utf-8")
    try:
        link.symlink_to(referent)
    except OSError as exc:
        pytest.skip(f"symbolic links are unavailable: {exc}")

    atomic_write_text(link, "new fictional linked text\n")

    assert link.is_symlink()
    assert referent.read_text(encoding="utf-8") == "new fictional linked text\n"


def test_atomic_write_preserves_dangling_symlink_and_creates_referent(tmp_path):
    shared = tmp_path / "shared"
    output = tmp_path / "output"
    shared.mkdir()
    output.mkdir()
    referent = shared / "fictional_pending.rpy"
    link = output / "fictional_pending.rpy"
    try:
        link.symlink_to(Path("..") / "shared" / referent.name)
    except OSError as exc:
        pytest.skip(f"symbolic links are unavailable: {exc}")

    assert link.is_symlink()
    assert not referent.exists()

    atomic_write_text(link, "created fictional linked text\n")

    assert link.is_symlink()
    assert referent.read_text(encoding="utf-8") == "created fictional linked text\n"
