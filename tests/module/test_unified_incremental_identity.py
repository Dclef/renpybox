from pathlib import Path

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
