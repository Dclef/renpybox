from pathlib import Path
import sys

from base.AppPaths import AppPaths
from base.PathHelper import get_resource_path


def test_app_paths_are_stable_and_use_one_root(tmp_path: Path) -> None:
    paths = AppPaths.from_root(tmp_path)

    assert paths.root == tmp_path.resolve()
    assert paths.config_path == tmp_path.resolve() / "config.json"
    assert paths.resource("icon.ico") == tmp_path.resolve() / "resource" / "icon.ico"
    assert paths.input_path.parent == paths.root
    assert paths.output_path.parent == paths.root


def test_app_paths_does_not_depend_on_current_directory(tmp_path: Path) -> None:
    paths = AppPaths.from_root(tmp_path / "app")
    assert paths.app("config.json") == paths.config_path


def test_frozen_paths_keep_writable_root_and_meipass_resources(
    monkeypatch,
    tmp_path: Path,
) -> None:
    meipass = tmp_path / "_internal"
    monkeypatch.setattr(sys, "frozen", True, raising = False)
    monkeypatch.setattr(sys, "_MEIPASS", str(meipass), raising = False)

    paths = AppPaths.detect()

    assert paths.root == Path(sys.executable).resolve().parent
    assert paths.resource("icon.ico") == meipass.resolve() / "resource" / "icon.ico"
    assert get_resource_path("resource", "icon.ico") == str(
        meipass.resolve() / "resource" / "icon.ico"
    )
    assert get_resource_path("resource/icon.ico") == str(
        meipass.resolve() / "resource" / "icon.ico"
    )
