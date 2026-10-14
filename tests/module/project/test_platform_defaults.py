"""共享接口模板与归一化规则：Qt5 与桌面版必须表现一致。

规则收口在 ``module/Project/PlatformDefaults.py``：
``frontend/Project/PlatformPage.py`` 与 ``api/app.py``（启动播种）、
``api/routes/platforms.py``（从旧版导入）都引用这里。
"""

import copy
import json

import pytest

from module.Config import Config
from module.Project.PlatformDefaults import (
    DEEPSEEK_CURRENT_MODEL,
    legacy_active_platform,
    load_default_platforms,
    merge_imported_platforms,
    normalize_platforms,
    read_legacy_platforms,
    seed_default_platforms,
)
from module.Secret.SecretStore import CREDENTIAL_ID_FIELD, LEGACY_CREDENTIAL_ID_FIELD, MemoryBackend, SecretStore


@pytest.fixture(autouse = True)
def isolated_secrets(monkeypatch: pytest.MonkeyPatch):
    """接口身份只写入配置字典，但隔离凭据库避免碰到真实 Windows 凭据。"""
    monkeypatch.setattr(SecretStore, "_instance", SecretStore(MemoryBackend()))


def _platform(name: str, **overrides) -> dict:
    item = {
        "id": 0,
        "name": name,
        "group": "online",
        "api_format": "OpenAI",
        "api_url": "https://example.invalid/v1",
        "model": "model-a",
        "api_key": [],
        "thinking": {"level": "OFF"},
        "top_p": 0.95,
        "temperature": 0.95,
        "presence_penalty": 0.0,
        "frequency_penalty": 0.0,
    }
    item.update(overrides)
    return item


def test_load_default_platforms_generates_fresh_identities() -> None:
    platforms = load_default_platforms()

    assert len(platforms) == 16
    assert [item["id"] for item in platforms] == list(range(16))
    assert platforms[0]["name"] == "SakuraLLM"

    identities = []
    for item in platforms:
        identity = item[CREDENTIAL_ID_FIELD]
        assert isinstance(identity, str) and len(identity) == 32
        # 默认模板不继承数字凭据别名，否则会读到旧平台的密钥
        assert LEGACY_CREDENTIAL_ID_FIELD not in item
        identities.append(identity)
    assert len(set(identities)) == len(identities)

    # 每次加载都是新身份，避免两份默认模板共用同一把密钥
    assert load_default_platforms()[0][CREDENTIAL_ID_FIELD] != identities[0]


def test_normalize_platforms_migrates_legacy_fields_and_is_idempotent() -> None:
    platforms = [
        _platform("DeepSeek", id = 0, api_url = "https://api.deepseek.com/v1/", model = "deepseek-chat", thinking = False),
        _platform("中转", id = 0, api_url = "https://relay.example.com/v1", model = "deepseek-chat", thinking = True),
        _platform("SakuraLLM", id = 0, api_format = "SakuraLLM", thinking = {"level": "BOGUS"}),
        _platform("GoogleFree", id = 0, api_format = "GoogleFree", thinking = {"level": "OFF"}),
        _platform("Bing", id = 0, api_format = "Bing", thinking = {"level": "OFF"}),
    ]

    assert normalize_platforms(platforms) is True

    assert platforms[0]["model"] == DEEPSEEK_CURRENT_MODEL
    # 自定义中转保持用户原值
    assert platforms[1]["model"] == "deepseek-chat"
    assert platforms[1]["thinking"] == {"level": "HIGH"}
    assert platforms[2]["thinking"] == {"level": "OFF"}
    # id 重复时重新连续编号
    assert [item["id"] for item in platforms] == list(range(len(platforms)))
    for item in platforms:
        assert isinstance(item[CREDENTIAL_ID_FIELD], str)

    # 幂等：再次归一化不再改动
    assert normalize_platforms(platforms) is False


def test_normalize_platforms_appends_missing_machine_formats() -> None:
    platforms = [_platform("OpenAI 官方", id = 3)]

    assert normalize_platforms(platforms) is True

    formats = [str(item.get("api_format", "")) for item in platforms]
    assert "GoogleFree" in formats and "Bing" in formats
    assert platforms[-1]["id"] == len(platforms) - 1
    # 补齐的机翻接口同样带独立凭据身份
    for item in platforms:
        assert isinstance(item[CREDENTIAL_ID_FIELD], str)


def test_normalize_platforms_keeps_custom_platforms_last() -> None:
    platforms = [
        _platform("自定义 OpenAI", id = 0, group = "custom"),
        _platform("DeepSeek", id = 1),
    ]

    assert normalize_platforms(platforms) is True

    # 自定义接口排在最后，非自定义接口保持相对顺序
    assert platforms[0]["name"] == "DeepSeek"
    assert platforms[-1]["name"] == "自定义 OpenAI"
    assert [item["id"] for item in platforms] == list(range(len(platforms)))


def test_merge_imported_platforms_never_overwrites_existing_entries() -> None:
    existing = _platform("我调好的接口", id = 0, **{CREDENTIAL_ID_FIELD: "a" * 32})
    duplicated = copy.deepcopy(existing)
    duplicated["name"] = "旧版里的同名接口"
    added = _platform("旧版新增", id = 1, **{CREDENTIAL_ID_FIELD: "b" * 32})

    merged, imported_count, skipped = merge_imported_platforms([existing], [duplicated, added], is_protected = lambda _item: True)

    assert (imported_count, skipped) == (1, 1)
    assert len(merged) == 2
    # 已存在的接口保持用户当前配置，不被旧版覆盖
    assert merged[0]["name"] == "我调好的接口"
    assert merged[1]["name"] == "旧版新增"


def test_merge_imported_platforms_claims_identity_for_unconfigured_entry() -> None:
    """全新安装刚播种出来的默认接口没有密钥，应认领旧版身份并采用旧版字段。

    否则用户从 Python 版升级后会看到两份同名接口，而且都读不到原来的密钥。
    """
    seeded = _platform("DeepSeek", id = 0, model = "default-model", **{CREDENTIAL_ID_FIELD: "f" * 32})
    legacy = _platform(
        "DeepSeek",
        id = 0,
        model = "user-tuned-model",
        thinking = {"level": "MAX"},
        **{CREDENTIAL_ID_FIELD: "9" * 32},
    )

    merged, imported_count, skipped = merge_imported_platforms([seeded], [legacy], is_protected = lambda _item: False)

    assert (imported_count, skipped) == (1, 0)
    assert len(merged) == 1
    assert merged[0][CREDENTIAL_ID_FIELD] == "9" * 32
    # 字段也采用旧值，否则用户调过的模型会被默认模板覆盖
    assert merged[0]["model"] == "user-tuned-model"
    assert merged[0]["thinking"] == {"level": "MAX"}


def test_merge_imported_platforms_keeps_entry_that_already_has_keys() -> None:
    """已经存了密钥的接口不认领旧身份，避免把用户新填的密钥指向旧记录。"""
    mine = _platform("DeepSeek", id = 0, model = "my-model", **{CREDENTIAL_ID_FIELD: "f" * 32})
    legacy = _platform("DeepSeek", id = 0, model = "legacy-model", **{CREDENTIAL_ID_FIELD: "9" * 32})

    merged, imported_count, skipped = merge_imported_platforms([mine], [legacy], is_protected = lambda _item: True)

    assert (imported_count, skipped) == (0, 1)
    assert merged[0][CREDENTIAL_ID_FIELD] == "f" * 32
    assert merged[0]["model"] == "my-model"


def test_merge_imported_platforms_claims_identity_end_to_end(monkeypatch) -> None:
    """认领身份后，旧版存在凭据管理器里的密钥要能直接读出来。"""
    store = SecretStore(MemoryBackend())
    monkeypatch.setattr(SecretStore, "_instance", store)

    identity = "7" * 32
    seeded = _platform("OpenAI", id = 0, **{CREDENTIAL_ID_FIELD: "8" * 32})
    legacy = _platform("OpenAI", id = 0, **{CREDENTIAL_ID_FIELD: identity})
    store.store_keys(legacy, ["legacy-secret"])

    merged, imported_count, _skipped = merge_imported_platforms([seeded], [legacy])

    assert imported_count == 1
    assert merged[0][CREDENTIAL_ID_FIELD] == identity
    assert store.resolve_keys(merged[0]) == ["legacy-secret"]


def test_merge_imported_platforms_renames_appended_duplicates() -> None:
    """不同地址的同名接口是两条记录，导入时按 PlatformNaming 规则改名。"""
    existing = _platform("接口", id = 0, api_url = "https://a.example/v1", **{CREDENTIAL_ID_FIELD: "a" * 32})
    other = _platform("接口", id = 1, api_url = "https://b.example/v1", **{CREDENTIAL_ID_FIELD: "b" * 32})

    merged, imported_count, skipped = merge_imported_platforms([existing], [other], is_protected = lambda _item: True)

    assert (imported_count, skipped) == (1, 0)
    assert [item["name"] for item in merged] == ["接口", "接口 2"]


def test_merge_imported_platforms_adopts_all_when_current_is_empty() -> None:
    imported = [_platform("A", id = 0), _platform("B", id = 1)]

    merged, imported_count, skipped = merge_imported_platforms(None, imported)

    assert (imported_count, skipped) == (2, 0)
    assert [item["name"] for item in merged] == ["A", "B"]
    # 深拷贝：调用方后续归一化不会改动传入的旧配置对象
    merged[0]["name"] = "changed"
    assert imported[0]["name"] == "A"


def test_merge_imported_platforms_falls_back_to_name_and_url_without_identity() -> None:
    first = _platform("同名", id = 0, api_url = "https://a.example/v1")
    second = _platform("同名", id = 1, api_url = "https://b.example/v1")

    merged, imported_count, skipped = merge_imported_platforms([first], [copy.deepcopy(first), second], is_protected = lambda _item: True)

    assert (imported_count, skipped) == (1, 1)
    assert len(merged) == 2


def test_read_legacy_platforms_rejects_non_config_payloads() -> None:
    with pytest.raises(ValueError):
        read_legacy_platforms(["not", "a", "dict"])
    with pytest.raises(ValueError):
        read_legacy_platforms({"theme": "LIGHT"})
    with pytest.raises(ValueError):
        read_legacy_platforms({"platforms": None})

    # 非字典条目被丢弃，合法条目保留
    assert read_legacy_platforms({"platforms": [{"name": "A"}, "junk", 3]}) == [{"name": "A"}]


def test_legacy_active_platform_only_accepts_plain_integers() -> None:
    assert legacy_active_platform({"activate_platform": 9}) == 9
    assert legacy_active_platform({"activate_platform": 0}) == 0
    # JSON true 是 bool，也是 int 子类，必须显式拒绝
    assert legacy_active_platform({"activate_platform": True}) is None
    assert legacy_active_platform({"activate_platform": "9"}) is None
    assert legacy_active_platform({}) is None
    assert legacy_active_platform(None) is None


def test_seed_default_platforms_fills_null_list_and_writes_config(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(Config, "CONFIG_PATH", str(tmp_path / "config.json"))
    config = Config()
    config.platforms = None
    config.save(strict = True)

    assert seed_default_platforms(config) is True

    saved = json.loads((tmp_path / "config.json").read_text(encoding = "utf-8"))
    assert len(saved["platforms"]) == 16
    assert saved["platforms"][0]["name"] == "SakuraLLM"
    # 第二次启动不再改动
    assert seed_default_platforms(Config().load()) is False


def test_seed_default_platforms_keeps_user_platforms(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(Config, "CONFIG_PATH", str(tmp_path / "config.json"))
    config = Config(platforms = [_platform("我自己的接口", id = 0)], activate_platform = 0)
    config.save(strict = True)

    assert seed_default_platforms(config) is True

    saved = json.loads((tmp_path / "config.json").read_text(encoding = "utf-8"))
    names = [item["name"] for item in saved["platforms"]]
    assert "我自己的接口" in names
    assert saved["activate_platform"] == 0
    assert "GoogleFree" in [item["api_format"] for item in saved["platforms"]]


def test_seed_default_platforms_propagates_save_failure(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(Config, "CONFIG_PATH", str(tmp_path / "config.json"))
    config = Config()
    config.platforms = None

    def fail_save(*args, **kwargs):
        raise PermissionError("只读目录")

    monkeypatch.setattr(config, "save", fail_save)
    with pytest.raises(PermissionError):
        seed_default_platforms(config)
