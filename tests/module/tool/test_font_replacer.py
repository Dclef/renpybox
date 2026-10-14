import json
import os
import stat
from pathlib import Path

from module.Tool.FontReplacer import FontReplacer


def _clear_readonly_tree(root: Path) -> None:
    """临时目录清理前解除只读，避免 Windows pytest tmp 删除失败。"""
    if not root.exists():
        return
    for path in root.rglob("*"):
        if path.is_file():
            try:
                os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
            except OSError:
                pass
    try:
        os.chmod(root, stat.S_IWRITE | stat.S_IREAD | stat.S_IEXEC)
    except OSError:
        pass


def test_gui_font_hook_does_not_clear_cache_while_loading_fonts() -> None:
    template = Path(FontReplacer().template_path).read_text(encoding="utf-8")
    load_hook = template.split("def my_load_face", 1)[1].split("renpy.text.font.load_face = my_load_face", 1)[0]

    assert "free_memory()" not in load_hook
    assert template.count("renpy.text.font.free_memory()") == 1


def test_safe_replace_font_backs_up_scripts_and_skips_backup_directory(tmp_path) -> None:
    game_dir = tmp_path / "game"
    fonts_dir = game_dir / "fonts"
    fonts_dir.mkdir(parents=True)
    (fonts_dir / "old.ttf").write_bytes(b"old-font")

    script_path = game_dir / "gui.rpy"
    original_script = (
        'define gui.text_font = "old.ttf"\n'
        'define gui.name_text_font = "other.otf"\n'
    )
    script_path.write_text(original_script, encoding="utf-8")

    old_backup_dir = game_dir / "fonts_backup" / "backup_old" / "original"
    old_backup_dir.mkdir(parents=True)
    old_backup_script = old_backup_dir / "gui.rpy"
    old_backup_script.write_text(original_script, encoding="utf-8")
    (old_backup_dir / "old.ttf").write_bytes(b"backup-font")

    source_font = tmp_path / "new.ttf"
    source_font.write_bytes(b"new-font")

    replacer = FontReplacer()
    success, message, details = replacer.safe_replace_font(
        game_dir=str(game_dir),
        source_font_path=str(source_font),
        original_fonts=["old.ttf", "other.otf"],
        create_backup=True,
    )

    assert success is True
    assert "2 处" in message
    assert details["replaced_files"] == 1
    assert details["replaced_count"] == 2
    assert script_path.read_text(encoding="utf-8") == (
        'define gui.text_font = "fonts/new.ttf"\n'
        'define gui.name_text_font = "fonts/new.ttf"\n'
    )
    assert old_backup_script.read_text(encoding="utf-8") == original_script

    backup_dir = game_dir / "fonts_backup" / details["backup_name"]
    assert (backup_dir / "original" / "gui.rpy.bak").read_text(encoding="utf-8") == original_script
    assert not (backup_dir / "original" / "gui.rpy").exists()
    manifest = json.loads((backup_dir / "fonts_manifest.json").read_text(encoding="utf-8"))
    backed_up_paths = {item["rel_path"] for item in manifest["files"]}
    assert "gui.rpy" in backed_up_paths
    assert all(item.get("storage_rel", "").endswith(".bak") or not str(item.get("rel_path", "")).endswith((".rpy", ".rpym")) for item in manifest["files"])
    assert all(not path.startswith("fonts_backup/") for path in backed_up_paths)

    restored, _ = replacer.restore_backup(str(game_dir), details["backup_name"])
    assert restored is True
    assert script_path.read_text(encoding="utf-8") == original_script


def test_create_backup_uses_unique_stamp_and_bak_extension(tmp_path) -> None:
    game_dir = tmp_path / "game"
    fonts_dir = game_dir / "fonts"
    fonts_dir.mkdir(parents=True)
    (fonts_dir / "old.ttf").write_bytes(b"old")
    (game_dir / "script.rpy").write_text('define gui.text_font = "old.ttf"\n', encoding="utf-8")

    replacer = FontReplacer()
    ok1, _, name1 = replacer.create_backup(str(game_dir), "new.ttf", ["old.ttf"])
    ok2, _, name2 = replacer.create_backup(str(game_dir), "new.ttf", ["old.ttf"])
    assert ok1 and ok2
    assert name1 and name2
    assert name1 != name2
    first = game_dir / "fonts_backup" / name1 / "original" / "script.rpy.bak"
    assert first.is_file()
    assert not (game_dir / "fonts_backup" / name1 / "original" / "script.rpy").exists()


def test_backup_storage_rel_covers_compiled_scripts() -> None:
    assert FontReplacer._backup_storage_rel("tl/a.rpy") == "tl/a.rpy.bak"
    assert FontReplacer._backup_storage_rel("tl/a.rpym") == "tl/a.rpym.bak"
    assert FontReplacer._backup_storage_rel("tl/a.rpyc") == "tl/a.rpyc.bak"
    assert FontReplacer._backup_storage_rel("tl/a.rpymc") == "tl/a.rpymc.bak"
    assert FontReplacer._backup_storage_rel("fonts/x.ttf") == "fonts/x.ttf"


def test_scan_fonts_and_discover_font_files_are_distinct(tmp_path) -> None:
    game_dir = tmp_path / "game"
    fonts_dir = game_dir / "fonts"
    fonts_dir.mkdir(parents=True)
    (fonts_dir / "used.ttf").write_bytes(b"u")
    (fonts_dir / "unused.otf").write_bytes(b"n")
    (game_dir / "gui.rpy").write_text('define gui.text_font = "fonts/used.ttf"\n', encoding="utf-8")

    replacer = FontReplacer()
    refs = replacer.scan_fonts(str(game_dir))
    files = [rel for rel, _ in replacer.discover_font_files(str(game_dir))]
    assert "fonts/used.ttf" in refs
    assert "fonts/unused.otf" not in refs
    assert "fonts/used.ttf" in files
    assert "fonts/unused.otf" in files


def test_create_backup_copy_failure_rejects_and_keeps_recoverable_path(tmp_path, monkeypatch) -> None:
    """任一文件复制失败 → 备份失败，不假成功；脚本以 .bak 落盘且无 live .rpy。"""
    game_dir = tmp_path / "game"
    fonts_dir = game_dir / "fonts"
    fonts_dir.mkdir(parents=True)
    (fonts_dir / "old.ttf").write_bytes(b"old")
    (fonts_dir / "other.otf").write_bytes(b"other")
    (game_dir / "gui.rpy").write_text('define gui.text_font = "old.ttf"\n', encoding="utf-8")

    real_copy2 = __import__("shutil").copy2
    calls = {"n": 0}

    def flaky_copy2(src, dst, *args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError("simulated copy failure")
        return real_copy2(src, dst, *args, **kwargs)

    monkeypatch.setattr("shutil.copy2", flaky_copy2)
    replacer = FontReplacer()
    ok, message, backup_name = replacer.create_backup(str(game_dir), "new.ttf", ["old.ttf"])
    assert ok is False
    assert backup_name
    assert "可恢复路径" in message or "备份失败" in message
    backup_dir = game_dir / "fonts_backup" / backup_name
    assert backup_dir.is_dir()
    assert list(backup_dir.rglob("*.rpy")) == []
    manifest = json.loads((backup_dir / "fonts_manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "failed"
    assert manifest.get("errors")


def test_safe_replace_aborts_when_backup_incomplete(tmp_path, monkeypatch) -> None:
    """不完整备份不得继续替换源码。"""
    game_dir = tmp_path / "game"
    fonts_dir = game_dir / "fonts"
    fonts_dir.mkdir(parents=True)
    (fonts_dir / "old.ttf").write_bytes(b"old")
    script = game_dir / "gui.rpy"
    original = 'define gui.text_font = "old.ttf"\n'
    script.write_text(original, encoding="utf-8")
    source = tmp_path / "new.ttf"
    source.write_bytes(b"new")

    monkeypatch.setattr(
        FontReplacer,
        "create_backup",
        lambda self, *args, **kwargs: (False, "备份失败（模拟）", "backup_incomplete"),
    )
    replacer = FontReplacer()
    success, message, details = replacer.safe_replace_font(
        game_dir=str(game_dir),
        source_font_path=str(source),
        original_fonts=["old.ttf"],
        create_backup=True,
    )
    assert success is False
    assert "备份失败" in message
    assert details["backup_name"] == "backup_incomplete"
    assert script.read_text(encoding="utf-8") == original
    assert not (fonts_dir / "new.ttf").exists()


def test_safe_replace_failure_keeps_details_without_false_restore(tmp_path, monkeypatch) -> None:
    game_dir = tmp_path / "game"
    fonts_dir = game_dir / "fonts"
    fonts_dir.mkdir(parents=True)
    (fonts_dir / "old.ttf").write_bytes(b"old")
    script = game_dir / "gui.rpy"
    script.write_text('define gui.text_font = "old.ttf"\n', encoding="utf-8")
    source = tmp_path / "new.ttf"
    source.write_bytes(b"new")

    monkeypatch.setattr(FontReplacer, "ensure_font_in_game", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        FontReplacer,
        "restore_backup",
        lambda self, game_dir, backup_name: (False, "模拟恢复失败"),
    )
    replacer = FontReplacer()
    success, message, details = replacer.safe_replace_font(
        game_dir=str(game_dir),
        source_font_path=str(source),
        original_fonts=["old.ttf"],
        create_backup=True,
    )
    assert success is False
    assert details.get("backup_name")
    assert details.get("restored") is False
    assert "完整恢复" not in message and "已从备份完整恢复" not in message
    assert "自动恢复未成功" in message or "请手动" in message


def test_batch_write_failure_propagates_failed_files(tmp_path, monkeypatch) -> None:
    """两脚本其一写失败：不得 success=True；须带实际成功计数与 failed_files。"""
    import module.Tool.FontReplacer as font_module

    game_dir = tmp_path / "game"
    fonts_dir = game_dir / "fonts"
    fonts_dir.mkdir(parents=True)
    (fonts_dir / "old.ttf").write_bytes(b"old")
    a = game_dir / "a.rpy"
    b = game_dir / "b.rpy"
    a.write_text('define gui.text_font = "old.ttf"\n', encoding="utf-8")
    b.write_text('define gui.name_text_font = "old.ttf"\n', encoding="utf-8")
    source = tmp_path / "new.ttf"
    source.write_bytes(b"new")

    real_atomic = font_module.atomic_write_text

    def flaky_atomic(path, text, **kwargs):
        if Path(path).name == "b.rpy":
            raise OSError("simulated write failure")
        return real_atomic(path, text, **kwargs)

    monkeypatch.setattr(font_module, "atomic_write_text", flaky_atomic)
    replacer = FontReplacer()
    success, message, details = replacer.safe_replace_font(
        game_dir=str(game_dir),
        source_font_path=str(source),
        original_fonts=["old.ttf"],
        create_backup=False,
    )
    assert success is False
    assert details["replaced_files"] == 1
    assert details["replaced_count"] >= 1
    assert "b.rpy" in details.get("failed_files") or any(
        str(item).endswith("b.rpy") for item in details.get("failed_files") or []
    )
    assert details.get("font_copied") is True
    assert details.get("partial") is True
    assert "fonts/new.ttf" in a.read_text(encoding="utf-8")
    assert 'old.ttf' in b.read_text(encoding="utf-8")
    assert "部分替换失败" in message


def test_no_backup_font_copied_tracks_written_without_backup_guess(tmp_path, monkeypatch) -> None:
    """无自动备份：字体已复制后 batch 抛错，details 须如实 font_copied，不能靠 backup 猜测。"""
    game_dir = tmp_path / "game"
    fonts_dir = game_dir / "fonts"
    fonts_dir.mkdir(parents=True)
    (fonts_dir / "old.ttf").write_bytes(b"old")
    script = game_dir / "gui.rpy"
    original = 'define gui.text_font = "old.ttf"\n'
    script.write_text(original, encoding="utf-8")
    source = tmp_path / "brand_new.ttf"
    source.write_bytes(b"brand-new")

    def boom_folder(self, *args, **kwargs):
        raise RuntimeError("simulated batch failure after font copy")

    monkeypatch.setattr(FontReplacer, "replace_fonts_in_folder", boom_folder)
    replacer = FontReplacer()
    success, message, details = replacer.safe_replace_font(
        game_dir=str(game_dir),
        source_font_path=str(source),
        original_fonts=["old.ttf"],
        create_backup=False,
    )
    assert success is False
    assert details.get("backup_name") in ("", None)
    assert details.get("font_dest")
    # 复制曾发生（font_dest 指向新建名）；清理成功则文件消失，失败则残留如实反馈
    new_font = fonts_dir / "brand_new.ttf"
    if new_font.exists():
        assert details.get("font_residue") or details.get("font_copied") is True
        assert "残留" in message or details.get("partial") is True
    else:
        assert details.get("font_residue") in ("", None)
    assert script.read_text(encoding="utf-8") == original
    assert "完整恢复" not in message


def test_restore_backup_failed_manifest_is_partial_not_full(tmp_path) -> None:
    """manifest.status=failed 时 restore 可恢复子集，但必须 False/部分恢复并保留路径。"""
    game_dir = tmp_path / "game"
    fonts_dir = game_dir / "fonts"
    fonts_dir.mkdir(parents=True)
    (fonts_dir / "old.ttf").write_bytes(b"live-old")
    script = game_dir / "gui.rpy"
    script.write_text('define gui.text_font = "changed.ttf"\n', encoding="utf-8")

    backup_name = "backup_partial_manifest"
    backup_dir = game_dir / "fonts_backup" / backup_name
    original_dir = backup_dir / "original"
    original_dir.mkdir(parents=True)
    (original_dir / "gui.rpy.bak").write_text(
        'define gui.text_font = "old.ttf"\n', encoding="utf-8"
    )
    (original_dir / "old.ttf").write_bytes(b"backed-old")
    manifest = {
        "timestamp": "partial",
        "source_font": "new.ttf",
        "game_dir": str(game_dir),
        "status": "failed",
        "errors": ["fonts/missing.otf: simulated"],
        "files": [
            {
                "rel_path": "gui.rpy",
                "storage_rel": "gui.rpy.bak",
                "backup_path": str(original_dir / "gui.rpy.bak"),
            },
            {
                "rel_path": "fonts/old.ttf",
                "storage_rel": "fonts/old.ttf",
                "backup_path": str(original_dir / "old.ttf"),
            },
        ],
        "created_at": "2026-01-01 00:00:00",
    }
    (backup_dir / "fonts_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    replacer = FontReplacer()
    ok, message = replacer.restore_backup(str(game_dir), backup_name)
    assert ok is False
    assert "部分恢复" in message
    assert backup_name in message or str(backup_dir) in message
    assert script.read_text(encoding="utf-8") == 'define gui.text_font = "old.ttf"\n'
    assert (fonts_dir / "old.ttf").read_bytes() == b"backed-old"
    assert backup_dir.is_dir()


def test_ensure_font_readonly_source_failure_cleans_temp(tmp_path, monkeypatch) -> None:
    """Windows 实证：只读源经 shutil.copy 后 .tmp 带只读，故障清理须去只读再删。"""
    import shutil

    source = tmp_path / "readonly.ttf"
    source.write_bytes(b"READONLY-FONT-BYTES")
    original_mode = source.stat().st_mode
    os.chmod(source, stat.S_IREAD)
    original_bytes = source.read_bytes()

    game_dir = tmp_path / "game"
    fonts_dir = game_dir / "fonts"
    fonts_dir.mkdir(parents=True)
    prior_dest = fonts_dir / "readonly.ttf"
    prior_bytes = b"EXISTING-TARGET"
    prior_dest.write_bytes(prior_bytes)

    real_copy = shutil.copy

    def copy_then_fail(src, dst, *args, **kwargs):
        # 真实复制（含只读 mode），再抛错，复现 PermissionError 残留路径
        real_copy(src, dst)
        raise OSError("simulated failure after readonly copy")

    monkeypatch.setattr("module.Tool.FontReplacer.shutil.copy", copy_then_fail)
    try:
        ensured = FontReplacer().ensure_font_in_game(
            str(game_dir), str(source), "readonly.ttf"
        )
        assert ensured is None
        # 不得留下 .readonly.ttf.<token>.tmp
        assert list(fonts_dir.glob("*.tmp")) == []
        assert list(fonts_dir.glob(".readonly.ttf.*.tmp")) == []
        # 源内容/属性不损坏，旧 target 不损坏
        assert source.read_bytes() == original_bytes
        assert prior_dest.read_bytes() == prior_bytes
        assert not (source.stat().st_mode & stat.S_IWRITE)
    finally:
        # fixture 自身负责解除只读，避免 tmp_path 清理失败
        _clear_readonly_tree(tmp_path)
        try:
            os.chmod(source, original_mode | stat.S_IWRITE)
        except OSError:
            pass


def test_ensure_font_copy_mid_failure_leaves_no_partial_target(tmp_path, monkeypatch) -> None:
    """copy 在实际 destination 写入 partial 后抛错：不得留下新目标/假成功/假完整恢复。"""
    import shutil

    source = tmp_path / "source.ttf"
    source.write_bytes(b"SOURCE-FONT-BYTES")
    original_source = source.read_bytes()

    real_copy = shutil.copy

    def flaky_copy(src, dst, *args, **kwargs):
        dest = Path(dst)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"PARTIAL")
        raise OSError("simulated mid-copy failure")

    monkeypatch.setattr("module.Tool.FontReplacer.shutil.copy", flaky_copy)

    for create_backup, dest_exists in (
        (False, False),
        (False, True),
        (True, False),
        (True, True),
    ):
        game_dir = tmp_path / f"game_b{int(create_backup)}_e{int(dest_exists)}"
        fonts_dir = game_dir / "fonts"
        fonts_dir.mkdir(parents=True)
        (fonts_dir / "old.ttf").write_bytes(b"old")
        script = game_dir / "gui.rpy"
        original_script = 'define gui.text_font = "old.ttf"\n'
        script.write_text(original_script, encoding="utf-8")
        dest = fonts_dir / "source.ttf"
        prior_dest = b"EXISTING-DEST"
        if dest_exists:
            dest.write_bytes(prior_dest)

        replacer = FontReplacer()
        success, message, details = replacer.safe_replace_font(
            game_dir=str(game_dir),
            source_font_path=str(source),
            original_fonts=["old.ttf"],
            create_backup=create_backup,
        )
        assert success is False, (create_backup, dest_exists, message)
        assert details.get("font_copied") is not True
        assert details.get("font_created") is not True
        assert not details.get("font_dest")
        assert source.read_bytes() == original_source
        assert script.read_text(encoding="utf-8") == original_script
        # 不得留下 partial 新目标；原目标内容保持
        if dest_exists:
            assert dest.is_file()
            assert dest.read_bytes() == prior_dest
            assert dest.read_bytes() != b"PARTIAL"
        else:
            assert not dest.exists()
        assert list(fonts_dir.glob(".source.ttf.*.tmp")) == []
        if not create_backup:
            assert details.get("restored") is not True
            assert "完整恢复" not in message
            assert details.get("partial") is not True
        else:
            # 允许从备份完整恢复，但游戏侧不得残留新建 partial 字体
            if details.get("restored") is True:
                assert "完整恢复" in message
            assert not dest.exists() or dest.read_bytes() == prior_dest

    # 源=目标无需复制的行为保留
    monkeypatch.setattr("module.Tool.FontReplacer.shutil.copy", real_copy)
    game_inplace = tmp_path / "game_inplace"
    fonts_inplace = game_inplace / "fonts"
    fonts_inplace.mkdir(parents=True)
    inplace = fonts_inplace / "inplace.ttf"
    inplace.write_bytes(b"inplace")
    ensured = FontReplacer().ensure_font_in_game(
        str(game_inplace), str(inplace), "inplace.ttf"
    )
    assert ensured == str(inplace)
    assert inplace.read_bytes() == b"inplace"


def test_backup_probe_read_failure_rejects_without_side_effects(tmp_path, monkeypatch) -> None:
    """备份探测阶段 read_text 失败：明确失败，不改脚本/字体，无 live 四种脚本。"""
    game_dir = tmp_path / "game"
    fonts_dir = game_dir / "fonts"
    fonts_dir.mkdir(parents=True)
    (fonts_dir / "old.ttf").write_bytes(b"old-font")
    script = game_dir / "gui.rpy"
    original = 'define gui.text_font = "old.ttf"\n'
    script.write_text(original, encoding="utf-8")
    # 额外三种扩展名占位，确认失败后 backup 树无 live 脚本
    (game_dir / "mod.rpym").write_text('define gui.name_text_font = "old.ttf"\n', encoding="utf-8")
    (game_dir / "compiled.rpyc").write_bytes(b"rpyc")
    (game_dir / "mod.rpymc").write_bytes(b"rpymc")
    source = tmp_path / "new.ttf"
    source.write_bytes(b"new-font")

    real_read_text = Path.read_text

    def flaky_read_text(self, *args, **kwargs):
        # 仅探测阶段用 read_text；替换阶段走 open()，不受影响
        if self.name in {"gui.rpy", "mod.rpym"}:
            raise OSError("simulated probe read failure")
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", flaky_read_text)
    replacer = FontReplacer()
    success, message, details = replacer.safe_replace_font(
        game_dir=str(game_dir),
        source_font_path=str(source),
        original_fonts=["old.ttf"],
        create_backup=True,
    )
    assert success is False
    assert "检查待备份脚本失败" in message or "备份失败" in message
    assert details.get("backup_name")
    backup_dir = game_dir / "fonts_backup" / details["backup_name"]
    assert backup_dir.is_dir()
    assert "可恢复路径" in message or backup_dir.name in message
    # 断言走 open，避免仍受探测期 Path.read_text patch 影响
    with open(script, encoding="utf-8") as fh:
        assert fh.read() == original
    assert not (fonts_dir / "new.ttf").exists()
    live = [
        p for p in backup_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in {".rpy", ".rpym", ".rpyc", ".rpymc"}
    ]
    assert live == []


def test_create_backup_manifest_dump_failure_keeps_recoverable_path(tmp_path, monkeypatch) -> None:
    """json.dump 失败：须保留已创建 .bak 路径且不继续替换源码。"""
    game_dir = tmp_path / "game"
    fonts_dir = game_dir / "fonts"
    fonts_dir.mkdir(parents=True)
    (fonts_dir / "old.ttf").write_bytes(b"old")
    script = game_dir / "gui.rpy"
    original = 'define gui.text_font = "old.ttf"\n'
    script.write_text(original, encoding="utf-8")
    source = tmp_path / "new.ttf"
    source.write_bytes(b"new")

    def boom_dump(*args, **kwargs):
        raise OSError("simulated json.dump failure")

    monkeypatch.setattr(json, "dump", boom_dump)
    replacer = FontReplacer()
    ok, message, backup_name = replacer.create_backup(
        str(game_dir), str(source), ["old.ttf"]
    )
    assert ok is False
    assert backup_name
    assert "可恢复路径" in message
    backup_dir = game_dir / "fonts_backup" / backup_name
    assert (backup_dir / "original" / "gui.rpy.bak").is_file()
    assert list(backup_dir.rglob("*.rpy")) == []

    success, replace_msg, details = replacer.safe_replace_font(
        game_dir=str(game_dir),
        source_font_path=str(source),
        original_fonts=["old.ttf"],
        create_backup=True,
    )
    assert success is False
    assert details.get("backup_name")
    assert script.read_text(encoding="utf-8") == original
    assert not (fonts_dir / "new.ttf").exists()
    assert "备份失败" in replace_msg
