"""一键翻译 API：检测、准备确认、应用与互斥。"""
from __future__ import annotations

import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.jobs import JobManager
from api.routes.jobs import router as jobs_router
from api.routes import onekey
from api.routes.onekey import router
from module.Config import Config
from module.Engine.Engine import Engine


@pytest.fixture
def onekey_app(tmp_path, monkeypatch):
    project = tmp_path / "story"
    game = project / "game"
    tl = game / "tl" / "chinese"
    tl.mkdir(parents=True)
    (game / "script.rpy").write_text('label start:\n    "hello"\n', encoding="utf-8")
    (tl / "script.rpy").write_text('translate chinese start:\n    "hello"\n', encoding="utf-8")
    config = Config()
    config.renpy_project_path = str(project)
    config.renpy_game_folder = str(game)
    config.renpy_tl_folder = str(tl)
    config.input_folder = str(tl)
    config.output_folder = str(project / "RenpyBox_Translation" / "chinese")
    config.cache_use_sqlite = False
    engine = Engine()
    monkeypatch.setattr(Engine, "get", classmethod(lambda cls: engine))
    app = FastAPI()
    app.state.config = config
    app.state.jobs = JobManager()
    app.include_router(router)
    app.include_router(jobs_router)
    with TestClient(app) as client:
        yield client, config, engine, project, game
        app.state.jobs.shutdown()


def _finish(client, job_id, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in {"done", "failed", "cancelled"} and not (job.get("result") or {}).get("worker_active"):
            return job
        time.sleep(0.01)
    pytest.fail(f"任务未结束：{job}")


def test_detect_ready_and_rejects_language_traversal(onekey_app, monkeypatch):
    client, _, _, project, _ = onekey_app
    monkeypatch.setattr(
        "api.routes.onekey.detect_game_status",
        lambda game_dir, language, cancel_check=None: ("ready", "可抽取"),
    )
    response = client.post("/api/onekey/detect", json={"game_dir": str(project), "language": "chinese"})
    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    bad = client.post("/api/onekey/detect", json={"game_dir": str(project), "language": "../evil"})
    assert bad.status_code == 400


def test_prepare_requires_confirm_and_does_not_start_translation(onekey_app, monkeypatch):
    client, config, engine, project, game = onekey_app
    response = client.post(
        "/api/onekey/prepare",
        json={"game_dir": str(project), "language": "chinese", "incremental": False, "confirm_write": False},
    )
    assert response.status_code == 400

    monkeypatch.setattr(
        "api.routes.onekey.detect_game_status",
        lambda game_dir, language, cancel_check=None: ("ready", "可抽取"),
    )
    monkeypatch.setattr(
        "api.routes.onekey.prepare_extraction_paths",
        lambda config, game_dir, tl_name, *, incremental: {
            "paths": None,
            "incremental_dir": None,
            "output_dir": config.output_folder,
            "main_tl_dir": config.input_folder,
            "main_output_dir": config.output_folder,
            "preserved_cache": None,
        },
    )
    monkeypatch.setattr(
        "api.routes.onekey.extract_project_text",
        lambda *args, **kwargs: (
            True,
            "抽取完成",
            SimpleNamespace(success=True, cancelled=False, incremental_dir=None, tl_dir=config.input_folder),
        ),
    )
    monkeypatch.setattr(
        "api.routes.onekey.configure_main_translation_paths",
        lambda config, game_dir, tl_name, *, remember_run=True: (config.input_folder, config.output_folder),
    )
    saved = {"count": 0}
    monkeypatch.setattr(
        type(config),
        "save",
        lambda self, *args, **kwargs: saved.__setitem__("count", saved["count"] + 1),
    )

    response = client.post(
        "/api/onekey/prepare",
        json={"game_dir": str(project), "language": "chinese", "incremental": False, "confirm_write": True},
    )
    assert response.status_code == 200, response.text
    job = _finish(client, response.json()["job"]["id"])
    assert job["status"] == "done"
    assert job["result"]["stage"] == "ready"
    assert engine.get_status() == Engine.Status.IDLE
    # 准备成功只配置路径，不假装翻译已成功。
    assert "translation" not in job["kind"]


@pytest.mark.parametrize("extract_ok", [True, False])
def test_prepare_configures_paths_only_after_successful_extraction(onekey_app, monkeypatch, extract_ok):
    """对齐 Qt5：抽取成功后才配置路径；抽取失败不能挪走旧增量输出缓存。"""
    client, config, engine, project, _ = onekey_app
    calls: list[str] = []
    monkeypatch.setattr(
        "api.routes.onekey.detect_game_status",
        lambda game_dir, language, cancel_check=None: ("ready", "可抽取"),
    )

    def fake_paths(config, game_dir, tl_name, *, incremental):
        calls.append("paths")
        return {
            "paths": None,
            "incremental_dir": None,
            "output_dir": config.output_folder,
            "main_tl_dir": config.input_folder,
            "main_output_dir": config.output_folder,
            "preserved_cache": None,
        }

    def fake_extract(*args, **kwargs):
        calls.append("extract")
        result = SimpleNamespace(success=extract_ok, cancelled=False, incremental_dir=None, tl_dir=config.input_folder)
        return extract_ok, "抽取完成" if extract_ok else "抽取失败", result

    monkeypatch.setattr("api.routes.onekey.prepare_extraction_paths", fake_paths)
    monkeypatch.setattr("api.routes.onekey.extract_project_text", fake_extract)
    monkeypatch.setattr(
        "api.routes.onekey.configure_main_translation_paths",
        lambda config, game_dir, tl_name, *, remember_run=True: (config.input_folder, config.output_folder),
    )
    monkeypatch.setattr(type(config), "save", lambda self, *args, **kwargs: None)

    response = client.post(
        "/api/onekey/prepare",
        json={"game_dir": str(project), "language": "chinese", "mode": "full", "confirm_write": True},
    )
    assert response.status_code == 200, response.text
    job = _finish(client, response.json()["job"]["id"])
    if extract_ok:
        assert job["status"] == "done"
        assert calls == ["extract", "paths"]
    else:
        assert job["status"] == "failed"
        assert calls == ["extract"]
    assert engine.get_status() == Engine.Status.IDLE


def test_apply_requires_confirm_and_rejects_busy_engine(onekey_app):
    client, config, engine, project, _ = onekey_app
    Path(config.output_folder).mkdir(parents=True, exist_ok=True)
    response = client.post(
        "/api/onekey/apply",
        json={"game_dir": str(project), "language": "chinese", "confirm": False},
    )
    assert response.status_code == 400
    assert engine.try_set_status(Engine.Status.IDLE, Engine.Status.TRANSLATING)
    response = client.post(
        "/api/onekey/apply",
        json={"game_dir": str(project), "language": "chinese", "confirm": True},
    )
    assert response.status_code == 409
    engine.release_status(Engine.Status.TRANSLATING)


def test_apply_full_uses_transaction_helper(onekey_app, monkeypatch, tmp_path):
    client, config, engine, project, game = onekey_app
    output = Path(config.output_folder)
    output.mkdir(parents=True)
    (output / "script.rpy").write_text('translate chinese start:\n    "你好"\n', encoding="utf-8")

    called = {}

    def fake_apply(**kwargs):
        called.update(kwargs)
        return True, "已应用 1 个文件", {"count": 1}

    monkeypatch.setattr("api.routes.onekey.apply_full_translation", fake_apply)
    response = client.post(
        "/api/onekey/apply",
        json={
            "game_dir": str(project),
            "language": "chinese",
            "incremental": False,
            "confirm": True,
            "incremental_output": None,
            "incremental_target": None,
        },
    )
    assert response.status_code == 200, response.text
    job = _finish(client, response.json()["job"]["id"])
    assert job["status"] == "done"
    assert called["output_files"]
    assert engine.get_status() == Engine.Status.IDLE


def test_detect_empty_path(onekey_app):
    client, config, *_ = onekey_app
    config.renpy_project_path = ""
    config.renpy_game_folder = ""
    response = client.post("/api/onekey/detect", json={"game_dir": "", "language": "chinese"})
    assert response.status_code == 400


@pytest.mark.parametrize("incremental", [False, True])
def test_real_prepare_and_apply_without_game_executable(onekey_app, incremental):
    """临时项目走真实检测、补充抽取与事务应用，不启动游戏或模型。"""
    client, config, engine, project, game = onekey_app
    (game / "script.rpy").write_text('label start:\n    show text "Standalone display text"\n    "hello"\n', encoding="utf-8")
    config.save(strict=True)
    source_before = (game / "script.rpy").read_bytes()
    response = client.post("/api/onekey/prepare", json={
        "game_dir": str(project), "language": "chinese", "confirm_write": True, "incremental": incremental,
    })
    assert response.status_code == 200, response.text
    job = _finish(client, response.json()["job"]["id"], timeout=15)
    assert job["status"] == "done", job
    assert job["result"]["stage"] == "ready"
    assert Path(config.input_folder).is_dir()
    assert not (game / "game").exists()
    extracted = list(Path(config.input_folder).rglob("*.rpy"))
    assert any("Standalone display text" in path.read_text(encoding="utf-8") for path in extracted)
    output = Path(config.output_folder)
    output.mkdir(parents=True, exist_ok=True)
    translated = 'translate chinese strings:\n    old "hello"\n    new "你好"\n'
    (output / "verified.rpy").write_text(translated, encoding="utf-8")
    response = client.post("/api/onekey/apply", json={
        "game_dir": str(project), "language": "chinese", "confirm": True, "incremental": incremental,
    })
    assert response.status_code == 200, response.text
    job = _finish(client, response.json()["job"]["id"], timeout=15)
    assert job["status"] == "done", job
    applied = (game / "tl" / "chinese" / "verified.rpy").read_text(encoding="utf-8")
    assert [line for line in applied.splitlines() if line.strip()] == translated.splitlines()
    assert (game / "script.rpy").read_bytes() == source_before
    assert engine.get_status() == Engine.Status.IDLE

def _patch_end_to_end_lexicon(monkeypatch, written: dict):
    """真实走 _prepare_lexicon_after_extract：只 mock 网络核心与扫描。"""
    class FakeRepository:
        has_storage = True
        output_folder = ""

        def load(self, config):
            return SimpleNamespace(
                assets = SimpleNamespace(glossary = [], revision = 1),
                analysis_candidates = {"items": [], "glossary_metadata": {}},
            )

        def merge_analysis_terms(self, entries):
            written.setdefault("merged", []).extend(dict(entry) for entry in entries)
            return {"items": []}

    monkeypatch.setattr(
        "module.Engine.Translator.ProjectAssetsRepository.ProjectAssetsRepository.from_config",
        classmethod(lambda cls, config: FakeRepository()),
    )
    monkeypatch.setattr(
        "api.routes.onekey._agent_platform",
        lambda config: ({"api_format": "OpenAI", "model": "m"}, ""),
    )
    monkeypatch.setattr(
        "module.Extract.GlossaryCandidateService.extract_glossary_candidates",
        lambda **kwargs: {
            "entries": [{"src": "Carol", "type": "角色"}, {"src": "East Square", "type": "地名"}],
            "status": "completed",
            "warnings": [],
        },
    )
    # 禁翻由受限扫描真实执行：用例应在项目内源码写入 [变量]。


def test_prepare_skip_extraction_runs_agent_glossary_and_preserve(onekey_app, monkeypatch):
    client, config, _, project, game = onekey_app
    written: dict = {}
    _patch_end_to_end_lexicon(monkeypatch, written)
    (game / "script.rpy").write_text('e "hello [hp]"', encoding = "utf-8")
    # 旧 input/output 与新项目不同：历史上会被误判成「项目已切换」。
    config.input_folder = str(project / "old_input")
    config.output_folder = str(project / "old_output")

    response = client.post("/api/onekey/prepare", json={
        "game_dir": str(project), "language": "chinese", "confirm_write": True,
        "skip_extraction": True, "prepare_glossary": True, "prepare_lexicon": True,
    })
    assert response.status_code == 200, response.text
    job = _finish(client, response.json()["job"]["id"], timeout=15)
    assert job["status"] == "done", job
    lexicon = job["result"]["lexicon"]
    assert lexicon["glossary"]["status"] == "completed", lexicon
    assert lexicon["glossary"]["added"] == 2
    assert lexicon["preserve"]["added"] == 1
    assert not any("项目已切换" in w for w in lexicon["warnings"])
    assert [item["src"] for item in written["merged"]] == ["Carol", "East Square"]
    assert [item["src"] for item in config.text_preserve_data] == ["[hp]"]


def test_prepare_fresh_extraction_runs_agent_glossary(onekey_app, monkeypatch):
    client, config, _, project, _ = onekey_app
    written: dict = {}
    _patch_end_to_end_lexicon(monkeypatch, written)
    config.input_folder = str(project / "old_input")
    config.output_folder = str(project / "old_output")
    monkeypatch.setattr(
        "api.routes.onekey.detect_game_status",
        lambda *a, **k: ("ready", "可抽取"),
    )
    monkeypatch.setattr(
        "api.routes.onekey.extract_project_text",
        lambda *a, **k: (True, "已抽取", SimpleNamespace(cancelled = False)),
    )
    monkeypatch.setattr(
        "api.routes.onekey.prepare_extraction_paths",
        lambda config, game_root, language, incremental = False: {
            "main_tl_dir": str(project / "game" / "tl" / "chinese"),
            "output_dir": str(project / "out"),
            "incremental_dir": None,
            "main_output_dir": str(project / "out"),
            "preserved_cache": None,
        },
    )

    response = client.post("/api/onekey/prepare", json={
        "game_dir": str(project), "language": "chinese", "confirm_write": True,
        "mode": "full", "official_extract": False, "supplement_mode": "aggressive",
        "prepare_glossary": True, "prepare_lexicon": False,
    })
    assert response.status_code == 200, response.text
    job = _finish(client, response.json()["job"]["id"], timeout=15)
    assert job["status"] == "done", job
    lexicon = job["result"]["lexicon"]
    assert lexicon["glossary"]["status"] == "completed", lexicon
    assert [item["src"] for item in written["merged"]] == ["Carol", "East Square"]
    assert not any("项目已切换" in w for w in lexicon["warnings"])

def _make_game_b(tmp_path) -> "Path":
    """在项目根下再建一个 game 目录，模拟用户在 body.game_dir 里换目标。"""
    game_b = tmp_path / "story" / "game_b"
    game_b.mkdir(parents = True)
    (game_b / "script_b.rpy").write_text('label start:\n    "b"\n', encoding = "utf-8")
    tl_b = game_b / "tl" / "chinese"
    tl_b.mkdir(parents = True)
    (tl_b / "script_b.rpy").write_text('translate chinese start:\n    "b"\n', encoding = "utf-8")
    return game_b


def _patch_scan_capture(monkeypatch, written: dict, captured: dict):
    """记录词库阶段实际使用的扫描根与目标路径，验证落在请求的项目里。"""
    original_confined = onekey._confined_scan_paths

    def fake_confined(config, scope_root):
        captured["scope_root"] = scope_root
        captured["scan_input"] = getattr(config, "input_folder", "")
        captured["scan_output"] = getattr(config, "output_folder", "")
        return original_confined(config, scope_root)

    monkeypatch.setattr(onekey, "_confined_scan_paths", fake_confined)
    monkeypatch.setattr(
        "module.Extract.GlossaryCandidateService.extract_glossary_candidates",
        lambda **kwargs: (
            captured.__setitem__("target_path", kwargs.get("target_path")),
            captured.__setitem__("scan_config", kwargs.get("config")),
            {
                "entries": [
                    {"src": "Carol", "type": "角色"},
                    {"src": "East Square", "type": "地名"},
                ],
                "status": "completed",
                "warnings": [],
            },
        )[-1],
    )


def test_scan_never_falls_back_to_other_project_without_source(onekey_app, monkeypatch, tmp_path):
    """B 没有源 .rpy 而 A 有时，扫描必须如实失败，绝不回退到 A。"""
    project = tmp_path / "isolated_project"
    game_b = project / "game"
    game_b.mkdir(parents = True, exist_ok = True)
    stale_game = tmp_path / "stale_game_a"
    stale_game.mkdir(parents = True)
    (stale_game / "a.rpy").write_text('e "A only."', encoding = "utf-8")

    config = Config()
    config.renpy_project_path = str(project)
    config.renpy_game_folder = str(stale_game)
    config.input_folder = str(stale_game / "tl" / "chinese")
    config.output_folder = str(tmp_path / "stale_output_a")

    # 旧逻辑会按 input/output/tl/game/project 顺序找到 A 的 .rpy；限定后必须返回 None。
    source, _tl_root = onekey._confined_scan_paths(config, str(project))
    assert source is None, "项目内没有源码时不得回退到项目外的 A"

    # 即使把旧项目路径全部塞进 config，find 也只在 scope 内找。
    outside_source, _tl = onekey._confined_scan_paths(config, str(tmp_path / "nowhere"))
    assert outside_source is None


def test_scan_confined_still_finds_project_source(onekey_app, monkeypatch, tmp_path):
    """项目内确有源码时仍能正常解析，且不会跨到 A。"""
    project = tmp_path / "isolated_project_b"
    game_b = project / "game"
    game_b.mkdir(parents = True, exist_ok = True)
    (game_b / "script.rpy").write_text('e "LUMA is here."', encoding = "utf-8")
    (game_b / "tl" / "chinese").mkdir(parents = True, exist_ok = True)
    stale_game = tmp_path / "stale_game_a"
    stale_game.mkdir(parents = True, exist_ok = True)
    (stale_game / "a.rpy").write_text('e "A only."', encoding = "utf-8")

    config = Config()
    config.renpy_project_path = str(project)
    config.renpy_game_folder = str(stale_game)

    source, tl_root = onekey._confined_scan_paths(config, str(project))

    assert source == game_b
    assert str(stale_game) not in str(source)
    assert tl_root is not None and tl_root.name == "chinese"


def _prepare_cross_project_preserve(onekey_app, monkeypatch, tmp_path, *, skip_extraction: bool):
    """构造 A 有 [old_only]、B 有 [new_only] 的跨项目禁翻场景（不 mock scanner）。"""
    client, config, _, project, game_b = onekey_app
    written: dict = {}
    _patch_end_to_end_lexicon(monkeypatch, written)
    # 请求前配置指向项目外的 A，A 的源码含 [old_only]。
    stale_project = tmp_path / "stale_game_a"
    stale_game = stale_project / "game"
    stale_game.mkdir(parents = True, exist_ok = True)
    (stale_game / "a.rpy").write_text('e "A [old_only]"', encoding = "utf-8")
    config.renpy_project_path = str(stale_project)
    config.renpy_game_folder = str(stale_game)
    config.renpy_tl_folder = str(stale_game / "tl" / "chinese")
    config.input_folder = str(game_b / "tl" / "chinese")
    config.output_folder = str(tmp_path / "stale_output_a")
    config.text_preserve_data = []
    # B 的源码含 [new_only]。
    (game_b / "script.rpy").write_text('e "B [new_only]"', encoding = "utf-8")

    payload = {"game_dir": str(project), "language": "chinese", "confirm_write": True,
        "prepare_glossary": True, "prepare_lexicon": True}
    if skip_extraction:
        payload["skip_extraction"] = True
    else:
        payload["mode"] = "full"
        payload["official_extract"] = False
        payload["supplement_mode"] = "aggressive"
        monkeypatch.setattr(
            "api.routes.onekey.detect_game_status",
            lambda *a, **k: ("ready", "可抽取"),
        )
        monkeypatch.setattr(
            "api.routes.onekey.extract_project_text",
            lambda *a, **k: (True, "已抽取", SimpleNamespace(cancelled = False)),
        )
        monkeypatch.setattr(
            "api.routes.onekey.prepare_extraction_paths",
            lambda config, game_root, language, incremental = False: {
                "main_tl_dir": str(game_b / "tl" / "chinese"),
                "output_dir": str(project / "out"),
                "incremental_dir": None,
                "main_output_dir": str(project / "out"),
                "preserved_cache": None,
            },
        )
    return client, config, project, game_b, stale_game, payload


@pytest.mark.parametrize("skip_extraction", [True, False])
def test_preserve_scans_only_requested_project(onekey_app, monkeypatch, tmp_path, skip_extraction):
    """禁翻真实扫描：只新增 B 的 [new_only]，绝不取 A 的 [old_only]。"""
    client, config, project, game_b, stale_game, payload = _prepare_cross_project_preserve(
        onekey_app, monkeypatch, tmp_path, skip_extraction = skip_extraction,
    )

    response = client.post("/api/onekey/prepare", json=payload)
    assert response.status_code == 200, response.text
    job = _finish(client, response.json()["job"]["id"], timeout=20)
    assert job["status"] == "done", job
    lexicon = job["result"]["lexicon"]
    assert lexicon["preserve"]["status"] == "completed", lexicon

    srcs = [item["src"] for item in config.text_preserve_data]
    assert srcs == ["[new_only]"], srcs
    assert "[old_only]" not in srcs, "禁翻扫描不得回退到旧项目 A"


@pytest.mark.parametrize("skip_extraction", [True, False])
def test_preserve_does_not_fall_back_when_project_has_no_source(
    onekey_app, monkeypatch, tmp_path, skip_extraction,
):
    """B 无源码、A 有源码时，禁翻如实失败且不写入 A 的变量。"""
    client, config, project, game_b, stale_game, payload = _prepare_cross_project_preserve(
        onekey_app, monkeypatch, tmp_path, skip_extraction = skip_extraction,
    )
    # 抹掉 B 的源码，只留 A 的 [old_only]。
    (game_b / "script.rpy").unlink()
    (game_b / "tl" / "chinese").mkdir(parents = True, exist_ok = True)

    response = client.post("/api/onekey/prepare", json=payload)
    assert response.status_code == 200, response.text
    job = _finish(client, response.json()["job"]["id"], timeout=20)
    assert job["status"] == "done", job
    lexicon = job["result"]["lexicon"]

    assert lexicon["preserve"]["status"] == "failed", lexicon
    srcs = [item["src"] for item in (config.text_preserve_data or [])]
    assert "[old_only]" not in srcs, "项目内没有源码时不得扫描旧项目"

def test_prepare_skip_extraction_scans_game_b_not_stale_game_a(onekey_app, monkeypatch, tmp_path):
    client, config, _, project, game_a = onekey_app
    written: dict = {}
    captured: dict = {}
    _patch_end_to_end_lexicon(monkeypatch, written)
    _patch_scan_capture(monkeypatch, written, captured)
    game_b = _make_game_b(project)
    # 请求前把配置指向另一个项目 A（项目外），验证词库阶段不会读它。
    stale_game = tmp_path / "stale_game_a"
    stale_tl = stale_game / "tl" / "chinese"
    stale_tl.mkdir(parents = True)
    (stale_game / "a.rpy").write_text('e "A only."', encoding = "utf-8")
    config.renpy_game_folder = str(stale_game)
    config.input_folder = str(stale_tl)
    config.output_folder = str(tmp_path / "stale_output_a")
    captured["stale_input"] = str(stale_tl)
    captured["stale_output"] = str(tmp_path / "stale_output_a")

    response = client.post("/api/onekey/prepare", json={
        "game_dir": str(project), "language": "chinese", "confirm_write": True,
        "skip_extraction": True, "prepare_glossary": True, "prepare_lexicon": False,
    })
    assert response.status_code == 200, response.text
    job = _finish(client, response.json()["job"]["id"], timeout=15)
    assert job["status"] == "done", job
    lexicon = job["result"]["lexicon"]
    assert lexicon["glossary"]["status"] == "completed", lexicon
    # 实际传给核心的 target_path 必须落在请求的项目内，而不是旧项目 A。
    assert captured["target_path"] == str(project / "game")
    assert str(project) in captured["target_path"]
    assert captured["stale_input"] not in captured["target_path"]
    assert captured["scope_root"] == str(project)
    assert [item["src"] for item in written["merged"]] == ["Carol", "East Square"]
    assert not any("项目已切换" in w for w in lexicon["warnings"])


def test_prepare_fresh_extraction_scans_game_b_not_stale_game_a(onekey_app, monkeypatch, tmp_path):
    client, config, _, project, game_a = onekey_app
    written: dict = {}
    captured: dict = {}
    _patch_end_to_end_lexicon(monkeypatch, written)
    _patch_scan_capture(monkeypatch, written, captured)
    game_b = _make_game_b(project)
    # 请求前把配置指向另一个项目 A（项目外），验证词库阶段不会读它。
    stale_game = tmp_path / "stale_game_a"
    stale_tl = stale_game / "tl" / "chinese"
    stale_tl.mkdir(parents = True)
    (stale_game / "a.rpy").write_text('e "A only."', encoding = "utf-8")
    config.renpy_game_folder = str(stale_game)
    config.input_folder = str(stale_tl)
    config.output_folder = str(tmp_path / "stale_output_a")
    captured["stale_input"] = str(stale_tl)
    captured["stale_output"] = str(tmp_path / "stale_output_a")
    monkeypatch.setattr(
        "api.routes.onekey.detect_game_status",
        lambda *a, **k: ("ready", "可抽取"),
    )
    monkeypatch.setattr(
        "api.routes.onekey.extract_project_text",
        lambda *a, **k: (True, "已抽取", SimpleNamespace(cancelled = False)),
    )
    monkeypatch.setattr(
        "api.routes.onekey.prepare_extraction_paths",
        lambda config, game_root, language, incremental = False: {
            "main_tl_dir": str(game_b / "tl" / "chinese"),
            "output_dir": str(project / "out"),
            "incremental_dir": None,
            "main_output_dir": str(project / "out"),
            "preserved_cache": None,
        },
    )
    # 抽取阶段完成后共享配置的 game 目录就是 B。
    original_prepare = onekey.prepare_extraction_paths

    def prepare_paths(config, game_root, language, incremental = False):
        config.renpy_game_folder = str(game_b)
        return original_prepare(config, game_root, language, incremental)

    monkeypatch.setattr("api.routes.onekey.prepare_extraction_paths", prepare_paths)

    response = client.post("/api/onekey/prepare", json={
        "game_dir": str(project), "language": "chinese", "confirm_write": True,
        "mode": "full", "official_extract": False, "supplement_mode": "aggressive",
        "prepare_glossary": True, "prepare_lexicon": False,
    })
    assert response.status_code == 200, response.text
    job = _finish(client, response.json()["job"]["id"], timeout=15)
    assert job["status"] == "done", job
    lexicon = job["result"]["lexicon"]
    assert lexicon["glossary"]["status"] == "completed", lexicon
    # 实际传给核心的 target_path 必须落在请求的项目内，而不是旧项目 A。
    assert str(project) in captured["target_path"]
    assert captured["stale_input"] not in captured["target_path"]
    assert captured["scope_root"] == str(project)
    assert [item["src"] for item in written["merged"]] == ["Carol", "East Square"]
    assert not any("项目已切换" in w for w in lexicon["warnings"])


def test_glossary_write_failure_does_not_block_preserve(onekey_app, monkeypatch):
    client, config, _, project, game = onekey_app
    _patch_end_to_end_lexicon(monkeypatch, {})
    config.text_preserve_data = []
    (game / "script.rpy").write_text('e "hello [hp]"', encoding = "utf-8")

    class BoomRepository:
        has_storage = True
        output_folder = ""

        def load(self, config):
            return SimpleNamespace(
                assets = SimpleNamespace(glossary = [], revision = 1),
                analysis_candidates = {"items": [], "glossary_metadata": {}},
            )

        def merge_analysis_terms(self, entries):
            raise OSError("术语写失败")

    monkeypatch.setattr(
        "module.Engine.Translator.ProjectAssetsRepository.ProjectAssetsRepository.from_config",
        classmethod(lambda cls, config: BoomRepository()),
    )

    response = client.post("/api/onekey/prepare", json={
        "game_dir": str(project), "language": "chinese", "confirm_write": True,
        "skip_extraction": True, "prepare_glossary": True, "prepare_lexicon": True,
    })
    assert response.status_code == 200, response.text
    job = _finish(client, response.json()["job"]["id"], timeout=15)
    assert job["status"] == "done", job
    lexicon = job["result"]["lexicon"]
    assert lexicon["glossary"]["status"] == "failed"
    assert lexicon["glossary"]["added"] == 0
    # 术语写失败不得阻断禁翻。
    assert lexicon["preserve"]["status"] == "completed"
    assert lexicon["preserve"]["added"] == 1
    assert [item["src"] for item in config.text_preserve_data] == ["[hp]"]


def test_preserve_write_failure_keeps_glossary_counts(onekey_app, monkeypatch):
    client, config, _, project, game = onekey_app
    written: dict = {}
    _patch_end_to_end_lexicon(monkeypatch, written)
    (game / "script.rpy").write_text('e "hello [hp]"', encoding = "utf-8")

    original_persist = onekey._persist_fields

    def boom_persist(live, values):
        if "text_preserve_data" in values:
            raise OSError("禁翻写失败")
        return original_persist(live, values)

    monkeypatch.setattr("api.routes.onekey._persist_fields", boom_persist)

    response = client.post("/api/onekey/prepare", json={
        "game_dir": str(project), "language": "chinese", "confirm_write": True,
        "skip_extraction": True, "prepare_glossary": True, "prepare_lexicon": True,
    })
    assert response.status_code == 200, response.text
    job = _finish(client, response.json()["job"]["id"], timeout=15)
    lexicon = job["result"]["lexicon"]
    # 禁翻写失败不得把已成功的术语标失败或清零。
    assert lexicon["glossary"]["status"] == "completed"
    assert lexicon["glossary"]["added"] == 2
    assert [item["src"] for item in written["merged"]] == ["Carol", "East Square"]
    assert lexicon["preserve"]["status"] == "failed"
    assert lexicon["preserve"]["added"] == 0

def test_prepare_glossary_defaults_off_and_is_independent(onekey_app, monkeypatch):
    client, config, _, project, _ = onekey_app
    calls: list[str] = []

    monkeypatch.setattr(
        "api.routes.onekey._prepare_lexicon_after_extract",
        lambda request, check_cancel, progress, snapshot, **kwargs: calls.append("prep") or {
            "success": True, "glossary": {"status": "skipped", "added": 0},
            "preserve": {"status": "skipped", "added": 0}, "warnings": [], "message": "已跳过",
        },
    )

    # 旧配置显式开着禁翻，但 Agent 术语必须仍然默认关闭。
    assert config.onekey_prepare_lexicon is True
    assert config.onekey_prepare_glossary is False

    response = client.post("/api/onekey/prepare", json={
        "game_dir": str(project), "language": "chinese", "confirm_write": True,
        "skip_extraction": True,
    })
    assert response.status_code == 200, response.text
    job = _finish(client, response.json()["job"]["id"], timeout=15)
    assert job["status"] == "done", job
    assert job["result"]["prepare_lexicon"] is True
    assert job["result"]["prepare_glossary"] is False
    assert job["result"]["lexicon"]["glossary"]["status"] == "skipped"
    assert calls == ["prep"]


def test_prepare_persists_both_flags_independently(onekey_app, monkeypatch):
    client, config, _, project, _ = onekey_app
    saved: dict = {}
    monkeypatch.setattr(
        Config, "save",
        lambda self, *args, **kwargs: saved.update(
            onekey_prepare_glossary = self.onekey_prepare_glossary,
            onekey_prepare_lexicon = self.onekey_prepare_lexicon,
        ),
    )
    monkeypatch.setattr(
        "api.routes.onekey._prepare_lexicon_after_extract",
        lambda request, check_cancel, progress, snapshot, **kwargs: {
            "success": True, "glossary": {"status": "skipped", "added": 0},
            "preserve": {"status": "skipped", "added": 0}, "warnings": [], "message": "已跳过",
        },
    )

    response = client.post("/api/onekey/prepare", json={
        "game_dir": str(project), "language": "chinese", "confirm_write": True,
        "skip_extraction": True, "prepare_glossary": True, "prepare_lexicon": False,
    })
    assert response.status_code == 200, response.text
    job = _finish(client, response.json()["job"]["id"], timeout=15)
    assert job["result"]["prepare_glossary"] is True
    assert job["result"]["prepare_lexicon"] is False
    assert saved.get("onekey_prepare_glossary") is True
    assert saved.get("onekey_prepare_lexicon") is False


def test_prepare_lexicon_failure_keeps_stage_ready(onekey_app, monkeypatch):
    client, _, _, project, _ = onekey_app

    def boom(request, check_cancel, progress, snapshot, **kwargs):
        raise OSError("模拟词库失败")

    monkeypatch.setattr("api.routes.onekey._prepare_lexicon_after_extract", boom)

    response = client.post("/api/onekey/prepare", json={
        "game_dir": str(project), "language": "chinese", "confirm_write": True,
        "skip_extraction": True, "prepare_glossary": True,
    })
    assert response.status_code == 200, response.text
    job = _finish(client, response.json()["job"]["id"], timeout=15)
    assert job["status"] == "done", job
    assert job["result"]["stage"] == "ready"
    assert job["result"]["lexicon"]["success"] is True
    assert any("词库失败" in warning for warning in job["result"]["lexicon"]["warnings"])
