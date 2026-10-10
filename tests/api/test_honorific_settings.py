"""称呼桥接配置：备注往返、校验、忙碌互斥与保存失败不落 live。"""
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes import settings
from module.Config import Config
from module.Engine.Engine import Engine
from module.TextProcessor import TextProcessor


def _client(config: Config, engine: Engine, monkeypatch):
    monkeypatch.setattr(Engine, "get", classmethod(lambda cls: engine))
    app = FastAPI()
    app.state.config = config
    app.include_router(settings.router)
    return TestClient(app)


def test_honorific_titles_string_and_dict_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "CONFIG_PATH", str(tmp_path / "config.json"))
    config = Config().load()
    engine = Engine()
    with _client(config, engine, monkeypatch) as client:
        payload = {
            "values": {
                "honorific_placeholder_titles": [
                    "mr",
                    {"src": "Dr", "comment": "医生"},
                    {"src": "  ", "comment": "应被过滤"},
                    {"src": "ms", "comment": ""},
                ],
                "honorific_placeholder_bridge_enable": True,
            }
        }
        response = client.patch("/api/settings", json=payload)
        assert response.status_code == 200, response.text
        stored = response.json()["values"]["honorific_placeholder_titles"]
        assert stored == ["mr", {"src": "dr", "comment": "医生"}, "ms"]
        reloaded = Config().load()
        assert reloaded.honorific_placeholder_titles == ["mr", {"src": "dr", "comment": "医生"}, "ms"]
        assert TextProcessor.parse_honorific_title_entries(reloaded.honorific_placeholder_titles) == [
            {"src": "mr", "comment": ""},
            {"src": "dr", "comment": "医生"},
            {"src": "ms", "comment": ""},
        ]


def test_honorific_invalid_input_and_save_failure_do_not_mutate_live(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "CONFIG_PATH", str(tmp_path / "config.json"))
    config = Config().load()
    config.honorific_placeholder_titles = ["mr", {"src": "dr", "comment": "保留"}]
    config.honorific_placeholder_bridge_enable = True
    engine = Engine()
    with _client(config, engine, monkeypatch) as client:
        bad_type = client.patch("/api/settings", json={
            "values": {"honorific_placeholder_titles": [{"src": 1, "comment": "x"}]},
        })
        assert bad_type.status_code == 400
        assert config.honorific_placeholder_titles == ["mr", {"src": "dr", "comment": "保留"}]

        bad_bool = client.patch("/api/settings", json={
            "values": {"honorific_placeholder_bridge_enable": "yes"},
        })
        assert bad_bool.status_code == 400
        assert config.honorific_placeholder_bridge_enable is True

        with monkeypatch.context() as scoped:
            def fail(*args, **kwargs):
                raise OSError("disk full")
            scoped.setattr(Config, "save", fail)
            failed = client.patch("/api/settings", json={
                "values": {
                    "honorific_placeholder_titles": ["sir"],
                    "honorific_placeholder_bridge_enable": False,
                },
            })
            assert failed.status_code == 500
            assert config.honorific_placeholder_titles == ["mr", {"src": "dr", "comment": "保留"}]
            assert config.honorific_placeholder_bridge_enable is True


def test_honorific_engine_busy_rejects_idle_barrier_and_single(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "CONFIG_PATH", str(tmp_path / "config.json"))
    config = Config().load()
    before = json.dumps(config.honorific_placeholder_titles, ensure_ascii=False)
    engine = Engine()
    payload = {"values": {"honorific_placeholder_titles": ["captain"]}}
    with _client(config, engine, monkeypatch) as client:
        engine.set_status(Engine.Status.TRANSLATING)
        assert client.patch("/api/settings", json=payload).status_code == 409
        engine.set_status(Engine.Status.IDLE)

        engine.set_stop_barrier(True)
        assert client.patch("/api/settings", json=payload).status_code == 409
        engine.set_stop_barrier(False)

        assert engine.try_begin_single_task()
        assert client.patch("/api/settings", json=payload).status_code == 409
        engine.end_single_task()

        assert client.patch("/api/settings", json=payload).status_code == 200
        assert config.honorific_placeholder_titles == ["captain"]
        assert json.dumps(Config().load().honorific_placeholder_titles, ensure_ascii=False) != before


def test_honorific_empty_list_allowed_and_defaults_endpoint_untouched(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "CONFIG_PATH", str(tmp_path / "config.json"))
    config = Config().load()
    config.honorific_placeholder_titles = ["mr"]
    engine = Engine()
    with _client(config, engine, monkeypatch) as client:
        cleared = client.patch("/api/settings", json={
            "values": {"honorific_placeholder_titles": [], "honorific_placeholder_bridge_enable": True},
        })
        assert cleared.status_code == 200
        assert cleared.json()["values"]["honorific_placeholder_titles"] == []
        assert cleared.json()["values"]["honorific_placeholder_bridge_enable"] is True
        defaults = client.get("/api/settings/honorific-defaults").json()["titles"]
        assert defaults == list(TextProcessor.DEFAULT_HONORIFIC_TITLES)
        assert config.honorific_placeholder_titles == []

def test_rule_save_holds_engine_until_disk_commit(tmp_path, monkeypatch):
    import threading

    monkeypatch.setattr(Config, 'CONFIG_PATH', str(tmp_path / 'config.json'))
    config = Config()
    config.honorific_placeholder_titles = ['mr']
    engine = Engine()
    entered = threading.Event()
    finish = threading.Event()

    def save(snapshot, strict=False):
        entered.set()
        assert finish.wait(3)

    monkeypatch.setattr(Config, 'save', save)
    with _client(config, engine, monkeypatch) as client:
        responses = []
        worker = threading.Thread(target=lambda: responses.append(client.patch('/api/settings', json={
            'values': {'honorific_placeholder_titles': ['sir']},
        })))
        worker.start()
        try:
            assert entered.wait(3)
            assert config.honorific_placeholder_titles == ['mr']
            assert not engine.try_set_status(Engine.Status.IDLE, Engine.Status.TRANSLATING)
            assert not engine.try_begin_single_task()
        finally:
            finish.set()
            worker.join(3)
        assert responses[0].status_code == 200
        assert config.honorific_placeholder_titles == ['sir']
        assert engine.get_status() == Engine.Status.IDLE
