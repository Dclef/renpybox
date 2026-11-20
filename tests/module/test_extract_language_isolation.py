"""抽取语言隔离回归：多语言 tl 工程、失败不谎报、相邻字面量不拼接。"""

from __future__ import annotations

import os
import struct
import zlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from module.Extract import UnifiedExtractor as ux
from module.Renpy import renpy_extract as rx
from module.Extract.RenpyExtractor import RenpyExtractor


OLD = "How can I help you, kind sir?"


def _make_project(tmp_path: Path) -> Path:
    """构造 tl/chinese + tl/japanese（含重复 old 与陈旧 .rpyc）的现场工程。"""
    project = tmp_path / "project"
    game = project / "game"
    (game / "scripts").mkdir(parents=True)
    (game / "scripts" / "characters.rpy").write_text(
        "menu:\n"
        f'        "{OLD}"\n'
        '        "Why did you go to town?"\n',
        encoding = "utf-8",
    )
    for language in ("chinese", "japanese"):
        target = game / "tl" / language
        target.mkdir(parents = True)
        (target / "characters.rpy").write_text(
            f"translate {language} strings:\n\n"
            f'    old "{OLD}"\n'
            f'    new "{language}"\n',
            encoding = "utf-8",
        )
        # 陈旧 .rpyc：现场常见「rpy 与 rpyc 同时存在」。
        (target / "characters.rpyc").write_bytes(b"RENPY RPC2" + b"\x00" * 32)
    return project


def _snapshot(directory: Path) -> dict[str, tuple[int, int, bytes]]:
    """目录内容 + mtime + 大小快照，用于证明其它语言目录零改动。"""
    result = {}
    for path in sorted(directory.rglob("*")):
        if not path.is_file():
            continue
        stat = path.stat()
        result[path.relative_to(directory).as_posix()] = (
            stat.st_mtime_ns,
            stat.st_size,
            path.read_bytes(),
        )
    return result


def _extractor(monkeypatch, official):
    """构造只跑官方抽取的 UnifiedExtractor，官方实现用 fake 替换。"""
    monkeypatch.setattr(
        ux.Config,
        "load",
        lambda self: SimpleNamespace(
            extract_use_official = True,
            extract_use_custom = False,
            onekey_inject_base_box = False,
            renpy_remove_string_duplicates = False,
            export_structured_json = False,
            export_trans_json = False,
        ),
    )
    extractor = ux.UnifiedExtractor.__new__(ux.UnifiedExtractor)
    extractor.logger = SimpleNamespace(
        info = lambda *a, **k: None,
        debug = lambda *a, **k: None,
        warning = lambda *a, **k: None,
        error = lambda *a, **k: None,
    )
    extractor._progress_callback = None
    extractor._cancel_callback = None
    extractor._last_suspicious_manifest = None
    extractor._last_suspicious_removed_count = 0
    extractor.official_extraction_error = ""
    extractor.renpy_extractor = SimpleNamespace(official_extract = official)
    return extractor


def test_official_extract_isolates_other_languages_and_restores_them(tmp_path, monkeypatch):
    project = _make_project(tmp_path)
    japanese = project / "game" / "tl" / "japanese"
    before = _snapshot(japanese)
    seen: list[list[str]] = []
    fake_exe = project / "game.exe"
    fake_exe.write_bytes(b"")

    extractor = RenpyExtractor()
    monkeypatch.setattr(extractor, "_resolve_game_exe", lambda _target: (fake_exe, project))
    monkeypatch.setattr("module.Extract.RenpyExtractor.get_python_path_from_game_path", lambda _exe: "python.exe")
    monkeypatch.setattr("module.Extract.RenpyExtractor.get_py_path", lambda _exe: str(tmp_path / "launch.py"))
    (tmp_path / "launch.py").write_text("", encoding = "utf-8")

    def fake_run_process(_command, **_kwargs):
        tl_root = project / "game" / "tl"
        seen.append(sorted(p.name for p in tl_root.iterdir()))
        return SimpleNamespace(stdout = "", returncode = 0)

    monkeypatch.setattr("utils.process_runner.run_process", fake_run_process)

    extractor.official_extract(project, "chinese", force = True)

    assert seen, "官方抽取没有真正执行"
    # 抽取期间其它语言目录一律不可见，目标语言仍然可见。
    assert "japanese" not in seen[0]
    assert "japanese.renpybox_isolated" in seen[0]
    assert "chinese" in seen[0]
    # 抽取结束后目录、内容与 mtime 全部原样回来。
    assert _snapshot(japanese) == before
    assert not (project / "game" / "tl" / "japanese.renpybox_isolated").exists()


def test_official_failure_is_reported_with_language_file_and_original(tmp_path, monkeypatch):
    project = _make_project(tmp_path)
    japanese = project / "game" / "tl" / "japanese"
    before = _snapshot(japanese)
    stdout = (
        "Exception: A translation for \"" + OLD + "\" already exists at "
        "game/tl/japanese/characters.rpy:7252."
    )

    def fake_official(_target, _tl_name, **_kwargs):
        raise RuntimeError(RenpyExtractor._duplicate_translation_message(stdout, "chinese", []))

    extractor = _extractor(monkeypatch, fake_official)
    extractor.renpy_extractor = SimpleNamespace(
        official_extract = fake_official,
    )
    monkeypatch.setattr(rx, "ExtractAllFilesInDir", lambda *a, **k: None)
    result = extractor.extract_regular(project, "chinese", exe_path = "game.exe")

    assert result.official_status == "failed"
    assert OLD in result.message
    assert "tl/japanese" in result.message
    assert "characters.rpy:7252" in result.message
    assert "删除 tl 文件夹" not in result.message
    assert "官方抽取失败" in result.message
    # 降级补充抽取不能把结果报成「抽取完成」而不提官方失败。
    assert result.message.count("官方抽取失败") >= 1
    assert _snapshot(japanese) == before


def test_duplicate_message_never_suggests_deleting_tl_folder():
    stdout = (
        "Exception: A translation for \"" + OLD + "\" already exists at "
        "game/tl/japanese/characters.rpy:7252."
    )
    message = RenpyExtractor._duplicate_translation_message(
        stdout, "chinese", [(Path("tl/japanese.renpybox_isolated"), Path("tl/japanese"))]
    )
    assert OLD in message
    assert "tl/japanese" in message
    assert "7252" in message
    assert "删除 tl 文件夹" not in message
    assert "未被修改" in message


def test_write_extracted_ignores_other_language_tl_directories(tmp_path):
    project = _make_project(tmp_path)
    game = project / "game"
    japanese = game / "tl" / "japanese"
    source = game / "scripts" / "characters.rpy"
    # 只在其它语言 tl 里出现的 old，不能算作本语言的已有覆盖。
    source.write_text(
        source.read_text(encoding = "utf-8") + '        "Japanese only line"\n',
        encoding = "utf-8",
    )
    japanese_extra = "Japanese only line"
    (japanese / "characters.rpy").write_text(
        (japanese / "characters.rpy").read_text(encoding = "utf-8")
        + f'    old "{japanese_extra}"\n    new "{japanese_extra}"\n',
        encoding = "utf-8",
    )
    before = _snapshot(japanese)

    rx.ExtractAllFilesInDir(
        str(game / "tl" / "chinese"), True, 4, False, True,
    )

    # 其它语言目录零改动（内容 + mtime 全部一致）。
    assert _snapshot(japanese) == before
    chinese = game / "tl" / "chinese" / "scripts" / "characters.rpy"
    assert chinese.exists()
    text = chinese.read_text(encoding = "utf-8")
    # japanese 的 old 不构成本语言覆盖：该原文仍然要被抽进 chinese。
    assert japanese_extra in text


def test_adjacent_menu_strings_are_not_merged_into_one_old(tmp_path):
    from module.Renpy.renpy_extract import merge_string_literal_continuations

    lines = [
        "    menu:",
        '        "How can I help you, kind sir?"',
        '        "Why did you go to town?" if tall_chat == 0:',
    ]
    merged = [line for line, _index in merge_string_literal_continuations(lines)]
    assert merged[1].strip() == '"How can I help you, kind sir?"'
    assert merged[2].strip() == '"Why did you go to town?" if tall_chat == 0:'
    assert not any(OLD + "Why did you go to town?" in line for line in merged)
