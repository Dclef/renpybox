"""一条龙的术语库 / 禁翻库预处理规则。"""

from __future__ import annotations

from module.OneKey import lexicon_prep as prep


def test_looks_like_term_keeps_proper_nouns():
    for value in ("Airi", "Akari", "Dark Forest", "Fist of the Wind", "The Book of Time"):
        assert prep.looks_like_term(value) is True, value


def test_looks_like_term_rejects_noise():
    # 界面按钮、动作、整句、纯符号都进过候选表（2026-10-18 用户反馈）。
    for value in ("Buy", "Calculate Progress", "Everyone", "Villager", "unknown", "Hello!", "12345", "!@#$"):
        assert prep.looks_like_term(value) is False, value


def test_filter_not_terms_spares_manual_entries():
    kept, removed = prep.filter_not_terms([
        {"src": "Buy", "candidate": True},
        {"src": "Buy", "candidate": False, "dst": "购买"},
        {"src": "Airi", "candidate": True},
    ])
    assert removed == 1
    assert [item["src"] for item in kept] == ["Buy", "Airi"]
    assert kept[0]["candidate"] is False


def test_dedupe_entries_prefers_manual_and_counts_removed():
    merged, removed = prep.dedupe_entries([
        {"src": "Airi", "candidate": True},
        {"src": "airi", "candidate": True},
        {"src": "Airi", "candidate": False, "dst": "爱理"},
        {"src": "Dark Forest", "candidate": True},
    ])
    srcs = sorted((item["src"].casefold(), bool(item.get("candidate"))) for item in merged)
    # 两个自动候选合并成一条，又被同名人工条目挤掉，共去掉 2 条。
    assert removed == 2
    # 人工条目优先保留，自动候选的同名词条让位。
    assert ("airi", False) in srcs
    assert ("dark forest", True) in srcs


def test_prepare_glossary_reports_counts():
    result = prep.prepare_glossary(
        object(),
        [{"src": "Buy", "candidate": True}, {"src": "Manual", "candidate": False, "dst": "人工"}],
        scan_names=lambda: {"Airi", "Buy", "Villager"},
    )
    assert result.scanned == 3
    assert result.kept_existing == 1
    assert result.removed_not_term >= 1
    assert result.changed is True
    srcs = {item["src"] for item in result.entries}
    assert "Airi" in srcs
    assert "Buy" not in srcs
    # 人工条目由调用方保留，不混进候选结果。
    assert "Manual" not in srcs


def test_prepare_glossary_disabled_returns_empty():
    result = prep.prepare_glossary(object(), [{"src": "Airi", "candidate": True}], enabled=False)
    assert result.entries == []
    assert result.changed is False


def test_prepare_preserve_merges_without_duplicates(monkeypatch):
    monkeypatch.setattr(
        prep.LexiconOps,
        "scan_preserve_variables",
        lambda config, cancel_check: {"entries": [{"src": "[name]"}, {"src": "[hp]"}], "enabled": True},
    )
    result = prep.prepare_preserve(object(), [{"src": "[name]", "comment": "已有"}])
    assert result.added == 1
    assert [item["src"] for item in result.entries] == ["[name]", "[hp]"]
    assert result.scanned == 2


def test_prepare_preserve_disabled_returns_empty():
    result = prep.prepare_preserve(object(), [{"src": "[name]"}], enabled=False)
    assert result.entries == []
    assert result.added == 0
