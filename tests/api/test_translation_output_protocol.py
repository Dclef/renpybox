"""翻译输出协议与单行模式联动：SINGLE_TEXT 只能配合单行请求，否则整轮翻译失败。"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes import settings
from api.routes.settings import sync_output_protocol
from module.Config import Config
from module.Engine.Engine import Engine


def _client(config: Config) -> TestClient:
    app = FastAPI()
    app.state.config = config
    app.include_router(settings.router)
    return TestClient(app)


def _patch(client: TestClient, values: dict) -> dict:
    response = client.patch("/api/settings", json = {"values": values})
    assert response.status_code == 200, response.text
    return response.json()["values"]


def test_patch_keeps_protocol_and_single_line_consistent(monkeypatch) -> None:
    monkeypatch.setattr(Engine, "get", classmethod(lambda cls: Engine()))
    config = Config().load()

    with _client(config) as client:
        values = _patch(client, {"translation_output_protocol": "SINGLE_TEXT"})
        assert values["single_line_translation_enable"] is True

        values = _patch(client, {"single_line_translation_enable": False})
        assert values["translation_output_protocol"] == Config.OUTPUT_PROTOCOL_STRUCTURED

        values = _patch(client, {"single_line_translation_enable": True})
        assert values["translation_output_protocol"] == Config.OUTPUT_PROTOCOL_SINGLE_TEXT

        values = _patch(client, {"translation_output_protocol": "JSONLINE"})
        assert values["single_line_translation_enable"] is False

        invalid = client.patch("/api/settings", json = {"values": {"translation_output_protocol": "BAD"}})
        assert invalid.status_code == 400

    saved = Config().load()
    assert saved.translation_output_protocol == Config.OUTPUT_PROTOCOL_JSONLINE
    assert saved.single_line_translation_enable is False


@pytest.mark.parametrize(
    ("protocol", "single_line", "expected"),
    [
        (Config.OUTPUT_PROTOCOL_SINGLE_TEXT, False, (Config.OUTPUT_PROTOCOL_SINGLE_TEXT, True)),
        (Config.OUTPUT_PROTOCOL_STRUCTURED, True, (Config.OUTPUT_PROTOCOL_SINGLE_TEXT, True)),
        (Config.OUTPUT_PROTOCOL_JSONLINE, False, (Config.OUTPUT_PROTOCOL_JSONLINE, False)),
    ],
)
def test_sync_normalizes_legacy_inconsistent_config(protocol, single_line, expected) -> None:
    config = Config(translation_output_protocol = protocol, single_line_translation_enable = single_line)
    sync_output_protocol(config)
    assert (config.translation_output_protocol, config.single_line_translation_enable) == expected


def test_start_snapshot_normalizes_saved_single_text_without_switch() -> None:
    from api.routes import translation
    from base.Base import Base

    config = Config().load()
    config.translation_output_protocol = Config.OUTPUT_PROTOCOL_SINGLE_TEXT
    config.single_line_translation_enable = False
    config.save(strict = True)

    payload, rejection = translation._prepare_payload(None, Base.TranslationStatus.TRANSLATING, "req")

    assert rejection is None
    assert payload["config"].single_line_translation_enable is True
    # 只改本轮快照，不偷偷改写用户配置文件。
    assert Config().load().single_line_translation_enable is False
