"""接口 CRUD 契约：密钥保护、失败回滚、引用重编号与忙碌屏障。"""

import copy
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes import platforms
from module.Config import Config
from module.Engine.Engine import Engine
from module.Secret.SecretStore import MemoryBackend, SecretStore


def test_platform_edits_preserve_secrets_and_other_settings(monkeypatch, tmp_path):
    store = SecretStore(MemoryBackend())
    monkeypatch.setattr(SecretStore, "_instance", store)
    monkeypatch.setattr(Config, "CONFIG_PATH", str(tmp_path / "config.json"))
    engine = SimpleNamespace(get_status = lambda: Engine.Status.IDLE, has_stop_barrier = lambda: False, has_single_tasks = lambda: False)
    monkeypatch.setattr(Engine, "get", classmethod(lambda cls: engine))
    config = Config(platforms = [
        {"id": 0, "name": "原接口", "api_format": "OpenAI", "model": "model-a", "api_key": [], "temperature": 0.7, "temperature_custom_enable": True},
        {"id": 1, "name": "Agent 接口", "api_format": "Google", "api_key": []},
    ], agent_platform = 1, token_threshold = 123)
    SecretStore.ensure_platform_identities(config.platforms)
    store.store_keys(config.platforms[0], ["original-secret"])
    store.store_keys(config.platforms[1], ["agent-secret"])
    config.save(strict = True)
    app = FastAPI()
    app.include_router(platforms.router)
    app.state.config = config
    with TestClient(app) as client:
        response = client.patch("/api/platforms/0", json = {"name": "仅改名称"})
        assert response.status_code == 200
        assert response.json()["values"]["platforms"][0]["api_key"] == "***"
        assert "original-secret" not in response.text
        assert store.resolve_keys(config.platforms[0]) == ["original-secret"]
        assert config.platforms[0]["temperature"] == 0.7
        assert config.token_threshold == 123
        assert client.post("/api/platforms/1/activate").status_code == 200
        assert (config.activate_platform, config.agent_platform) == (1, 1)
        assert client.post("/api/platforms", json = {"name": "新接口", "api_keys": ["new-secret"]}).status_code == 200
        assert store.resolve_keys(config.platforms[2]) == ["new-secret"]
        assert client.patch("/api/platforms/0", json = {"api_keys": ["***"]}).status_code == 400
        assert store.resolve_keys(config.platforms[0]) == ["original-secret"]

        original = copy.deepcopy(config.platforms)
        def fail_save(*args, **kwargs):
            raise PermissionError("不可写")
        with monkeypatch.context() as scoped:
            scoped.setattr(config, "save", fail_save)
            assert client.patch("/api/platforms/0", json = {"api_keys": ["replacement-secret"], "model": "changed"}).status_code == 500
        assert config.platforms == original
        assert store.resolve_keys(config.platforms[0]) == ["original-secret"]

        assert client.patch("/api/platforms/0", json = {"api_keys": ["replacement-secret"]}).status_code == 200
        assert store.resolve_keys(config.platforms[0]) == ["replacement-secret"]
        assert client.patch("/api/platforms/0", json = {"api_keys": []}).status_code == 200
        assert store.resolve_keys(config.platforms[0]) == []
        assert client.delete("/api/platforms/0").status_code == 200
        assert (config.activate_platform, config.agent_platform) == (0, 0)
        assert [item["id"] for item in config.platforms] == [0, 1]
        assert store.resolve_keys(config.platforms[0]) == ["agent-secret"]
        assert store.resolve_keys(config.platforms[1]) == ["new-secret"]
        assert client.patch("/api/platforms/999", json = {"name": "不存在"}).status_code == 404
        assert client.patch("/api/platforms/0", json = {"api_url": "file:///secret"}).status_code == 400
        engine.get_status = lambda: Engine.Status.TRANSLATING
        assert client.post("/api/platforms", json = {"name": "忙碌时新增"}).status_code == 409
        assert client.delete("/api/platforms/0").status_code == 409
    saved = Config().load()
    assert saved.token_threshold == 123
    assert saved.agent_platform == 0
    assert saved.platforms[0]["name"] == "Agent 接口"

def test_platform_test_reserves_engine_and_releases_after_failure(monkeypatch):
    """复用测试器时先原子占用引擎；意外异常不泄漏密钥且不会留在 TESTING。"""
    engine = Engine()
    seen = []
    def fail_test(event, data):
        assert engine.get_status() == Engine.Status.TESTING
        assert data == {"id": 0}
        raise RuntimeError("sdk 回显 sensitive-secret")
    engine.api_test = SimpleNamespace(_platform_test_start_guarded = fail_test)
    monkeypatch.setattr(Engine, "get", classmethod(lambda cls: engine))
    monkeypatch.setattr(platforms.EventManager, "get", classmethod(lambda cls: SimpleNamespace(emit = lambda event, data: seen.append((event, data)))))
    class ImmediateThread:
        def __init__(self, *, target, **kwargs):
            self.target = target
        def start(self):
            self.target()
    monkeypatch.setattr(platforms.threading, "Thread", ImmediateThread)
    app = FastAPI()
    app.include_router(platforms.router)
    app.state.config = Config(platforms = [{"id": 0, "name": "测试接口"}])
    with TestClient(app) as client:
        engine.set_status(Engine.Status.TRANSLATING)
        assert client.post("/api/platforms/0/test").status_code == 409
        assert not seen
        engine.set_status(Engine.Status.IDLE)
        assert client.post("/api/platforms/0/test").json() == {"accepted": True}
    assert engine.get_status() == Engine.Status.IDLE
    assert len(seen) == 1 and seen[0][1]["result"] is False
    assert "sensitive-secret" not in str(seen)


def test_model_list_uses_saved_credentials_and_hides_sdk_errors(monkeypatch):
    from module.Engine.API import ModelList

    engine = Engine()
    monkeypatch.setattr(Engine, "get", classmethod(lambda cls: engine))
    config = Config(platforms=[{"id": 0, "api_url": "https://example.invalid/v1", "api_format": "OpenAI", "api_key": ["test-private-key"]}])
    app = FastAPI()
    app.state.config = config
    app.include_router(platforms.router)
    seen = []
    def models(url, key, api_format):
        seen.append((url, key, api_format))
        return ["model-a", "model-b"]
    monkeypatch.setattr(ModelList, "list_models", models)
    with TestClient(app) as client:
        response = client.get("/api/platforms/0/models")
        assert response.json() == {"models": ["model-a", "model-b"]}
        assert seen == [("https://example.invalid/v1", "test-private-key", "OpenAI")]
        assert "test-private-key" not in response.text
        assert client.get("/api/platforms/99/models").status_code == 404
        engine.set_status(Engine.Status.TRANSLATING)
        assert client.get("/api/platforms/0/models").status_code == 409
        engine.set_status(Engine.Status.IDLE)
        def failed(*args):
            raise RuntimeError("test-private-key")
        monkeypatch.setattr(ModelList, "list_models", failed)
        response = client.get("/api/platforms/0/models")
        assert response.status_code == 502
        assert "test-private-key" not in response.text


def test_model_list_shared_sdk_paths(monkeypatch):
    import sys
    from module.Engine.API.ModelList import list_models
    from base.Base import Base

    calls = []
    class Client:
        def __init__(self, **kwargs):
            calls.append(kwargs)
            self.models = SimpleNamespace(list=lambda: [SimpleNamespace(id="z", name="z"), SimpleNamespace(id="a", name="a"), SimpleNamespace(id="a", name="a")])
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=Client))
    monkeypatch.setitem(sys.modules, "anthropic", SimpleNamespace(Anthropic=Client))
    monkeypatch.setitem(sys.modules, "google.genai", SimpleNamespace(Client=Client))
    import google
    monkeypatch.setattr(google, "genai", sys.modules["google.genai"], raising=False)
    for api_format in (Base.APIFormat.OPENAI, Base.APIFormat.ANTHROPIC, Base.APIFormat.GOOGLE):
        assert list_models("https://example.invalid", "key", api_format) == ["a", "z"]
    assert calls[0]["timeout"] == 30
    assert calls[2]["http_options"] == {"timeout": 30000}
    before = len(calls)
    assert list_models("", "", next(iter(Base.MACHINE_API_FORMATS))) == ["free"]
    assert len(calls) == before
