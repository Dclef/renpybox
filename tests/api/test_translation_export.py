"""写入译文文件：只在空闲或翻译中受理，空闲时按当前项目缓存目录导出。"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes import translation
from base.Base import Base
from module.Config import Config
from module.Engine.Engine import Engine


def _client(config: Config) -> TestClient:
    app = FastAPI()
    app.state.config = config
    app.include_router(translation.router)
    return TestClient(app)


def _engine(monkeypatch) -> Engine:
    engine = Engine()
    monkeypatch.setattr(Engine, "get", classmethod(lambda cls: engine))
    return engine


def test_idle_export_uses_resolved_cache_folder(monkeypatch, tmp_path) -> None:
    _engine(monkeypatch)
    emitted: list[tuple] = []
    monkeypatch.setattr(translation, "_emit", lambda event, data: emitted.append((event, data)))
    resolved = tmp_path / "project_cache_output"
    monkeypatch.setattr(translation, "resolve_translation_output", lambda config: resolved)

    with _client(Config().load()) as client:
        body = client.post("/api/translation/export").json()

    assert body["ok"] is True
    assert emitted == [(Base.Event.TRANSLATION_MANUAL_EXPORT, {"output_folder": str(resolved)})]


def test_translating_export_is_accepted(monkeypatch) -> None:
    engine = _engine(monkeypatch)
    engine.set_status(Engine.Status.TRANSLATING)
    emitted: list = []
    monkeypatch.setattr(translation, "_emit", lambda event, data: emitted.append(event))

    with _client(Config().load()) as client:
        response = client.post("/api/translation/export")

    assert response.status_code == 200
    assert emitted == [Base.Event.TRANSLATION_MANUAL_EXPORT]


@pytest.mark.parametrize("busy", ["stopping", "quality", "testing", "barrier"])
def test_export_rejects_states_translator_would_ignore(monkeypatch, busy) -> None:
    engine = _engine(monkeypatch)
    if busy == "stopping":
        engine.set_status(Engine.Status.STOPPING)
    elif busy == "quality":
        engine.set_status(Engine.Status.QUALITY)
    elif busy == "testing":
        engine.set_status(Engine.Status.TESTING)
    else:
        engine.set_stop_barrier(True)
    monkeypatch.setattr(translation, "_emit", lambda event, data: pytest.fail("不可导出时不得投递事件"))

    with _client(Config().load()) as client:
        response = client.post("/api/translation/export")

    assert response.status_code == 409
    assert response.json()["detail"]
