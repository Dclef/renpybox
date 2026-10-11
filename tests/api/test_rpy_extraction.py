"""RPY 抽取设置 API：分类隔离、proof 上下文、分页、busy409（tmp RuleStore）。"""

from __future__ import annotations

import copy
import threading
import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.jobs import JobManager
from api.routes.jobs import router as jobs_router
from api.routes.rpy_extraction import router, starter_profile
from module.Config import Config
from module.Engine.Engine import Engine
from module.Extract.GameExtractionRules import RuleError, RuleStore, project_key


@pytest.fixture
def rpy_app(tmp_path, monkeypatch):
    project, game = _make_project(tmp_path)
    config = Config()
    _bind(config, project)
    engine = Engine()
    monkeypatch.setattr(Engine, "get", classmethod(lambda cls: engine))
    app = FastAPI()
    app.state.config = config
    app.state.jobs = JobManager()
    app.state.rpy_rule_store_path = tmp_path / "game_extraction_profiles.json"
    app.state.rpy_scan_sessions = {}
    app.include_router(router)
    app.include_router(jobs_router)
    with TestClient(app) as client:
        yield client, config, engine, project, game, app
        app.state.jobs.shutdown()


def _make_project(root: Path) -> tuple[Path, Path]:
    project = root / "Demo"
    game = project / "game"
    tl = game / "tl" / "chinese"
    tl.mkdir(parents=True)
    (game / "scene.rpy").write_text('e "Hello."\n"Continue":\ntext "Start"\n', encoding="utf-8")
    (tl / "scene.rpy").write_text(
        'translate chinese strings:\n    old "Hello."\n    new ""\n',
        encoding="utf-8",
    )
    return project, game


def _make_tl_many(project: Path, language: str, count: int) -> Path:
    folder = project / "game" / "tl" / language
    folder.mkdir(parents=True, exist_ok=True)
    body = f"translate {language} strings:\n" + "".join(
        f'    old "{language.title()} {index}"\n    new ""\n' for index in range(count)
    )
    (folder / "scene.rpy").write_text(body, encoding="utf-8")
    return folder


def _bind(config: Config, project: Path) -> None:
    game = project / "game"
    config.renpy_project_path = str(project)
    config.renpy_game_folder = str(game)
    config.renpy_tl_folder = str(game / "tl" / "chinese")
    config.input_folder = str(game / "tl" / "chinese")
    config.output_folder = ""


def _finish(client, job_id, timeout=20.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        result = job.get("result") or {}
        if job["status"] in {"done", "failed", "cancelled"} and not result.get("worker_active"):
            return job
        time.sleep(0.02)
    pytest.fail(f"任务未结束：{job}")


def _ctx(project: Path, category="source", language="chinese", **extra):
    return {
        "project_key": project_key(project),
        "path": str(project),
        "category": category,
        "language": language,
        **extra,
    }


def _preview_until_done(client, project, profile, category="source", language="chinese"):
    preview = client.post(
        "/api/rpy-extraction/preview",
        json=_ctx(project, category=category, language=language, profile=profile),
    )
    assert preview.status_code == 200, preview.text
    job = _finish(client, preview.json()["job"]["id"])
    assert job["status"] == "done", job
    scan = job["result"]["scan"]
    while not scan["completed"] and scan.get("can_continue"):
        cont = client.post(
            "/api/rpy-extraction/preview/continue",
            json=_ctx(project, category=category, language=language, profile=profile),
        )
        assert cont.status_code == 200, cont.text
        job = _finish(client, cont.json()["job"]["id"])
        assert job["status"] == "done", job
        scan = job["result"]["scan"]
    return job, scan


def test_category_isolation_source_vs_tl(rpy_app):
    client, _, _, project, _, app = rpy_app
    store = RuleStore(app.state.rpy_rule_store_path)
    source = starter_profile("source")
    for rule in source["rules"]:
        rule["enabled"] = False
    store.save(source, project, bind=False)
    store.select(project, "source", "combined", source["id"])

    source_status = client.get(
        "/api/rpy-extraction",
        params={"path": str(project), "category": "source", "language": "chinese"},
    ).json()
    tl_status = client.get(
        "/api/rpy-extraction",
        params={"path": str(project), "category": "tl", "language": "chinese"},
    ).json()

    assert source_status["mode"] == "combined"
    assert source_status["applied_profile_id"] == source["id"]
    assert any(p["id"] == source["id"] for p in source_status["profiles"])
    assert tl_status["mode"] == "builtin"
    assert tl_status["applied_profile_id"] is None
    assert all(p["id"] != source["id"] for p in tl_status["profiles"])
    assert source_status["project_key"] == tl_status["project_key"] == project_key(project)
    assert tl_status["new_rule_template"]["pattern"].startswith(r"^\s*old\s+")


def test_apply_mode_not_confused_with_unsaved_dropdown(rpy_app):
    client, _, _, project, _, app = rpy_app
    store = RuleStore(app.state.rpy_rule_store_path)
    profile = starter_profile("source")
    for rule in profile["rules"]:
        rule["enabled"] = False
    store.save(profile, project, bind=False)

    pending = client.get(
        "/api/rpy-extraction",
        params={
            "path": str(project),
            "category": "source",
            "language": "chinese",
            "pending_mode": "combined",
            "pending_profile_id": profile["id"],
        },
    ).json()
    assert pending["dirty"] is True
    assert pending["applied_mode"] == "builtin"
    assert "未保存" in pending["summary"]
    assert store.selection(project, "source")[0] == "builtin"

    applied = client.post(
        "/api/rpy-extraction/select",
        json=_ctx(project, mode="combined", profile_id=profile["id"]),
    )
    assert applied.status_code == 200, applied.text
    body = applied.json()
    assert body["applied_mode"] == "combined"
    assert body["applied_profile_id"] == profile["id"]
    assert body["dirty"] is False
    assert "当前已生效" in body["summary"]
    assert store.selection(project, "source")[0] == "combined"


def test_preview_continue_draft_and_save_bind_tmp_store(rpy_app):
    client, _, engine, project, game, app = rpy_app
    store_path = Path(app.state.rpy_rule_store_path)
    profile = starter_profile("source")

    job, scan = _preview_until_done(client, project, profile)
    assert scan["completed"] is True
    assert scan["can_save_bind"] is True

    bind = client.post(
        "/api/rpy-extraction/save-bind",
        json=_ctx(project, profile=profile),
    )
    assert bind.status_code == 200, bind.text
    bind_job = _finish(client, bind.json()["job"]["id"])
    assert bind_job["status"] == "done", bind_job
    assert bind_job["result"]["written"] is True
    assert bind_job["result"]["action"] == "save_bind"

    store = RuleStore(store_path)
    mode, bound = store.selection(project, "source")
    assert mode == "combined"
    assert bound is not None and bound["id"] == profile["id"]
    assert any(r["enabled"] for r in bound["rules"])

    draft_profile = starter_profile("tl")
    draft = client.post(
        "/api/rpy-extraction/save-draft",
        json=_ctx(project, category="tl", profile=draft_profile),
    )
    assert draft.status_code == 200, draft.text
    draft_job = _finish(client, draft.json()["job"]["id"])
    assert draft_job["status"] == "done"
    assert draft_job["result"]["written"] is True
    data = store.load()
    saved = next(p for p in data["profiles"] if p["id"] == draft_profile["id"])
    assert saved["category"] == "tl"
    assert all(not r["enabled"] for r in saved["rules"])
    assert store.selection(project, "source")[0] == "combined"
    assert store.selection(project, "tl")[0] == "builtin"
    assert (game / "scene.rpy").read_text(encoding="utf-8").startswith('e "Hello."')
    assert store_path.is_file()
    assert engine.get_status() == Engine.Status.IDLE


def test_reject_select_without_profile_and_project_mismatch(rpy_app):
    client, _, _, project, _, _ = rpy_app
    missing = client.post(
        "/api/rpy-extraction/select",
        json=_ctx(project, mode="combined", profile_id=None),
    )
    assert missing.status_code == 400
    stale = client.post(
        "/api/rpy-extraction/select",
        json={**_ctx(project, mode="builtin"), "project_key": "stale-key"},
    )
    assert stale.status_code == 409


def test_pagination_page_two_reaches_candidate_201(rpy_app):
    client, _, _, project, _, _ = rpy_app
    _make_tl_many(project, "chinese", 201)
    profile = starter_profile("tl")
    job, scan = _preview_until_done(client, project, profile, category="tl", language="chinese")
    assert scan["candidate_total"] == 201
    assert len(scan["candidates"]) == 200
    assert scan["page"] == 1
    assert scan["page_count"] == 2

    page2 = client.get(
        "/api/rpy-extraction",
        params={"path": str(project), "category": "tl", "language": "chinese", "page": 2},
    ).json()
    assert page2["scan"]["page"] == 2
    assert page2["scan"]["candidate_total"] == 201
    assert len(page2["scan"]["candidates"]) == 1
    assert page2["scan"]["candidates"][0]["text"] == "Chinese 200"


def test_proof_isolated_by_language_base(rpy_app):
    client, _, _, project, _, app = rpy_app
    _make_tl_many(project, "chinese", 3)
    _make_tl_many(project, "english", 1)
    profile = starter_profile("tl")

    _preview_until_done(client, project, profile, category="tl", language="chinese")
    english = client.get(
        "/api/rpy-extraction",
        params={"path": str(project), "category": "tl", "language": "english"},
    ).json()
    assert "english" in english["base"].replace("\\", "/").lower()
    assert english["scan"]["has_scan"] is False
    assert english["scan"]["can_save_bind"] is False

    bind = client.post(
        "/api/rpy-extraction/save-bind",
        json=_ctx(project, category="tl", language="english", profile=profile),
    )
    # 无 english 会话 proof：受理前直接 400，不写库
    assert bind.status_code == 400, bind.text
    store = RuleStore(app.state.rpy_rule_store_path)
    assert store.selection(project, "tl")[0] == "builtin"


def test_changed_profile_rejects_save_bind(rpy_app):
    client, _, _, project, _, _ = rpy_app
    profile = starter_profile("source")
    _preview_until_done(client, project, profile)
    modified = copy.deepcopy(profile)
    modified["name"] = "已修改未重新预览"
    response = client.post(
        "/api/rpy-extraction/save-bind",
        json=_ctx(project, profile=modified),
    )
    assert response.status_code == 400


def test_select_busy_409_while_save_bind_verifying(rpy_app):
    client, _, engine, project, _, app = rpy_app
    profile = starter_profile("source")
    _preview_until_done(client, project, profile)

    # 找到当前会话 proof，阻塞 verify_sources
    sessions = app.state.rpy_scan_sessions
    session = next(iter(sessions.values()))
    proof = session["scan"]
    original = proof.verify_sources
    entered = threading.Event()
    released = threading.Event()

    def blocked_verify(cancel=None, deadline=None):
        entered.set()
        assert released.wait(5), "验证同步点超时"
        return original(cancel, deadline)

    proof.verify_sources = blocked_verify
    response = client.post("/api/rpy-extraction/save-bind", json=_ctx(project, profile=profile))
    assert response.status_code == 200, response.text
    assert entered.wait(5), "保存未进入验证同步点"
    selection = client.post("/api/rpy-extraction/select", json=_ctx(project, mode="builtin", profile_id=None))
    released.set()
    save_job = _finish(client, response.json()["job"]["id"])
    assert selection.status_code == 409, selection.text
    assert save_job["status"] == "done"
    final = client.get(
        "/api/rpy-extraction",
        params={"path": str(project), "category": "source", "language": "chinese"},
    ).json()
    assert final["applied_mode"] == "combined"
    assert engine.get_status() == Engine.Status.IDLE


def test_cross_category_overwrite_rejected_without_store_damage(rpy_app):
    client, _, _, project, _, app = rpy_app
    store = RuleStore(app.state.rpy_rule_store_path)
    profile = starter_profile("tl")
    for rule in profile["rules"]:
        rule["enabled"] = False
    store.save(profile, project, bind=True)
    store.select(project, "tl", "combined", profile["id"])
    before = store.load()

    # body category=source 但 profile 仍是 tl → 受理前拒绝，失败不改规则库
    draft = client.post(
        "/api/rpy-extraction/save-draft",
        json=_ctx(project, category="source", profile=profile),
    )
    assert draft.status_code == 400, draft.text

    # 直接改 profile.category 伪装也不行：同 id 已在 tl
    spoofed = copy.deepcopy(profile)
    spoofed["category"] = "source"
    spoof = client.post(
        "/api/rpy-extraction/save-draft",
        json=_ctx(project, category="source", profile=spoofed),
    )
    assert spoof.status_code == 400, spoof.text

    after = store.load()
    assert after == before
    tl_status = client.get(
        "/api/rpy-extraction",
        params={"path": str(project), "category": "tl", "language": "chinese"},
    )
    assert tl_status.status_code == 200
    assert tl_status.json()["applied_profile_id"] == profile["id"]


def test_rule_store_save_rejects_cross_category_id(tmp_path):
    store = RuleStore(tmp_path / "rules.json")
    project = tmp_path / "Demo"
    (project / "game").mkdir(parents=True)
    tl = starter_profile("tl")
    for rule in tl["rules"]:
        rule["enabled"] = False
    store.save(tl, project, bind=True)
    spoofed = copy.deepcopy(tl)
    spoofed["category"] = "source"
    with pytest.raises(RuleError) as exc:
        store.save(spoofed, project, bind=False)
    assert exc.value.code == "binding"
    data = store.load()
    saved = next(p for p in data["profiles"] if p["id"] == tl["id"])
    assert saved["category"] == "tl"


def test_create_profile_is_draft_only(rpy_app):
    client, _, _, project, _, app = rpy_app
    store = RuleStore(app.state.rpy_rule_store_path)
    before = store.load()
    created = client.post("/api/rpy-extraction/profiles", json=_ctx(project))
    assert created.status_code == 200, created.text
    assert created.json()["editor_profile"]["id"]
    assert store.load() == before

    starter = client.post("/api/rpy-extraction/profiles", json=_ctx(project, starter=True))
    assert starter.status_code == 200
    assert starter.json()["editor_profile"]["rules"]
    assert store.load() == before


def test_empty_owner_to_bound_rejects_save_draft(rpy_app, tmp_path):
    """未绑定 owner 受理后、compute 前绑定其他项目：不得 written。"""
    client, config, _, project, _, app = rpy_app
    other = tmp_path / "OtherOwner"
    (other / "game").mkdir(parents=True)
    store = RuleStore(app.state.rpy_rule_store_path)
    before = store.load()

    config.renpy_project_path = ""
    config.renpy_game_folder = ""
    config.renpy_tl_folder = ""
    config.input_folder = ""

    import api.routes.rpy_extraction as rpy_mod

    original_acquire = rpy_mod._acquire_engine

    def bind_other_then_acquire():
        _bind(config, other)
        return original_acquire()

    rpy_mod._acquire_engine = bind_other_then_acquire
    try:
        response = client.post(
            "/api/rpy-extraction/save-draft",
            json=_ctx(project, category="tl", profile=starter_profile("tl")),
        )
    finally:
        rpy_mod._acquire_engine = original_acquire

    assert response.status_code == 200, response.text
    job = _finish(client, response.json()["job"]["id"])
    assert job["status"] == "failed"
    assert job["result"]["written"] is False
    assert store.load() == before


def test_owner_change_after_verify_rejects_save_bind(rpy_app, tmp_path):
    """verify 完成后、写库前切 owner：不得 written，规则库不变。"""
    client, config, _, project, _, app = rpy_app
    other = tmp_path / "OtherOwner"
    (other / "game").mkdir(parents=True)
    profile = starter_profile("source")
    _preview_until_done(client, project, profile)
    store = RuleStore(app.state.rpy_rule_store_path)
    before = store.load()

    session = next(iter(app.state.rpy_scan_sessions.values()))
    proof = session["scan"]
    original = proof.verify_sources
    entered = threading.Event()
    released = threading.Event()
    verify_count = {"n": 0}

    def verified_then_wait(cancel=None, deadline=None):
        verify_count["n"] += 1
        original(cancel, deadline)
        if verify_count["n"] == 1:
            entered.set()
            assert released.wait(5), "验证同步点超时"

    proof.verify_sources = verified_then_wait
    response = client.post("/api/rpy-extraction/save-bind", json=_ctx(project, profile=profile))
    assert response.status_code == 200, response.text
    assert entered.wait(5), "保存未进入已验证同步点"
    _bind(config, other)
    released.set()
    save_job = _finish(client, response.json()["job"]["id"])
    assert save_job["status"] == "failed"
    assert save_job["result"]["written"] is False
    assert store.load() == before


def test_source_change_after_verify_rejects_save_bind(rpy_app):
    """verify 完成后改源文件：最终 save 再 verify 拒绝，规则库不变。"""
    client, _, _, project, game, app = rpy_app
    profile = starter_profile("source")
    _preview_until_done(client, project, profile)
    store = RuleStore(app.state.rpy_rule_store_path)
    before = store.load()
    source = game / "scene.rpy"

    session = next(iter(app.state.rpy_scan_sessions.values()))
    proof = session["scan"]
    original = proof.verify_sources
    entered = threading.Event()
    released = threading.Event()
    verify_count = {"n": 0}

    def verified_then_wait(cancel=None, deadline=None):
        verify_count["n"] += 1
        if verify_count["n"] == 1:
            original(cancel, deadline)
            entered.set()
            assert released.wait(5), "验证同步点超时"
        else:
            # 第二次为写库前校验：先放行改源后再走真实 verify
            return original(cancel, deadline)

    proof.verify_sources = verified_then_wait
    response = client.post("/api/rpy-extraction/save-bind", json=_ctx(project, profile=profile))
    assert response.status_code == 200, response.text
    assert entered.wait(5), "保存未进入已验证同步点"
    source.write_text('e "Changed after verify."\n', encoding="utf-8")
    released.set()
    save_job = _finish(client, response.json()["job"]["id"])
    assert save_job["status"] == "failed"
    assert save_job["result"]["written"] is False
    assert store.load() == before


def test_select_409_while_single_task_busy(rpy_app):
    """单条重译占用时同步 mutation 必须 409 且不改库。"""
    client, _, engine, project, _, app = rpy_app
    store = RuleStore(app.state.rpy_rule_store_path)
    before = store.load()
    assert engine.try_begin_single_task()
    try:
        response = client.post(
            "/api/rpy-extraction/select",
            json=_ctx(project, mode="builtin", profile_id=None),
        )
        assert response.status_code == 409, response.text
        assert store.load() == before
    finally:
        engine.end_single_task()
