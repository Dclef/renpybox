"""一条龙的词库准备阶段必须真正跑到，不能被 NameError 悄悄降级。

回归：``_prepare_lexicon_after_extract`` 里用 ``LexiconOps.xxx`` 调用，但模
块只按名字导入过成员、没导入模块本身，于是每次都抛 ``NameError``，被外层
``except Exception`` 吞成「词库准备失败」。抽取本身成功，测试全绿，用户却
永远拿不到自动术语候选（2026-10-18）。
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from api.routes import onekey
from module.Config import Config
from module.Tool import LexiconOps


def test_lexicon_ops_module_is_imported():
    assert onekey.LexiconOps is LexiconOps


def _fake_state() -> SimpleNamespace:
    carol = SimpleNamespace(
        to_dict=lambda: {"source": "Carol", "target": "", "note": "自动提取 / character", "record_id": "c1"}
    )
    return SimpleNamespace(
        assets=SimpleNamespace(glossary=[]),
        analysis_candidates={"items": [carol], "glossary_metadata": {"c1": {"type": "角色"}}},
    )


def test_prepare_lexicon_stage_reports_success(monkeypatch, tmp_path):
    config = Config()
    config.renpy_project_path = str(tmp_path)
    config.renpy_game_folder = str(tmp_path / "game")
    config.renpy_tl_folder = str(tmp_path / "game" / "tl" / "chinese")
    config.save = lambda *args, **kwargs: None

    written: dict = {}

    class FakeRepository:
        has_storage = True

        def load(self, config):
            return _fake_state()

        def replace_analysis_terms(self, entries, removed_record_ids=()):
            written["entries"] = entries
            written["removed"] = removed_record_ids
            return []

    monkeypatch.setattr(
        "module.Engine.Translator.ProjectAssetsRepository.ProjectAssetsRepository.from_config",
        classmethod(lambda cls, config: FakeRepository()),
    )
    monkeypatch.setattr(onekey.LexiconOps, "resolve_renpy_scan_paths", lambda config: (tmp_path / "game", tmp_path / "game" / "tl" / "chinese"))
    monkeypatch.setattr(onekey.LexiconOps, "extract_names_from_source", lambda source, cancel: {"Carol", "Buy"})
    monkeypatch.setattr(onekey.LexiconOps, "extract_names_from_miss_files", lambda source, tl, cancel: set())
    monkeypatch.setattr(onekey.LexiconOps, "effective_tl_name", lambda config, tl_root: "chinese")
    monkeypatch.setattr(
        "module.OneKey.lexicon_prep.prepare_preserve",
        lambda config, existing, cancel_check=None, enabled=True: SimpleNamespace(
            entries=[], added=0, scanned=0, summary=lambda: "禁翻库：未变动",
        ),
    )

    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(config=config)))
    report = onekey._prepare_lexicon_after_extract(
        request, lambda: None, lambda message, percent=0, stage=None: None, config,
    )

    assert report["success"] is True, report
    assert report["glossary"]["scanned"] == 2
    # 「Buy」被过滤掉，只剩真名字写进库。
    assert [item["src"] for item in written["entries"]] == ["Carol"]
    assert "message" in report


def test_prepare_lexicon_skips_after_project_switch(monkeypatch, tmp_path):
    config = Config()
    config.renpy_project_path = str(tmp_path)
    other = Config()
    other.renpy_project_path = str(tmp_path / "elsewhere")

    monkeypatch.setattr(onekey.LexiconOps, "resolve_renpy_scan_paths", lambda config: (None, None))
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(config=other)))
    report = onekey._prepare_lexicon_after_extract(
        request, lambda: None, lambda message, percent=0, stage=None: None, config,
    )
    assert report["success"] is False
    assert "项目已切换" in report["message"]
