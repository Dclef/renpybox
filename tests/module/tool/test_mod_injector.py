from importlib import import_module
from pathlib import Path

from module.Tool.ModInjector import ModInjector


mod_injector_module = import_module("module.Tool.ModInjector")


def _fake_resources(monkeypatch, tmp_path: Path) -> dict[str, Path]:
    resource_root = tmp_path / "resources"
    resources = {
        "hook_gallery_unlock.rpy": resource_root / "hook_gallery_unlock.rpy",
        "0x52-URM-2.6.2.rpa": resource_root / "0x52-URM-2.6.2.rpa",
        "hook_urm_button.rpy": resource_root / "hook_urm_button.rpy",
        "hook_simple_modifier.rpy": resource_root / "hook_simple_modifier.rpy",
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


def test_install_status_and_uninstall_all_mods(monkeypatch, tmp_path) -> None:
    _fake_resources(monkeypatch, tmp_path)
    game_dir = tmp_path / "game"
    game_dir.mkdir()
    injector = ModInjector()

    assert injector.install(str(game_dir), "gallery_unlock")[0] is True
    assert injector.install(str(game_dir), "urm")[0] is True
    assert injector.install(str(game_dir), "simple_modifier")[0] is True
    assert injector.status(str(game_dir)) == {
        "gallery_unlock": True,
        "urm": True,
        "simple_modifier": True,
    }

    gallery_compiled = game_dir / "hook_gallery_unlock.rpyc"
    gallery_compiled.write_bytes(b"compiled")
    (game_dir / "hook_gallery_unlock.rpy").unlink()
    assert injector.status(str(game_dir))["gallery_unlock"] is True

    urm_button_compiled = game_dir / "hook_urm_button.rpyc"
    urm_button_compiled.write_bytes(b"compiled")
    (game_dir / "hook_urm_button.rpy").unlink()
    assert injector.status(str(game_dir))["urm"] is True

    simple_modifier_compiled = game_dir / "hook_simple_modifier.rpyc"
    simple_modifier_compiled.write_bytes(b"compiled")
    (game_dir / "hook_simple_modifier.rpy").unlink()
    assert injector.status(str(game_dir))["simple_modifier"] is True

    assert injector.uninstall(str(game_dir), "gallery_unlock")[0] is True
    assert injector.uninstall(str(game_dir), "urm")[0] is True
    assert injector.uninstall(str(game_dir), "simple_modifier")[0] is True
    assert not (game_dir / "hook_gallery_unlock.rpy").exists()
    assert not gallery_compiled.exists()
    assert not (game_dir / "0x52-URM-2.6.2.rpa").exists()
    assert not (game_dir / "hook_urm_button.rpy").exists()
    assert not urm_button_compiled.exists()
    assert not (game_dir / "hook_simple_modifier.rpy").exists()
    assert not simple_modifier_compiled.exists()


def test_install_backs_up_existing_target(monkeypatch, tmp_path) -> None:
    resources = _fake_resources(monkeypatch, tmp_path)
    game_dir = tmp_path / "game"
    game_dir.mkdir()
    target = game_dir / "hook_gallery_unlock.rpy"
    target.write_text("old content", encoding="utf-8")
    backup = game_dir / "hook_gallery_unlock.rpy.bak"
    backup.write_text("stale backup", encoding="utf-8")

    success, _ = ModInjector().install(str(game_dir), "gallery_unlock")

    assert success is True
    assert backup.read_text(encoding="utf-8") == "old content"
    assert target.read_bytes() == resources["hook_gallery_unlock.rpy"].read_bytes()


def test_install_clears_stale_rpyc_for_script_mod(monkeypatch, tmp_path) -> None:
    _fake_resources(monkeypatch, tmp_path)
    game_dir = tmp_path / "game"
    game_dir.mkdir()
    stale_rpyc = game_dir / "hook_gallery_unlock.rpyc"
    stale_rpyc.write_bytes(b"stale")

    success, _ = ModInjector().install(str(game_dir), "gallery_unlock")

    assert success is True
    assert not stale_rpyc.exists()


def test_resource_directory_is_never_modified(monkeypatch, tmp_path) -> None:
    resources = _fake_resources(monkeypatch, tmp_path)
    injector = ModInjector()

    for key, source in (
        ("gallery_unlock", resources["hook_gallery_unlock.rpy"]),
        ("urm", resources["0x52-URM-2.6.2.rpa"]),
        ("simple_modifier", resources["hook_simple_modifier.rpy"]),
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

    legacy_target = next(iter(resources.values())).parent / "dumuqiao.rpy"
    legacy_target.write_text("legacy", encoding="utf-8")
    assert injector.remove_legacy_dumuqiao(str(legacy_target.parent))[0] is False
    assert legacy_target.read_text(encoding="utf-8") == "legacy"


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


def test_install_validates_all_mod_files_before_writing(
    monkeypatch, tmp_path
) -> None:
    resources = _fake_resources(monkeypatch, tmp_path)
    resources["hook_urm_button.rpy"].unlink()
    game_dir = tmp_path / "game"
    game_dir.mkdir()
    target = game_dir / "0x52-URM-2.6.2.rpa"
    target.write_bytes(b"existing")

    success, message = ModInjector().install(str(game_dir), "urm")

    assert success is False
    assert "模组资源不存在" in message
    assert target.read_bytes() == b"existing"
    assert not target.with_name(f"{target.name}.bak").exists()


def test_uninstall_never_installed_mod_is_successful(tmp_path) -> None:
    game_dir = tmp_path / "game"
    game_dir.mkdir()

    success, _ = ModInjector().uninstall(str(game_dir), "gallery_unlock")

    assert success is True


def test_remove_legacy_dumuqiao_only_removes_known_live_files(tmp_path) -> None:
    game_dir = tmp_path / "game"
    game_dir.mkdir()
    legacy_script = game_dir / "dumuqiao.rpy"
    legacy_compiled = game_dir / "dumuqiao.rpyc"
    legacy_backup = game_dir / "dumuqiao.rpy.bak"
    unrelated_script = game_dir / "dumuqiao_custom.rpy"
    legacy_script.write_text("legacy", encoding="utf-8")
    legacy_compiled.write_bytes(b"compiled")
    legacy_backup.write_text("backup", encoding="utf-8")
    unrelated_script.write_text("custom", encoding="utf-8")
    injector = ModInjector()

    assert injector.has_legacy_dumuqiao(str(game_dir)) is True
    assert injector.remove_legacy_dumuqiao(str(game_dir))[0] is True
    assert injector.has_legacy_dumuqiao(str(game_dir)) is False
    assert not legacy_script.exists()
    assert not legacy_compiled.exists()
    assert legacy_backup.read_text(encoding="utf-8") == "backup"
    assert unrelated_script.read_text(encoding="utf-8") == "custom"


def test_gallery_hook_keeps_cross_version_safe_syntax() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    hook_file = repo_root / "resource" / "mods" / "gallery_unlock" / "hook_gallery_unlock.rpy"
    content = hook_file.read_text(encoding="utf-8")

    # Keep Python 2 compatibility: disallow f-strings in embedded python blocks.
    assert 'f"' not in content
    assert "f'" not in content

    # Guard against reintroducing unsafe identity comparisons from upstream code.
    assert " is 0" not in content
    assert ' is ""' not in content

    # Allow unicode only in NameError-guarded compatibility fallback.
    assert "_rb_text_types = (str, unicode)" in content
    assert "except NameError" in content
    assert "str = unicode" not in content
    # 默认 store 中的 renpy 必须保留为 renpy.exports，否则游戏 GUI 初始化会崩溃。
    assert all(line.strip() != "import renpy" for line in content.splitlines())
    assert "import renpy as _rb_renpy" in content
    assert 'name.startswith("dumuqiao")' in content
    assert 'name == "URMSettings"' in content
    assert 'textbutton "MOD"' in content
    assert 'key "K_F9"' in content
    assert "开启全部画廊" in content
    assert "恢复游戏原本的画廊进度" in content
    assert 'textbutton "内置修改器"' in content
    assert "screen _rb_simple_modifier()" not in content
    assert "_rb_simple_modifier_available" in content
    assert "_rb_modifier_candidates" not in content
    assert "画廊全解锁：（开）" in content
    assert "画廊全解锁：（关）" in content
    assert "对话文字" not in content
    assert "_rb_dialogue_font" not in content
    assert "画廊全解锁：[开]" not in content
    assert "锁住画廊" not in content
    assert "action x52URM.Open()" in content


def test_simple_modifier_hook_is_self_contained_and_does_not_browse_runtime_state() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    hook_file = repo_root / "resource" / "mods" / "simple_modifier" / "hook_simple_modifier.rpy"
    content = hook_file.read_text(encoding="utf-8")

    assert "screen _rb_simple_modifier()" in content
    assert "style.say_dialogue" not in content
    assert "_rb_sm_apply_styles" in content
    assert "renpy.style.rebuild()" in content
    assert "对话框设置" in content
    assert "选项框设置" in content
    assert "快捷菜单" in content
    assert "内置修改器（RenpyBox）" in content
    assert "仿独木桥" not in content
    assert "persistent.__dict__" not in content
    assert 'config.overlay_screens.append("_rb_simple_modifier_toggle")' in content


def test_urm_button_hook_uses_confirmed_safe_entry() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    hook_file = repo_root / "resource" / "mods" / "urm" / "hook_urm_button.rpy"
    content = hook_file.read_text(encoding="utf-8")

    assert 'globals().get("x52URM")' in content
    assert 'hasattr(urm, "Open")' in content
    assert "quickmenuEnabled" not in content
    assert "quickmenuBtnUrm" not in content
    assert 'globals().get("_rb_gallery_installed", False)' in content
    assert "action x52URM.Open()" in content
    assert 'key "alt_K_m"' not in content
