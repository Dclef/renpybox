"""一条龙的词库准备阶段：Agent 术语 + 独立禁翻，失败不阻断。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from api.routes import onekey
from module.Config import Config
from module.Tool import LexiconOps


def test_lexicon_ops_module_is_imported():
    assert onekey.LexiconOps is LexiconOps


def _fake_state(items=None, glossary=None) -> SimpleNamespace:
    return SimpleNamespace(
        assets=SimpleNamespace(glossary=glossary or [], revision=1),
        analysis_candidates={"items": items or [], "glossary_metadata": {}},
    )


def _config(tmp_path) -> Config:
    # 词库阶段只在项目根内解析源码，测试必须放真实 .rpy 才能被扫到。
    game = tmp_path / "game"
    game.mkdir(parents = True, exist_ok = True)
    (game / "script.rpy").write_text('e "LUMA is here [hp]."', encoding = "utf-8")
    (game / "tl" / "chinese").mkdir(parents = True, exist_ok = True)
    config = Config()
    config.renpy_project_path = str(tmp_path)
    config.renpy_game_folder = str(game)
    config.renpy_tl_folder = str(game / "tl" / "chinese")
    # 本文件验证词库阶段本身，默认打开术语提取；关闭场景由用例显式传入。
    config.onekey_prepare_glossary = True
    config.save = lambda *args, **kwargs: None
    return config


def _patch_repository(monkeypatch, written: dict, items=None):
    class FakeRepository:
        has_storage = True
        output_folder = ""

        def load(self, config):
            return _fake_state(items)

        def merge_analysis_terms(self, entries):
            written.setdefault("merged", []).extend(dict(entry) for entry in entries)
            return {"items": []}

        def replace_analysis_terms(self, entries, removed_record_ids=()):
            written["replaced"] = list(entries)
            return {"items": []}

    monkeypatch.setattr(
        "module.Engine.Translator.ProjectAssetsRepository.ProjectAssetsRepository.from_config",
        classmethod(lambda cls, config: FakeRepository()),
    )


def _request(config):
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(config=config)))


def _noop_progress(message, percent=0, stage=None):
    return None


def test_prepare_stage_runs_agent_and_preserve(monkeypatch, tmp_path):
    config = _config(tmp_path)
    written: dict = {}
    _patch_repository(monkeypatch, written)
    monkeypatch.setattr(onekey, "_agent_platform", lambda config: ({"api_format": "OpenAI", "model": "m"}, ""))
    monkeypatch.setattr(
        onekey, "_confined_scan_paths",
        lambda config, scope_root: (tmp_path / "game", None),
    )
    monkeypatch.setattr(
        onekey.LexiconOps,
        "scan_preserve_variables",
        lambda config, cancel_check: {"entries": [{"src": "[hp]"}], "enabled": True},
    )

    captured: dict = {}

    def fake_extract(**kwargs):
        captured.update(kwargs)
        return {
            "entries": [{"src": "Carol"}, {"src": "Buy"}],
            "status": "completed",
            "warnings": [],
        }

    monkeypatch.setattr(
        "module.Extract.GlossaryCandidateService.extract_glossary_candidates",
        fake_extract,
    )

    report = onekey._prepare_lexicon_after_extract(
        _request(config), lambda: None, _noop_progress, config,
    )

    assert report["success"] is True, report
    assert report["glossary"]["status"] == "completed"
    assert report["glossary"]["added"] == 2
    assert report["preserve"]["status"] == "completed"
    assert report["preserve"]["added"] == 1
    # 只 merge 新候选，绝不 replace 覆盖已有条目。
    assert "replaced" not in written
    assert [item["src"] for item in written["merged"]] == ["Carol", "Buy"]
    assert captured["platform"]["model"] == "m"
    assert config.text_preserve_data == [{"src": "[hp]", "comment": ""}]


def test_prepare_stage_merges_all_agent_term_types(monkeypatch, tmp_path):
    config = _config(tmp_path)
    written: dict = {}
    _patch_repository(monkeypatch, written)
    monkeypatch.setattr(onekey, "_agent_platform", lambda config: ({"api_format": "OpenAI", "model": "m"}, ""))
    monkeypatch.setattr(
        onekey, "_confined_scan_paths",
        lambda config, scope_root: (tmp_path / "game", None),
    )
    monkeypatch.setattr(
        onekey.LexiconOps, "scan_preserve_variables",
        lambda config, cancel_check: {"entries": [], "enabled": False},
    )
    monkeypatch.setattr(
        "module.Extract.GlossaryCandidateService.extract_glossary_candidates",
        lambda **kwargs: {
            "entries": [
                {"src": "Carol", "type": "角色"},
                {"src": "East Square", "type": "地名"},
                {"src": "Silver Guild", "type": "组织"},
                {"src": "Moon Blade", "type": "物品"},
                {"src": "Mana Circle", "type": "术语"},
            ],
            "status": "completed",
            "warnings": [],
        },
    )

    report = onekey._prepare_lexicon_after_extract(
        _request(config), lambda: None, _noop_progress, config,
        prepare_preserve_enabled = False,
    )

    merged = {item["src"]: item["type"] for item in written["merged"]}
    # 一键选项是术语提取：非角色类型必须一并合并，不被角色筛选吃掉。
    assert set(merged) == {"Carol", "East Square", "Silver Guild", "Moon Blade", "Mana Circle"}
    assert merged["East Square"] == "候选 / 地名"
    assert merged["Silver Guild"] == "候选 / 组织"
    assert merged["Moon Blade"] == "候选 / 物品"
    assert merged["Carol"] == "候选 / 角色"
    assert report["glossary"]["added"] == 5


def test_prepare_stage_without_agent_marks_glossary_failed_but_preserve_runs(monkeypatch, tmp_path):
    config = _config(tmp_path)
    written: dict = {}
    _patch_repository(monkeypatch, written)
    monkeypatch.setattr(onekey, "_agent_platform", lambda config: (None, "尚未设定 Agent 接口"))
    monkeypatch.setattr(
        onekey.LexiconOps, "scan_preserve_variables",
        lambda config, cancel_check: {"entries": [{"src": "[hp]"}], "enabled": True},
    )

    report = onekey._prepare_lexicon_after_extract(
        _request(config), lambda: None, _noop_progress, config,
        scan_scope_root = str(tmp_path),
    )

    assert report["success"] is True
    assert report["glossary"]["status"] == "failed"
    assert report["glossary"]["added"] == 0
    assert report["preserve"]["status"] == "completed"
    assert any("Agent" in warning for warning in report["warnings"])
    assert "merged" not in written


def test_prepare_stage_skips_both_when_disabled(monkeypatch, tmp_path):
    config = _config(tmp_path)
    written: dict = {}
    _patch_repository(monkeypatch, written)
    monkeypatch.setattr(onekey, "_agent_platform", lambda config: ({"api_format": "OpenAI", "model": "m"}, ""))

    report = onekey._prepare_lexicon_after_extract(
        _request(config), lambda: None, _noop_progress, config,
        prepare_glossary_enabled = False,
        prepare_preserve_enabled = False,
    )

    assert report["glossary"]["status"] == "skipped"
    assert report["preserve"]["status"] == "skipped"
    assert written == {}


def test_prepare_stage_does_not_overwrite_existing_entries(monkeypatch, tmp_path):
    config = _config(tmp_path)
    written: dict = {}
    existing = [{"record_id": "r1", "source": "Carol", "target": "卡罗尔", "note": "手工"}]
    _patch_repository(monkeypatch, written, items=existing)
    monkeypatch.setattr(onekey, "_agent_platform", lambda config: ({"api_format": "OpenAI", "model": "m"}, ""))
    monkeypatch.setattr(
        onekey, "_confined_scan_paths",
        lambda config, scope_root: (tmp_path / "game", None),
    )
    monkeypatch.setattr(onekey.LexiconOps, "scan_preserve_variables", lambda config, cancel_check: {"entries": [], "enabled": False})
    monkeypatch.setattr(
        "module.Extract.GlossaryCandidateService.extract_glossary_candidates",
        lambda **kwargs: {
            "entries": [{"src": "Carol"}, {"src": "Zyx"}],
            "status": "completed",
            "warnings": [],
        },
    )

    report = onekey._prepare_lexicon_after_extract(
        _request(config), lambda: None, _noop_progress, config,
        prepare_preserve_enabled = False,
    )

    assert [item["src"] for item in written["merged"]] == ["Zyx"]
    assert report["glossary"]["added"] == 1


def test_prepare_stage_reselects_against_current_library_before_write(monkeypatch, tmp_path):
    """Agent 运行期间用户新增同 src：写盘前必须重读再筛，不能覆盖备注/重新启用。"""
    config = _config(tmp_path)
    written: dict = {}
    initial = _fake_state([])
    late = SimpleNamespace(
        assets = SimpleNamespace(glossary = [], revision = 2),
        analysis_candidates = {
            "items": [{"record_id": "late", "source": "Carol", "target": "", "enabled": False}],
            "glossary_metadata": {},
        },
    )
    calls = {"n": 0}

    class FakeRepository:
        has_storage = True
        output_folder = ""

        def load(self, config):
            calls["n"] += 1
            return late if calls["n"] > 1 else initial

        def merge_analysis_terms(self, entries):
            written.setdefault("merged", []).extend(dict(entry) for entry in entries)
            return {"items": []}

    monkeypatch.setattr(
        "module.Engine.Translator.ProjectAssetsRepository.ProjectAssetsRepository.from_config",
        classmethod(lambda cls, config: FakeRepository()),
    )
    monkeypatch.setattr(onekey, "_agent_platform", lambda config: ({"api_format": "OpenAI", "model": "m"}, ""))
    monkeypatch.setattr(
        onekey, "_confined_scan_paths",
        lambda config, scope_root: (tmp_path / "game", None),
    )
    monkeypatch.setattr(
        "module.Extract.GlossaryCandidateService.extract_glossary_candidates",
        lambda **kwargs: {"entries": [{"src": "Carol"}, {"src": "Zyx"}], "status": "completed", "warnings": []},
    )

    report = onekey._prepare_lexicon_after_extract(
        _request(config), lambda: None, _noop_progress, config,
        prepare_preserve_enabled = False,
    )

    assert [item["src"] for item in written["merged"]] == ["Zyx"]
    assert report["glossary"]["added"] == 1


def test_prepare_stage_preserves_concurrent_preserve_edits(monkeypatch, tmp_path):
    config = _config(tmp_path)
    config.text_preserve_data = [{"src": "[name]", "comment": "已有"}]
    written: dict = {}
    _patch_repository(monkeypatch, written)
    monkeypatch.setattr(onekey, "_agent_platform", lambda config: (None, "no agent"))
    monkeypatch.setattr(
        onekey.LexiconOps, "scan_preserve_variables",
        lambda config, cancel_check: {"entries": [{"src": "[name]"}, {"src": "[hp]"}], "enabled": True},
    )

    report = onekey._prepare_lexicon_after_extract(
        _request(config), lambda: None, _noop_progress, config,
        prepare_glossary_enabled = False,
        scan_scope_root = str(tmp_path),
    )

    assert report["preserve"]["added"] == 1
    srcs = [item["src"] for item in config.text_preserve_data]
    assert srcs == ["[name]", "[hp]"]
    assert config.text_preserve_data[0]["comment"] == "已有"


def test_prepare_stage_write_failure_reports_failed_with_zero(monkeypatch, tmp_path):
    config = _config(tmp_path)
    monkeypatch.setattr(onekey, "_agent_platform", lambda config: ({"api_format": "OpenAI", "model": "m"}, ""))
    monkeypatch.setattr(
        onekey, "_confined_scan_paths",
        lambda config, scope_root: (tmp_path / "game", None),
    )
    monkeypatch.setattr(
        "module.Extract.GlossaryCandidateService.extract_glossary_candidates",
        lambda **kwargs: {"entries": [{"src": "Zyx"}], "status": "completed", "warnings": []},
    )

    class BoomRepository:
        has_storage = True
        output_folder = ""

        def load(self, config):
            return _fake_state([])

        def merge_analysis_terms(self, entries):
            raise OSError("磁盘只读")

    monkeypatch.setattr(
        "module.Engine.Translator.ProjectAssetsRepository.ProjectAssetsRepository.from_config",
        classmethod(lambda cls, config: BoomRepository()),
    )

    report = onekey._prepare_lexicon_after_extract(
        _request(config), lambda: None, _noop_progress, config,
        prepare_preserve_enabled = False,
    )

    assert report["glossary"]["status"] == "failed"
    assert report["glossary"]["added"] == 0
    assert any("磁盘只读" in warning for warning in report["warnings"])


def test_prepare_stage_isolates_platform_exception_preserve_still_runs(monkeypatch, tmp_path):
    config = _config(tmp_path)
    written: dict = {}
    _patch_repository(monkeypatch, written)

    def boom(config):
        raise RuntimeError("平台配置损坏")

    monkeypatch.setattr(onekey, "_agent_platform", boom)
    monkeypatch.setattr(
        onekey.LexiconOps, "scan_preserve_variables",
        lambda config, cancel_check: {"entries": [{"src": "[hp]"}], "enabled": True},
    )

    report = onekey._prepare_lexicon_after_extract(
        _request(config), lambda: None, _noop_progress, config,
        scan_scope_root = str(tmp_path),
    )

    assert report["glossary"]["status"] == "failed"
    assert report["preserve"]["status"] == "completed"
    assert report["preserve"]["added"] == 1


def test_prepare_stage_isolates_repository_load_exception(monkeypatch, tmp_path):
    config = _config(tmp_path)
    monkeypatch.setattr(onekey, "_agent_platform", lambda config: ({"api_format": "OpenAI", "model": "m"}, ""))
    monkeypatch.setattr(
        onekey, "_confined_scan_paths",
        lambda config, scope_root: (tmp_path / "game", None),
    )
    monkeypatch.setattr(
        onekey.LexiconOps, "scan_preserve_variables",
        lambda config, cancel_check: {"entries": [{"src": "[hp]"}], "enabled": True},
    )

    class BadLoad:
        has_storage = True
        output_folder = ""

        def load(self, config):
            raise OSError("索引损坏")

    monkeypatch.setattr(
        "module.Engine.Translator.ProjectAssetsRepository.ProjectAssetsRepository.from_config",
        classmethod(lambda cls, config: BadLoad()),
    )

    report = onekey._prepare_lexicon_after_extract(
        _request(config), lambda: None, _noop_progress, config,
        scan_scope_root = str(tmp_path),
    )

    assert report["glossary"]["status"] == "failed"
    assert report["preserve"]["status"] == "completed"
    assert report["preserve"]["added"] == 1


def test_prepare_stage_skips_after_project_switch(monkeypatch, tmp_path):
    config = _config(tmp_path)
    other = Config()
    other.renpy_project_path = str(tmp_path / "elsewhere")
    written: dict = {}
    _patch_repository(monkeypatch, written, items=[])
    monkeypatch.setattr(onekey, "_agent_platform", lambda config: ({"api_format": "OpenAI", "model": "m"}, ""))
    monkeypatch.setattr(
        onekey, "_confined_scan_paths",
        lambda config, scope_root: (tmp_path / "game", None),
    )
    monkeypatch.setattr(
        "module.Extract.GlossaryCandidateService.extract_glossary_candidates",
        lambda **kwargs: {"entries": [{"src": "Carol"}], "status": "completed", "warnings": []},
    )

    report = onekey._prepare_lexicon_after_extract(
        _request(other), lambda: None, _noop_progress, config,
    )

    assert "merged" not in written
    assert report["glossary"]["status"] == "failed"
    assert any("项目已切换" in warning for warning in report["warnings"])


def test_prepare_stage_accepts_expected_identity(monkeypatch, tmp_path):
    """路径配置后传入的预期身份必须被接受，不能被误判成项目切换。"""
    config = _config(tmp_path)
    written: dict = {}
    _patch_repository(monkeypatch, written)
    monkeypatch.setattr(onekey, "_agent_platform", lambda config: ({"api_format": "OpenAI", "model": "m"}, ""))
    monkeypatch.setattr(
        onekey, "_confined_scan_paths",
        lambda config, scope_root: (tmp_path / "game", None),
    )
    monkeypatch.setattr(
        "module.Extract.GlossaryCandidateService.extract_glossary_candidates",
        lambda **kwargs: {"entries": [{"src": "Carol"}], "status": "completed", "warnings": []},
    )

    live = _config(tmp_path)
    live.input_folder = str(tmp_path / "new" / "chinese")
    report = onekey._prepare_lexicon_after_extract(
        _request(live), lambda: None, _noop_progress, config,
        prepare_preserve_enabled = False,
        expected_identity = onekey._project_identity(live),
    )

    assert report["glossary"]["status"] == "completed"
    assert [item["src"] for item in written["merged"]] == ["Carol"]


def test_glossary_write_failure_does_not_zero_preserve(monkeypatch, tmp_path):
    """术语写失败只影响术语这一路，禁翻照常写入并保留真实计数。"""
    config = _config(tmp_path)
    monkeypatch.setattr(onekey, "_agent_platform", lambda config: ({"api_format": "OpenAI", "model": "m"}, ""))
    monkeypatch.setattr(
        onekey, "_confined_scan_paths",
        lambda config, scope_root: (tmp_path / "game", None),
    )
    monkeypatch.setattr(
        onekey.LexiconOps, "scan_preserve_variables",
        lambda config, cancel_check: {"entries": [{"src": "[hp]"}], "enabled": True},
    )
    monkeypatch.setattr(
        "module.Extract.GlossaryCandidateService.extract_glossary_candidates",
        lambda **kwargs: {"entries": [{"src": "Carol"}], "status": "completed", "warnings": []},
    )

    class BoomRepository:
        has_storage = True
        output_folder = ""

        def load(self, config):
            return _fake_state([])

        def merge_analysis_terms(self, entries):
            raise OSError("术语库只读")

    monkeypatch.setattr(
        "module.Engine.Translator.ProjectAssetsRepository.ProjectAssetsRepository.from_config",
        classmethod(lambda cls, config: BoomRepository()),
    )

    report = onekey._prepare_lexicon_after_extract(
        _request(config), lambda: None, _noop_progress, config,
        prepare_glossary_enabled = True,
        prepare_preserve_enabled = True,
    )

    assert report["glossary"]["status"] == "failed"
    assert report["glossary"]["added"] == 0
    assert report["preserve"]["status"] == "completed", "术语失败不得阻断禁翻"
    assert report["preserve"]["added"] == 1
    assert [item["src"] for item in config.text_preserve_data] == ["[hp]"]


def test_preserve_write_failure_keeps_glossary_success(monkeypatch, tmp_path):
    """禁翻写失败只影响禁翻这一路，术语的完成状态与计数必须保留。"""
    config = _config(tmp_path)
    written: dict = {}
    _patch_repository(monkeypatch, written)
    monkeypatch.setattr(onekey, "_agent_platform", lambda config: ({"api_format": "OpenAI", "model": "m"}, ""))
    monkeypatch.setattr(
        onekey, "_confined_scan_paths",
        lambda config, scope_root: (tmp_path / "game", None),
    )
    monkeypatch.setattr(
        onekey.LexiconOps, "scan_preserve_variables",
        lambda config, cancel_check: {"entries": [{"src": "[hp]"}], "enabled": True},
    )
    monkeypatch.setattr(
        "module.Extract.GlossaryCandidateService.extract_glossary_candidates",
        lambda **kwargs: {"entries": [{"src": "Carol"}, {"src": "East Square"}],
            "status": "completed", "warnings": []},
    )

    original_persist = onekey._persist_fields

    def boom_persist(live, values):
        if "text_preserve_data" in values:
            raise OSError("禁翻表只读")
        return original_persist(live, values)

    monkeypatch.setattr("api.routes.onekey._persist_fields", boom_persist)

    report = onekey._prepare_lexicon_after_extract(
        _request(config), lambda: None, _noop_progress, config,
        prepare_glossary_enabled = True,
        prepare_preserve_enabled = True,
    )

    assert report["glossary"]["status"] == "completed", "禁翻失败不得把术语标失败"
    assert report["glossary"]["added"] == 2, "已成功的术语计数不能被清零"
    assert [item["src"] for item in written["merged"]] == ["Carol", "East Square"]
    assert report["preserve"]["status"] == "failed"
    assert report["preserve"]["added"] == 0


def test_preserve_write_keeps_full_existing_rows(monkeypatch, tmp_path):
    """落盘合并必须保留已有行的 enabled / regex / 嵌套字段。"""
    config = _config(tmp_path)
    config.text_preserve_data = [
        {
            "src": "[name]",
            "comment": "手工备注",
            "enabled": False,
            "regex": True,
            "metadata": {"owner": "user"},
        }
    ]
    written: dict = {}
    _patch_repository(monkeypatch, written)
    monkeypatch.setattr(onekey, "_agent_platform", lambda config: (None, "no agent"))
    monkeypatch.setattr(
        onekey.LexiconOps, "scan_preserve_variables",
        lambda config, cancel_check: {"entries": [{"src": "[hp]"}], "enabled": True},
    )

    report = onekey._prepare_lexicon_after_extract(
        _request(config), lambda: None, _noop_progress, config,
        prepare_glossary_enabled = False,
        prepare_preserve_enabled = True,
        scan_scope_root = str(tmp_path),
    )

    assert report["preserve"]["added"] == 1
    assert config.text_preserve_data[0] == {
        "src": "[name]",
        "comment": "手工备注",
        "enabled": False,
        "regex": True,
        "metadata": {"owner": "user"},
    }
    assert [item["src"] for item in config.text_preserve_data] == ["[name]", "[hp]"]


def test_prepared_config_drives_scanning(monkeypatch, tmp_path):
    """传入 prepared_config 时，扫描与扫描平台都必须来自它而不是旧 config。"""
    stale = _config(tmp_path / "old")
    fresh_root = tmp_path / "fresh"
    fresh = _config(fresh_root)
    seen: dict = {}

    def fake_scan(config, scope_root):
        seen["resolved_game"] = getattr(config, "renpy_game_folder", "")
        seen["scope_root"] = scope_root
        return fresh_root / "game", None

    monkeypatch.setattr(onekey, "_confined_scan_paths", fake_scan)
    monkeypatch.setattr(
        onekey, "_agent_platform",
        lambda config: (seen.__setitem__("platform_game", getattr(config, "renpy_game_folder", "")),
            ({"api_format": "OpenAI", "model": "m"}, ""))[-1],
    )
    monkeypatch.setattr(
        "module.Extract.GlossaryCandidateService.extract_glossary_candidates",
        lambda **kwargs: {"entries": [{"src": "Carol"}], "status": "completed", "warnings": []},
    )
    monkeypatch.setattr(
        onekey, "_confined_scan_paths",
        lambda config, scope_root: fake_scan(config, scope_root),
    )
    written: dict = {}
    _patch_repository(monkeypatch, written)

    onekey._prepare_lexicon_after_extract(
        _request(fresh), lambda: None, _noop_progress, stale,
        prepare_glossary_enabled = True,
        prepare_preserve_enabled = False,
        prepared_config = fresh,
        scan_scope_root = str(fresh_root),
    )

    assert seen["resolved_game"] == str(fresh_root / "game")
    assert seen["platform_game"] == str(fresh_root / "game")
    assert seen["scope_root"] == str(fresh_root)


def test_prepare_safely_maps_interrupted_to_cancelled(monkeypatch, tmp_path):
    import asyncio

    config = _config(tmp_path)
    body = SimpleNamespace(prepare_glossary = True, prepare_lexicon = True)

    def boom(*args, **kwargs):
        raise InterruptedError("stopped")

    monkeypatch.setattr(onekey, "_prepare_lexicon_after_extract", boom)

    with pytest.raises(asyncio.CancelledError):
        onekey._prepare_lexicon_safely(
            _request(config), lambda: None, _noop_progress, config, body,
        )


def test_prepare_safely_degrades_regular_error(monkeypatch, tmp_path):
    config = _config(tmp_path)
    body = SimpleNamespace(prepare_glossary = True, prepare_lexicon = True)

    def boom(*args, **kwargs):
        raise OSError("boom")

    monkeypatch.setattr(onekey, "_prepare_lexicon_after_extract", boom)

    report = onekey._prepare_lexicon_safely(
        _request(config), lambda: None, _noop_progress, config, body,
    )

    assert report["success"] is True
    assert report["glossary"]["status"] == "failed"
    assert report["glossary"]["added"] == 0
    assert any("boom" in warning for warning in report["warnings"])


def test_character_button_still_role_only():
    """独立「Agent 提取人名」入口保持仅角色，不受一键术语改动影响。"""
    import inspect

    from module.Extract import GlossaryCandidateService as service_module

    source = inspect.getsource(service_module.extract_character_candidates)
    assert "character_only = True" in source
    glossary_source = inspect.getsource(service_module.extract_glossary_candidates)
    assert "character_only" not in glossary_source
