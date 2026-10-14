"""桌面版启动播种：全新安装不能再停在空接口列表。

Python / Qt5 版在接口页构造时播种默认接口（``frontend/Project/PlatformPage.py``），
桌面版此前没有这一步，用户升级后会看到「还没有翻译接口」，看起来像数据丢了。
播种放在 sidecar 的 lifespan 里，与 Qt5 行为对齐。
"""

import json

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from module.Config import Config
from module.Secret.SecretStore import MemoryBackend, SecretStore


@pytest.fixture(autouse = True)
def isolated_secrets(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(SecretStore, "_instance", SecretStore(MemoryBackend()))


def test_startup_seeds_default_platforms_when_list_is_null(monkeypatch, tmp_path) -> None:
    path = tmp_path / "config.json"
    monkeypatch.setattr(Config, "CONFIG_PATH", str(path))
    config = Config()
    config.platforms = None
    config.save(strict = True)

    with TestClient(create_app()) as client:
        response = client.get("/api/settings")

        assert response.status_code == 200
        platforms = response.json()["values"]["platforms"]
        assert len(platforms) == 16
        assert platforms[0]["name"] == "SakuraLLM"
        # 播种后 id 连续，接口管理页可以直接按 id 启用
        assert [item["id"] for item in platforms] == list(range(16))

    # 落盘结果与内存一致，重启后不会重复播种
    saved = json.loads(path.read_text(encoding = "utf-8"))
    assert len(saved["platforms"]) == 16
    with TestClient(create_app()) as client:
        assert len(client.get("/api/settings").json()["values"]["platforms"]) == 16


def test_startup_keeps_user_platforms_and_appends_machine_formats(monkeypatch, tmp_path) -> None:
    path = tmp_path / "config.json"
    monkeypatch.setattr(Config, "CONFIG_PATH", str(path))
    config = Config(
        platforms = [{
            "id": 0,
            "name": "我调好的接口",
            "group": "online",
            "api_format": "OpenAI",
            "api_url": "https://example.invalid/v1",
            "model": "my-model",
            "api_key": [],
            "thinking": {"level": "MAX"},
        }],
        activate_platform = 0,
    )
    config.save(strict = True)

    with TestClient(create_app()) as client:
        values = client.get("/api/settings").json()["values"]

    names = [item["name"] for item in values["platforms"]]
    assert "我调好的接口" in names
    assert values["platforms"][0]["name"] == "我调好的接口"
    assert values["platforms"][0]["model"] == "my-model"
    assert values["platforms"][0]["thinking"] == {"level": "MAX"}
    assert values["activate_platform"] == 0
    formats = [item["api_format"] for item in values["platforms"]]
    assert "GoogleFree" in formats and "Bing" in formats


def test_startup_survives_unwritable_config_directory(monkeypatch, tmp_path) -> None:
    """播种失败不能让 sidecar 起不来：只记日志，保留原配置继续启动。"""
    path = tmp_path / "config.json"
    monkeypatch.setattr(Config, "CONFIG_PATH", str(path))
    Config(platforms = None).save(strict = True)

    def fail_save(*args, **kwargs):
        raise PermissionError("只读目录")

    monkeypatch.setattr(Config, "save", fail_save)

    with TestClient(create_app()) as client:
        assert client.get("/health").json()["ok"] is True
        assert client.get("/api/settings").status_code == 200
