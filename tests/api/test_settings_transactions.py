"""规则保存必须完整验证和落盘，失败不得部分生效。"""
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes import settings
from module.Config import Config
from module.Engine.Engine import Engine
from module.TextProcessor import TextProcessor


def test_rule_save_is_atomic_and_busy_protected(monkeypatch):
    config = Config().load()
    config.text_preserve_data = [{"src": "original", "comment": "保留"}]
    engine = Engine()
    monkeypatch.setattr(Engine, "get", classmethod(lambda cls: engine))
    app = FastAPI()
    app.state.config = config
    app.include_router(settings.router)
    payload = {"values": {"text_preserve_data": [{"src": "next"}], "text_preserve_enable": False}}
    with TestClient(app) as client:
        invalid = client.patch("/api/settings", json={"values": {"text_preserve_data": [], "text_preserve_enable": "invalid"}})
        assert invalid.status_code == 400
        assert config.text_preserve_data[0]["src"] == "original"
        with monkeypatch.context() as scoped:
            def fail(*args, **kwargs):
                raise OSError("disk full")
            scoped.setattr(Config, "save", fail)
            assert client.patch("/api/settings", json=payload).status_code == 500
            assert config.text_preserve_data[0]["src"] == "original"
        engine.try_begin_single_task()
        assert client.patch("/api/settings", json=payload).status_code == 409
        engine.end_single_task()
        assert client.patch("/api/settings", json=payload).status_code == 200
        assert config.text_preserve_enable is False
        assert Config().load().text_preserve_data == [{"src": "next"}]
        before = json.dumps(config.honorific_placeholder_titles)
        assert client.get("/api/settings/honorific-defaults").json()["titles"] == list(TextProcessor.DEFAULT_HONORIFIC_TITLES)
        assert json.dumps(config.honorific_placeholder_titles) == before
