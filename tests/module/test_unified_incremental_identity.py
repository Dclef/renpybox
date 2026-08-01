from pathlib import Path

import pytest

from module.Extract.UnifiedExtractor import UnifiedExtractor


def make_extractor() -> UnifiedExtractor:
    extractor = UnifiedExtractor.__new__(UnifiedExtractor)
    extractor.logger = type("TestLogger", (), {"info": lambda self, message: None})()
    return extractor


def write_tl(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_numbered_blocks_are_compared_by_file_and_label(tmp_path):
    existing = tmp_path / "existing"
    extracted = tmp_path / "extracted"
    extractor = make_extractor()

    write_tl(
        existing / "plot" / "first.rpy",
        '''translate chinese first_scene_11111111:

    # narrator "Repeated dialogue."
    narrator "已有译文。"

translate chinese strings:

    old "Global string"
    new "全局字符串"
''',
    )
    write_tl(
        extracted / "plot" / "second.rpy",
        '''translate chinese second_scene_22222222:

    # narrator "Repeated dialogue."
    narrator "Repeated dialogue."

translate chinese strings:

    old "Global string"
    new "Global string"

    old "New string"
    new "New string"
''',
    )

    assert extractor._get_string_originals(existing) == {"Global string"}
    assert extractor._get_string_originals(extracted) == {"Global string", "New string"}
    assert extractor._collect_numbered_block_keys(existing) == {
        ("plot/first.rpy", "first_scene_11111111")
    }
    assert extractor._collect_numbered_block_keys(extracted) == {
        ("plot/second.rpy", "second_scene_22222222")
    }


def test_incremental_output_keeps_repeated_dialogue_in_new_numbered_block(tmp_path):
    source = tmp_path / "source"
    target = tmp_path / "target"
    extractor = make_extractor()
    write_tl(
        source / "plot" / "second.rpy",
        '''translate chinese second_scene_22222222:

    # narrator "Repeated dialogue."
    narrator "Repeated dialogue."

translate chinese strings:

    old "Existing global string"
    new "Existing global string"

    old "New global string"
    new "New global string"
''',
    )

    extractor._extract_new_entries_to_folder(
        source,
        target,
        {"New global string"},
        "chinese",
        selected_block_keys={("plot/second.rpy", "second_scene_22222222")},
    )

    output = (target / "plot" / "second.rpy").read_text(encoding="utf-8")
    assert "translate chinese second_scene_22222222:" in output
    assert '# narrator "Repeated dialogue."' in output
    assert 'narrator "Repeated dialogue."' in output
    assert 'old "New global string"' in output
    assert 'old "Existing global string"' not in output


def test_direct_incremental_merge_keeps_new_numbered_block_with_repeated_text(tmp_path):
    target = tmp_path / "target"
    source = tmp_path / "source"
    extractor = make_extractor()
    write_tl(
        target / "plot" / "scene.rpy",
        '''translate chinese old_scene_11111111:

    # narrator "Repeated dialogue."
    narrator "旧场景译文。"

translate chinese strings:

    old "Existing global string"
    new "已有全局翻译"
''',
    )
    write_tl(
        source / "plot" / "scene.rpy",
        '''translate chinese new_scene_22222222:

    # narrator "Repeated dialogue."
    narrator "Repeated dialogue."

translate chinese strings:

    old "Existing global string"
    new "Existing global string"

    old "New global string"
    new "New global string"
''',
    )

    extractor._merge_new_entries(
        target,
        source,
        {"New global string"},
        {},
        selected_block_keys={("plot/scene.rpy", "new_scene_22222222")},
    )

    output = (target / "plot" / "scene.rpy").read_text(encoding="utf-8")
    assert "translate chinese old_scene_11111111:" in output
    assert "translate chinese new_scene_22222222:" in output
    assert output.count('old "Existing global string"') == 1
    assert 'old "New global string"' in output


def test_numbered_block_translation_does_not_hide_global_string_placeholder(tmp_path):
    tl_dir = tmp_path / "translations"
    extractor = make_extractor()
    write_tl(
        tl_dir / "chapter" / "observatory.rpy",
        '''translate chinese observatory_signal_13572468:

    # guide "Shared signal"
    guide "共享信号的场景译文"

translate chinese strings:

    old "Shared signal"
    new "Shared signal"

    old "Calibrated beacon"
    new "已校准信标"
''',
    )

    all_strings = extractor._get_string_originals(tl_dir)
    translated_strings = extractor._get_translated_string_originals(tl_dir)
    block_originals = extractor._collect_block_originals(tl_dir)
    pending = extractor._get_untranslated_originals(tl_dir)
    pending -= block_originals - all_strings
    pending -= translated_strings

    assert all_strings == {"Shared signal", "Calibrated beacon"}
    assert translated_strings == {"Calibrated beacon"}
    assert pending == {"Shared signal"}


def test_static_menu_supplement_is_not_hidden_by_block_in_another_file(tmp_path):
    project = tmp_path / "project"
    game_dir = project / "game"
    tl_dir = game_dir / "tl" / "chinese"
    extractor = make_extractor()
    write_tl(
        game_dir / "chapter" / "control_room.rpy",
        '''label control_room:
    menu:
        "Launch probe":
            pass
''',
    )
    write_tl(
        tl_dir / "chapter" / "briefing.rpy",
        '''translate chinese briefing_probe_24681357:

    # scientist "Launch probe"
    scientist "发射探测器的场景译文"
''',
    )

    added = extractor._append_static_supplement_entries(project, tl_dir, "chinese")

    output = (tl_dir / "chapter" / "control_room.rpy").read_text(encoding="utf-8")
    assert added == 1
    assert 'old "Launch probe"' in output


def test_existing_string_translation_map_excludes_numbered_blocks(tmp_path):
    tl_dir = tmp_path / "translations"
    extractor = make_extractor()
    write_tl(
        tl_dir / "chapter" / "planetarium.rpy",
        '''translate chinese planetarium_intro_11223344:

    # curator "Open the dome"
    curator "打开穹顶的场景译文"

translate chinese strings:

    old "Activate star map"
    new "启动星图"
''',
    )

    translations = extractor._get_existing_string_translations(tl_dir)

    assert translations == {"Activate star map": "启动星图"}
    assert "Open the dome" not in translations


def test_merge_incremental_folder_keeps_numbered_only_blocks(tmp_path):
    game_dir = tmp_path / "fictional_game"
    target = game_dir / "game" / "tl" / "chinese" / "plot" / "signals.rpy"
    incremental = game_dir / "game" / "tl" / "chinese_new"
    delta = incremental / "plot" / "signals.rpy"
    write_tl(
        target,
        'translate chinese signal_alpha_11111111:\n'
        '    # guide "The amber relay is quiet."\n'
        '    guide "琥珀中继器很安静。"\n',
    )
    write_tl(
        delta,
        'translate chinese signal_beta_22222222:\n'
        '    # pilot "The silver relay is awake."\n'
        '    pilot "银色中继器已苏醒。"\n',
    )

    result = UnifiedExtractor().merge_incremental_folder(
        game_dir, "chinese", incremental, clean_duplicates=False
    )

    assert result.success is True
    merged = target.read_text(encoding="utf-8")
    assert "signal_alpha_11111111" in merged
    assert "signal_beta_22222222" in merged
    assert "银色中继器已苏醒。" in merged
    assert not incremental.exists()


def test_merge_incremental_folder_preserves_staging_when_verification_fails(
    tmp_path, monkeypatch
):
    game_dir = tmp_path / "fictional_game"
    incremental = game_dir / "game" / "tl" / "chinese_new"
    delta = incremental / "plot" / "beacon.rpy"
    write_tl(
        delta,
        'translate chinese beacon_gamma_33333333:\n'
        '    # navigator "A violet beacon is missing."\n'
        '    navigator "紫色信标不见了。"\n',
    )
    extractor = UnifiedExtractor()
    monkeypatch.setattr(extractor, "_merge_new_entries", lambda *args, **kwargs: None)

    result = extractor.merge_incremental_folder(
        game_dir, "chinese", incremental, clean_duplicates=False
    )

    assert result.success is False
    assert "已保留增量目录" in result.message
    assert delta.exists()


def test_legacy_translation_restore_keeps_same_text_numbered_blocks_independent(tmp_path):
    tl_dir = tmp_path / "tl" / "chinese"
    path = tl_dir / "plot" / "observatory.rpy"
    extractor = UnifiedExtractor()
    write_tl(
        path,
        'translate chinese guide_view_11111111:\n'
        '    # guide "The same star is visible."\n'
        '    guide "向导看到的那颗星。"\n\n'
        'translate chinese pilot_view_22222222:\n'
        '    # pilot "The same star is visible."\n'
        '    pilot "领航员看到的那颗星。"\n',
    )
    translations = extractor._get_existing_translations(tl_dir)
    write_tl(
        path,
        'translate chinese guide_view_11111111:\n'
        '    # guide "The same star is visible."\n'
        '    guide ""\n\n'
        'translate chinese pilot_view_22222222:\n'
        '    # pilot "The same star is visible."\n'
        '    pilot ""\n',
    )

    extractor._merge_translations(tl_dir, translations)

    restored = path.read_text(encoding="utf-8")
    assert restored.count("向导看到的那颗星。") == 1
    assert restored.count("领航员看到的那颗星。") == 1


def test_regular_backup_failure_stops_before_overwrite(tmp_path, monkeypatch):
    game_dir = tmp_path / "fictional_game"
    tl_dir = game_dir / "game" / "tl" / "chinese"
    write_tl(tl_dir / "plot" / "archive.rpy", "stable archive\n")
    extractor = UnifiedExtractor()

    def fail_move(_source, _target):
        raise OSError("fictional backup failure")

    monkeypatch.setattr("module.Extract.UnifiedExtractor.shutil.move", fail_move)

    with pytest.raises(RuntimeError, match="已停止抽取"):
        extractor._backup_tl_dir(game_dir, "chinese")

    assert (tl_dir / "plot" / "archive.rpy").read_text(encoding="utf-8") == "stable archive\n"


def test_changed_source_in_same_numbered_label_is_replaced_after_retranslation(tmp_path):
    game_dir = tmp_path / "fictional_game"
    target = game_dir / "game" / "tl" / "chinese" / "plot" / "comet.rpy"
    incremental = game_dir / "game" / "tl" / "chinese_new"
    delta = incremental / "plot" / "comet.rpy"
    write_tl(
        target,
        'translate chinese comet_report_44444444:\n'
        '    # astronomer "The comet is dim."\n'
        '    astronomer "彗星很暗。"\n',
    )
    write_tl(
        delta,
        'translate chinese comet_report_44444444:\n'
        '    # astronomer "The comet is dazzling."\n'
        '    astronomer "彗星十分耀眼。"\n',
    )
    extractor = UnifiedExtractor()
    before = extractor._collect_numbered_block_fingerprints(target.parents[1])
    changed = extractor._collect_numbered_block_fingerprints(incremental)
    assert before[("plot/comet.rpy", "comet_report_44444444")] != changed[
        ("plot/comet.rpy", "comet_report_44444444")
    ]

    result = extractor.merge_incremental_folder(
        game_dir, "chinese", incremental, clean_duplicates=False
    )

    assert result.success is True
    merged = target.read_text(encoding="utf-8")
    assert "The comet is dim." not in merged
    assert "彗星很暗。" not in merged
    assert "The comet is dazzling." in merged
    assert "彗星十分耀眼。" in merged


def test_repeated_text_inside_one_numbered_block_keeps_each_translation(tmp_path):
    tl_dir = tmp_path / "tl" / "chinese"
    path = tl_dir / "plot" / "echo.rpy"
    extractor = UnifiedExtractor()
    write_tl(
        path,
        'translate chinese echo_test_55555555:\n'
        '    # guide "Echo confirmed."\n'
        '    guide "第一次回声已确认。"\n'
        '    # guide "Echo confirmed."\n'
        '    guide "第二次回声已确认。"\n',
    )
    translations = extractor._get_existing_translations(tl_dir)
    write_tl(
        path,
        'translate chinese echo_test_55555555:\n'
        '    # guide "Echo confirmed."\n'
        '    guide ""\n'
        '    # guide "Echo confirmed."\n'
        '    guide ""\n',
    )

    extractor._merge_translations(tl_dir, translations)

    restored = path.read_text(encoding="utf-8")
    assert restored.count("第一次回声已确认。") == 1
    assert restored.count("第二次回声已确认。") == 1


def test_cross_file_write_failure_preserves_incremental_translation(tmp_path, monkeypatch):
    game_dir = tmp_path / "fictional_game"
    tl_dir = game_dir / "game" / "tl" / "chinese"
    staging = game_dir / "game" / "tl" / "chinese_new"
    placeholder = tl_dir / "menus" / "telescope.rpy"
    same_relative_target = tl_dir / "updates" / "night.rpy"
    delta = staging / "updates" / "night.rpy"
    write_tl(
        placeholder,
        'translate chinese strings:\n\n'
        '    old "Align the fictional telescope"\n'
        '    new "Align the fictional telescope"\n',
    )
    write_tl(
        same_relative_target,
        'translate chinese strings:\n\n'
        '    old "Keep the observatory quiet"\n'
        '    new "保持天文台安静"\n',
    )
    write_tl(
        delta,
        'translate chinese strings:\n\n'
        '    old "Align the fictional telescope"\n'
        '    new "校准虚构望远镜"\n',
    )

    unified_module = __import__(
        "module.Extract.UnifiedExtractor", fromlist=["atomic_write_text"]
    )
    real_atomic_write = unified_module.atomic_write_text

    def fail_placeholder_write(path, text, **kwargs):
        if Path(path) == placeholder:
            raise OSError("fictional write interruption")
        return real_atomic_write(path, text, **kwargs)

    monkeypatch.setattr(unified_module, "atomic_write_text", fail_placeholder_write)

    result = UnifiedExtractor().merge_incremental_folder(
        game_dir, "chinese", staging, clean_duplicates=False
    )

    assert result.success is False
    assert "跨文件占位译文未写入" in result.message
    assert delta.exists()
    assert 'new "Align the fictional telescope"' in placeholder.read_text(
        encoding="utf-8"
    )
