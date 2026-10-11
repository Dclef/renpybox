from __future__ import annotations

import stat
from pathlib import Path

from module.File.SourceBackup import backup_source_rpy, validate_external_backup_root
import module.File.SourceBackup as source_backup_module


def test_local_bak_skips_existing(tmp_path):
    rpy = tmp_path / "a.rpy"
    rpy.write_text('label start:\n    "hi"\n', encoding="utf-8")
    bak = rpy.with_suffix(".rpy.bak")
    bak.write_text("old\n", encoding="utf-8")

    result = backup_source_rpy(tmp_path, None)

    assert result["copied"] == 0
    assert bak.read_text(encoding="utf-8") == "old\n"
    assert result["written_files"] == []


def test_external_backup_overwrites(tmp_path):
    source = tmp_path / "src"
    source.mkdir()
    rpy = source / "story.rpy"
    rpy.write_text("v1\n", encoding="utf-8")
    backup = tmp_path / "backup"
    (backup / "story.rpy").parent.mkdir(parents=True)
    (backup / "story.rpy").write_text("stale\n", encoding="utf-8")

    result = backup_source_rpy(source, backup)

    assert result["copied"] == 1
    assert (backup / "story.rpy").read_text(encoding="utf-8") == "v1\n"
    assert result["warnings"] == []
    assert any(Path(p).name == "story.rpy" for p in result["written_files"])


def test_rejects_backup_inside_game(tmp_path):
    project = tmp_path / "Demo"
    game = project / "game"
    game.mkdir(parents=True)
    source = tmp_path / "source_in"
    source.mkdir()
    bad_backup = game / "backups"

    message = validate_external_backup_root(
        bad_backup,
        source_root=source,
        game_dir=game,
    )

    assert message is not None
    assert "game" in message


def test_external_overlap_source_returns_warning_no_copy(tmp_path):
    source = tmp_path / "src"
    source.mkdir()
    (source / "a.rpy").write_text("x\n", encoding="utf-8")

    result = backup_source_rpy(source, source)

    assert result["copied"] == 0
    assert result["warnings"]
    assert "重叠" in result["warnings"][0]


def test_cancel_stops_and_keeps_partial(tmp_path):
    source = tmp_path / "src"
    source.mkdir()
    for i in range(5):
        (source / f"f{i}.rpy").write_text(f"{i}\n", encoding="utf-8")
    backup = tmp_path / "bak"
    state = {"n": 0}

    def should_stop():
        state["n"] += 1
        return state["n"] > 2

    result = backup_source_rpy(source, backup, should_stop=should_stop)

    assert result["cancelled"] is True
    assert result["copied"] >= 1
    assert result["written_files"]
    assert any("取消" in w for w in result["warnings"])


def test_progress_callback_fires(tmp_path):
    source = tmp_path / "src"
    source.mkdir()
    (source / "a.rpy").write_text("a\n", encoding="utf-8")
    (source / "b.rpy").write_text("b\n", encoding="utf-8")
    backup = tmp_path / "out"
    events = []

    backup_source_rpy(
        source,
        backup,
        progress_callback=lambda cur, total, msg: events.append((cur, total, msg)),
    )

    assert len(events) == 2
    assert events[-1][0] == 2
    assert events[-1][1] == 2


def test_atomic_copy_failure_leaves_no_half_written_dest(tmp_path, monkeypatch):
    """copy2 写临时文件时失败：最终目标不得留下半写内容；Qt warning 继续语义保留。"""
    import module.File.SourceBackup as sb

    source = tmp_path / "src"
    source.mkdir()
    (source / "a.rpy").write_text("complete\n", encoding="utf-8")
    backup = tmp_path / "bak"
    existing = backup / "a.rpy"
    backup.mkdir()
    existing.write_text("previous\n", encoding="utf-8")

    def boom_copy2(src, dst, *args, **kwargs):
        Path(dst).write_text("HALF", encoding="utf-8")
        raise OSError("disk full")

    monkeypatch.setattr(sb.shutil, "copy2", boom_copy2)

    result = backup_source_rpy(source, backup)

    assert result["copied"] == 0
    assert result["warnings"]
    assert any("备份失败" in w for w in result["warnings"])
    # 原子 replace 未发生：旧内容保留，临时半写不得变成正式目标
    assert existing.read_text(encoding="utf-8") == "previous\n"
    leftovers = list(backup.glob(".a.rpy.*.tmp"))
    assert leftovers == []


def test_local_bak_atomic_failure_does_not_create_bak(tmp_path, monkeypatch):
    import module.File.SourceBackup as sb

    rpy = tmp_path / "story.rpy"
    rpy.write_text("ok\n", encoding="utf-8")
    bak = rpy.with_suffix(".rpy.bak")

    def boom_copy2(src, dst, *args, **kwargs):
        Path(dst).write_text("HALF", encoding="utf-8")
        raise OSError("fail")

    monkeypatch.setattr(sb.shutil, "copy2", boom_copy2)
    result = backup_source_rpy(tmp_path, None)

    assert result["copied"] == 0
    assert not bak.exists()
    assert result["warnings"]


def test_readonly_source_copy_failure_clears_tmp_no_side_effect(
    tmp_path, monkeypatch
):
    """只读源 copy2 到 tmp 后失败：清只读再删 tmp，不留残留、不新建 bak。"""
    source = tmp_path / "game" / "a.rpy"
    source.parent.mkdir(parents=True)
    source.write_text("# source\n", encoding="utf-8")
    source.chmod(stat.S_IREAD)
    bak = source.with_suffix(source.suffix + ".bak")

    real_copy2 = source_backup_module.shutil.copy2

    def failed_copy(src, dst, *args, **kwargs):
        real_copy2(src, dst, *args, **kwargs)
        raise OSError("模拟复制文件属性后失败")

    monkeypatch.setattr(source_backup_module.shutil, "copy2", failed_copy)

    try:
        result = backup_source_rpy(source, None)
        assert result["copied"] == 0
        assert list(source.parent.glob(".*.tmp")) == []
        assert not bak.exists()
        assert any("备份失败" in w for w in result["warnings"])
    finally:
        source.chmod(stat.S_IWRITE | stat.S_IREAD)


def test_readonly_source_copy_failure_keeps_existing_dest_bytes(
    tmp_path, monkeypatch
):
    """外部备份已有目标时：只读源原子复制失败，目标字节不变且无 tmp 残留。"""
    source_dir = tmp_path / "game"
    source = source_dir / "a.rpy"
    source_dir.mkdir(parents=True)
    source.write_text("# source\n", encoding="utf-8")
    source.chmod(stat.S_IREAD)
    backup_root = tmp_path / "backup"
    existing_dest = backup_root / "a.rpy"
    backup_root.mkdir()
    existing_bytes = b"# previous backup\n"
    existing_dest.write_bytes(existing_bytes)

    real_copy2 = source_backup_module.shutil.copy2

    def failed_copy(src, dst, *args, **kwargs):
        real_copy2(src, dst, *args, **kwargs)
        raise OSError("模拟复制文件属性后失败")

    monkeypatch.setattr(source_backup_module.shutil, "copy2", failed_copy)

    try:
        result = backup_source_rpy(source_dir, backup_root)
    finally:
        source.chmod(stat.S_IWRITE | stat.S_IREAD)

    assert result["copied"] == 0
    assert list(backup_root.glob(".a.rpy.*.tmp")) == []
    assert existing_dest.read_bytes() == existing_bytes
