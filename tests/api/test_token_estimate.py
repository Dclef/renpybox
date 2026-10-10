"""Token 估算：无 body / {} 兼容，无平台与无条目返回 409。"""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes import translation
from base.Base import Base
from module.Cache.CacheItem import CacheItem
from module.Config import Config
from module.Engine.Engine import Engine
from module.TokenEstimator import TokenEstimate


def _app(config: Config) -> FastAPI:
    app = FastAPI()
    app.state.config = config
    app.include_router(translation.router)
    return app


def _platform(pid: int = 0, name: str = "测试接口") -> dict:
    return {
        "id": pid,
        "name": name,
        "api_format": "OpenAI",
        "model": "test-model",
        "api_key": [],
        "input_price_per_million": 1.0,
        "output_price_per_million": 2.0,
    }


@pytest.fixture
def estimate_env(monkeypatch):
    """隔离引擎与估算器，不触真实模型 / 用户工程。"""
    engine = Engine()
    monkeypatch.setattr(Engine, "get", classmethod(lambda cls: engine))
    calls: list[dict] = []

    class FakeEstimator:
        def __init__(self, config, platform, items):
            calls.append({"platform": platform, "items": items})

        def estimate(self) -> TokenEstimate:
            return TokenEstimate(
                total_source_tokens = 10,
                estimated_input_tokens = 20,
                estimated_output_tokens = 12,
                estimated_cost = 0.05,
                batch_count = 1,
                untranslated_count = 1,
            )

    monkeypatch.setattr("module.TokenEstimator.TokenEstimator", FakeEstimator)
    monkeypatch.setattr(
        translation,
        "_load_items_for_estimate",
        lambda config: [CacheItem(src = "Hello", status = Base.TranslationStatus.UNTRANSLATED)],
    )
    return SimpleNamespace(calls = calls)


@pytest.mark.parametrize(
    "send",
    [
        lambda client: client.post("/api/translation/estimate"),
        lambda client: client.post("/api/translation/estimate", json = {}),
        # 复现原桌面端：带 application/json 但 body 为空 → 旧实现 422 Field required
        lambda client: client.post(
            "/api/translation/estimate",
            content = b"",
            headers = {"Content-Type": "application/json"},
        ),
    ],
)
def test_estimate_accepts_missing_or_empty_body(estimate_env, send):
    config = Config(platforms = [_platform()], activate_platform = 0)
    with TestClient(_app(config)) as client:
        response = send(client)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["untranslated_count"] == 1
    assert body["batch_count"] == 1
    assert body["estimated_input_tokens"] == 20
    assert estimate_env.calls[-1]["platform"]["id"] == 0


def test_estimate_uses_platform_id_when_provided(estimate_env):
    config = Config(
        platforms = [_platform(0, "A"), _platform(1, "B")],
        activate_platform = 0,
    )
    with TestClient(_app(config)) as client:
        response = client.post("/api/translation/estimate", json = {"platform_id": 1})
    assert response.status_code == 200
    assert estimate_env.calls[0]["platform"]["name"] == "B"


def test_estimate_409_without_platform(estimate_env):
    config = Config(platforms = [], activate_platform = 0)
    with TestClient(_app(config)) as client:
        response = client.post("/api/translation/estimate", json = {})
    assert response.status_code == 409
    assert "平台" in response.json()["detail"]
    assert estimate_env.calls == []


def test_estimate_409_without_items(monkeypatch):
    engine = Engine()
    monkeypatch.setattr(Engine, "get", classmethod(lambda cls: engine))
    monkeypatch.setattr(translation, "_load_items_for_estimate", lambda config: [])
    config = Config(platforms = [_platform()], activate_platform = 0)
    with TestClient(_app(config)) as client:
        response = client.post("/api/translation/estimate", json = {})
    assert response.status_code == 409
    assert "条目" in response.json()["detail"]
