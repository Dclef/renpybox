import json
from pathlib import Path

from module.Tool.FontReplacer import FontReplacer


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
    assert (backup_dir / "original" / "gui.rpy").read_text(encoding="utf-8") == original_script
    manifest = json.loads((backup_dir / "fonts_manifest.json").read_text(encoding="utf-8"))
    backed_up_paths = {item["rel_path"] for item in manifest["files"]}
    assert "gui.rpy" in backed_up_paths
    assert all(not path.startswith("fonts_backup/") for path in backed_up_paths)

    restored, _ = replacer.restore_backup(str(game_dir), details["backup_name"])
    assert restored is True
    assert script_path.read_text(encoding="utf-8") == original_script
