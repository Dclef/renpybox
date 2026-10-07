"""静态提示词预览复用真实构造器，不能改配置或发起模型请求。"""
import copy
from dataclasses import asdict

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes.settings import router
from module.Config import Config


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
