"""AI 清洗角色 / AI 复核关系的验收口径。

两条线各管一件事，谁都不许越界：
- 清洗只判断「谁是人」，把猫狗、报幕员、占位符丢掉，绝不动任何一条关系；
- 复核只处理规则挖出来的边，保留就换成 AI 边，否决就留档成 rejected 边，
  重扫不能让它复活，也绝不删除角色卡。
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes.workbench import (
    _apply_clean,
    _collect_rule_edges,
    _group_rule_edges,
    _merge_scan_drafts,
    router,
)
from module.Config import Config
from module.Engine.Translator.ProjectAssetsRepository import ProjectAssetsRepository
from module.Workbench.AnalysisService import WorkbenchAnalysisService
from module.Workbench.CharacterScanner import CharacterScanner
from module.Workbench.WorkbenchData import (
    RELATION_SOURCE_AI,
    RELATION_SOURCE_REJECTED,
    RELATION_SOURCE_RULE,
    create_default_character_card,
    merge_relations,
    normalize_relation,
    normalize_relation_chapters,
    normalize_relations,
)


def _card(name: str, relations: list[dict] | None = None, **extra) -> dict:
    card = create_default_character_card(name)
    card["relations"] = relations or []
    card.update(extra)
    return card


def _rule(target: str, relation: str, *, count: int = 1, samples: list[str] | None = None, category: str = "family") -> dict:
    return {
        "target": target,
        "relation": relation,
        "category": category,
        "note": "证据：" + ((samples or [])[0] if samples else ""),
        "source": RELATION_SOURCE_RULE,
        "count": count,
        "samples": list(samples or []),
    }


# --------------------------------------------------------------- 数据层规范
def test_relation_keeps_count_and_multiple_samples():
    item = normalize_relation({
        "target": "Bob",
        "relation": "姐妹",
        "count": 7,
        "samples": ["第一句", "", "第二句", "第三句", "第四句"],
    })
    assert item["count"] == 7
    # 最多三条、去空、保序。
    assert item["samples"] == ["第一句", "第二句", "第三句"]
    # 没写 count 的老数据按 1 条命中算，负数也退回 1。
    assert normalize_relation({"target": "Bob"})["count"] == 1
    assert normalize_relation({"target": "Bob", "count": -5})["count"] == 1


def test_normalize_relations_keeps_larger_count_when_duplicated():
    merged = normalize_relations([
        {"target": "Bob", "relation": "姐妹", "count": 2, "samples": ["甲"]},
        {"target": "bob", "relation": "姐妹", "count": 5, "samples": ["乙"]},
    ])
    assert len(merged) == 1
    assert merged[0]["count"] == 5
    assert merged[0]["samples"] == ["甲", "乙"]


def test_merge_relations_never_drops_rejected_edges():
    base = [{
        "target": "Bob",
        "relation": "姐妹",
        "category": "family",
        "note": "AI 否决：台词只是比喻",
        "source": RELATION_SOURCE_REJECTED,
        "count": 3,
        "samples": ["你不是我姐姐"],
    }]
    incoming = [_rule("Bob", "姐妹", count=9, samples=["叫姐姐"])]
    merged = merge_relations(base, incoming, RELATION_SOURCE_RULE)
    assert len(merged) == 1
    assert merged[0]["source"] == RELATION_SOURCE_REJECTED
    assert merged[0]["count"] == 3


# ----------------------------------------------------------- 重扫不复活否决边
def test_rescan_does_not_resurrect_rejected_edge():
    existing = [_card("Alice", [{
        "target": "Bob",
        "relation": "姐妹",
        "category": "family",
        "note": "AI 否决：台词只是比喻",
        "source": RELATION_SOURCE_REJECTED,
        "count": 2,
        "samples": ["你不是我姐姐"],
    }])]
    incoming = [_card("Alice", [_rule("Bob", "姐妹", count=4, samples=["叫姐姐"])])]
    merged = _merge_scan_drafts(existing, incoming)
    relations = merged[0]["relations"]
    assert len(relations) == 1
    assert relations[0]["source"] == RELATION_SOURCE_REJECTED
    # 否决边本身原样保留，不被新证据洗白。
    assert relations[0]["note"] == "AI 否决：台词只是比喻"


# ------------------------------------------------------------------ 清洗口径
def test_apply_clean_drops_noise_and_never_touches_relations():
    relations = [_rule("Bob", "姐妹", count=3, samples=["叫姐姐"])]
    cards = [
        _card("Alice", list(relations), is_primary=False),
        _card("A Cat", [_rule("Alice", "朋友", samples=["喵"])]),
    ]
    judged = {
        "alice": {"name": "Alice", "role": "main", "faction": "王家", "note": "贯穿全篇"},
        "a cat": {"name": "A Cat", "role": "noise", "faction": "", "note": "动物"},
    }
    kept, dropped, enriched = _apply_clean(cards, judged)
    assert dropped == 1 and enriched >= 1
    assert [card["name"] for card in kept] == ["Alice"]
    alice = kept[0]
    # 关系一条都没动，连 count/samples 都在。
    assert alice["relations"] == relations
    assert alice["relations"][0]["source"] == RELATION_SOURCE_RULE


def test_apply_clean_does_not_clear_manual_primary_flag():
    card = _card("Carol", [_rule("Alice", "朋友")], is_primary=True, faction="旧阵营")
    judged = {"carol": {"name": "Carol", "role": "side", "faction": "新阵营", "note": "配角"}}
    kept, dropped, _ = _apply_clean([card], judged)
    assert dropped == 0
    assert kept[0]["is_primary"] is True  # 人工勾过的主角标记不清 False
    assert kept[0]["faction"] == "旧阵营"  # 已有阵营不被覆盖
    assert kept[0]["relations"][0]["source"] == RELATION_SOURCE_RULE


def test_clean_prompt_marks_non_human_speakers_as_noise():
    service = WorkbenchAnalysisService()
    prompt = service.build_character_clean_prompt(
        [{"name": "A Cat", "lines": 30, "variable": "cat", "samples": ["喵……"]}],
        {"setting_summary": "校园"},
    )
    # 动物/报幕员这些必须明确归 noise，walkon 只留给有人类身份的路人。
    assert "noise" in prompt
    assert "动物" in prompt and "旁白" in prompt
    assert "猫" in prompt
    assert "不是人类就不是 walkon" in prompt
    # 清洗只说角色，不许它输出关系。
    assert "不要输出、评论或修改任何人物关系" in prompt


# --------------------------------------------------------------- 候选边整理
def test_collect_rule_edges_carries_real_count_and_samples():
    card = _card("Alice", [
        _rule("Bob", "姐妹", count=4, samples=["叫姐姐", "亲爱的姐姐"]),
        {"target": "Carol", "relation": "朋友", "category": "friendly", "note": "人定的", "source": "manual"},
        {"target": "Dave", "relation": "朋友", "category": "friendly", "note": "否决", "source": RELATION_SOURCE_REJECTED},
    ])
    edges = _collect_rule_edges([card])
    assert len(edges) == 1
    assert edges[0]["count"] == 4
    assert edges[0]["samples"] == ["叫姐姐", "亲爱的姐姐"]
    assert edges[0]["word"]  # 由 RELATION_WORDS 反查得到称谓词


def test_collect_rule_edges_does_not_double_count_formal_and_draft():
    """同一条边同时躺在正式资料和草稿里时只算一次，count 不能虚高。"""
    edge = _rule("Bob", "姐妹", count=3, samples=["叫姐姐"])
    formal = [_card("Alice", [dict(edge)])]
    draft = [_card("Alice", [dict(edge)])]
    edges = _collect_rule_edges(formal + draft)
    assert len(edges) == 1
    assert edges[0]["count"] == 3


def test_group_rule_edges_merges_same_pair():
    edges = _group_rule_edges([
        {"from": "Alice", "to": "Bob", "word": "sister", "relation": "姐妹", "category": "family", "count": 2, "samples": ["甲"]},
        {"from": "Alice", "to": "bob", "word": "friend", "relation": "朋友", "category": "friendly", "count": 3, "samples": ["乙"]},
    ])
    assert len(edges) == 1
    assert edges[0]["count"] == 5
    assert set(edges[0]["relations"]) == {"姐妹", "朋友"}
    assert edges[0]["samples"] == ["甲", "乙"]


# ------------------------------------------------------------- 复核端到端
def _client(tmp_path, monkeypatch, cards, drafts=None):
    monkeypatch.setattr(ProjectAssetsRepository, "_resolve_active_project", lambda self: None)
    project = tmp_path / "story"
    (project / "game" / "tl" / "chinese").mkdir(parents = True)
    config = Config()
    config.renpy_project_path = str(project)
    config.renpy_game_folder = str(project / "game")
    config.renpy_tl_folder = str(project / "game" / "tl" / "chinese")
    config.input_folder = config.renpy_tl_folder
    config.output_folder = str(project / "RenpyBox_Translation" / "chinese")
    config.cache_use_sqlite = False
    repository = ProjectAssetsRepository.from_config(config)
    repository.load(config)
    config.renpy_workbench_character_cards = cards
    config.renpy_workbench_generated_character_drafts = list(drafts or [])
    repository.save_workbench_view(config)
    app = FastAPI()
    app.state.config = config
    app.include_router(router)
    return TestClient(app), config


def _review(client, monkeypatch, verdicts):
    """用假的模型返回跑一次 /relations/analyze。"""
    monkeypatch.setattr(WorkbenchAnalysisService, "ensure_analysis_ready", lambda self, config, **kwargs: {})
    monkeypatch.setattr(
        WorkbenchAnalysisService,
        "request_json_text_verbose",
        lambda self, config, platform, prompt, **kwargs: (__import__("json").dumps(verdicts, ensure_ascii = False), 10, 5),
    )
    snapshot = client.get("/api/workbench").json()
    response = client.post(
        "/api/workbench/relations/analyze",
        json={"storage_key": snapshot["storage_key"], "revision": snapshot["revision"]},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _relations(response: dict, collection: str, name: str) -> list[dict]:
    return next(card for card in response["snapshot"][collection] if card["name"] == name)["relations"]


def test_review_keep_true_replaces_rule_edges_with_single_ai_edge(tmp_path, monkeypatch):
    cards = [
        _card("Alice", [
            _rule("Bob", "姐妹", count=3, samples=["叫姐姐"]),
            _rule("Bob", "朋友", count=2, samples=["我最好的朋友"]),
        ]),
        _card("Bob"),
    ]
    client, _ = _client(tmp_path, monkeypatch, cards)
    result = _review(client, monkeypatch, [
        {"from": "Alice", "to": "Bob", "relation": "姐妹", "category": "family", "keep": True, "reason": "证据成立"},
    ])
    relations = _relations(result, "characters", "Alice")
    assert len(relations) == 1
    assert relations[0]["source"] == RELATION_SOURCE_AI
    assert relations[0]["relation"] == "姐妹"
    assert relations[0]["count"] == 5
    assert set(relations[0]["samples"]) == {"叫姐姐", "我最好的朋友"}
    assert result["applied"] == 1 and result["rejected"] == 0


def test_review_keep_false_leaves_only_rejected_edges(tmp_path, monkeypatch):
    cards = [
        _card("Alice", [
            _rule("Bob", "姐妹", count=3, samples=["叫姐姐"]),
            _rule("Bob", "朋友", count=2, samples=["我最好的朋友"]),
        ]),
        _card("Bob"),
    ]
    client, _ = _client(tmp_path, monkeypatch, cards)
    result = _review(client, monkeypatch, [
        {"from": "Alice", "to": "Bob", "relation": "", "category": "", "keep": False, "reason": "台词是比喻"},
    ])
    relations = _relations(result, "characters", "Alice")
    # 一对人只算一次否决，但两个原关系词各自留档，且不再有规则边存活。
    assert result["rejected"] == 1 and result["applied"] == 0
    assert [item["source"] for item in relations] == [RELATION_SOURCE_REJECTED, RELATION_SOURCE_REJECTED]
    assert {item["relation"] for item in relations} == {"姐妹", "朋友"}
    assert all(item["note"].startswith("AI 否决：台词是比喻") for item in relations)
    # 角色卡一张都没少。
    assert {card["name"] for card in result["snapshot"]["characters"]} == {"Alice", "Bob"}


def test_review_reaches_rule_edges_that_live_in_drafts(tmp_path, monkeypatch):
    cards = [_card("Alice"), _card("Bob")]
    drafts = [_card("Alice", [_rule("Bob", "姐妹", count=2, samples=["叫姐姐"])])]
    client, _ = _client(tmp_path, monkeypatch, cards, drafts)
    result = _review(client, monkeypatch, [
        {"from": "Alice", "to": "Bob", "relation": "姐妹", "category": "family", "keep": True, "reason": "成立"},
    ])
    # 只写草稿，正式资料不动。
    draft_relations = _relations(result, "character_drafts", "Alice")
    assert [item["source"] for item in draft_relations] == [RELATION_SOURCE_AI]
    assert _relations(result, "characters", "Alice") == []
    assert result["applied"] == 1


def test_review_ignores_pairs_the_model_invented(tmp_path, monkeypatch):
    cards = [_card("Alice", [_rule("Bob", "姐妹", count=1, samples=["叫姐姐"])]), _card("Bob")]
    client, _ = _client(tmp_path, monkeypatch, cards)
    result = _review(client, monkeypatch, [
        {"from": "Alice", "to": "Carol", "relation": "朋友", "category": "friendly", "keep": True, "reason": "编的"},
    ])
    assert result["applied"] == 0 and result["rejected"] == 0
    # 原有规则边原封不动。
    assert [item["source"] for item in _relations(result, "characters", "Alice")] == [RELATION_SOURCE_RULE]


def test_review_accepts_scan_relations_that_survive_roundtrip(tmp_path, monkeypatch):
    """扫描产出的 count/samples 必须真的能存进项目文件再被复核读到。"""
    cards = [_card("Alice"), _card("Bob")]
    drafts = [_card("Alice", [{
        "target": "Bob",
        "relation": "姐妹",
        "category": "family",
        "note": "证据：叫姐姐",
        "source": RELATION_SOURCE_RULE,
        "count": 6,
        "samples": ["叫姐姐", "姐姐大人"],
    }])]
    client, config = _client(tmp_path, monkeypatch, cards, drafts)
    persisted = client.get("/api/workbench").json()
    alice = next(card for card in persisted["character_drafts"] if card["name"] == "Alice")
    assert alice["relations"][0]["count"] == 6
    assert alice["relations"][0]["samples"] == ["叫姐姐", "姐姐大人"]
    result = _review(client, monkeypatch, [
        {"from": "Alice", "to": "Bob", "relation": "姐妹", "category": "family", "keep": True, "reason": "成立"},
    ])
    assert _relations(result, "character_drafts", "Alice")[0]["count"] == 6


def test_scan_writes_count_and_samples_from_miner(tmp_path, monkeypatch):
    """mine_relations 直接把挖掘器的 count/samples 写进关系边。"""
    from module.Workbench import RelationMiner

    # RelationMiner.mine 是模块级函数（复用同一个挖掘器实例），不是类方法。
    monkeypatch.setattr(RelationMiner, "mine", lambda game_dir, names: [
        RelationMiner.RelationEvidence(
            from_name="Alice",
            to_name="Bob",
            relation="姐妹",
            category="family",
            count=8,
            samples=["叫姐姐", "姐姐大人", "我姐姐", "多余的第四条"],
        ),
    ])
    project = tmp_path / "story"
    (project / "game").mkdir(parents = True)
    scan = type("Scan", (), {"names": {"Alice", "Bob"}})()
    grouped = CharacterScanner.mine_relations(scan, project)
    edge = grouped["Alice"][0]
    assert edge["count"] == 8
    assert edge["samples"] == ["叫姐姐", "姐姐大人", "我姐姐"]
    assert edge["note"] == "证据：叫姐姐"


# ------------------------------------------------------------- 章节证据（时间线）
def test_relation_miner_records_chapters_in_natural_order(tmp_path):
    """挖掘器要按剧本文件记住命中分布：文件、行号、次数、证据，且自然序。"""
    from module.Workbench import RelationMiner

    # 故意先写 events10 再写 events2：自然序必须让 events2 排在前面。
    game = tmp_path / "game"
    game.mkdir()
    (game / "defs.rpy").write_text(
        'define mom = Character("Momoko")\ndefine airi = Character("Airi")\n',
        encoding = "utf-8",
    )
    (game / "events10.rpy").write_text(
        'label ch10:\n    airi "My mom is here."\n    airi "Mom again"\n    mom "yes"\n',
        encoding = "utf-8",
    )
    (game / "events2.rpy").write_text(
        'label ch2:\n    airi "I saw my mom today."\n    mom "Hello."\n',
        encoding = "utf-8",
    )

    rows = RelationMiner.mine(game, {"Momoko", "Airi"})
    assert len(rows) == 1
    row = rows[0]
    assert (row.from_name, row.to_name) == ("Airi", "Momoko")
    chapters = row.chapters
    # events2 在 events10 前面，这正是纯字典序做不到的地方。
    assert [item["file"] for item in chapters] == ["events2.rpy", "events10.rpy"]
    assert chapters[0]["count"] == 1
    assert chapters[0]["line"] == 2
    assert chapters[1]["count"] == 2
    assert chapters[1]["line"] == 2
    # 每个文件的证据最多 2 条，且都来自本文件。
    assert chapters[0]["samples"] == ["I saw my mom today."]
    assert chapters[1]["samples"] == ["My mom is here.", "Mom again"]
    # 总数仍然等于各章节之和。
    assert row.count == sum(item["count"] for item in chapters)


def test_normalize_relation_chapters_rejects_dirty_rows():
    chapters = normalize_relation_chapters([
        {"file": "", "count": 5},  # 没文件名，落不到列上
        {"file": "../escape.rpy"},  # 越界路径
        "not a dict",
        {"file": "events3.rpy", "line": 0, "count": 0, "samples": ["长" * 300, "长" * 300, "第三条"]},
        {"file": "events3.rpy", "line": 12, "count": 4, "samples": ["另一条"]},
    ])
    assert [item["file"] for item in chapters] == ["events3.rpy"]
    chapter = chapters[0]
    # 同文件合并：次数相加，行号取最早那次，证据去重截断且每条不超过 120 字。
    assert chapter["count"] == 5
    assert chapter["line"] == 1
    assert len(chapter["samples"]) == 2
    assert all(len(text) <= 120 for text in chapter["samples"])
    # 缺省给空列表，老数据不会因此报错。
    assert normalize_relation({"target": "Bob"})["chapters"] == []


def test_normalize_relation_chapters_caps_at_32_files():
    chapters = normalize_relation_chapters([
        {"file": f"events{index}.rpy", "count": index} for index in range(1, 41)
    ])
    assert len(chapters) == 32
    # 保留命中次数最多的那些，且输出仍是自然序。
    assert chapters[0]["file"] == "events9.rpy"
    assert chapters[-1]["file"] == "events40.rpy"


def test_group_rule_edges_merges_chapters():
    edges = _group_rule_edges([
        {
            "from": "Alice", "to": "Bob", "word": "sister", "relation": "姐妹", "category": "family",
            "count": 2, "samples": ["甲"],
            "chapters": [{"file": "events2.rpy", "line": 9, "count": 2, "samples": ["甲"]}],
        },
        {
            "from": "Alice", "to": "bob", "word": "friend", "relation": "朋友", "category": "friendly",
            "count": 3, "samples": ["乙"],
            "chapters": [
                {"file": "events10.rpy", "line": 7, "count": 3, "samples": ["乙"]},
                {"file": "events2.rpy", "line": 20, "count": 1, "samples": ["丙"]},
            ],
        },
    ])
    assert len(edges) == 1
    chapters = {item["file"]: item for item in edges[0]["chapters"]}
    assert [item["file"] for item in edges[0]["chapters"]] == ["events2.rpy", "events10.rpy"]
    # 同文件次数相加、行号取最早、证据去重。
    assert chapters["events2.rpy"]["count"] == 3
    assert chapters["events2.rpy"]["line"] == 9
    assert chapters["events2.rpy"]["samples"] == ["甲", "丙"]
    assert chapters["events10.rpy"]["count"] == 3


def test_review_keep_true_keeps_merged_chapters(tmp_path, monkeypatch):
    cards = [
        _card("Alice", [
            {
                **_rule("Bob", "姐妹", count=3, samples=["叫姐姐"]),
                "chapters": [{"file": "events2.rpy", "line": 9, "count": 3, "samples": ["叫姐姐"]}],
            },
            {
                **_rule("Bob", "朋友", count=2, samples=["我最好的朋友"]),
                "chapters": [{"file": "events10.rpy", "line": 7, "count": 2, "samples": ["我最好的朋友"]}],
            },
        ]),
        _card("Bob"),
    ]
    client, _ = _client(tmp_path, monkeypatch, cards)
    result = _review(client, monkeypatch, [
        {"from": "Alice", "to": "Bob", "relation": "姐妹", "category": "family", "keep": True, "reason": "成立"},
    ])
    relations = _relations(result, "characters", "Alice")
    assert len(relations) == 1
    assert relations[0]["source"] == RELATION_SOURCE_AI
    # 合成一条 AI 边，章节不能因此丢掉任何一列。
    assert [item["file"] for item in relations[0]["chapters"]] == ["events2.rpy", "events10.rpy"]
    assert {item["file"]: item["count"] for item in relations[0]["chapters"]} == {
        "events2.rpy": 3,
        "events10.rpy": 2,
    }


def test_review_keep_false_keeps_original_chapters(tmp_path, monkeypatch):
    chapters = [{"file": "events3.rpy", "line": 15, "count": 4, "samples": ["叫姐姐"]}]
    cards = [
        _card("Alice", [{**_rule("Bob", "姐妹", count=4, samples=["叫姐姐"]), "chapters": chapters}]),
        _card("Bob"),
    ]
    client, _ = _client(tmp_path, monkeypatch, cards)
    result = _review(client, monkeypatch, [
        {"from": "Alice", "to": "Bob", "relation": "", "category": "", "keep": False, "reason": "比喻"},
    ])
    relations = _relations(result, "characters", "Alice")
    assert [item["source"] for item in relations] == [RELATION_SOURCE_REJECTED]
    # 否决边保留原章节，用户还能回看「这条被否的证据出现在哪一章」。
    assert relations[0]["chapters"] == chapters


def test_relation_chapters_survive_project_snapshot(tmp_path, monkeypatch):
    """章节证据要真的能写进项目文件再读回来，否则前端永远拿不到。"""
    cards = [_card("Alice", [{
        "target": "Bob",
        "relation": "姐妹",
        "category": "family",
        "note": "证据：叫姐姐",
        "source": RELATION_SOURCE_RULE,
        "count": 4,
        "samples": ["叫姐姐"],
        "chapters": [
            {"file": "events2.rpy", "line": 9, "count": 3, "samples": ["叫姐姐"]},
            {"file": "events10.rpy", "line": 7, "count": 1, "samples": ["我的姐姐"]},
        ],
    }]), _card("Bob")]
    client, _ = _client(tmp_path, monkeypatch, cards)
    persisted = client.get("/api/workbench").json()
    alice = next(card for card in persisted["characters"] if card["name"] == "Alice")
    assert [item["file"] for item in alice["relations"][0]["chapters"]] == ["events2.rpy", "events10.rpy"]
    assert alice["relations"][0]["chapters"][0]["line"] == 9


def test_translation_snapshot_keeps_relation_chapters():
    """翻译快照的规范化过滤器必须透传 chapters，否则每次存盘都会抹掉时间线数据。"""
    from module.Engine.Translator.TranslationTaskContext import ProjectAssets

    card = {
        "id": "character_abc",
        "name": "Alice",
        "relations": [{
            "target": "Bob",
            "relation": "姐妹",
            "category": "family",
            "note": "证据：叫姐姐",
            "source": RELATION_SOURCE_RULE,
            "count": 4,
            "samples": ["叫姐姐"],
            "chapters": [{"file": "events2.rpy", "line": 9, "count": 3, "samples": ["叫姐姐"]}],
        }],
    }
    assets = ProjectAssets.from_dict({"character_cards": {"enabled": True, "items": [card]}})
    chapters = assets.to_dict()["character_cards"]["items"][0]["relations"][0]["chapters"]
    assert [item["file"] for item in chapters] == ["events2.rpy"]
    assert chapters[0]["line"] == 9 and chapters[0]["count"] == 3
    # 往返仍然相等（快照层的既有契约）。
    assert ProjectAssets.from_dict(assets.to_dict()) == assets
