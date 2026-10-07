"""工作台迁移的持久化边界：项目隔离、版本冲突和候选晋升。"""
from __future__ import annotations

import copy

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes.workbench import router
from module.Config import Config
from module.Engine.Translator.ProjectAssetsRepository import ProjectAssetsRepository
from module.Workbench.WorkbenchData import create_default_character_card


def _client(tmp_path, monkeypatch):
    # 本测试只验证项目资产，不启动翻译引擎或读写用户全局配置。
    monkeypatch.setattr(ProjectAssetsRepository, "_resolve_active_project", lambda self: None)
    project = tmp_path / "story"
    (project / "game" / "tl" / "chinese").mkdir(parents = True)
    config = Config()
    config.renpy_project_path = str(project)
    config.renpy_game_folder = str(project / "game")
    config.renpy_tl_folder = str(project / "game" / "tl" / "chinese")
    config.input_folder = config.renpy_tl_folder
    config.output_folder = str(project / "RenpyBox_Translation" / "chinese_new")
    config.cache_use_sqlite = False
    repository = ProjectAssetsRepository.from_config(config)
    repository.load(config)
    repository.replace_glossary([{"src": "city", "dst": "城邦", "case_sensitive": True}], enabled = True)
    config.renpy_workbench_worldbook_data = {"genre": "悬疑", "custom_context": "不可丢失的扩展背景"}
    config.renpy_workbench_character_cards = [create_default_character_card("Alice")]
    repository.save_workbench_view(config)
    app = FastAPI()
    app.state.config = config
    app.include_router(router)
    return TestClient(app), config, repository


def _edit(snapshot):
    return {key: copy.deepcopy(snapshot[key]) for key in (
        "storage_key", "revision", "characters", "worldbook_enabled", "characters_enabled",
    )} | {"worldbook": {"genre": "奇幻"}}


def test_workbench_saves_in_main_project_and_rejects_stale_or_other_project(tmp_path, monkeypatch):
    client, config, repository = _client(tmp_path, monkeypatch)
    snapshot = client.get("/api/workbench").json()
    body = _edit(snapshot)
    body['characters'][0]['identity'] = '城邦侦探'
    body['characters'].append(create_default_character_card('Bob'))
    body["characters_enabled"] = True
    saved = client.patch("/api/workbench", json = body)
    assert saved.status_code == 200
    latest = saved.json()
    persisted = repository.load()
    assert persisted.assets.worldbook.to_dict()["genre"] == "奇幻"
    assert persisted.assets.worldbook.to_dict()["custom_context"] == "不可丢失的扩展背景"
    assert persisted.assets.character_cards[0]['identity'] == '城邦侦探'
    assert len(persisted.assets.character_cards) == 2
    assert persisted.assets.glossary[0].target == "城邦"
    assert persisted.analysis_candidates["glossary_metadata"][persisted.assets.glossary[0].record_id]["case_sensitive"]
    assert config.renpy_workbench_worldbook_data["genre"] == "悬疑"
    assert (tmp_path / "story" / "RenpyBox_Translation" / "chinese" / "cache" / "project.json").exists()
    assert not (tmp_path / "story" / "RenpyBox_Translation" / "chinese_new" / "cache").exists()
    assert client.patch("/api/workbench", json = body).status_code == 409
    invalid = _edit(latest)
    invalid["characters"][0]["enabled"] = "false"
    assert client.patch('/api/workbench', json = invalid).status_code == 400
    deleted = _edit(latest)
    deleted['characters'] = deleted['characters'][:1]
    response = client.patch('/api/workbench', json = deleted)
    assert response.status_code == 200
    latest = response.json()
    assert len(repository.load().assets.character_cards) == 1
    (tmp_path / 'other' / 'game').mkdir(parents = True)
    config.renpy_project_path = str(tmp_path / 'other')
    config.renpy_game_folder = ""
    config.renpy_tl_folder = ""
    config.input_folder = ''
    config.output_folder = ''
    assert client.patch("/api/workbench", json = _edit(latest)).status_code == 409


def test_glossary_keeps_unseen_candidates_and_requires_explicit_confirmation(tmp_path, monkeypatch):
    client, _, repository = _client(tmp_path, monkeypatch)
    repository.merge_analysis_terms([{"source": "Alice", "target": "爱丽丝", "type": "角色", "case_sensitive": True}])
    snapshot = client.get("/api/workbench/glossary").json()
    alice = next(row for row in snapshot["rows"] if row["src"] == "Alice")
    assert alice["candidate"] and alice["dst"] == "爱丽丝"
    repository.merge_analysis_terms([{"source": "Bob", "target": "鲍勃"}])
    saved = client.patch("/api/workbench/glossary", json = snapshot)
    assert saved.status_code == 200
    snapshot = saved.json()
    assert next(row for row in snapshot["rows"] if row["src"] == "Alice")["candidate"]
    assert next(row for row in snapshot["rows"] if row["src"] == "Bob")["candidate"]
    alice = next(row for row in snapshot["rows"] if row["src"] == "Alice")
    alice["candidate_confirmed"] = True
    # 删除已见的 Bob 候选；保留后来出现的 Carol。
    snapshot["rows"] = [row for row in snapshot["rows"] if row["src"] != "Bob"]
    repository.merge_analysis_terms([{"source": "Carol", "target": "卡萝尔"}])
    promoted = client.patch("/api/workbench/glossary", json = snapshot).json()
    alice = next(row for row in promoted["rows"] if row["src"] == "Alice")
    assert not alice["candidate"] and alice["type"] == "角色" and alice["case_sensitive"]
    assert not any(row["src"] == "Bob" for row in promoted["rows"])
    assert next(row for row in promoted["rows"] if row["src"] == "Carol")["candidate"]


def test_draft_application_and_preview_reuse_real_asset_rules(tmp_path, monkeypatch):
    client, config, repository = _client(tmp_path, monkeypatch)
    config.renpy_workbench_generated_worldbook_draft = {"tone_style": "克制", "genre": ""}
    alice = create_default_character_card("Alice")
    alice["identity"] = "侦探"
    config.renpy_workbench_generated_character_drafts = [alice]
    repository.save_workbench_view(config)
    snapshot = client.get("/api/workbench").json()
    version = {"storage_key": snapshot["storage_key"], "revision": snapshot["revision"]}
    result = client.post("/api/workbench/apply-drafts", json = version)
    assert result.status_code == 200
    saved = result.json()
    assert saved["worldbook"]["genre"] == "悬疑"
    assert saved["worldbook"]["tone_style"] == "克制"
    assert saved["characters"][0]["identity"] == "侦探"
    assert not any(saved["worldbook_draft"].values()) and not saved["character_drafts"]
    version["revision"] = saved["revision"]
    preview = client.post("/api/workbench/preview", json = {**version, "sample": "Alice enters the city."})
    assert preview.status_code == 200
    assert preview.json()["matched_names"] == ["Alice"]
    assert "侦探" in preview.json()["context"] and "克制" in preview.json()["context"]