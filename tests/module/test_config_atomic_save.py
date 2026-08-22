import json
from pathlib import Path

import pytest

from base.LogManager import LogManager
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
    assert config.save() is config

    assert temp_config_path.read_text(encoding = "utf-8") == before
    assert list(temp_config_path.parent.glob("*.tmp")) == []


def test_load_failure_logs_outside_config_lock(
    temp_config_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    temp_config_path.write_text("{broken", encoding="utf-8")
    calls = []

    class LoggerStub:
        def error(self, message, error=None) -> None:
            acquired = Config.CONFIG_LOCK.acquire(blocking=False)
            calls.append((message, error, acquired))
            if acquired:
                Config.CONFIG_LOCK.release()

    logger = LoggerStub()
    monkeypatch.setattr(LogManager, "get", classmethod(lambda cls: logger))

    config = Config().load(str(temp_config_path))

    assert config is not None
    assert len(calls) == 1
    assert calls[0][1] is None
    assert calls[0][2] is True


def test_strict_save_propagates_failure_without_replacing_file(
    temp_config_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = Config()
    config.save()
    before = temp_config_path.read_text(encoding="utf-8")

    def broken_dumps(*args, **kwargs):
        raise RuntimeError("strict serialization failure")

    monkeypatch.setattr("module.Config.json.dumps", broken_dumps)

    with pytest.raises(RuntimeError, match="strict serialization failure"):
        config.save(strict=True)

    assert temp_config_path.read_text(encoding="utf-8") == before
    assert list(temp_config_path.parent.glob("*.tmp")) == []
