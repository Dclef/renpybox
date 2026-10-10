"""Hakimi 结构导出与 Emoji 替换真实临时游戏。"""
from __future__ import annotations

from pathlib import Path

import openpyxl
import pytest

from module.Extract.EmojiReplacer import (
    apply_replacements_dir,
    backup_folder,
    generate_emoji_replacement_sheets,
    load_default_mapping,
)
from module.Extract.HakimiSuiteRunner import HakimiSuiteRunner
from module.Tool.AssetSuiteOps import AssetSuiteCancelled


def _make_game(tmp_path: Path) -> Path:
    root = tmp_path / "DemoGame"
    game = root / "game"
    tl = game / "tl" / "chinese"
    tl.mkdir(parents=True)
    (game / "script.rpy").write_text(
        'define eileen = Character("Eileen")\n'
        'label start:\n'
        '    e "Hello world"\n'
        '    text "Menu Item":\n'
        '        pass\n'
        '    $ renpy.notify("Notify Me")\n',
        encoding="utf-8",
    )
    (game / "data.json").write_text('{"safe": "External Text", "noise": 1}', encoding="utf-8")
    (tl / "existing.rpy").write_text(
        'translate chinese strings:\n\n'
        '    old "Hello world"\n'
        '    new "你好世界"\n\n'
        '    old "{color=#fff}Tag{/color}"\n'
        '    new "{color=#fff}标签{/color}"\n',
        encoding="utf-8",
    )
    (root / "DemoGame.exe").write_bytes(b"MZ")
    return root


def test_hakimi_modes_dedupe_and_escape(tmp_path: Path):
    root = _make_game(tmp_path)
    runner = HakimiSuiteRunner()

    mode1 = runner.run(root, "chinese", mode="1", confirm_overwrite=True)
    assert mode1.base_dir is not None
    names = openpyxl.load_workbook(mode1.excel_dir / "names.xlsx").active
    others = openpyxl.load_workbook(mode1.excel_dir / "others.xlsx").active
    name_values = {cell.value for cell in names["A"][1:] if cell.value}
    other_values = {cell.value for cell in others["A"][1:] if cell.value}
    assert "Eileen" in name_values
    assert "Hello world" not in other_values  # 已有 tl old 去重
    rpy = (mode1.rpy_dir / "translate_names.rpy").read_text(encoding="utf-8")
    assert 'old "Eileen"' in rpy

    mode2 = runner.run(root, "chinese", mode="2", confirm_overwrite=True)
    assert mode2.replace_count >= mode1.replace_count or mode2.others_count >= 0

    mode3 = runner.run(root, "chinese", mode="3", confirm_overwrite=True, gen_emoji=True)
    assert mode3.emoji_replacements >= 1
    assert (mode3.emoji_dir / "Tag_Protection_Pre(译前).xlsx").exists()

    # 含反斜线/换行的字面量应合法转义
    (root / "game" / "escape.rpy").write_text(
        'define hero = Character("A\\"B\\nC")\n',
        encoding="utf-8",
    )
    again = runner.run(root, "chinese", mode="1", confirm_overwrite=True)
    text = (again.rpy_dir / "translate_names.rpy").read_text(encoding="utf-8")
    assert "\\\\" in text or '\\"' in text or "\\n" in text


def test_hakimi_rejects_bad_language(tmp_path: Path):
    root = _make_game(tmp_path)
    with pytest.raises(ValueError):
        HakimiSuiteRunner().run(root, "../evil", mode="1", confirm_overwrite=True)


def test_hakimi_cancel_during_scan(tmp_path: Path):
    root = _make_game(tmp_path)
    with pytest.raises(AssetSuiteCancelled):
        HakimiSuiteRunner().run(root, "chinese", mode="1", confirm_overwrite=True, cancel_check=lambda: True)


def test_emoji_prepare_restore_and_safe_backup(tmp_path: Path):
    root = _make_game(tmp_path)
    runner = HakimiSuiteRunner()
    result = runner.run(root, "chinese", mode="1", gen_emoji=True, confirm_overwrite=True)
    assert result.emoji_dir is not None

    target = root / "game" / "tl" / "chinese"
    original = (target / "existing.rpy").read_text(encoding="utf-8")
    mapping_pre = load_default_mapping(root, "prepare")
    backup = backup_folder(target, project_root=root)
    assert "_renpybox_backups" in backup.parts
    assert backup.exists()
    success, failed, changed = apply_replacements_dir(target, mapping_pre, is_restore=False)
    assert success >= 1
    assert failed == 0
    prepared = (target / "existing.rpy").read_text(encoding="utf-8")
    assert prepared != original or changed == 0 or "{color" not in prepared

    mapping_post = load_default_mapping(root, "restore")
    apply_replacements_dir(target, mapping_post, is_restore=True)
    restored = (target / "existing.rpy").read_text(encoding="utf-8")
    assert "{color=#fff}Tag{/color}" in restored or "{color=#fff}标签{/color}" in restored


def test_emoji_missing_tl_reports(tmp_path: Path):
    root = _make_game(tmp_path)
    missing = root / "game" / "tl" / "missing"
    with pytest.raises(FileNotFoundError):
        generate_emoji_replacement_sheets(missing, tmp_path / "out")


def test_official_extract_stub_receives_cancel(tmp_path: Path, monkeypatch):
    root = _make_game(tmp_path)
    seen = {}
    cancelled = {"value": False}

    class StubExtractor:
        def official_extract(self, target_path, tl_name, *, generate_empty=False, force=False, timeout_seconds=900.0, should_stop=None, progress_callback=None):
            seen["exe"] = target_path
            seen["tl"] = tl_name
            seen["should_stop"] = should_stop
            cancelled["value"] = True
            if should_stop and should_stop():
                raise RuntimeError("官方抽取已取消")
            return Path(target_path)

    runner = HakimiSuiteRunner(renpy_extractor=StubExtractor())
    with pytest.raises(Exception):
        runner.run(
            root,
            "chinese",
            use_official=True,
            exe_path=root / "DemoGame.exe",
            mode="1",
            confirm_overwrite=True,
            cancel_check=lambda: cancelled["value"],
        )
    assert seen["tl"] == "chinese"
    assert callable(seen["should_stop"])
