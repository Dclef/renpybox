"""新增接口的名称去重：``POST /api/platforms`` 不能产生同名记录。

Qt5 规则见 ``frontend/Project/PlatformPage.py:65-74``（``名称`` → ``名称 2``），
实现在 ``module/Project/PlatformNaming.py``，两端共用。
"""

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes import platforms
from module.Config import Config
from module.Engine.Engine import Engine
from module.Secret.SecretStore import MemoryBackend, SecretStore


def _client(platforms_data: list[dict] | None = None) -> tuple[TestClient, Config]:
    config = Config(platforms = platforms_data if platforms_data is not None else [])
    app = FastAPI()
    app.include_router(platforms.router)
    app.state.config = config
    return TestClient(app), config


def test_create_platform_deduplicates_duplicate_name(monkeypatch, tmp_path):
    monkeypatch.setattr(SecretStore, "_instance", SecretStore(MemoryBackend()))
    monkeypatch.setattr(Config, "CONFIG_PATH", str(tmp_path / "config.json"))
    engine = SimpleNamespace(
        get_status = lambda: Engine.Status.IDLE,
        has_stop_barrier = lambda: False,
        has_single_tasks = lambda: False,
    )
    monkeypatch.setattr(Engine, "get", classmethod(lambda cls: engine))

    client, config = _client([
        {"id": 0, "name": "OpenAI 官方", "api_format": "OpenAI", "api_key": []},
        {"id": 1, "name": "OpenAI 官方 2", "api_format": "OpenAI", "api_key": []},
    ])
    with client:
        response = client.post("/api/platforms", json = {"name": "OpenAI 官方"})
        assert response.status_code == 200
        # 已占用 2 → 新建记录取下一个可用编号，与 Qt5 的递增后缀一致。
        assert config.platforms[2]["name"] == "OpenAI 官方 3"
        assert config.platforms[2]["id"] == 2
        assert response.json()["values"]["platforms"][2]["name"] == "OpenAI 官方 3"

        # 名称未被占用时保持原样；首尾空白照旧剥掉。
        assert client.post("/api/platforms", json = {"name": "  新接口  "}).status_code == 200
        assert config.platforms[3]["name"] == "新接口"

    assert len({item["name"] for item in config.platforms}) == len(config.platforms)
