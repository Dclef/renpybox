# -*- coding: utf-8 -*-
"""运行时 HOOK 写回 tl 的注释与布局回归测试。"""

import os
import subprocess
from pathlib import Path

import pytest

from module.Extract.RenpyExtractor import RenpyExtractor
import module.File.AtomicWrite as atomic_write_module


def test_runtime_hook_writes_single_game_prefix_comment(tmp_path):
    """运行时 payload 的 filename 自带 game/ 前缀时，注释不能变成 game/game/。"""
    project = tmp_path / "gameproj"
    (project / "game" / "tl" / "chinese").mkdir(parents=True)

    extractor = RenpyExtractor()
    runtime_data = {
        "dialogues": {
            "game/src/plot/beacon.rpy": [
                ["beacon_greet_11111111", "guide", "Hello.", 12],
                ["beacon_leave_22222222", "guide", "Goodbye.", 40],
            ]
        },
        "strings": {},
    }
    tl_dir = extractor._write_runtime_tl(
        project,
        "chinese",
        runtime_data,
        generate_empty=False,
        incremental=False,
    )

    text = (tl_dir / "src" / "plot" / "beacon.rpy").read_text(encoding="utf-8")
    assert "# game/src/plot/beacon.rpy:12" in text
    assert "# game/src/plot/beacon.rpy:40" in text
    assert "# game/game/" not in text
    # 编号块按原顺序写入。
    assert text.index("beacon_greet_11111111") < text.index("beacon_leave_22222222")


def test_runtime_hook_incremental_keeps_existing_dialogue(tmp_path):
    """增量模式只追加缺失对白，已有条目不被覆盖。"""
    project = tmp_path / "gameproj"
    tl_dir = project / "game" / "tl" / "chinese"
    tl_dir.mkdir(parents=True)
    existing = tl_dir / "src" / "plot" / "beacon.rpy"
    existing.parent.mkdir(parents=True)
    existing.write_text(
        "translate chinese beacon_greet_11111111:\n"
        '    # guide "Hello."\n'
        '    guide "你好。"\n',
        encoding="utf-8",
    )

    extractor = RenpyExtractor()
    runtime_data = {
        "dialogues": {
            "game/src/plot/beacon.rpy": [
                ["beacon_greet_11111111", "guide", "Hello.", 12],
                ["beacon_leave_22222222", "guide", "Goodbye.", 40],
            ]
        },
        "strings": {},
    }
    tl_dir = extractor._write_runtime_tl(
        project,
        "chinese",
        runtime_data,
        generate_empty=False,
        incremental=True,
    )

    text = (tl_dir / "src" / "plot" / "beacon.rpy").read_text(encoding="utf-8")
    assert 'guide "你好。"' in text
    assert "beacon_leave_22222222" in text


def test_write_runtime_tl_records_only_session_writes_and_honors_stop(tmp_path):
    """本次写入列表不含未改旧文件；取消后保留已成功文件，不继续写后续文件。"""
    project = tmp_path / "gameproj"
    tl_dir = project / "game" / "tl" / "chinese"
    tl_dir.mkdir(parents=True)
    (tl_dir / "old.rpy").write_text(
        "translate chinese strings:\n\n"
        '    old "keep"\n'
        '    new "保留"\n',
        encoding="utf-8",
    )

    extractor = RenpyExtractor()
    written_files: list[str] = []
    tl = extractor._write_runtime_tl(
        project,
        "chinese",
        {
            "dialogues": {"game/a.rpy": [["a_id_11111111", "n", "First", 1]]},
            "strings": {},
        },
        generate_empty=False,
        incremental=True,
        written_files=written_files,
    )
    assert any(Path(p).name == "a.rpy" for p in written_files)
    assert not any(Path(p).name == "old.rpy" for p in written_files)
    assert (tl / "a.rpy").is_file()

    # sorted(a, b)：写完 a 后 should_stop，不得再写 b；已写 a 保留。
    written_partial: list[str] = []

    def should_stop_mid():
        return len(written_partial) >= 1

    with pytest.raises(RuntimeError, match="已取消"):
        extractor._write_runtime_tl(
            project,
            "chinese",
            {
                "dialogues": {
                    "game/a.rpy": [["a_id_aaaaaaaa", "n", "First", 1]],
                    "game/b.rpy": [["b_id_bbbbbbbb", "n", "Second", 2]],
                },
                "strings": {},
            },
            generate_empty=False,
            incremental=False,
            should_stop=should_stop_mid,
            written_files=written_partial,
        )

    assert len(written_partial) == 1
    assert Path(written_partial[0]).name == "a.rpy"
    assert Path(written_partial[0]).is_file()
    assert not (tl_dir / "b.rpy").exists()


def test_runtime_extract_popen_failure_cleans_injected_hook(tmp_path, monkeypatch):
    """Popen 抛错不得残留临时 hook / 结果文件；不启动真实 exe。"""
    project = tmp_path / "gameproj"
    game = project / "game"
    game.mkdir(parents=True)
    exe = project / "Game.exe"
    exe.write_bytes(b"MZ" + b"\0" * 32)

    hook_source = tmp_path / "hook_runtime_extract.rpy"
    hook_source.write_text("# hook\n", encoding="utf-8")
    monkeypatch.setattr(
        "module.Extract.RenpyExtractor.get_resource_path",
        lambda *parts: str(hook_source),
    )

    def boom_popen(*_a, **_k):
        raise OSError("simulated popen failure")

    monkeypatch.setattr(subprocess, "Popen", boom_popen)

    extractor = RenpyExtractor()
    hook_target = game / RenpyExtractor.HOOK_RUNTIME
    result_path = project / RenpyExtractor.HOOK_RESULT

    with pytest.raises(OSError, match="simulated popen failure"):
        extractor.runtime_extract(exe, "chinese", timeout=5)

    assert not hook_target.exists()
    assert not result_path.exists()
    assert not hook_target.with_suffix(".rpyc").exists()


def test_write_runtime_tl_atomic_append_failure_preserves_bytes(tmp_path, monkeypatch):
    """原子 replace 失败：原文件字节不变、无 .tmp 残留、written_files 不记该文件。"""
    project = tmp_path / "gameproj"
    tl_dir = project / "game" / "tl" / "chinese"
    tl_dir.mkdir(parents=True)
    target = tl_dir / "a.rpy"
    original = b"# original preserved\n"
    target.write_bytes(original)

    real_replace = atomic_write_module.os.replace

    def boom_replace(src, dst, *args, **kwargs):
        # 临时文件已写好；replace 失败必须回滚可见状态
        raise OSError("simulated atomic replace failure")

    monkeypatch.setattr(atomic_write_module.os, "replace", boom_replace)

    written: list[str] = []
    with pytest.raises(OSError, match="simulated atomic replace failure"):
        RenpyExtractor()._write_runtime_tl(
            project,
            "chinese",
            {"dialogues": {}, "strings": {"a.rpy": [["Hello", "Hello"]]}},
            generate_empty=False,
            incremental=True,
            written_files=written,
        )

    assert target.read_bytes() == original
    assert list(tl_dir.glob(".a.rpy.*.tmp")) == []
    assert written == []


def test_write_runtime_tl_first_success_second_atomic_fail_keeps_first(
    tmp_path, monkeypatch
):
    """首文件原子成功后第二文件 replace 失败：保留首条 written_files，第二文件原字节不变。"""
    project = tmp_path / "gameproj"
    tl_dir = project / "game" / "tl" / "chinese"
    tl_dir.mkdir(parents=True)
    a = tl_dir / "a.rpy"
    b = tl_dir / "b.rpy"
    a.write_text("# a keep\n", encoding="utf-8")
    b_original = b"# b keep\n"
    b.write_bytes(b_original)

    real_replace = os.replace
    seen_targets: list[str] = []

    def flaky_replace(src, dst, *args, **kwargs):
        dst_path = Path(dst)
        seen_targets.append(dst_path.name)
        if dst_path.name == "b.rpy":
            raise OSError("second file replace failed")
        return real_replace(src, dst, *args, **kwargs)

    monkeypatch.setattr(atomic_write_module.os, "replace", flaky_replace)

    written: list[str] = []
    with pytest.raises(OSError, match="second file replace failed"):
        RenpyExtractor()._write_runtime_tl(
            project,
            "chinese",
            {
                "dialogues": {},
                "strings": {
                    "a.rpy": [["HelloA", "HelloA"]],
                    "b.rpy": [["HelloB", "HelloB"]],
                },
            },
            generate_empty=False,
            incremental=True,
            written_files=written,
        )

    assert len(written) == 1
    assert Path(written[0]).name == "a.rpy"
    assert "HelloA" in a.read_text(encoding="utf-8")
    assert b.read_bytes() == b_original
    assert list(tl_dir.glob(".b.rpy.*.tmp")) == []


def test_write_runtime_tl_dedupe_records_changed_old_files(tmp_path):
    """增量无新条目时后置去重真实改写旧 TL，必须记入 written_files。"""
    project = tmp_path / "gameproj"
    tl_dir = project / "game" / "tl" / "chinese"
    tl_dir.mkdir(parents=True)
    content = (
        "translate chinese strings:\n\n"
        '    old "Hello"\n'
        '    new "已有"\n'
    )
    a = tl_dir / "a.rpy"
    b = tl_dir / "b.rpy"
    a.write_text(content, encoding="utf-8")
    b.write_text(content, encoding="utf-8")
    before = {p: p.read_bytes() for p in (a, b)}

    written: list[str] = []
    RenpyExtractor()._write_runtime_tl(
        project,
        "chinese",
        {"dialogues": {}, "strings": {"a.rpy": [["Hello", "Hello"]]}},
        generate_empty=False,
        incremental=True,
        written_files=written,
    )

    changed = [p for p, data in before.items() if p.read_bytes() != data]
    assert changed == [b]
    assert any(Path(p).name == "b.rpy" for p in written)
    assert not any(Path(p).name == "a.rpy" for p in written)


def test_write_runtime_tl_no_change_leaves_written_empty(tmp_path):
    """无新追加、无去重改写、无编号重排时 written_files 必须为空。"""
    project = tmp_path / "gameproj"
    tl_dir = project / "game" / "tl" / "chinese"
    tl_dir.mkdir(parents=True)
    (tl_dir / "only.rpy").write_text(
        "translate chinese strings:\n\n"
        '    old "Unique"\n'
        '    new "唯一"\n',
        encoding="utf-8",
    )
    written: list[str] = []
    RenpyExtractor()._write_runtime_tl(
        project,
        "chinese",
        {"dialogues": {}, "strings": {"only.rpy": [["Unique", "Unique"]]}},
        generate_empty=False,
        incremental=True,
        written_files=written,
    )
    assert written == []


def test_write_runtime_tl_cancel_before_dedupe_write_keeps_append_list(
    tmp_path, monkeypatch
):
    """后置去重写前取消：不得被 warning 吞掉后继续排序；已成功 append 保留。"""
    project = tmp_path / "gameproj"
    tl_dir = project / "game" / "tl" / "chinese"
    tl_dir.mkdir(parents=True)
    dup = (
        "translate chinese strings:\n\n"
        '    old "Hello"\n'
        '    new "已有"\n'
    )
    (tl_dir / "a.rpy").write_text(dup, encoding="utf-8")
    (tl_dir / "b.rpy").write_text(dup, encoding="utf-8")

    written: list[str] = []
    state = {"stop": False}

    import module.Extract.ReplaceGenerator as rg

    real_dedupe = rg.dedupe_string_translations

    def gated_dedupe(*args, **kwargs):
        state["stop"] = True
        return real_dedupe(*args, **kwargs)

    monkeypatch.setattr(rg, "dedupe_string_translations", gated_dedupe)

    with pytest.raises(RuntimeError, match="已取消"):
        RenpyExtractor()._write_runtime_tl(
            project,
            "chinese",
            {
                "dialogues": {},
                "strings": {"c.rpy": [["Fresh", "Fresh"]]},
            },
            generate_empty=False,
            incremental=True,
            should_stop=lambda: state["stop"],
            written_files=written,
        )

    assert any(Path(p).name == "c.rpy" for p in written)
    # 取消发生在去重写前：b 不应被去重改写记入（若已改则不应继续到排序阶段）
    assert (tl_dir / "c.rpy").is_file()
