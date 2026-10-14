"""AndroidProjectTools：检测、备份失败不删、pack 失败保旧、越界清理拒绝。"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from module.Tool.AndroidProjectTools import (
    AndroidProjectToolsError,
    detect_resource_dirs,
    ensure_project_dist_dir,
    make_shell_archive,
    pack_archive_from_dirs,
    parse_remove_dirs,
    preflight_shell_archive,
    resolve_archive_source_dirs,
    resolve_safe_remove_targets,
    sanitize_android_dist_assets,
    split_items,
)


def _project(tmp_path: Path) -> tuple[Path, Path]:
    project = tmp_path / "Game"
    game = project / "game"
    (game / "images").mkdir(parents=True)
    (game / "audio").mkdir(parents=True)
    (game / "gui").mkdir(parents=True)
    (game / "images" / "a.png").write_bytes(b"png")
    (game / "audio" / "b.ogg").write_bytes(b"ogg")
    (game / "gui" / "c.png").write_bytes(b"png")
    (game / "script.rpy").write_text("label start:\n    pass\n", encoding="utf-8")
    return project, game


def test_split_and_empty_remove_dirs():
    assert split_items("a;b,c\nd") == ["a", "b", "c", "d"]
    assert parse_remove_dirs("") == []
    assert parse_remove_dirs("  ") == []
    assert parse_remove_dirs("images; audio") == ["images", "audio"]


def test_detect_skips_gui_and_replaces_hints(tmp_path):
    project, game = _project(tmp_path)
    detected = detect_resource_dirs(game, hints=["images", "gui", "../escape"])
    assert "images" in detected
    assert "audio" in detected
    assert "gui" not in detected
    assert all(".." not in name for name in detected)
    _ = project


def test_empty_source_is_game_absolute_external_allowed(tmp_path):
    project, game = _project(tmp_path)
    external = tmp_path / "external_assets"
    external.mkdir()
    (external / "x.png").write_bytes(b"x")
    assert resolve_archive_source_dirs(project, "") == [game.resolve()]
    resolved = resolve_archive_source_dirs(project, f"images;{external}")
    assert any(path.name == "images" for path in resolved)
    assert any(path.resolve() == external.resolve() for path in resolved)


def test_remove_escape_rejected(tmp_path):
    _, game = _project(tmp_path)
    with pytest.raises(AndroidProjectToolsError):
        resolve_safe_remove_targets(game, [".."])
    with pytest.raises(AndroidProjectToolsError):
        resolve_safe_remove_targets(game, [str(tmp_path)])
    with pytest.raises(AndroidProjectToolsError):
        resolve_safe_remove_targets(game, ["."])


def test_dist_sanitize_scoped_and_whitelist(tmp_path):
    project, _ = _project(tmp_path)
    dist = project / "android.dist"
    assets = dist / "assets"
    assets.mkdir(parents=True)
    (assets / "game").mkdir()
    (assets / "renpy").mkdir()
    (assets / "android.json").write_text("{}", encoding="utf-8")
    (assets / "junk.txt").write_text("x", encoding="utf-8")
    (assets / "android-foo").mkdir()
    result = sanitize_android_dist_assets(project)
    assert (assets / "game").is_dir()
    assert (assets / "renpy").is_dir()
    assert (assets / "android.json").is_file()
    assert (assets / "android-foo").is_dir()
    assert not (assets / "junk.txt").exists()
    assert "junk.txt" in result["removed"]
    with pytest.raises(AndroidProjectToolsError):
        ensure_project_dist_dir(project, tmp_path / "other")


def test_backup_fail_does_not_pack_or_delete(tmp_path, monkeypatch):
    project, game = _project(tmp_path)
    monkeypatch.setattr(
        "module.Tool.AndroidProjectTools._write_backup_zip",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("disk full")),
    )
    with pytest.raises(AndroidProjectToolsError, match="备份失败"):
        make_shell_archive(
            project,
            source_text="images",
            remove_text="images",
            backup=True,
        )
    assert (game / "images" / "a.png").is_file()
    assert not (project / "archive.rpa").exists()


def test_uncovered_cleanup_refused_when_backup(tmp_path):
    project, game = _project(tmp_path)
    with pytest.raises(AndroidProjectToolsError, match="未被打包源覆盖"):
        make_shell_archive(
            project,
            source_text="images",
            remove_text="audio",
            backup=True,
        )
    assert (game / "audio" / "b.ogg").is_file()
    assert not (project / "archive.rpa").exists()


def test_pack_failure_keeps_old_archive_and_sources(tmp_path, monkeypatch):
    project, game = _project(tmp_path)
    old = project / "archive.rpa"
    old.write_bytes(b"OLD-ARCHIVE")
    (game / "archive.rpa").write_bytes(b"INTERNAL")

    class BoomArchive:
        def __init__(self, *args, **kwargs):
            pass

        def add_file_path(self, *args, **kwargs):
            return None

        def save(self, path):
            raise RuntimeError("save failed")

    monkeypatch.setattr("module.Tool.rpatool_core.RenPyArchive", BoomArchive)
    result = pack_archive_from_dirs(
        [game / "images"],
        game_dir=game,
        archive_path=old,
        exclude_paths=set(),
    )
    assert result["success"] is False
    assert old.read_bytes() == b"OLD-ARCHIVE"
    assert (game / "images" / "a.png").is_file()


def test_make_shell_success_cleanup_and_internal_removed(tmp_path):
    project, game = _project(tmp_path)
    (game / "archive.rpa").write_bytes(b"INTERNAL")
    result = make_shell_archive(
        project,
        source_text="",
        remove_text="images",
        backup=True,
    )
    assert result["success"] is True
    assert Path(result["archive_path"]).is_file()
    assert result["backup_path"] and Path(result["backup_path"]).is_file()
    assert "images" in result["removed"]
    assert not (game / "images").exists()
    assert not (game / "archive.rpa").exists()
    assert (game / "audio" / "b.ogg").is_file()


def test_empty_cleanup_skips_delete(tmp_path):
    project, game = _project(tmp_path)
    result = make_shell_archive(
        project,
        source_text="images",
        remove_text="",
        backup=True,
    )
    assert result["success"] is True
    assert result["removed"] == []
    assert (game / "images" / "a.png").is_file()


def _make_junction(link: Path, target: Path) -> None:
    if os.name != "nt":
        link.symlink_to(target, target_is_directory=True)
        return
    link.parent.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0 or not link.exists():
        pytest.skip(f"无法创建 Junction: {completed.stderr or completed.stdout}")


@pytest.mark.skipif(os.name != "nt", reason="Junction 探针仅 Windows")
def test_junction_alias_rejected_before_resolve(tmp_path):
    """alias→game/images：lexical 联接在 resolve 前拒绝，不得返回真 images。"""
    _, game = _project(tmp_path)
    valuable = game / "images" / "valuable.txt"
    valuable.write_text("keep", encoding="utf-8")
    alias = game / "alias"
    _make_junction(alias, game / "images")
    with pytest.raises(AndroidProjectToolsError, match="链接|联接"):
        resolve_safe_remove_targets(game, ["alias"])
    assert valuable.is_file()
    assert valuable.read_text(encoding="utf-8") == "keep"


def test_preflight_rejects_before_any_write(tmp_path):
    project, game = _project(tmp_path)
    with pytest.raises(AndroidProjectToolsError):
        preflight_shell_archive(
            project,
            source_text="images",
            remove_text="../outside",
            backup=True,
        )
    assert (game / "images" / "a.png").is_file()
    assert not (project / "archive.rpa").exists()
    assert not list(project.glob("archive_backup_*.zip"))
