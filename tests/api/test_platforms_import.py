"""``POST /api/platforms/import``：把旧版配置的接口搬进桌面版。

桌面版把配置放在 ``%APPDATA%\\RenpyBox``（旧版为 ``RenpyBox-newUI``），旧 Python 版放在程序目录，
两者互不可见。导入只搬运接口字段与稳定凭据身份：密钥本体在 Windows 凭据
管理器里且是全局的，凭身份即可自动认领。
"""

import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes import platforms
from module.Config import Config
from module.Engine.Engine import Engine
from module.Secret.SecretStore import CREDENTIAL_ID_FIELD, MemoryBackend, SecretStore


@pytest.fixture(autouse = True)
def isolated_engine(monkeypatch: pytest.MonkeyPatch):
    engine = SimpleNamespace(
        get_status = lambda: Engine.Status.IDLE,
        has_stop_barrier = lambda: False,
        has_single_tasks = lambda: False,
    )
    monkeypatch.setattr(Engine, "get", classmethod(lambda cls: engine))
    return engine


@pytest.fixture(autouse = True)
def isolated_secrets(monkeypatch: pytest.MonkeyPatch):
    store = SecretStore(MemoryBackend())
    monkeypatch.setattr(SecretStore, "_instance", store)
    return store


def _client(current: list[dict] | None = None, activate: int = 0) -> tuple[TestClient, Config]:
    config = Config(platforms = current if current is not None else [], activate_platform = activate)
    app = FastAPI()
    app.include_router(platforms.router)
    app.state.config = config
    return TestClient(app), config


def _write_legacy(tmp_path, platforms_data, activate: int | None = None) -> str:
    payload: dict = {"config_version": 2, "platforms": platforms_data}
    if activate is not None:
        payload["activate_platform"] = activate
    path = tmp_path / "legacy-config.json"
    path.write_text(json.dumps(payload, ensure_ascii = False), encoding = "utf-8")
    return str(path)


def _legacy_platform(name: str, identity: str, **overrides) -> dict:
    item = {
        "id": 0,
        "name": name,
        "group": "online",
        "api_format": "OpenAI",
        "api_url": "https://example.invalid/v1",
        "model": "model-a",
        "api_key": [],
        "thinking": {"level": "OFF"},
        CREDENTIAL_ID_FIELD: identity,
    }
    item.update(overrides)
    return item


def test_import_adopts_legacy_platforms_and_credentials(monkeypatch, tmp_path) -> None:
    store = SecretStore(MemoryBackend())
    monkeypatch.setattr(SecretStore, "_instance", store)
    identity = "a" * 32
    # 旧版那台机器上，密钥已经存在凭据管理器里
    store.store_keys({CREDENTIAL_ID_FIELD: identity}, ["legacy-secret"])

    path = _write_legacy(tmp_path, [_legacy_platform("旧版接口", identity)], activate = 0)
    client, config = _client()

    with client:
        response = client.post("/api/platforms/import", json = {"path": path})

        assert response.status_code == 200
        body = response.json()
        assert body["imported"] == 1
        assert body["skipped"] == 0
        assert config.activate_platform == 0
        # 密钥靠稳定身份自动认领，不必搬运
        assert store.resolve_keys(config.platforms[0]) == ["legacy-secret"]
        # 响应仍走通用脱敏，不回传明文密钥
        assert "legacy-secret" not in response.text

    # 落盘内容可被重新读出，且补齐了机翻接口
    saved = Config().load()
    names = [item["name"] for item in saved.platforms]
    assert "旧版接口" in names
    assert "GoogleFree" in [item["api_format"] for item in saved.platforms]


def test_import_moves_plaintext_keys_into_credential_store(monkeypatch, tmp_path) -> None:
    """旧配置里残留的明文密钥要迁进凭据库，不能留在 JSON 里。"""
    store = SecretStore(MemoryBackend())
    monkeypatch.setattr(SecretStore, "_instance", store)
    identity = "b" * 32
    path = _write_legacy(tmp_path, [_legacy_platform("明文接口", identity, api_key = ["plain-secret"])])

    client, config = _client()
    with client:
        assert client.post("/api/platforms/import", json = {"path": path}).status_code == 200

    assert store.resolve_keys(config.platforms[0]) == ["plain-secret"]
    assert config.platforms[0]["api_key"] == []


def test_import_appends_without_overwriting_existing_platforms(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(SecretStore, "_instance", SecretStore(MemoryBackend()))
    identity = "c" * 32
    mine = _legacy_platform("我调好的接口", identity, model = "my-model")
    legacy_dup = _legacy_platform("旧版里的同名接口", identity, model = "legacy-model")
    legacy_new = _legacy_platform("旧版新增", "d" * 32)
    path = _write_legacy(tmp_path, [legacy_dup, legacy_new])

    client, config = _client([mine])
    with client:
        body = client.post("/api/platforms/import", json = {"path": path}).json()

    assert (body["imported"], body["skipped"]) == (1, 1)
    names = [item["name"] for item in config.platforms]
    assert "我调好的接口" in names and "旧版新增" in names
    # 当前配置里那条记录不被旧版覆盖
    assert config.platforms[0]["name"] == "我调好的接口"
    assert config.platforms[0]["model"] == "my-model"


def test_import_activates_legacy_selection(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(SecretStore, "_instance", SecretStore(MemoryBackend()))
    legacy = [_legacy_platform("A", "e" * 32), _legacy_platform("B", "f" * 32)]
    legacy[0]["id"], legacy[1]["id"] = 0, 1
    path = _write_legacy(tmp_path, legacy, activate = 1)

    client, config = _client()
    with client:
        assert client.post("/api/platforms/import", json = {"path": path}).status_code == 200

    assert config.activate_platform == 1
    assert config.get_platform(1)["name"] == "B"


def test_import_keeps_current_selection_when_not_requested(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(SecretStore, "_instance", SecretStore(MemoryBackend()))
    path = _write_legacy(tmp_path, [_legacy_platform("A", "1" * 32)], activate = 0)

    client, config = _client()
    with client:
        assert client.post("/api/platforms/import", json = {"path": path, "activate": False}).status_code == 200

    assert config.activate_platform == 0


def test_import_rejects_missing_or_invalid_files(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(SecretStore, "_instance", SecretStore(MemoryBackend()))
    client, config = _client()

    missing = tmp_path / "missing.json"
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding = "utf-8")
    no_platforms = tmp_path / "no-platforms.json"
    no_platforms.write_text(json.dumps({"theme": "LIGHT"}), encoding = "utf-8")
    empty = _write_legacy(tmp_path, [])

    with client:
        for path, expected in (
            (str(missing), "找不到这个文件"),
            (str(broken), "无法读取这份配置"),
            (str(no_platforms), "没有接口列表"),
            (empty, "没有可导入的接口"),
        ):
            response = client.post("/api/platforms/import", json = {"path": path})
            assert response.status_code == 400, path
            assert expected in response.json()["detail"], path

    assert config.platforms == []


def test_import_is_blocked_while_engine_is_busy(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(SecretStore, "_instance", SecretStore(MemoryBackend()))
    path = _write_legacy(tmp_path, [_legacy_platform("A", "2" * 32)])
    client, config = _client()

    with client:
        Engine.get().get_status = lambda: Engine.Status.TRANSLATING
        response = client.post("/api/platforms/import", json = {"path": path})
        assert response.status_code == 409
    assert config.platforms == []


def test_import_rolls_back_when_save_fails(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(SecretStore, "_instance", SecretStore(MemoryBackend()))
    path = _write_legacy(tmp_path, [_legacy_platform("A", "3" * 32)])
    client, config = _client()

    def fail_save(*args, **kwargs):
        raise PermissionError("只读目录")

    with client:
        monkeypatch.setattr(config, "save", fail_save)
        response = client.post("/api/platforms/import", json = {"path": path})

    assert response.status_code == 500
    assert config.platforms == []


def test_import_after_startup_seeding_reclaims_legacy_identities(monkeypatch, tmp_path) -> None:
    """复现用户场景：全新安装启动时播种了 16 条默认接口，随后导入旧版配置。

    播种出来的条目没有密钥，应当认领旧版身份而不是再追加一份同名接口 ——
    否则列表会翻倍到 32 条，而且哪一条都读不到原来的密钥。
    """
    store = SecretStore(MemoryBackend())
    monkeypatch.setattr(SecretStore, "_instance", store)

    # 旧版 16 条接口，密钥都在凭据管理器里
    legacy = []
    for index in range(16):
        identity = f"{index:032d}"
        item = _legacy_platform(f"接口 {index}", identity, api_url = f"https://api{index}.example/v1")
        item["id"] = index
        legacy.append(item)
        store.store_keys(item, [f"secret-{index}"])

    path = _write_legacy(tmp_path, legacy, activate = 3)
    client, config = _client()

    with client:
        # 先模拟启动播种：全新安装的默认接口
        from module.Project.PlatformDefaults import load_default_platforms

        config.platforms = load_default_platforms()
        config.save(strict = True)

        # 旧版那 16 条与默认模板不同名，会全部作为新条目导入
        body = client.post("/api/platforms/import", json = {"path": path}).json()

        assert body["imported"] == 16
        assert body["skipped"] == 0
        assert len(config.platforms) == 32
        # 追加的条目拿新编号，不与已播种的 0..15 撞号
        assert [item["id"] for item in config.platforms] == list(range(32))
        # 旧版启用的是「接口 3」，归一化重编号后仍指向同一条（不是第 3 条）
        active = config.get_platform(config.activate_platform)
        assert active["name"] == "接口 3"
        assert store.resolve_keys(active) == ["secret-3"]

    # 名称不重复：默认模板与旧版接口各自保留
    names = [item["name"] for item in config.platforms]
    assert len(set(names)) == len(names)


def test_import_reclaims_seeded_platform_with_same_name(monkeypatch, tmp_path) -> None:
    """旧版接口与默认模板同名同地址时认领身份，不产生重复条目。"""
    store = SecretStore(MemoryBackend())
    monkeypatch.setattr(SecretStore, "_instance", store)

    identity = "e" * 32
    legacy = _legacy_platform(
        "SakuraLLM",
        identity,
        group = "local",
        api_format = "SakuraLLM",
        api_url = "http://127.0.0.1:8080",
        model = "no_model_required",
    )
    store.store_keys(legacy, ["sakura-key"])
    path = _write_legacy(tmp_path, [legacy])

    client, config = _client()
    with client:
        from module.Project.PlatformDefaults import load_default_platforms

        config.platforms = load_default_platforms()
        config.save(strict = True)
        before = len(config.platforms)

        body = client.post("/api/platforms/import", json = {"path": path}).json()

    assert body["imported"] == 1
    assert len(config.platforms) == before
    sakura = next(item for item in config.platforms if item["name"] == "SakuraLLM")
    assert sakura["credential_id"] == identity
    assert store.resolve_keys(sakura) == ["sakura-key"]


def test_import_rejects_unknown_fields(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(SecretStore, "_instance", SecretStore(MemoryBackend()))
    path = _write_legacy(tmp_path, [_legacy_platform("A", "4" * 32)])
    client, _ = _client()

    with client:
        response = client.post("/api/platforms/import", json = {"path": path, "content": "..."})
    assert response.status_code == 422
