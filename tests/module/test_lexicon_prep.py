"""一条龙的词库预处理：术语交给 Agent，禁翻表保留结构扫描。"""

from __future__ import annotations

import pytest

from module.OneKey import lexicon_prep as prep


def test_prepare_glossary_only_adds_missing_src():
    payload = {
        "status": "completed",
        "entries": [
            {"src": "Airi", "type": "角色"},
            {"src": "Dark Forest", "type": "地名"},
            {"src": "Rose", "type": "角色"},
        ],
        "warnings": [],
    }
    existing = [
        {"src": "Airi", "dst": "爱理", "comment": "手工译名", "enabled": False},
        {"src": "Manual", "dst": "人工", "candidate": False},
    ]

    result = prep.prepare_glossary(
        object(), existing, extract=lambda: payload
    )

    assert result.status == "completed"
    # 已存在的 src 一律不返回，避免覆盖译名/备注或重新启用禁用项。
    assert [item["src"] for item in result.entries] == ["Dark Forest", "Rose"]
    assert result.added == 2
    assert result.kept_existing == 2
    assert result.changed is True


def test_prepare_glossary_partial_keeps_available_candidates():
    payload = {
        "status": "partial",
        "entries": [{"src": "Zyx", "type": "角色"}],
        "warnings": ["第 2 块未能取得结果"],
    }

    result = prep.prepare_glossary(object(), [], extract=lambda: payload)

    assert result.status == "partial"
    assert result.added == 1
    assert result.warnings == ["第 2 块未能取得结果"]


def test_prepare_glossary_failed_reports_warning_without_raising():
    payload = {"status": "failed", "entries": [], "warnings": ["尚未设定 Agent 接口"]}

    result = prep.prepare_glossary(object(), [], extract=lambda: payload)

    assert result.status == "failed"
    assert result.entries == []
    assert result.added == 0
    assert "Agent 接口" in result.error
    assert "Agent 接口" in result.summary()


def test_prepare_glossary_extract_exception_becomes_failed():
    def boom():
        raise OSError("模拟网络中断")

    result = prep.prepare_glossary(object(), [], extract=boom)

    assert result.status == "failed"
    assert "网络中断" in result.error
    assert result.entries == []


def test_prepare_glossary_without_channel_is_failed():
    result = prep.prepare_glossary(object(), [], extract=None)

    assert result.status == "failed"
    assert result.entries == []


def test_prepare_glossary_disabled_returns_skipped():
    result = prep.prepare_glossary(object(), [{"src": "Airi"}], enabled=False)

    assert result.status == "skipped"
    assert result.entries == []
    assert result.changed is False
    assert result.summary() == "术语提取已跳过"


def test_prepare_glossary_propagates_cancel():
    def cancelled() -> bool:
        return True

    with pytest.raises(InterruptedError):
        prep.prepare_glossary(
            object(), [], extract=lambda: {"status": "completed", "entries": []},
            cancel_check = cancelled,
        )


def test_build_candidate_rows_keeps_source_text_and_type():
    rows = prep.build_candidate_rows(
        [{"src": "NORA", "type": "角色", "comment": "来自第 3 块"}]
    )

    assert rows[0]["src"] == "NORA"
    assert rows[0]["type"] == "候选 / 角色"
    assert rows[0]["comment"] == "来自第 3 块"
    assert rows[0]["candidate"] is True
    assert rows[0]["candidate_confirmed"] is False


def test_select_new_entries_dedupes_batch_and_known():
    rows = prep.build_candidate_rows(
        [{"src": "Airi"}, {"src": "airi"}, {"src": "Manual"}, {"src": "Zyx"}]
    )

    fresh = prep.select_new_entries(rows, {"manual"})

    assert [item["src"] for item in fresh] == ["Airi", "Zyx"]


def test_merge_preserve_entries_copies_existing_rows_verbatim():
    """已有行必须完整复制：enabled / regex / 嵌套 metadata 都不能丢。"""
    existing = [
        {
            "src": "[name]",
            "comment": "手工备注",
            "enabled": False,
            "regex": True,
            "metadata": {"owner": "user", "hits": 3},
        },
        {"src": "[hp]", "comment": "", "enabled": True},
    ]

    merged, added = prep.merge_preserve_entries(existing, [{"src": "[mp]"}])

    assert added == 1
    assert merged[0] == existing[0], "已有行必须原样保留（含嵌套字段）"
    assert merged[0]["enabled"] is False
    assert merged[0]["regex"] is True
    assert merged[0]["metadata"] == {"owner": "user", "hits": 3}
    assert merged[1] == existing[1]
    assert merged[2] == {"src": "[mp]", "comment": ""}


def test_merge_preserve_entries_does_not_mutate_input():
    existing = [
        {"src": "[name]", "enabled": False, "metadata": {"k": [1, 2]}},
    ]

    merged, _added = prep.merge_preserve_entries(existing, [])

    assert merged[0] is not existing[0]
    merged[0]["enabled"] = True
    assert existing[0]["enabled"] is False, "不得就地修改调用方的数据"

def test_prepare_preserve_merges_without_duplicates(monkeypatch):
    monkeypatch.setattr(
        prep.LexiconOps,
        "scan_preserve_variables",
        lambda config, cancel_check: {
            "entries": [{"src": "[name]"}, {"src": "[hp]"}],
            "enabled": True,
        },
    )

    result = prep.prepare_preserve(object(), [{"src": "[name]", "comment": "已有"}])

    assert result.status == "completed"
    assert result.added == 1
    assert [item["src"] for item in result.entries] == ["[name]", "[hp]"]
    assert result.entries[0]["comment"] == "已有"
    assert result.scanned == 2


def test_prepare_preserve_disabled_returns_skipped():
    result = prep.prepare_preserve(object(), [{"src": "[name]"}], enabled=False)

    assert result.status == "skipped"
    assert result.entries == []
    assert result.added == 0


def test_prepare_preserve_failure_is_reported_not_raised(monkeypatch):
    def boom(config, cancel_check):
        raise OSError("扫描失败")

    monkeypatch.setattr(prep.LexiconOps, "scan_preserve_variables", boom)

    result = prep.prepare_preserve(object(), [{"src": "[name]"}])

    assert result.status == "failed"
    assert "扫描失败" in result.error
    assert result.added == 0
