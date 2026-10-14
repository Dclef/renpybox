"""规则保存必须完整验证和落盘，失败不得部分生效。"""
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes import settings
from module.Config import Config
from module.Engine.Engine import Engine
from module.TextProcessor import TextProcessor


def _settings_client(monkeypatch, config: Config | None = None) -> tuple[TestClient, Config]:
    config = config if config is not None else Config()
    engine = Engine()
    monkeypatch.setattr(Engine, "get", classmethod(lambda cls: engine))
    app = FastAPI()
    app.state.config = config
    app.include_router(settings.router)
    return TestClient(app), config


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


def test_numeric_settings_reject_out_of_range_values(monkeypatch, tmp_path):
    """整数设置必须有范围：负数 max_workers / request_timeout 会让线程池死锁。"""
    monkeypatch.setattr(Config, "CONFIG_PATH", str(tmp_path / "config.json"))
    client, config = _settings_client(monkeypatch)

    with client:
        # Qt5 BasicSettingsPage 是 QSpinBox setRange(0, 9999999)。
        rejected = client.patch("/api/settings", json = {"values": {"max_workers": -1}})
        assert rejected.status_code == 400
        assert "max_workers" in rejected.json()["detail"]
        assert config.max_workers == 16

        assert client.patch("/api/settings", json = {"values": {"request_timeout": -5}}).status_code == 400
        assert config.request_timeout == 60

        # 上限同样受约束；0 是合法值（表示关闭/自动）。
        assert client.patch("/api/settings", json = {"values": {"max_workers": 99999999}}).status_code == 400
        assert config.max_workers == 16

        accepted = client.patch("/api/settings", json = {"values": {"max_workers": 0}})
        assert accepted.status_code == 200
        assert config.max_workers == 0
        assert client.patch("/api/settings", json = {"values": {"max_workers": 9999999}}).status_code == 200
        assert config.max_workers == 9999999

        # 资产批次预算下限是 1：0 会让预算失效。
        assert client.patch("/api/settings", json = {"values": {"asset_prompt_max_items": 0}}).status_code == 400
        assert client.patch("/api/settings", json = {"values": {"asset_prompt_max_items": 64}}).status_code == 200

        # 表外允许负值的索引字段不受影响；未知键仍然是 400。
        assert client.patch("/api/settings", json = {"values": {"agent_platform": -1}}).status_code == 200
        assert config.agent_platform == -1
        assert client.patch("/api/settings", json = {"values": {"not_a_setting": 1}}).status_code == 400


def _bound_cases():
    cases = []
    for field, (minimum, maximum) in Config.INTEGER_SETTING_BOUNDS.items():
        cases.append(pytest.param(field, minimum, maximum, id=field))
    return cases


@pytest.mark.parametrize("field, minimum, maximum", _bound_cases())
def test_integer_setting_bounds_accept_edges_and_reject_outside(
    monkeypatch, tmp_path, field, minimum, maximum,
):
    """INTEGER_SETTING_BOUNDS 全部 13 项：边界可写，越界拒绝。"""
    monkeypatch.setattr(Config, "CONFIG_PATH", str(tmp_path / "config.json"))
    client, config = _settings_client(monkeypatch)

    with client:
        assert client.patch("/api/settings", json={"values": {field: minimum}}).status_code == 200
        assert getattr(config, field) == minimum
        assert client.patch("/api/settings", json={"values": {field: maximum}}).status_code == 200
        assert getattr(config, field) == maximum

        below = client.patch("/api/settings", json={"values": {field: minimum - 1}})
        assert below.status_code == 400
        assert field in below.json()["detail"]
        assert getattr(config, field) == maximum

        above = client.patch("/api/settings", json={"values": {field: maximum + 1}})
        assert above.status_code == 400
        assert field in above.json()["detail"]
        assert getattr(config, field) == maximum

    assert getattr(config, field) == maximum


@pytest.mark.parametrize("bad_value", [True, False, 1.5, "16", "0", "max_workers"])
@pytest.mark.parametrize("field", list(Config.INTEGER_SETTING_BOUNDS))
def test_integer_settings_reject_bool_float_and_string(monkeypatch, tmp_path, field, bad_value):
    """整数字段拒绝 bool（含 JSON true/false）、float、整数字面量字符串。"""
    monkeypatch.setattr(Config, "CONFIG_PATH", str(tmp_path / "config.json"))
    client, config = _settings_client(monkeypatch)
    before = getattr(config, field)

    with client:
        response = client.patch("/api/settings", json={"values": {field: bad_value}})
        assert response.status_code == 400
        assert field in response.json()["detail"]
        assert getattr(config, field) == before


@pytest.mark.parametrize("polluted", [True, False, "8", 3.14])
def test_integer_patch_recovers_from_polluted_current_value(monkeypatch, tmp_path, polluted):
    """内存/落盘被污染后，后续合法整数 PATCH 仍按声明类型修复。"""
    monkeypatch.setattr(Config, "CONFIG_PATH", str(tmp_path / "config.json"))
    config = Config()
    config.max_workers = polluted  # type: ignore[assignment]
    client, config = _settings_client(monkeypatch, config)

    with client:
        rejected = client.patch("/api/settings", json={"values": {"max_workers": True}})
        assert rejected.status_code == 400
        assert config.max_workers == polluted

        accepted = client.patch("/api/settings", json={"values": {"max_workers": 12}})
        assert accepted.status_code == 200
        assert config.max_workers == 12


@pytest.mark.parametrize("save", [True, False])
def test_mixed_valid_and_invalid_patch_is_transactional(monkeypatch, tmp_path, save):
    """同一 PATCH 含合法+非法字段时整单失败：内存不改，save 也不落盘。"""
    monkeypatch.setattr(Config, "CONFIG_PATH", str(tmp_path / "config.json"))
    config = Config()
    config.max_workers = 16
    config.request_timeout = 60
    config.save(strict=True)
    client, config = _settings_client(monkeypatch, config)

    with client:
        response = client.patch(
            "/api/settings",
            json={
                "values": {"max_workers": 8, "request_timeout": -1},
                "save": save,
            },
        )
        assert response.status_code == 400
        assert config.max_workers == 16
        assert config.request_timeout == 60
        loaded = Config().load()
        assert loaded.max_workers == 16
        assert loaded.request_timeout == 60


def test_agent_platform_index_negative_one_still_allowed(monkeypatch, tmp_path):
    """索引字段 -1 哨兵必须保留，不受整数范围表约束。"""
    monkeypatch.setattr(Config, "CONFIG_PATH", str(tmp_path / "config.json"))
    client, config = _settings_client(monkeypatch)
    with client:
        assert client.patch("/api/settings", json={"values": {"agent_platform": -1}}).status_code == 200
        assert config.agent_platform == -1


@pytest.mark.parametrize(
    "value",
    [True, False, 1.0, "0", None],
)
def test_validate_integer_setting_rejects_non_int(value):
    with pytest.raises(ValueError, match="期望整数"):
        Config.validate_integer_setting("max_workers", value)


def test_negative_int_setting_pattern_matches_lowercase_field_names():
    """表外兜底正则必须匹配 snake_case 小写字段名。"""
    assert Config.integer_setting_bounds("custom_timeout_seconds") == (0, Config.SETTING_VALUE_MAX)
    assert Config.integer_setting_bounds("widget_item_count") == (0, Config.SETTING_VALUE_MAX)
    assert Config.integer_setting_bounds("agent_platform") is None
    assert Config.INTEGER_SETTING_BOUNDS["renpy_format_indent"][0] == 0
    assert Config.INTEGER_SETTING_BOUNDS["renpy_format_line_width"][0] == 0
