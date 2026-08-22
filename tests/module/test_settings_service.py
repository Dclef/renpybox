import json
import time
from pathlib import Path

import pytest

from module.Config import Config
from module.SettingsService import SettingsService


def test_settings_service_debounces_and_persists_latest_values(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    service = SettingsService(path=path, debounce_seconds=0.02)
    try:
        service.update({"proxy_url": "one"})
        service.update({"proxy_url": "two", "max_workers": 3})
        time.sleep(0.08)
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["proxy_url"] == "two"
        assert payload["max_workers"] == 3
    finally:
        service.close(save=False)


def test_settings_service_immediate_save_is_strict(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    service = SettingsService(path=path, debounce_seconds=1)
    service.update({"proxy_url": "saved"}, immediate=True)
    service.close(save=False)

    assert json.loads(path.read_text(encoding="utf-8"))["proxy_url"] == "saved"


def test_settings_service_rejects_unknown_fields(tmp_path: Path) -> None:
    service = SettingsService(path=tmp_path / "config.json")
    try:
        with pytest.raises(AttributeError, match="Unknown config fields"):
            service.update({"not_a_config_field": True})
    finally:
        service.close(save=False)


def test_settings_service_close_prevents_later_edits(tmp_path: Path) -> None:
    service = SettingsService(config=Config(), path=tmp_path / "config.json")
    service.close(save=False)

    with pytest.raises(RuntimeError, match="closed"):
        service.update({"proxy_url": "blocked"})
