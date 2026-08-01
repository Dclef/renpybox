import json
from pathlib import Path

import pytest

from base.Base import Base
from frontend.Project.PlatformPage import (
    PLATFORM_GROUPS,
    deduplicate_platform_name,
    infer_group,
    resolve_group,
)


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

    for filename in EXPECTED_GROUPS:
        assert (
            presets_by_language["zh"][filename]["group"]
            == presets_by_language["en"][filename]["group"]
        )
