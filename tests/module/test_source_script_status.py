"""真实磁盘扫描与 OneKey/Agent 状态一致性回归。"""

import os

import pytest

from frontend.RenpyToolbox.OneKeyWorkers import detect_game_status
from module.Agent.tools.inspection_tools import _file_summary, inspect_translation_project
from module.Config import Config
from module.Renpy import ProjectPaths as paths_module
from module.Renpy.ProjectPaths import (
    RenpyProjectPaths, apply_to_config, source_script_counts, source_script_summary,
)


@pytest.mark.parametrize("files,counts,pending,status", [
    (["script.rpyc"], (0, 1), 1, "need_decompile"),
    (["script.rpyc", "script.rpy"], (1, 1), 0, "ready"),
    (["script.rpyc", "script.rpy", "extra.rpyc"], (1, 2), 1, "need_decompile"),
    (["a/script.rpyc", "a/script.rpy", "b/c/scene.rpyc", "b/c/scene.rpy"], (2, 2), 0, "ready"),
    (["a/script.rpyc", "b/script.rpy"], (1, 1), 1, "need_decompile"),
    (["script.rpyc", "script.rpy", "tl/chinese/extra.rpyc"], (1, 1), 0, "ready"),
    (["script.RPYC", "script.RPY"], (1, 1), 0, "ready"),
    (["script.rpy"], (1, 0), 0, "ready"),
    (["archive.rpa"], (0, 0), 0, "need_unpack"),
    ([], (0, 0), 0, "empty"),
    (["script.rpyc", "tl/chinese/script.rpy"], (0, 1), 1, "need_decompile"),
])
def test_status_pairing(tmp_path, files, counts, pending, status):
    game = tmp_path / "game"
    game.mkdir()
    for name in files:
        path = game / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"script")
    paths = RenpyProjectPaths.from_path(tmp_path, "chinese")
    summary = source_script_summary(paths)
    assert source_script_counts(paths) == counts
    assert summary.pending_rpyc_count == pending
    assert not summary.error and not summary.cancelled
    assert detect_game_status(str(tmp_path), "chinese")[0] == status
    agent = _file_summary(paths)
    assert agent["status"] == status
    assert (agent["rpy_count"], agent["rpyc_count"]) == counts
    assert agent["pending_rpyc_count"] == pending


def test_pairing_obeys_platform_filename_case(tmp_path):
    game = tmp_path / "game"
    game.mkdir()
    (game / "Story.rpy").touch()
    (game / "story.rpyc").touch()
    paths = RenpyProjectPaths.from_path(tmp_path)
    expected = 0 if os.path.normcase("Story") == os.path.normcase("story") else 1
    assert source_script_summary(paths).pending_rpyc_count == expected


def test_cancelled_scan_cannot_be_ready(tmp_path, monkeypatch):
    game = tmp_path / "game"
    game.mkdir()
    def walk(*args, **kwargs):
        yield str(game), [], ["script.rpy"]
        cancelled[0] = True
    cancelled = [False]
    monkeypatch.setattr(paths_module.os, "walk", walk)
    assert detect_game_status(str(tmp_path), "chinese", cancel_check=lambda: cancelled[0]) == ("cancelled", "")


@pytest.mark.parametrize("raises", [False, True])
def test_read_error_cannot_be_ready(tmp_path, monkeypatch, raises):
    game = tmp_path / "game"
    game.mkdir()
    def walk(*args, **kwargs):
        yield str(game), [], ["script.rpy"]
        error = PermissionError("无法读取源码子目录")
        if raises:
            raise error
        kwargs["onerror"](error)
    monkeypatch.setattr(paths_module.os, "walk", walk)
    paths = RenpyProjectPaths.from_path(tmp_path)
    summary = source_script_summary(paths)
    assert summary.rpy_count == 1 and summary.error
    assert detect_game_status(str(tmp_path), "chinese")[0] == "error"
    assert _file_summary(paths)["status"] == "error"
    config = apply_to_config(Config(), paths)
    result = inspect_translation_project(config=config)
    assert not result.success
    assert result.code == "SOURCE_SCAN_FAILED"
