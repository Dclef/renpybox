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


def test_atomic_write_default_newline_matches_path_write_text(tmp_path):
    expected = tmp_path / "expected.rpy"
    target = tmp_path / "actual.rpy"
    text = "first line\nsecond line\n"
    expected.write_text(text, encoding="utf-8")

    atomic_write_text(target, text)

    assert target.read_bytes() == expected.read_bytes()


def test_atomic_write_can_explicitly_preserve_lf(tmp_path):
    target = tmp_path / "lf.rpy"

    atomic_write_text(target, "first line\nsecond line\n", newline="")

    assert target.read_bytes() == b"first line\nsecond line\n"


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


def test_atomic_write_rejects_symlink_escaping_allowed_roots(tmp_path):
    outside = tmp_path / "outside.rpy"
    outside.write_text("secret", encoding="utf-8")
    target_dir = tmp_path / "tl" / "chinese"
    target_dir.mkdir(parents=True)
    link = target_dir / "escape.rpy"
    try:
        link.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"symbolic links are unavailable: {exc}")

    with pytest.raises(RuntimeError, match="escapes allowed roots"):
        atomic_write_text(link, "new content", allowed_roots=[target_dir])

    # 受限根目录之外的文件不得被写入。
    assert outside.read_text(encoding="utf-8") == "secret"


@pytest.mark.parametrize("path_kind", ["relative", "absolute"])
def test_atomic_write_rejects_ordinary_path_escaping_allowed_roots(tmp_path, path_kind):
    output = tmp_path / "output"
    output.mkdir()
    outside = tmp_path / "output-other" / "fictional.txt"
    outside.parent.mkdir()
    outside.write_text("original fictional sentinel", encoding="utf-8")
    target = outside if path_kind == "absolute" else output / ".." / "output-other" / outside.name

    with pytest.raises(RuntimeError, match="escapes allowed roots"):
        atomic_write_text(target, "unexpected replacement", allowed_roots=[output])

    assert outside.read_text(encoding="utf-8") == "original fictional sentinel"
    assert list(outside.parent.glob("*.tmp")) == []


def test_atomic_write_rejects_escape_before_creating_parent_directories(tmp_path):
    output = tmp_path / "output"
    output.mkdir()
    outside = tmp_path / "outside" / "nested"

    with pytest.raises(RuntimeError, match="escapes allowed roots"):
        atomic_write_text(
            output / ".." / "outside" / "nested" / "fictional.txt",
            "unexpected creation",
            allowed_roots=[output],
        )

    assert not outside.parent.exists()


def test_atomic_write_rejects_parent_symlink_escaping_allowed_roots(tmp_path):
    output = tmp_path / "output"
    outside = tmp_path / "outside"
    output.mkdir()
    outside.mkdir()
    link = output / "linked"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symbolic links are unavailable: {exc}")
    victim = outside / "fictional.txt"
    victim.write_text("original fictional sentinel", encoding="utf-8")

    with pytest.raises(RuntimeError, match="escapes allowed roots"):
        atomic_write_text(link / victim.name, "unexpected replacement", allowed_roots=[output])

    assert victim.read_text(encoding="utf-8") == "original fictional sentinel"


def test_atomic_write_allows_new_nested_path_within_allowed_roots(tmp_path):
    output = tmp_path / "output"
    target = output / "nested" / "fictional.txt"

    atomic_write_text(target, "new fictional text", allowed_roots=[output])

    assert target.read_text(encoding="utf-8") == "new fictional text"
