import json
from pathlib import Path

import pytest

from module.Config import Config


@pytest.fixture()
def temp_config_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    path = tmp_path / "config.json"
    monkeypatch.setattr(Config, "CONFIG_PATH", str(path))
    return path


def test_save_writes_latest_snapshot_atomically(temp_config_path: Path) -> None:
    config = Config()
    config.source_language = "Chinese"
    config.save()

    data = json.loads(temp_config_path.read_text(encoding = "utf-8"))
    assert data["source_language"] == "Chinese"
    # 工作台资产按项目隔离默认值恢复，不携带实例态
    assert "source_language" in data

    config.target_language = "English"
    config.save()
    data = json.loads(temp_config_path.read_text(encoding = "utf-8"))
    assert data["target_language"] == "English"


def test_save_failure_keeps_previous_file_intact(
    temp_config_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = Config()
    config.source_language = "Chinese"
    config.save()
    before = temp_config_path.read_text(encoding = "utf-8")

    # 序列化中途失败：旧文件必须原样、无 tmp 残留
    def broken_dumps(*args, **kwargs):
        raise RuntimeError("simulated serialization failure")

    monkeypatch.setattr("module.Config.json.dumps", broken_dumps)
    config.save()

    assert temp_config_path.read_text(encoding = "utf-8") == before
    assert list(temp_config_path.parent.glob("*.tmp")) == []
