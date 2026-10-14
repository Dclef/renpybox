"""ArchiveOps：容量解析与解包契约（不删源档）。"""
from pathlib import Path

import pytest

from module.Tool.ArchiveOps import (
    cleanup_decompiled_rpyc,
    cleanup_unpack_artifacts,
    parse_rpa_size_limit,
    resolve_game_dir,
    resolve_pack_output,
    unpack_game,
)


def test_parse_rpa_size_limit_units():
    assert parse_rpa_size_limit("1G") == 1024 ** 3
    assert parse_rpa_size_limit("512") == 512 * 1024 ** 2


def test_resolve_game_dir_from_project_and_exe(tmp_path):
    game = tmp_path / "game"
    game.mkdir()
    exe = tmp_path / "game.exe"
    exe.write_bytes(b"mz")
    assert resolve_game_dir(tmp_path) == game.resolve()
    assert resolve_game_dir(game) == game.resolve()
    assert resolve_game_dir(exe) == game.resolve()


def test_unpack_game_never_removes_archives(tmp_path, monkeypatch):
    game = tmp_path / "game"
    game.mkdir()
    archive = game / "assets.rpa"
    archive.write_bytes(b"RPA")

    class FakePacker:
        def unpack_rpa_files(self, game_dir, *, direct, script_only, remove_archives, progress_callback=None):
            assert remove_archives is False
            assert Path(game_dir) == game
            if progress_callback:
                progress_callback("direct")
            return {"success": True, "method": "direct", "count": 1}

    result = unpack_game(game, packer=FakePacker())
    assert result["success"] is True
    assert result["archives_removed"] is False
    assert archive.exists()


def test_resolve_missing_path(tmp_path):
    with pytest.raises(FileNotFoundError):
        resolve_game_dir(tmp_path / "missing")


def test_resolve_pack_output_derives_sibling_rpa_when_blank(tmp_path):
    images = tmp_path / "game" / "images"
    images.mkdir(parents=True)
    expected = (tmp_path / "game" / "images.rpa").resolve()
    assert resolve_pack_output(images, "") == expected
    assert resolve_pack_output(images, None) == expected
    assert resolve_pack_output(images, "  ") == expected
    explicit = tmp_path / "custom.RPA"
    assert resolve_pack_output(images, str(explicit)) == explicit.resolve()
    with pytest.raises(ValueError):
        resolve_pack_output(images, str(tmp_path / "out.zip"))
    with pytest.raises(FileNotFoundError):
        resolve_pack_output(images, str(tmp_path / "missing" / "out.rpa"))


def test_resolve_pack_output_rejects_unloadable_root_game_rpa(tmp_path):
    game = tmp_path / "game"
    game.mkdir()
    with pytest.raises(ValueError):
        resolve_pack_output(game, "")
    explicit = game / "patch.rpa"
    assert resolve_pack_output(game, str(explicit)) == explicit.resolve()


@pytest.mark.parametrize("existing", ["archive.rpa", "archive.part001.rpa"])
def test_resolve_pack_output_refuses_overwriting_archive_inside_source(tmp_path, existing):
    game = tmp_path / "game"
    game.mkdir()
    (game / existing).write_bytes(b"original")
    with pytest.raises(FileExistsError):
        resolve_pack_output(game, str(game / "archive.rpa"))
    assert (game / existing).read_bytes() == b"original"
    images = game / "images"
    images.mkdir()
    (game / "images.rpa").write_bytes(b"old")
    assert resolve_pack_output(images, "") == (game / "images.rpa").resolve()


def _real_archive(tmp_path, files: dict[str, bytes], name: str = "assets.rpa") -> Path:
    from module.Tool.Packer import Packer

    source = tmp_path / "src" / "game"
    for rel, data in files.items():
        path = source / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    game = tmp_path / "project" / "game"
    game.mkdir(parents=True)
    Packer().pack_from_dir(str(source), str(game / name))
    return game


def _offline_packer(monkeypatch):
    from module.Tool.Packer import Packer

    packer = Packer()
    monkeypatch.setattr(packer, "_get_game_python", lambda _root: None)
    monkeypatch.setattr(packer, "_which_unrpa", lambda: None)
    monkeypatch.setattr(packer, "_local_rpatool", lambda: Path("rpatool"))
    return packer


def test_unpack_without_rpa_skips_unren_and_fails(tmp_path, monkeypatch):
    from module.Tool.Packer import Packer

    game = tmp_path / "game"
    game.mkdir()
    packer = Packer()
    monkeypatch.setattr(packer, "validate_rpa_paths", lambda _dir: True)
    monkeypatch.setattr(packer, "unpack_all_unren", lambda *a, **k: (0, []))

    def no_unren(*_args, **_kwargs):
        raise AssertionError("没有 RPA 时不应进入 UnRen 兜底")

    monkeypatch.setattr(packer, "unpack_all_unren_bat", no_unren)
    result = unpack_game(game, packer=packer)
    assert result["success"] is False
    assert result["code"] == "NO_RPA"
    assert "没有 .rpa" in result["message"]


def test_script_only_in_process_unpack_filters_resources(tmp_path, monkeypatch):
    game = _real_archive(tmp_path, {
        "script.rpy": b"label start:\n",
        "script.rpyc": b"compiled",
        "images/bg.png": b"png",
        "audio/theme.ogg": b"ogg",
    })
    result = unpack_game(game, direct=False, script_only=True, packer=_offline_packer(monkeypatch))
    assert result["success"] is True
    assert (game / "script.rpy").read_bytes() == b"label start:\n"
    assert (game / "script.rpyc").read_bytes() == b"compiled"
    assert not (game / "images").exists()
    assert not (game / "audio").exists()
    assert (game / "assets.rpa").exists()


def test_in_process_unpack_never_overwrites_source_archive(tmp_path, monkeypatch):
    game = _real_archive(tmp_path, {"assets.rpa": b"nested", "script.rpy": b"x"})
    original = (game / "assets.rpa").read_bytes()
    result = unpack_game(game, direct=False, packer=_offline_packer(monkeypatch))
    assert result["success"] is True
    assert (game / "assets.rpa").read_bytes() == original
    assert (game / "script.rpy").read_bytes() == b"x"


def test_script_only_skips_unfilterable_fallbacks(tmp_path, monkeypatch):
    import utils.process_runner

    game = tmp_path / "game"
    game.mkdir()
    (game / "broken.rpa").write_bytes(b"not an archive")
    packer = _offline_packer(monkeypatch)
    monkeypatch.setattr(packer, "validate_rpa_paths", lambda _dir: True)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("仅脚本模式不应调用无法过滤的外部 CLI / UnRen")

    monkeypatch.setattr(utils.process_runner, "run_process", forbidden)
    monkeypatch.setattr(packer, "unpack_all_unren_bat", forbidden)
    result = unpack_game(game, direct=False, script_only=True, packer=packer)
    assert result["success"] is False
    assert result["code"] == "SCRIPT_ONLY_UNSUPPORTED"
    assert (game / "broken.rpa").read_bytes() == b"not an archive"


def _make_project(tmp_path):
    root = tmp_path / "project"
    game = root / "game"
    game.mkdir(parents=True)
    return root, game


def test_cleanup_unpack_artifacts_only_removes_whitelist(tmp_path):
    root, game = _make_project(tmp_path)
    (game / "script.rpy").write_text("label start:\n", encoding="utf-8")
    (game / "script.rpyc").write_bytes(b"compiled")
    (game / "__pycache__").mkdir()
    (game / "__pycache__" / "x.cpython-39.pyc").write_bytes(b"pyc")
    (game / "unpacked_rpa" / "images").mkdir(parents=True)
    (game / "unpacked_rpa" / "images" / "bg.png").write_bytes(b"png")
    (root / "decompiler").mkdir()
    (root / "decompiler" / "__init__.py").write_text("", encoding="utf-8")
    for name in ("unrpyc.py", "decomp.cab", "game.pid", "unpack.finish"):
        (root / name).write_bytes(b"tmp")
    (root / "user_tool.py").write_text("keep", encoding="utf-8")
    (root / "renpy").mkdir()
    (root / "renpy" / "__pycache__").mkdir()

    result = cleanup_unpack_artifacts(root)

    assert result["success"] is True
    assert result["count"] == 7
    for gone in ("unrpyc.py", "decomp.cab", "game.pid", "unpack.finish", "decompiler"):
        assert not (root / gone).exists()
    assert not (game / "__pycache__").exists()
    assert not (game / "unpacked_rpa").exists()
    assert (game / "script.rpy").exists()
    assert (game / "script.rpyc").exists()
    assert (root / "user_tool.py").exists()
    assert (root / "renpy" / "__pycache__").exists()
    assert game.is_dir() and root.is_dir()


def test_cleanup_unpack_artifacts_skips_dirs_with_user_scripts(tmp_path):
    root, game = _make_project(tmp_path)
    script = game / "unpacked_rpa" / "story" / "edited.rpy"
    script.parent.mkdir(parents=True)
    script.write_text("label edited:\n", encoding="utf-8")
    (root / "decompiler").write_text("not a dir", encoding="utf-8")

    result = cleanup_unpack_artifacts(game)

    assert result["count"] == 0
    assert script.exists()
    assert (root / "decompiler").is_file()
    assert str(game / "unpacked_rpa") in result["skipped"]


def test_cleanup_unpack_artifacts_stops_when_cancelled(tmp_path):
    root, _ = _make_project(tmp_path)
    (root / "unrpyc.py").write_text("tmp", encoding="utf-8")
    result = cleanup_unpack_artifacts(root, stop_check=lambda: True)
    assert result["count"] == 0
    assert (root / "unrpyc.py").exists()


def test_cleanup_decompiled_rpyc_keeps_orphans(tmp_path):
    root, game = _make_project(tmp_path)
    (game / "a.rpy").write_text("", encoding="utf-8")
    (game / "a.rpyc").write_bytes(b"c")
    (game / "sub").mkdir()
    (game / "sub" / "B.RPY").write_text("", encoding="utf-8")
    (game / "sub" / "b.rpyc").write_bytes(b"c")
    (game / "orphan.rpyc").write_bytes(b"c")

    result = cleanup_decompiled_rpyc(root)

    assert result["count"] == 2
    assert not (game / "a.rpyc").exists()
    assert not (game / "sub" / "b.rpyc").exists()
    assert (game / "orphan.rpyc").exists()
    assert (game / "a.rpy").exists()


def test_cleanup_decompiled_rpyc_includes_tl_like_qt5(tmp_path):
    root, game = _make_project(tmp_path)
    tl = game / "tl" / "chinese"
    tl.mkdir(parents=True)
    (tl / "script.rpy").write_text("", encoding="utf-8")
    (tl / "script.rpyc").write_bytes(b"c")
    (tl / "orphan.rpyc").write_bytes(b"c")
    (game / "tl" / "None").mkdir()
    (game / "tl" / "None" / "common.rpyc").write_bytes(b"c")

    result = cleanup_decompiled_rpyc(root)

    assert result["count"] == 1
    assert not (tl / "script.rpyc").exists()
    assert (tl / "script.rpy").exists()
    assert (tl / "orphan.rpyc").exists()
    assert (game / "tl" / "None" / "common.rpyc").exists()


def test_renpy_decompiler_default_contract_still_skips_tl(tmp_path):
    from module.Tool.RenpyDecompiler import remove_decompiled_rpyc

    _, game = _make_project(tmp_path)
    tl = game / "tl" / "chinese"
    tl.mkdir(parents=True)
    (tl / "script.rpy").write_text("", encoding="utf-8")
    (tl / "script.rpyc").write_bytes(b"c")

    assert remove_decompiled_rpyc(game) == 0
    assert (tl / "script.rpyc").exists()
