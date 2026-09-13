import runpy
from pathlib import Path

import pytest

from module.Tool.Packer import Packer
from module.Tool.rpatool_core import RenPyArchive


@pytest.mark.parametrize(
    ("major", "preferred_name"),
    [(7, "UnRen-legacy.bat"), (8, "UnRen-current.bat")],
)
def test_select_unren_prefers_game_local_script_for_detected_version(
    tmp_path, monkeypatch, major, preferred_name
) -> None:
    """按 Ren'Py 主版本优先使用游戏目录自带的匹配脚本。"""
    (tmp_path / "UnRen-legacy.bat").write_text("legacy", encoding="utf-8")
    (tmp_path / "UnRen-current.bat").write_text("current", encoding="utf-8")
    packer = Packer()
    monkeypatch.setattr(packer, "_detect_renpy_major", lambda _root: major)

    scripts, detected = packer._select_unren_bats(tmp_path)

    assert detected == major
    assert scripts[0].name == preferred_name


def test_unpack_rpa_files_uses_direct_result_without_fallback(monkeypatch) -> None:
    packer = Packer()
    stages = []
    direct_args = {}
    monkeypatch.setattr(packer, "validate_rpa_paths", lambda _game_dir: True)

    def unpack_direct(game_dir, *, script_only, remove_archives):
        direct_args.update(
            game_dir=game_dir,
            script_only=script_only,
            remove_archives=remove_archives,
        )
        return 2, []

    monkeypatch.setattr(packer, "find_rpa_files", lambda _game_dir: [])
    monkeypatch.setattr(packer, "unpack_all_unren", unpack_direct)
    monkeypatch.setattr(
        packer,
        "unpack_all",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("不应调用外部工具")),
    )

    result = packer.unpack_rpa_files(
        "game",
        script_only=True,
        progress_callback=stages.append,
    )

    assert result == {
        "success": True,
        "method": "direct",
        "count": 2,
        "message": "直接解包完成，共解包 2 个 RPA 文件",
    }
    assert direct_args == {
        "game_dir": "game",
        "script_only": True,
        "remove_archives": False,
    }
    assert stages == ["direct"]


def test_unpack_rpa_files_falls_back_to_unren_bat(monkeypatch) -> None:
    packer = Packer()
    stages = []
    external_args = {}
    monkeypatch.setattr(packer, "validate_rpa_paths", lambda _game_dir: True)

    monkeypatch.setattr(packer, "find_rpa_files", lambda _game_dir: ["a.rpa", "b.rpa"])
    monkeypatch.setattr(
        packer,
        "unpack_all_unren",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("直接解包失败")),
    )

    def unpack_external(game_dir, **kwargs):
        external_args.update(game_dir=game_dir, **kwargs)
        return 0, []

    monkeypatch.setattr(packer, "unpack_all", unpack_external)
    monkeypatch.setattr(packer, "unpack_all_unren_bat", lambda *_args, **_kwargs: (True, []))

    result = packer.unpack_rpa_files(
        "game",
        script_only=True,
        progress_callback=stages.append,
    )

    assert result == {
        "success": True,
        "method": "unren_bat",
        "count": 2,
        "message": "UnRen 兜底解包完成",
    }
    assert external_args == {
        "game_dir": "game",
        "script_only": True,
        "output_root": "game",
    }
    assert stages == ["direct", "direct_failed", "external", "unren_bat"]


def test_unpack_rpa_files_uses_unren_bat_when_external_tool_fails(monkeypatch) -> None:
    packer = Packer()
    monkeypatch.setattr(packer, "validate_rpa_paths", lambda _game_dir: True)
    monkeypatch.setattr(packer, "find_rpa_files", lambda _game_dir: ["archive.rpa"])
    monkeypatch.setattr(
        packer,
        "unpack_all",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("外部工具失败")),
    )
    monkeypatch.setattr(packer, "unpack_all_unren_bat", lambda *_args, **_kwargs: (True, []))

    result = packer.unpack_rpa_files("game", direct=False)

    assert result["success"] is True
    assert result["method"] == "unren_bat"
    assert result["count"] == 1


def test_unpack_rpa_files_rejects_unsafe_archive_path_before_unpacking(tmp_path, monkeypatch) -> None:
    game_dir = tmp_path / "game"
    game_dir.mkdir()
    archive_path = game_dir / "archive.rpa"
    archive = RenPyArchive(version=3)
    archive.add("../outside.txt", b"unsafe")
    archive.save(str(archive_path))
    packer = Packer()
    monkeypatch.setattr(packer, "_get_game_python", lambda _root: None)
    monkeypatch.setattr(
        packer,
        "unpack_all_unren",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("不应启动解包")),
    )

    with pytest.raises(ValueError, match="不安全路径"):
        packer.unpack_rpa_files(str(game_dir))

    assert not (tmp_path / "outside.txt").exists()


def test_unpack_rpa_files_skips_unren_bat_without_complete_validation(monkeypatch) -> None:
    packer = Packer()
    monkeypatch.setattr(packer, "validate_rpa_paths", lambda _game_dir: False)
    monkeypatch.setattr(packer, "find_rpa_files", lambda _game_dir: ["archive.rpa"])
    monkeypatch.setattr(packer, "unpack_all", lambda *_args, **_kwargs: (0, []))
    monkeypatch.setattr(
        packer,
        "unpack_all_unren_bat",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("不应启动 UnRen 兜底")),
    )

    result = packer.unpack_rpa_files("game", direct=False)

    assert result["success"] is False
    assert result["method"] == "none"


@pytest.mark.parametrize("script_name", ["rpatool", "unren_rpatool.py"])
def test_builtin_unpackers_reject_paths_outside_output(tmp_path, script_name) -> None:
    script_path = Path(__file__).resolve().parents[3] / "resource" / "tools" / script_name
    safe_output_path = runpy.run_path(str(script_path))["_safe_output_path"]
    output_dir = tmp_path / "game"
    output_dir.mkdir()

    with pytest.raises(ValueError, match="unsafe archive path"):
        safe_output_path(str(output_dir), "../outside.txt")

    assert not (tmp_path / "outside.txt").exists()


def test_unren_rpatool_handles_single_archive_after_loader_reindex(tmp_path) -> None:
    """单个归档被 Ren'Py 重建索引后仍应使用新列表最后一项。"""
    script_path = Path(__file__).resolve().parents[3] / "resource" / "tools" / "unren_rpatool.py"
    module = runpy.run_path(str(script_path))
    archive_path = tmp_path / "archive.rpa"
    archive_path.write_bytes(b"RPA")

    class ConfigStub:
        archives = []
        searchpath = []
        basedir = ""

    class LoaderStub:
        archives = []

        def index_archives(self):
            self.archives = [("archive", {"script.rpyc": [(0, 0)]})]

    archive = module["RenPyArchive"](
        str(archive_path), 1, ConfigStub(), LoaderStub()
    )

    assert archive.list() == ["script.rpyc"]
