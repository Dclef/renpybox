from pathlib import Path

import pytest

from module.Tool.Packer import Packer
from module.Tool.rpatool_core import RenPyArchive


def _write_file(path: Path, size: int, fill: bytes = b"x") -> bytes:
    content = fill * size
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return content


def _read_archive_files(paths: list[Path]) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    for path in paths:
        archive = RenPyArchive(str(path))
        try:
            for name in archive.list():
                assert name not in files
                files[name] = archive.read(name)
        finally:
            if archive.handle is not None:
                archive.handle.close()
                archive.handle = None
    return files


def test_pack_without_size_limit_returns_requested_archive(tmp_path: Path) -> None:
    source_dir = tmp_path / "game"
    expected = _write_file(source_dir / "script.rpy", 32, b"a")
    output = tmp_path / "archive.rpa"

    result = Packer().pack_from_dir(str(source_dir), str(output))

    assert [path.name for path in result] == ["archive.rpa"]
    assert all(isinstance(path, Path) for path in result)
    assert _read_archive_files(result) == {"script.rpy": expected}


def test_split_archives_use_numbered_names_and_respect_actual_limit(
    tmp_path: Path,
) -> None:
    source_dir = tmp_path / "game"
    file_size = 300 * 1024
    limit = 512 * 1024
    expected = {
        "a.bin": _write_file(source_dir / "a.bin", file_size, b"a"),
        "b.bin": _write_file(source_dir / "b.bin", file_size, b"b"),
        "c.bin": _write_file(source_dir / "c.bin", file_size, b"c"),
    }
    output = tmp_path / "base.rpa"

    result = Packer().pack_from_dir(
        str(source_dir),
        str(output),
        max_part_size_bytes=limit,
    )

    assert [path.name for path in result] == [
        "base.part001.rpa",
        "base.part002.rpa",
        "base.part003.rpa",
    ]
    assert all(path.stat().st_size <= limit for path in result)
    assert not output.exists()
    assert _read_archive_files(result) == expected


def test_oversized_single_file_preserves_existing_output(tmp_path: Path) -> None:
    source_dir = tmp_path / "game"
    limit = 128 * 1024
    _write_file(source_dir / "oversized.bin", limit + 1)
    output = tmp_path / "base.rpa"
    original_output = b"existing archive"
    output.write_bytes(original_output)

    with pytest.raises(RuntimeError):
        Packer().pack_from_dir(
            str(source_dir),
            str(output),
            max_part_size_bytes=limit,
        )

    assert output.read_bytes() == original_output
    assert list(tmp_path.glob("base.part*.rpa")) == []


def test_repack_removes_stale_tail_parts(tmp_path: Path) -> None:
    source_dir = tmp_path / "game"
    file_size = 300 * 1024
    limit = 512 * 1024
    first_file = _write_file(source_dir / "a.bin", file_size, b"a")
    _write_file(source_dir / "b.bin", file_size, b"b")
    _write_file(source_dir / "c.bin", file_size, b"c")
    output = tmp_path / "base.rpa"
    packer = Packer()

    first_result = packer.pack_from_dir(
        str(source_dir),
        str(output),
        max_part_size_bytes=limit,
    )
    assert [path.name for path in first_result] == [
        "base.part001.rpa",
        "base.part002.rpa",
        "base.part003.rpa",
    ]

    (source_dir / "b.bin").unlink()
    (source_dir / "c.bin").unlink()
    second_result = packer.pack_from_dir(
        str(source_dir),
        str(output),
        max_part_size_bytes=limit,
    )

    assert [path.name for path in second_result] == ["base.part001.rpa"]
    assert not (tmp_path / "base.part002.rpa").exists()
    assert not (tmp_path / "base.part003.rpa").exists()
    assert _read_archive_files(second_result) == {"a.bin": first_file}


def test_output_family_inside_source_is_not_packed(tmp_path: Path) -> None:
    source_dir = tmp_path / "images"
    payload = _write_file(source_dir / "payload.bin", 64, b"p")
    output = source_dir / "base.rpa"
    output.write_bytes(b"old base")
    (source_dir / "base.part009.rpa").write_bytes(b"old part")

    result = Packer().pack_from_dir(
        str(source_dir),
        str(output),
        max_part_size_bytes=512 * 1024,
    )

    assert [path.name for path in result] == ["base.part001.rpa"]
    assert not output.exists()
    assert not (source_dir / "base.part009.rpa").exists()
    assert _read_archive_files(result) == {"images/payload.bin": payload}


def test_save_failure_preserves_existing_output_and_cleans_staging(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_dir = tmp_path / "game"
    file_size = 300 * 1024
    limit = 512 * 1024
    _write_file(source_dir / "a.bin", file_size, b"a")
    _write_file(source_dir / "b.bin", file_size, b"b")
    output = tmp_path / "base.rpa"
    original_output = b"existing archive"
    output.write_bytes(original_output)
    original_save = RenPyArchive.save
    save_count = 0

    def fail_second_save(self, filename=None):
        nonlocal save_count
        save_count += 1
        if save_count == 2:
            raise OSError("模拟第二个分包写入失败")
        return original_save(self, filename)

    monkeypatch.setattr(RenPyArchive, "save", fail_second_save)

    with pytest.raises(RuntimeError, match="保存 RPA 失败"):
        Packer().pack_from_dir(
            str(source_dir),
            str(output),
            max_part_size_bytes=limit,
        )

    assert output.read_bytes() == original_output
    assert list(tmp_path.glob("base.part*.rpa")) == []
    assert list(tmp_path.glob(".base.packing-*")) == []


def test_cancel_between_parts_preserves_existing_output(tmp_path: Path) -> None:
    source_dir = tmp_path / "game"
    file_size = 300 * 1024
    limit = 512 * 1024
    _write_file(source_dir / "a.bin", file_size, b"a")
    _write_file(source_dir / "b.bin", file_size, b"b")
    output = tmp_path / "base.rpa"
    original_output = b"existing archive"
    output.write_bytes(original_output)
    cancelled = False

    def on_progress(current: int, total: int, message: str) -> None:
        nonlocal cancelled
        if current > 0 and total == 2 and message.startswith("已完成第 1/"):
            cancelled = True

    with pytest.raises(RuntimeError, match="打包已取消"):
        Packer().pack_from_dir(
            str(source_dir),
            str(output),
            progress_callback=on_progress,
            stop_check=lambda: cancelled,
            max_part_size_bytes=limit,
        )

    assert output.read_bytes() == original_output
    assert list(tmp_path.glob("base.part*.rpa")) == []
    assert list(tmp_path.glob(".base.packing-*")) == []


def test_switching_back_to_single_archive_removes_split_family(
    tmp_path: Path,
) -> None:
    source_dir = tmp_path / "game"
    expected = _write_file(source_dir / "script.rpy", 32, b"a")
    output = tmp_path / "base.rpa"
    (tmp_path / "base.part001.rpa").write_bytes(b"old part 1")
    (tmp_path / "base.part002.rpa").write_bytes(b"old part 2")

    result = Packer().pack_from_dir(str(source_dir), str(output))

    assert [path.name for path in result] == ["base.rpa"]
    assert list(tmp_path.glob("base.part*.rpa")) == []
    assert _read_archive_files(result) == {"script.rpy": expected}
