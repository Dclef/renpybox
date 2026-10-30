"""RENPYSOURCE 写回：良性残留不再让整次写回报错。

"从缓存重新注入译文"（REINJECT）是对已经翻译好的输出文件再写一遍，此时
绝大多数条目早已生效（applied=0、already_applied 大量），只剩少量无字符
标签、陈旧行号、同行多条被前序条目消费的残留。本模块锁定这些良性类别
只计数不抛错，同时锁定真实未生效仍要报错、失败前已成功的写回不丢。
"""

import json

import pytest

from base.Base import Base
from module.Cache.CacheItem import CacheItem
from module.Config import Config
from module.File.RENPYSOURCE import RENPYSOURCE

REPORT_NAME = "writeback_report_renpy_source.json"
COLOR_ONLY_TEXT = "{color=#a54a54a}"

# 用户报障日志里的 6 个文件与当时的 (translated, applied, already_applied, skipped)。
REINJECT_LOG_CASES = (
    ("_content/sandbox/action_menu.rpy", 4, 3, 3),
    ("_scripts/autolayer.rpy", 17, 2, 16),
    ("_scripts/characters.rpy", 65, 64, 117),
    ("_scripts/flags.rpy", 5, 4, 3),
    ("_scripts/preferences_screen.rpy", 30, 29, 4),
    ("bubble_screen_integration.rpy", 1, 0, 8),
)


def _make_config(tmp_path) -> Config:
    config = Config()
    config.input_folder = str(tmp_path / "input")
    config.output_folder = str(tmp_path / "output")
    config.renpy_backup_original = False
    return config


def _item(
    rel_path: str,
    row: int,
    src: str,
    dst: str,
    *,
    slot: int | None = None,
) -> CacheItem:
    """构造一条 RENPYSOURCE 条目；slot=None 模拟没有 renpy_source.literal_slot 的缓存。"""
    extra = ""
    if slot is not None:
        extra = {
            "renpy_source": {
                "line": row,
                "line_type": "STRING",
                "literal_slot": slot,
            }
        }
    return CacheItem(
        src=src,
        dst=dst,
        row=row,
        file_path=rel_path,
        file_type=CacheItem.FileType.RENPYSOURCE,
        text_type=CacheItem.TextType.RENPY,
        status=Base.TranslationStatus.TRANSLATED,
        extra_field=extra,
    )


def _write_pair(
    tmp_path,
    rel_path: str,
    source_text: str,
    output_text: str | None,
):
    """写入输入源码（写回参考行）与已翻译的输出文件。"""
    source = tmp_path / "input" / rel_path
    output = tmp_path / "output" / rel_path
    source.parent.mkdir(parents=True, exist_ok=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(source_text, encoding="utf-8")
    if output_text is not None:
        output.write_text(output_text, encoding="utf-8")
    return source, output


def _report_entry(tmp_path, rel_path: str) -> dict:
    report_path = tmp_path / "output" / REPORT_NAME
    report = json.loads(report_path.read_text(encoding="utf-8"))
    for entry in report:
        if entry["file"] == rel_path:
            return entry
    raise AssertionError(f"写回报告里没有 {rel_path}")


def _build_reinject_file(
    tmp_path,
    rel_path: str,
    translated: int,
    already_applied: int,
    skipped: int,
) -> list[CacheItem]:
    """按日志里的四个计数器造一个"已翻译过一遍"的文件。

    - already_applied 条：输出行已是译文，条目没有 literal_slot；
    - translated - already_applied 条：行号越界的陈旧条目；
    - 余下条目：只有颜色码、没有任何可译字符的条目（dst == src）。
    """
    source_lines: list[str] = []
    output_lines: list[str] = []
    items: list[CacheItem] = []

    for index in range(already_applied):
        row = len(source_lines) + 1
        source_lines.append(f'    narrator "Signal {index} remains."')
        output_lines.append(f'    narrator "信号 {index} 仍然存在。"')
        items.append(
            _item(rel_path, row, f"Signal {index} remains.", f"信号 {index} 仍然存在。")
        )

    # 只有颜色码的条目：无字符可译，dst 与 src 相同。
    benign_total = already_applied + skipped - translated
    for _index in range(benign_total):
        row = len(source_lines) + 1
        line = f'    text "{COLOR_ONLY_TEXT}"'
        source_lines.append(line)
        output_lines.append(line)
        items.append(_item(rel_path, row, COLOR_ONLY_TEXT, COLOR_ONLY_TEXT))

    # 陈旧条目：行号落在文件之外（缓存生成后原文件被删行）。
    stale_total = translated - already_applied
    base_row = len(source_lines) + 1
    for index in range(stale_total):
        items.append(
            _item(
                rel_path,
                base_row + index,
                f"Stale signal {index}.",
                f"陈旧信号 {index}。",
            )
        )

    _write_pair(
        tmp_path,
        rel_path,
        "\n".join(source_lines) + "\n",
        "\n".join(output_lines) + "\n",
    )
    return items


@pytest.mark.parametrize(
    "rel_path, translated, already_applied, skipped", REINJECT_LOG_CASES
)
def test_reinject_log_scenario_is_classified_instead_of_failing(
    tmp_path, rel_path, translated, already_applied, skipped
):
    items = _build_reinject_file(
        tmp_path, rel_path, translated, already_applied, skipped
    )

    # 复刻报障现场：写回不得抛错。
    RENPYSOURCE(_make_config(tmp_path)).write_to_path(items)

    entry = _report_entry(tmp_path, rel_path)
    assert entry["translated_items"] == translated
    assert entry["applied"] == 0
    assert entry["already_applied"] == already_applied
    assert entry["stale"] == translated - already_applied
    assert entry["untranslatable"] == already_applied + skipped - translated
    assert entry["no_translation"] == 0
    assert entry["skipped"] == skipped
    assert entry["unapplied"] == 0
    assert entry["unapplied_items"] == []
    assert entry["benign_samples"]


@pytest.mark.parametrize(
    "text",
    [
        COLOR_ONLY_TEXT,
        "{color=#a54a54a}{/color}",
        "#a54a54a",
        "{b}{/b}",
        "  ...?! 123  ",
    ],
)
def test_untranslatable_text_is_counted_without_error(tmp_path, text):
    rel_path = "fictional_tag_only.rpy"
    line = f'    text "{text}"'
    _write_pair(tmp_path, rel_path, line + "\n", line + "\n")

    RENPYSOURCE(_make_config(tmp_path)).write_to_path(
        [_item(rel_path, 1, text, text)]
    )

    entry = _report_entry(tmp_path, rel_path)
    assert entry["untranslatable"] == 1
    assert entry["no_translation"] == 0
    assert entry["unapplied"] == 0


def test_identical_destination_counts_as_no_translation(tmp_path):
    """dst 与 src 相同的普通条目：缓存里本来就没有译文，只计数不报错。"""
    rel_path = "fictional_untranslated.rpy"
    line = '    narrator "Plain fictional sentence."\n'
    _write_pair(tmp_path, rel_path, line, line)

    RENPYSOURCE(_make_config(tmp_path)).write_to_path(
        [_item(rel_path, 1, "Plain fictional sentence.", "Plain fictional sentence.")]
    )

    entry = _report_entry(tmp_path, rel_path)
    assert entry["no_translation"] == 1
    assert entry["untranslatable"] == 0
    assert entry["translated_items"] == 0
    assert entry["unapplied"] == 0


def test_out_of_range_row_counts_as_stale_without_error(tmp_path):
    rel_path = "fictional_stale_row.rpy"
    _write_pair(
        tmp_path,
        rel_path,
        '    narrator "One line only."\n',
        '    narrator "只有一行。"\n',
    )

    # 译文不在输出文件里，行号又越界：属于陈旧缓存，只计数不报错。
    RENPYSOURCE(_make_config(tmp_path)).write_to_path(
        [_item(rel_path, 99, "One line only.", "并不存在于该文件的译文。")]
    )

    entry = _report_entry(tmp_path, rel_path)
    assert entry["stale"] == 1
    assert entry["translated_items"] == 1
    assert entry["unapplied"] == 0


def test_row_drift_with_destination_already_in_file_is_reclassified(tmp_path):
    """行号漂了、但译文确实已在文件里：改判已生效，不报错也不进 needs_review。"""
    rel_path = "fictional_row_drift.rpy"
    _write_pair(
        tmp_path,
        rel_path,
        '    narrator "Drifted signal."\n',
        '    narrator "漂移信号。"\n',
    )

    RENPYSOURCE(_make_config(tmp_path)).write_to_path(
        [_item(rel_path, 99, "Drifted signal.", "漂移信号。")]
    )

    entry = _report_entry(tmp_path, rel_path)
    assert entry["stale"] == 0
    assert entry["already_applied"] == 1
    assert entry["unapplied"] == 0
    assert entry["needs_review"] == []
    # 先记过一条 stale 样例，取证改判后再追加一条 already_in_file；两条都保留是刻意的。
    assert [sample["kind"] for sample in entry["benign_samples"]] == [
        "stale",
        "already_in_file",
    ]


def test_needs_review_lists_translated_stale_item(tmp_path):
    rel_path = "fictional_review_stale.rpy"
    _write_pair(
        tmp_path,
        rel_path,
        '    narrator "Fresh line."\n',
        '    narrator "新鲜句子。"\n',
    )

    RENPYSOURCE(_make_config(tmp_path)).write_to_path(
        [_item(rel_path, 99, "Fresh line.", "文件里没有的译文。")]
    )

    entry = _report_entry(tmp_path, rel_path)
    assert entry["stale"] == 1
    assert entry["needs_review"] == [
        {
            "row": 99,
            "src": "Fresh line.",
            "dst": "文件里没有的译文。",
            "status": "TRANSLATED",
            "reason": "stale",
        }
    ]


def test_needs_review_ignores_untranslated_status(tmp_path):
    rel_path = "fictional_review_untranslated.rpy"
    _write_pair(
        tmp_path,
        rel_path,
        '    narrator "Fresh line."\n',
        '    narrator "新鲜句子。"\n',
    )
    item = _item(rel_path, 99, "Fresh line.", "文件里没有的译文。")
    item.set_status(Base.TranslationStatus.UNTRANSLATED)

    RENPYSOURCE(_make_config(tmp_path)).write_to_path([item])

    entry = _report_entry(tmp_path, rel_path)
    assert entry["stale"] == 1
    assert entry["needs_review"] == []


def test_needs_review_lists_unapplied_item(tmp_path):
    rel_path = "fictional_review_unapplied.rpy"
    _write_pair(
        tmp_path,
        rel_path,
        '    textbutton "Alpha" action Function(play, "X")\n',
        '    textbutton "Beta" action Function(play, "X")\n',
    )

    with pytest.raises(RuntimeError, match="译文未生效"):
        RENPYSOURCE(_make_config(tmp_path)).write_to_path(
            [_item(rel_path, 1, "Alpha", "甲")]
        )

    entry = _report_entry(tmp_path, rel_path)
    assert entry["unapplied"] == 1
    assert entry["needs_review"] == [
        {
            "row": 1,
            "src": "Alpha",
            "dst": "甲",
            "status": "TRANSLATED",
            "reason": "unapplied",
        }
    ]


def test_benign_leftovers_emit_warning(tmp_path, monkeypatch):
    rel_path = "fictional_warning.rpy"
    _write_pair(
        tmp_path,
        rel_path,
        '    narrator "One line only."\n',
        '    narrator "只有一行。"\n',
    )
    messages: list[str] = []
    monkeypatch.setattr(
        RENPYSOURCE,
        "warning",
        lambda self, message, *args, **kwargs: messages.append(message),
    )

    RENPYSOURCE(_make_config(tmp_path)).write_to_path(
        [_item(rel_path, 99, "One line only.", "并不存在于该文件的译文。")]
    )

    assert any("良性残留" in message for message in messages)


def test_changed_line_without_source_counts_as_stale(tmp_path):
    """输出行和原始行里都没有该原文：陈旧缓存，只计数不报错。"""
    rel_path = "fictional_rewritten.rpy"
    _write_pair(
        tmp_path,
        rel_path,
        '    narrator "A brand new line."\n',
        '    narrator "一条全新的句子。"\n',
    )

    RENPYSOURCE(_make_config(tmp_path)).write_to_path(
        [_item(rel_path, 1, "Old signal.", "旧信号。")]
    )

    entry = _report_entry(tmp_path, rel_path)
    assert entry["stale"] == 1
    assert entry["unapplied"] == 0


def test_reinject_with_recorded_slot_detects_already_applied(tmp_path):
    rel_path = "fictional_recorded_slot.rpy"
    line = '$ renpy.notify("Echo"); renpy.notify("Echo")\n'
    output_line = '$ renpy.notify("Echo"); renpy.notify("回声")\n'
    _, output = _write_pair(tmp_path, rel_path, line, output_line)

    # 有记载槽位时只看本槽位：第二个槽位已经是译文。
    RENPYSOURCE(_make_config(tmp_path)).write_to_path(
        [_item(rel_path, 1, "Echo", "回声", slot=1)]
    )

    entry = _report_entry(tmp_path, rel_path)
    assert entry["applied"] == 0
    assert entry["already_applied"] == 1
    assert entry["unapplied"] == 0
    assert output.read_text(encoding="utf-8") == output_line


def test_reinject_without_literal_slot_still_detects_already_applied(tmp_path):
    rel_path = "fictional_screen.rpy"
    _write_pair(
        tmp_path,
        rel_path,
        '    textbutton "Launch the beacon" action Function(play, "click")\n',
        '    textbutton "发射信标" action Function(play, "click")\n',
    )

    # 没有 renpy_source.literal_slot：只能靠行内容判定已生效。
    RENPYSOURCE(_make_config(tmp_path)).write_to_path(
        [_item(rel_path, 1, "Launch the beacon", "发射信标")]
    )

    entry = _report_entry(tmp_path, rel_path)
    assert entry["applied"] == 0
    assert entry["already_applied"] == 1
    assert entry["unapplied"] == 0


def test_reinject_matches_expected_rewrite_for_repeated_literal(tmp_path):
    rel_path = "fictional_echo.rpy"
    _write_pair(
        tmp_path,
        rel_path,
        '$ renpy.notify("Echo"); renpy.notify("Echo")\n',
        '$ renpy.notify("回声"); renpy.notify("Echo")\n',
    )

    # 同一行有两条相同原文、又没有槽位记录：按"原始行替换后应得的结果"判定。
    RENPYSOURCE(_make_config(tmp_path)).write_to_path(
        [_item(rel_path, 1, "Echo", "回声")]
    )

    entry = _report_entry(tmp_path, rel_path)
    assert entry["applied"] == 0
    assert entry["already_applied"] == 1
    assert entry["unapplied"] == 0


def test_second_item_on_same_row_is_not_reported_as_failure(tmp_path):
    rel_path = "fictional_duplicate_row.rpy"
    _write_pair(tmp_path, rel_path, '    narrator "Echo"\n', '    narrator "Echo"\n')

    RENPYSOURCE(_make_config(tmp_path)).write_to_path(
        [
            _item(rel_path, 1, "Echo", "回声一"),
            _item(rel_path, 1, "Echo", "回声二"),
        ]
    )

    entry = _report_entry(tmp_path, rel_path)
    assert entry["applied"] == 1
    assert entry["already_applied"] == 1
    assert entry["unapplied"] == 0


def test_real_unapplied_item_still_raises_with_samples(tmp_path):
    rel_path = "fictional_broken.rpy"
    _write_pair(
        tmp_path,
        rel_path,
        '    narrator "Original signal."\n',
        '    narrator "Unrelated signal."\n',
    )

    with pytest.raises(RuntimeError, match="译文未生效") as failure:
        RENPYSOURCE(_make_config(tmp_path)).write_to_path(
            [_item(rel_path, 1, "Original signal.", "原始信号。")]
        )

    message = str(failure.value)
    assert "unapplied=1" in message
    assert "1:Original signal.->原始信号。" in message

    entry = _report_entry(tmp_path, rel_path)
    assert entry["unapplied"] == 1
    assert entry["unapplied_items"] == [
        {"row": 1, "src": "Original signal.", "dst": "原始信号。"}
    ]


def test_successful_writes_survive_a_later_failure(tmp_path):
    rel_path = "fictional_partial.rpy"
    _, output = _write_pair(
        tmp_path,
        rel_path,
        '    narrator "First signal."\n    narrator "Original signal."\n',
        '    narrator "First signal."\n    narrator "Unrelated signal."\n',
    )

    with pytest.raises(RuntimeError, match="译文未生效"):
        RENPYSOURCE(_make_config(tmp_path)).write_to_path(
            [
                _item(rel_path, 1, "First signal.", "第一信号。"),
                _item(rel_path, 2, "Original signal.", "原始信号。"),
            ]
        )

    # 先写文件再抛错：已经成功的第 1 行不能丢。
    assert "第一信号。" in output.read_text(encoding="utf-8")
    entry = _report_entry(tmp_path, rel_path)
    assert entry["applied"] == 1
    assert entry["unapplied"] == 1
