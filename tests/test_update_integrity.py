import pytest

from buildtools.update_assets import build_manifest
from update_integrity import validate_installed_files


def _installed_tree(tmp_path):
    install = tmp_path / "install"
    (install / "_internal").mkdir(parents=True)
    (install / "RenpyBox.exe").write_bytes(b"EXE")
    (install / "_internal" / "dependency.dll").write_bytes(b"dependency")
    return install


def test_validate_installed_files_accepts_intact_installation(tmp_path) -> None:
    install = _installed_tree(tmp_path)
    validate_installed_files(install, build_manifest(install, "v1.0.0"))


@pytest.mark.parametrize("damage", ["missing", "modified", "resized"])
def test_validate_installed_files_rejects_damaged_dependency(tmp_path, damage: str) -> None:
    install = _installed_tree(tmp_path)
    manifest = build_manifest(install, "v1.0.0")
    dependency = install / "_internal" / "dependency.dll"
    if damage == "missing":
        dependency.unlink()
    elif damage == "modified":
        dependency.write_bytes(b"DEPENDENCY")
    else:
        dependency.write_bytes(b"dependency-extra")

    with pytest.raises(RuntimeError, match="全量更新"):
        validate_installed_files(install, manifest)


@pytest.mark.parametrize(
    "broken_entry",
    [
        {},
        {"size": -1, "sha256": "0" * 64},
        {"size": 1, "sha256": "not-a-sha256"},
    ],
)
def test_validate_installed_files_rejects_invalid_manifest_entry(
    tmp_path, broken_entry: dict
) -> None:
    install = _installed_tree(tmp_path)
    manifest = build_manifest(install, "v1.0.0")
    manifest["files"]["dependency.dll"] = broken_entry

    with pytest.raises(RuntimeError, match="清单无效"):
        validate_installed_files(install, manifest)


def test_validate_installed_files_rejects_escape_path(tmp_path) -> None:
    install = _installed_tree(tmp_path)
    manifest = build_manifest(install, "v1.0.0")
    manifest["files"]["../victim.txt"] = manifest["files"].pop("_internal/dependency.dll")

    with pytest.raises(RuntimeError):
        validate_installed_files(install, manifest)
