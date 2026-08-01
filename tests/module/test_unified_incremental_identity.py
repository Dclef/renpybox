from pathlib import Path

from module.Extract.UnifiedExtractor import UnifiedExtractor


def make_extractor() -> UnifiedExtractor:
    return UnifiedExtractor.__new__(UnifiedExtractor)


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
