"""静态提示词预览复用真实构造器，不能改配置或发起模型请求。"""
import copy
from dataclasses import asdict

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes.settings import router
from module.Config import Config
from base.BaseLanguage import BaseLanguage


def test_prompt_preview_reads_current_custom_sections():
    config = Config()
    config.translation_prompt_mode = "CUSTOM"
    config.translation_custom_prompts = {"ZH": "保留人物的说话方式", "EN": "Keep character voice"}
    config.translation_style_id = "CUSTOM"
    config.translation_custom_style = "短句，避免解释"
    before = copy.deepcopy(asdict(config))
    app = FastAPI()
    app.state.config = config
    app.include_router(router)
    with TestClient(app) as client:
        response = client.get("/api/settings/prompt-preview")
    assert response.status_code == 200
    sections = response.json()
    assert set(sections) == {"base", "style", "fixed"}
    assert "保留人物的说话方式" in sections["base"] or "Keep character voice" in sections["base"]
    assert "短句，避免解释" in sections["style"]
    assert sections["fixed"].strip()
    assert asdict(config) == before


def test_prompt_editor_preserves_placeholders_and_saved_sections():
    config = Config()
    config.source_language = BaseLanguage.Enum.EN
    config.target_language = BaseLanguage.Enum.ZH
    app = FastAPI()
    app.state.config = config
    app.include_router(router)
    before = copy.deepcopy(asdict(config))
    with TestClient(app) as client:
        raw = client.get("/api/settings/prompt-preview?raw=true").json()
        assert raw["language"] == "ZH"
        assert "{source_language}" in raw["base"]
        assert "{target_language}" in raw["base"]
        assert asdict(config) == before
        fixed = client.get("/api/settings/prompt-preview").json()["fixed"]
        edited = "将{source_language}翻译为{target_language}，保留人物语气。"
        response = client.patch("/api/settings", json={"values": {
            "translation_prompt_mode": "CUSTOM",
            "translation_custom_prompts": {"ZH": edited, "EN": "Keep the English draft"},
            "translation_custom_prompt_enabled_languages": ["ZH"],
            "translation_style_id": "CUSTOM",
            "translation_custom_style": "用简洁自然的表达。",
        }})
        assert response.status_code == 200
        assert Config().load().translation_custom_prompts["ZH"] == edited
        preview = client.get("/api/settings/prompt-preview").json()
        assert "{target_language}" not in preview["base"]
        assert "保留人物语气" in preview["base"]
        assert preview["style"] == "用简洁自然的表达。"
        assert preview["fixed"] == fixed
        reopened = client.get("/api/settings/prompt-preview?raw=true").json()
        assert reopened["base"] == edited
