"""Desktop launchers separate writable user data from bundled resources."""

from pathlib import Path
import sys

from base.AppPaths import AppPaths
from base.PathHelper import get_app_path, get_resource_path


def test_desktop_paths_keep_settings_and_resources_separate(monkeypatch, tmp_path: Path) -> None:
    user_data = tmp_path / "user data"
    bundle = tmp_path / "Program Files" / "RenpyBox" / "resources" / "backend"
    monkeypatch.setenv("RENPYBOX_APP_ROOT", str(user_data))
    monkeypatch.setenv("RENPYBOX_RESOURCE_ROOT", str(bundle))

    paths = AppPaths.detect()

    assert paths.config_path == user_data / "config.json"
    assert paths.log_path == user_data / "log"
    assert paths.input_path == user_data / "input"
    assert paths.output_path == user_data / "output"
    assert paths.resource("icon.ico") == bundle / "resource" / "icon.ico"
    assert get_resource_path("resource", "prompt", "zh") == str(bundle / "resource" / "prompt" / "zh")
    assert get_resource_path("resource/icon.ico") == str(bundle / "resource" / "icon.ico")
    assert get_app_path("storage", "profiles.json") == str(user_data / "storage" / "profiles.json")


def test_desktop_paths_override_frozen_executable_and_meipass(monkeypatch, tmp_path: Path) -> None:
    user_data = tmp_path / "user"
    bundle = tmp_path / "bundle"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "extracted"), raising=False)
    monkeypatch.setenv("RENPYBOX_APP_ROOT", str(user_data))
    monkeypatch.setenv("RENPYBOX_RESOURCE_ROOT", str(bundle))

    paths = AppPaths.detect()

    assert paths.root == user_data
    assert paths.resource_root == bundle


def test_user_root_does_not_redirect_frozen_bundled_resources(monkeypatch, tmp_path: Path) -> None:
    user_data = tmp_path / "user"
    extracted = tmp_path / "_internal"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(extracted), raising=False)
    monkeypatch.setenv("RENPYBOX_APP_ROOT", str(user_data))
    monkeypatch.delenv("RENPYBOX_RESOURCE_ROOT", raising=False)

    paths = AppPaths.detect()

    assert paths.config_path == user_data / "config.json"
    assert paths.resource("icon.ico") == extracted / "resource" / "icon.ico"


def test_desktop_explicit_paths_are_stable_after_chdir(monkeypatch, tmp_path: Path) -> None:
    user_data = tmp_path / "user"
    bundle = tmp_path / "bundle"
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.setenv("RENPYBOX_APP_ROOT", str(user_data))
    monkeypatch.setenv("RENPYBOX_RESOURCE_ROOT", str(bundle))
    monkeypatch.chdir(elsewhere)

    paths = AppPaths.detect()

    assert paths.root == user_data
    assert paths.resource_root == bundle
