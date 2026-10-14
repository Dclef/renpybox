"""Python 客户端必须显式提示桌面迁移，不能解压桌面包覆盖自己。"""
import importlib

import pytest

from base.Base import Base
from base.VersionManager import VersionManager

vm_module = importlib.import_module("base.VersionManager")


def desktop_release(version="0.9.0", *, legacy=False):
    result = {
        "tag_name": f"RenpyBox_v{version}",
        "body": "Desktop release notes",
        "draft": False,
        "prerelease": False,
        "assets": [{
            "name": f"RenpyBox-NewUI-{version}-x64.exe",
            "size": 1024,
            "browser_download_url": f"https://github.com/Dclef/renpybox/releases/download/RenpyBox_v{version}/RenpyBox-NewUI-{version}-x64.exe",
            "digest": "sha256:" + "a" * 64,
        }],
    }
    if legacy:
        result["assets"].append({
            "name": f"RenpyBox_v{version}.zip", "size": 2048,
            "browser_download_url": "https://github.com/Dclef/renpybox/releases/download/compat.zip",
        })
    return result


@pytest.mark.parametrize("tag", ["v0.9.0", "RenpyBox_v0.9.0"])
def test_desktop_only_release_is_normalized_without_requiring_legacy_zip(tag):
    release = desktop_release()
    release["tag_name"] = tag
    latest = VersionManager._normalize_release(release)
    assert latest["delivery"] == "desktop"
    assert latest["asset"]["name"] == "RenpyBox-NewUI-0.9.0-x64.exe"
    assert VersionManager.desktop_release_url(latest).endswith(f"/releases/tag/{tag}")


def test_combined_release_prompts_migration_without_selecting_compatibility_zip():
    latest = VersionManager._normalize_release(desktop_release(legacy=True))
    assert latest["delivery"] == "desktop"
    with pytest.raises(RuntimeError, match="Desktop"):
        VersionManager._select_download_asset(latest)


@pytest.mark.parametrize("current", ["v0.8.2", "v0.9.0"])
def test_newer_and_same_version_python_build_offer_desktop_migration(monkeypatch, current):
    monkeypatch.setattr(Base, "subscribe", lambda *args: None)
    manager = VersionManager()
    manager.set_version(current)
    emitted = []
    monkeypatch.setattr(manager, "emit", lambda event, data: emitted.append((event, data)))
    class Response:
        def raise_for_status(self):
            pass
        def json(self):
            return desktop_release(legacy=True)
    monkeypatch.setattr(vm_module.httpx, "get", lambda *args, **kwargs: Response())
    manager.app_update_check_start_task("", {"manual": True})
    result = next(data for event, data in emitted if event == Base.Event.APP_UPDATE_CHECK_DONE)
    assert result["error"] == ""
    assert result["new_version"] is True
    assert result["status"] == VersionManager.Status.DESKTOP_AVAILABLE


def test_legacy_only_release_still_uses_python_zip():
    release = desktop_release(legacy=True)
    release["assets"] = release["assets"][1:]
    latest = VersionManager._normalize_release(release)
    assert latest.get("delivery") != "desktop"
    assert VersionManager._select_download_asset(latest)["name"] == "RenpyBox_v0.9.0.zip"


@pytest.mark.parametrize("change", ["wrong-version", "zip-only", "draft", "prerelease", "empty-url"])
def test_invalid_desktop_asset_cannot_turn_into_migration(change):
    release = desktop_release(legacy=True)
    if change == "wrong-version":
        release["assets"][0]["name"] = "RenpyBox-NewUI-0.8.2-x64.exe"
    elif change == "zip-only":
        release["assets"][0]["name"] = "RenpyBox-NewUI-0.9.0-x64.zip"
    elif change == "empty-url":
        release["assets"][0]["browser_download_url"] = ""
    else:
        release[change] = True
    if change in {"draft", "prerelease"}:
        with pytest.raises(RuntimeError, match="stable"):
            VersionManager._normalize_release(release)
    else:
        assert VersionManager._normalize_release(release).get("delivery") != "desktop"


def test_download_entry_does_not_start_worker_for_desktop_release(monkeypatch):
    monkeypatch.setattr(Base, "subscribe", lambda *args: None)
    manager = VersionManager()
    manager.latest = VersionManager._normalize_release(desktop_release(legacy=True))
    manager.status = VersionManager.Status.DESKTOP_AVAILABLE
    monkeypatch.setattr(vm_module.threading, "Thread", lambda **kwargs: pytest.fail("desktop installer must not reach the Python updater"))
    manager.app_update_download_start("", {})
    assert manager.status == VersionManager.Status.DESKTOP_AVAILABLE
