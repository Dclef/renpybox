"""API 用例必须隔离配置与凭据，不能修改正在使用的工程。"""
import pytest

from module.Config import Config
from module.Secret.SecretStore import MemoryBackend, SecretStore


@pytest.fixture(autouse=True)
def isolated_api_config(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "CONFIG_PATH", str(tmp_path / "config.json"))
    monkeypatch.setattr(SecretStore, "_instance", SecretStore(MemoryBackend()))
    config = Config()
    config.input_folder = str(tmp_path / "input")
    config.output_folder = str(tmp_path / "output")
    config.renpy_project_path = config.renpy_game_folder = config.renpy_tl_folder = ""
    config.save(strict=True)
