import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from base.Base import Base
from frontend.Project.PlatformPage import (
    PLATFORM_GROUPS,
    PlatformPage,
    deduplicate_platform_name,
    infer_group,
    resolve_group,
)
from module.Config import Config
from module.Secret.SecretStore import MemoryBackend, SecretStore


ROOT = Path(__file__).resolve().parents[3]
EXPECTED_GROUPS = {
    "0_sakura.json": "local",
    "1_google.json": "online",
    "2_openai.json": "online",
    "3_deepseek.json": "online",
    "4_anthropic.json": "online",
    "5_aliyun.json": "online",
    "6_zhipu.json": "online",
    "7_yi.json": "online",
    "8_moonshot.json": "online",
    "9_siliconflow.json": "online",
    "10_volcengine.json": "online",
    "11_custom_google.json": "custom",
    "12_custom_openai.json": "custom",
    "13_custom_anthropic.json": "custom",
    "14_deepl.json": "machine",
    "15_deeplx.json": "machine",
}


def test_resolve_group_prefers_valid_explicit_group() -> None:
    platform = {
        "group": "online",
        "api_format": Base.APIFormat.SAKURALLM,
        "api_url": "http://127.0.0.1:8080",
    }

    assert resolve_group(platform) == "online"


@pytest.mark.parametrize(
    "api_format",
    (Base.APIFormat.DEEPL, Base.APIFormat.DEEPLX),
)
def test_infer_group_places_non_llm_formats_in_machine(api_format: Base.APIFormat) -> None:
    assert infer_group({"api_format": api_format}) == "machine"


def test_infer_group_places_sakura_in_local() -> None:
    assert infer_group({"api_format": Base.APIFormat.SAKURALLM}) == "local"


@pytest.mark.parametrize("api_url", ("http://127.0.0.1:8080", "http://localhost:5000/v1"))
def test_infer_group_places_local_urls_in_local(api_url: str) -> None:
    assert infer_group({"api_format": Base.APIFormat.OPENAI, "api_url": api_url}) == "local"


@pytest.mark.parametrize("name", ("自定义 OpenAI", "Custom Anthropic"))
def test_infer_group_places_custom_names_in_custom(name: str) -> None:
    assert infer_group({"name": name, "api_url": "https://example.com"}) == "custom"


def test_infer_group_places_regular_cloud_api_in_online() -> None:
    platform = {
        "name": "OpenAI",
        "api_format": Base.APIFormat.OPENAI,
        "api_url": "https://api.openai.com/v1",
    }

    assert infer_group(platform) == "online"


def test_resolve_group_infers_invalid_group_without_mutating_platform() -> None:
    platform = {"group": "foo", "name": "Custom OpenAI"}

    assert resolve_group(platform) == "custom"
    assert platform == {"group": "foo", "name": "Custom OpenAI"}


def test_deduplicate_platform_name_uses_incrementing_suffixes() -> None:
    platforms = [{"name": "OpenAI"}]

    assert deduplicate_platform_name("OpenAI", platforms) == "OpenAI 2"
    platforms.append({"name": "OpenAI 2"})
    assert deduplicate_platform_name("OpenAI", platforms) == "OpenAI 3"


@pytest.mark.parametrize(
    ("agent_platform", "expected_agent_platform"),
    ((1, -1), (2, 1)),
)
def test_delete_platform_keeps_agent_platform_index_in_sync(
    monkeypatch,
    agent_platform: int,
    expected_agent_platform: int,
) -> None:
    config = Config(
        platforms=[{"id": 0}, {"id": 1}, {"id": 2}],
        activate_platform=2,
        agent_platform=agent_platform,
    )
    rebuilt = []
    page = SimpleNamespace(rebuild_all=lambda: rebuilt.append(True))
    monkeypatch.setattr(Config, "load", lambda self: config)
    monkeypatch.setattr(Config, "save", lambda self, **_kwargs: self)
    monkeypatch.setattr(SecretStore, "get", lambda: SecretStore(MemoryBackend()))

    PlatformPage.delete_platform(page, 1)

    assert [platform["id"] for platform in config.platforms] == [0, 1]
    assert config.activate_platform == 1
    assert config.agent_platform == expected_agent_platform
    assert rebuilt == [True]


def test_delete_platform_clears_exact_identity_before_reindex(monkeypatch) -> None:
    store = SecretStore(MemoryBackend())
    first = {"id": 0}
    removed = {"id": 1}
    last = {"id": 2}
    store.store_keys(removed, ["removed-key"])
    config = Config(
        platforms=[first, removed, last],
        activate_platform=0,
        agent_platform=-1,
    )
    page = SimpleNamespace(rebuild_all=lambda: None, emit=lambda *_args: None)
    monkeypatch.setattr(Config, "load", lambda self: config)
    monkeypatch.setattr(Config, "save", lambda self, **_kwargs: self)
    monkeypatch.setattr(SecretStore, "get", lambda: store)

    PlatformPage.delete_platform(page, 1)

    assert store.resolve_keys(removed) == []
    assert config.platforms == [first, last]
    assert [item["id"] for item in config.platforms] == [0, 1]


def test_delete_platform_cleanup_failure_only_leaves_unreachable_identity(monkeypatch) -> None:
    class FailingClearStore:
        @staticmethod
        def resolve_keys(platform: dict) -> list[str]:
            return ["kept-key"]

        @staticmethod
        def clear_keys(platform: dict) -> bool:
            return False

    platforms = [{"id": 0}, {"id": 1}]
    config = Config(platforms=platforms, activate_platform=0, agent_platform=-1)
    events = []
    rebuilt = []
    page = SimpleNamespace(
        rebuild_all=lambda: rebuilt.append(True),
        emit=lambda *args: events.append(args),
    )
    monkeypatch.setattr(Config, "load", lambda self: config)
    monkeypatch.setattr(Config, "save", lambda self, **_kwargs: self)
    monkeypatch.setattr(SecretStore, "get", lambda: FailingClearStore())

    PlatformPage.delete_platform(page, 1)

    assert config.platforms == [{"id": 0}]
    assert len(events) == 1
    assert rebuilt == [True]


def test_delete_platform_save_failure_never_clears_credentials(monkeypatch) -> None:
    class TrackingStore:
        cleared = False

        def clear_keys(self, platform: dict) -> bool:
            self.cleared = True
            return True

    store = TrackingStore()
    config = Config(
        platforms=[{"id": 0}, {"id": 1}],
        activate_platform=1,
        agent_platform=1,
    )
    page = SimpleNamespace(rebuild_all=lambda: None, emit=lambda *_args: None)
    monkeypatch.setattr(Config, "load", lambda self: config)
    monkeypatch.setattr(
        Config,
        "save",
        lambda self, **_kwargs: (_ for _ in ()).throw(OSError("disk full")),
    )
    monkeypatch.setattr(SecretStore, "get", lambda: store)

    with pytest.raises(OSError, match="disk full"):
        PlatformPage.delete_platform(page, 1)

    assert store.cleared is False
    assert config.platforms == [{"id": 0}, {"id": 1}]
    assert config.activate_platform == 1
    assert config.agent_platform == 1


def test_add_platform_assigns_fresh_identity(monkeypatch) -> None:
    existing = {"id": 0, "name": "OpenAI"}
    SecretStore.ensure_platform_identity(existing, preserve_legacy = False)
    config = Config(platforms=[existing])
    rebuilt = []
    page = SimpleNamespace(rebuild_all=lambda: rebuilt.append(True))
    monkeypatch.setattr(Config, "load", lambda self: config)
    monkeypatch.setattr(Config, "save", lambda self, **_kwargs: self)

    PlatformPage.add_platform(page, existing)

    added = config.platforms[1]
    assert added["credential_id"] != existing["credential_id"]
    assert "legacy_credential_id" not in added
    assert added["id"] == 1
    assert rebuilt == [True]


def test_all_bilingual_platform_presets_have_matching_valid_groups() -> None:
    presets_by_language: dict[str, dict[str, dict]] = {}

    for language in ("zh", "en"):
        directory = ROOT / "resource" / "platforms" / language
        presets_by_language[language] = {
            path.name: json.loads(path.read_text(encoding="utf-8-sig"))
            for path in directory.glob("*.json")
        }
        assert set(presets_by_language[language]) == set(EXPECTED_GROUPS)

        for filename, expected_group in EXPECTED_GROUPS.items():
            group = presets_by_language[language][filename].get("group")
            assert group in PLATFORM_GROUPS
            assert group == expected_group

        assert presets_by_language[language]["3_deepseek.json"]["model"] == "deepseek-v4-flash"

    for filename in EXPECTED_GROUPS:
        assert (
            presets_by_language["zh"][filename]["group"]
            == presets_by_language["en"][filename]["group"]
        )


def test_deepseek_legacy_model_migrates_only_on_official_endpoint() -> None:
    class MigrationPage:
        @staticmethod
        def load_default_platforms() -> list[dict]:
            return []

    platforms = [
        {
            "id": 0,
            "name": "DeepSeek",
            "api_format": Base.APIFormat.OPENAI,
            "api_url": "https://api.deepseek.com/v1/",
            "model": "deepseek-chat",
            "thinking": {"level": "OFF"},
        },
        {
            "id": 1,
            "name": "自定义中转",
            "api_format": Base.APIFormat.OPENAI,
            "api_url": "https://relay.example.com/v1",
            "model": "deepseek-chat",
            "thinking": {"level": "OFF"},
        },
        {
            "id": 2,
            "name": "DeepSeek Pro",
            "api_format": Base.APIFormat.OPENAI,
            "api_url": "https://api.deepseek.com",
            "model": "deepseek-v4-pro",
            "thinking": {"level": "OFF"},
        },
        {
            "id": 3,
            "name": "伪装域名",
            "api_format": Base.APIFormat.OPENAI,
            "api_url": "https://api.deepseek.com.proxy.example/v1",
            "model": "deepseek-chat",
            "thinking": {"level": "OFF"},
        },
    ]

    assert PlatformPage.ensure_default_platforms(MigrationPage(), platforms) is True

    models = {item["name"]: item["model"] for item in platforms}
    assert models == {
        "DeepSeek": "deepseek-v4-flash",
        "自定义中转": "deepseek-chat",
        "DeepSeek Pro": "deepseek-v4-pro",
        "伪装域名": "deepseek-chat",
    }
    assert PlatformPage.ensure_default_platforms(MigrationPage(), platforms) is False
