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
        values = response.json()["values"]
        platforms = values["platforms"]
        assert values["activate_platform"] == next(item["id"] for item in platforms if item["api_format"] == "Bing")
        assert len(platforms) == 17
        assert platforms[0]["name"] == "SakuraLLM"
        index_translate = next(item for item in platforms if item["api_format"] == "IndexTranslate")
        assert index_translate["group"] == "online"
        assert index_translate["name"] == "哔哩哔哩（免费）"
        assert index_translate["api_url"] == "https://index-translate.bilibili.com/v1"
        assert index_translate["model"] == "Index-Translate-35B-A3B"
        # 播种后 id 连续，接口管理页可以直接按 id 启用
        assert [item["id"] for item in platforms] == list(range(17))

    # 落盘结果与内存一致，重启后不会重复播种
    saved = json.loads(path.read_text(encoding = "utf-8"))
    assert len(saved["platforms"]) == 17
    assert saved["platforms"][saved["activate_platform"]]["api_format"] == "Bing"
    assert next(item for item in saved["platforms"] if item["api_format"] == "IndexTranslate")["api_key"] == []
    with TestClient(create_app()) as client:
        assert len(client.get("/api/settings").json()["values"]["platforms"]) == 17


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
    assert {"GoogleFree", "Bing", "IndexTranslate"}.issubset(formats)


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
