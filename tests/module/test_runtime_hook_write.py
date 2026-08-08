# -*- coding: utf-8 -*-
"""运行时 HOOK 写回 tl 的注释与布局回归测试。"""

from module.Extract.RenpyExtractor import RenpyExtractor


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
