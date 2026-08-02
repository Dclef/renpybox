from importlib import import_module
from pathlib import Path

from module.Tool.ModInjector import ModInjector


mod_injector_module = import_module("module.Tool.ModInjector")


def _fake_resources(monkeypatch, tmp_path: Path) -> dict[str, Path]:
    resource_root = tmp_path / "resources"
    resources = {
        "0x52-URM-2.6.2.rpa": resource_root / "0x52-URM-2.6.2.rpa",
        "dumuqiao.rpy": resource_root / "dumuqiao.rpy",
    }
    for name, path in resources.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"resource:{name}", encoding="utf-8")

    monkeypatch.setattr(
        mod_injector_module,
        "get_resource_path",
        lambda *parts: str(
            resource_root if parts[-1] == "mods" else resources[parts[-1]]
        ),
    )
    return resources


def test_resolve_game_dir_supports_project_game_file_and_missing_path(tmp_path) -> None:
    project_dir = tmp_path / "project"
    game_dir = project_dir / "game"
    game_dir.mkdir(parents=True)
    script = game_dir / "script.rpy"
    script.write_text("", encoding="utf-8")
    missing = tmp_path / "missing"
    injector = ModInjector()

    assert injector.resolve_game_dir(str(project_dir)) == game_dir
    assert injector.resolve_game_dir(str(game_dir)) == game_dir
    assert injector.resolve_game_dir(str(script)) == game_dir
    assert injector.resolve_game_dir(str(missing)) == missing


def test_install_status_and_uninstall_both_mods(monkeypatch, tmp_path) -> None:
    _fake_resources(monkeypatch, tmp_path)
    game_dir = tmp_path / "game"
    game_dir.mkdir()
    injector = ModInjector()

    assert injector.install(str(game_dir), "urm")[0] is True
    assert injector.install(str(game_dir), "quick_menu")[0] is True
    assert injector.status(str(game_dir)) == {"urm": True, "quick_menu": True}

    compiled = game_dir / "dumuqiao.rpyc"
    compiled.write_bytes(b"compiled")
    (game_dir / "dumuqiao.rpy").unlink()
    assert injector.status(str(game_dir))["quick_menu"] is True
    assert injector.uninstall(str(game_dir), "urm")[0] is True
    assert injector.uninstall(str(game_dir), "quick_menu")[0] is True
    assert not (game_dir / "0x52-URM-2.6.2.rpa").exists()
    assert not (game_dir / "dumuqiao.rpy").exists()
    assert not compiled.exists()


def test_install_backs_up_existing_target(monkeypatch, tmp_path) -> None:
    resources = _fake_resources(monkeypatch, tmp_path)
    game_dir = tmp_path / "game"
    game_dir.mkdir()
    target = game_dir / "dumuqiao.rpy"
    target.write_text("old content", encoding="utf-8")
    backup = game_dir / "dumuqiao.rpy.bak"
    backup.write_text("stale backup", encoding="utf-8")

    success, _ = ModInjector().install(str(game_dir), "quick_menu")

    assert success is True
    assert backup.read_text(encoding="utf-8") == "old content"
    assert target.read_bytes() == resources["dumuqiao.rpy"].read_bytes()


def test_resource_directory_is_never_modified(monkeypatch, tmp_path) -> None:
    resources = _fake_resources(monkeypatch, tmp_path)
    injector = ModInjector()

    for key, source in (
        ("urm", resources["0x52-URM-2.6.2.rpa"]),
        ("quick_menu", resources["dumuqiao.rpy"]),
    ):
        original = source.read_bytes()

        assert injector.install(str(source.parent), key)[0] is False
        assert injector.uninstall(str(source.parent), key)[0] is False
        assert source.read_bytes() == original
        assert not source.with_name(f"{source.name}.bak").exists()

    protected_dir = next(iter(resources.values())).parent / "other"
    protected_dir.mkdir()
    assert injector.install(str(protected_dir), "urm")[0] is False
    assert not (protected_dir / "0x52-URM-2.6.2.rpa").exists()


def test_install_returns_failure_when_resource_is_missing(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        mod_injector_module,
        "get_resource_path",
        lambda *parts: str(tmp_path / "missing" / parts[-1]),
    )
    game_dir = tmp_path / "game"
    game_dir.mkdir()

    success, message = ModInjector().install(str(game_dir), "urm")

    assert success is False
    assert "模组资源不存在" in message


def test_uninstall_never_installed_mod_is_successful(tmp_path) -> None:
    game_dir = tmp_path / "game"
    game_dir.mkdir()

    success, _ = ModInjector().uninstall(str(game_dir), "quick_menu")

    assert success is True
