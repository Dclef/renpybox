from pathlib import Path
from enum import Enum

import pytest

from module.Extract.UnifiedExtractor import UnifiedExtractor
from module.Renpy.renpy_tl_core import parse_tl_document


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


def test_incremental_scanners_accept_legacy_str_enum_kinds(tmp_path, monkeypatch):
    class LegacyKind(str, Enum):
        LABEL = "LABEL"
        STRINGS = "STRINGS"
        PYTHON = "PYTHON"
        OTHER = "OTHER"

    tl_dir = tmp_path / "legacy_runtime"
    write_tl(
        tl_dir / "plot" / "beacon.rpy",
        '''translate chinese fictional_beacon_12345678:

    # guide "The fictional beacon glows."
    guide "虚构信标正在发光。"

translate chinese strings:

    old "Fictional beacon"
    new "虚构信标"
''',
    )

    def parse_with_legacy_enum(lines):
        doc = parse_tl_document(lines)
        for block in doc.blocks:
            block.kind = LegacyKind(block.kind.value)
            for statement in block.statements:
                statement.block_kind = block.kind
        return doc

    monkeypatch.setattr(
        "module.Extract.UnifiedExtractor.parse_tl_document",
        parse_with_legacy_enum,
    )
    extractor = make_extractor()
    block_originals = set()

    assert extractor._get_string_originals(
        tl_dir, block_originals=block_originals
    ) == {"Fictional beacon"}
    assert block_originals == {"The fictional beacon glows."}
    assert extractor._collect_numbered_block_keys(tl_dir) == {
        ("plot/beacon.rpy", "fictional_beacon_12345678")
    }
    translations = extractor._get_existing_translations(tl_dir)
    assert translations.strings == {"Fictional beacon": "虚构信标"}
    assert list(translations.blocks.values()) == ["虚构信标正在发光。"]


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


def test_numbered_identity_is_layout_independent_across_formats(tmp_path):
    """增量格式（头部后无空行）与官方/合并格式（头部后有空行）身份一致。"""
    from module.Renpy.renpy_tl_io import RenpyTlItemExtractor

    official = tmp_path / "official.rpy"
    official.write_text(
        "translate chinese kitchen_scene_244739f4:\n"
        "\n"
        '    # mono "Yes, ma\'am."\n'
        '    mono ""\n'
        "\n"
        '    # mono "Again?"\n'
        '    mono "Again?"\n',
        encoding="utf-8",
    )
    delta = tmp_path / "delta.rpy"
    delta.write_text(
        "translate chinese kitchen_scene_244739f4:\n"
        '    # mono "Yes, ma\'am."\n'
        '    mono ""\n'
        '    # mono "Again?"\n'
        '    mono "Again?"\n',
        encoding="utf-8",
    )

    extractor = make_extractor()
    item_extractor = RenpyTlItemExtractor()

    def keys(path):
        doc = parse_tl_document(path.read_text(encoding="utf-8").splitlines())
        items = item_extractor.extract(doc, "kitchen.rpy")
        return [
            extractor._numbered_item_translation_key("kitchen.rpy", item)
            for item in items
        ]

    official_keys = keys(official)
    delta_keys = keys(delta)
    assert len(official_keys) == 2
    assert official_keys == delta_keys
    # 相同模板文本的相邻语句仍可通过序号区分。
    assert len({key[4] for key in delta_keys}) == 2


def test_declined_candidates_recorded_and_skipped(tmp_path, monkeypatch):
    """判定不译的候选写入项目清单，后续补充抽取不再重复提出。"""
    from module.Extract.UnifiedExtractor import (
        load_declined_candidates,
        record_declined_candidates,
    )

    game_dir = tmp_path / "gameproj"
    tl_dir = game_dir / "game" / "tl" / "chinese"
    tl_dir.mkdir(parents=True)

    assert record_declined_candidates(game_dir, "chinese", {"CineSaga", "Screen 1"}) == 2
    assert load_declined_candidates(game_dir, "chinese") == {"CineSaga", "Screen 1"}
    # 重复记录幂等。
    assert record_declined_candidates(game_dir, "chinese", {"CineSaga"}) == 0

    extractor = make_extractor()
    candidates = {
        "CineSaga": "res/meta/sets.rpy",
        "Screen 1": "res/meta/sets.rpy",
        "Fresh candidate": "res/meta/other.rpy",
    }
    monkeypatch.setattr(
        "module.Extract.UnifiedExtractor.rx.collect_static_source_strings",
        lambda game_dir: candidates,
    )
    monkeypatch.setattr(
        "module.Extract.UnifiedExtractor.rx.collect_static_menu_strings",
        lambda game_dir: {},
    )
    added = extractor._append_static_supplement_entries(
        game_dir,
        tl_dir,
        "chinese",
        candidates=candidates,
        menu_candidates=set(),
    )
    assert added == 1
    assert not (tl_dir / "res" / "meta" / "sets.rpy").exists()
    text = (tl_dir / "res" / "meta" / "other.rpy").read_text(encoding="utf-8")
    assert 'old "Fresh candidate"' in text


def test_merge_new_entries_places_label_blocks_before_strings_block(tmp_path):
    """合并后编号翻译块位于 old/new strings 块之前，strings 保持文件最后。"""
    tl_dir = tmp_path / "tl"
    tl_dir.mkdir()
    target = tl_dir / "scene.rpy"
    target.write_text(
        "translate chinese strings:\n"
        '    old "Old string"\n'
        '    new "旧字符串"\n',
        encoding="utf-8",
    )

    source = tmp_path / "source"
    source.mkdir()
    delta = source / "scene.rpy"
    delta.write_text(
        "translate chinese new_scene_33333333:\n"
        '    # guide "Brand new line."\n'
        '    guide "全新台词。"\n'
        "translate chinese strings:\n"
        '    old "New string"\n'
        '    new "新字符串"\n',
        encoding="utf-8",
    )

    extractor = make_extractor()
    extractor._merge_new_entries(
        tl_dir,
        source,
        {"New string"},
        {},
        selected_block_keys={("scene.rpy", "new_scene_33333333")},
    )

    text = target.read_text(encoding="utf-8")
    assert (
        text.index("translate chinese new_scene_33333333:")
        < text.index("translate chinese strings:")
    )
    assert 'old "New string"' in text
    assert 'old "Old string"' in text


def test_collect_declined_candidates_from_cycle(tmp_path):
    """合并周期结束后，提出但未进入翻译输出的候选被收集。"""
    game_dir = tmp_path / "gameproj"
    staging = game_dir / "game" / "tl" / "chinese_new"
    output = tmp_path / "output"
    staging.mkdir(parents=True)
    output.mkdir()
    (staging / "proposed.rpy").write_text(
        "translate chinese strings:\n"
        '    old "Proposed but dropped"\n'
        '    new "Proposed but dropped"\n'
        '    old "Translated fine"\n'
        '    new "译文"\n',
        encoding="utf-8",
    )
    (output / "applied.rpy").write_text(
        "translate chinese strings:\n"
        '    old "Translated fine"\n'
        '    new "译文"\n',
        encoding="utf-8",
    )

    extractor = make_extractor()
    declined = extractor._collect_declined_candidates_from_cycle(
        game_dir,
        "chinese",
        output,
    )
    assert declined == {"Proposed but dropped"}


def test_sort_numbered_blocks_by_source_line(tmp_path):
    """编号块按源行号升序整理，缺失位置注释的块补注释，strings 保持最后。"""
    game_dir = tmp_path / "gameproj"
    tl_dir = game_dir / "game" / "tl" / "chinese"
    tl_dir.mkdir(parents=True)
    source = game_dir / "game" / "src" / "plot" / "scene.rpy"
    source.parent.mkdir(parents=True)
    source.write_text(
        'guide "First line."\n'
        'guide "Second line."\n'
        'guide "Third line."\n',
        encoding="utf-8",
    )
    tl_file = tl_dir / "src" / "plot" / "scene.rpy"
    tl_file.parent.mkdir(parents=True)
    # 顺序故意打乱：第三行在前、第一行中间、第二行最后，strings 块夹在中间。
    tl_file.write_text(
        "translate chinese third_33333333:\n"
        '    # guide "Third line."\n'
        '    guide "第三行。"\n'
        "\n"
        "translate chinese first_11111111:\n"
        '    # guide "First line."\n'
        '    guide "第一行。"\n'
        "\n"
        "translate chinese strings:\n"
        '    old "S"\n'
        '    new "字符串"\n'
        "\n"
        "translate chinese second_22222222:\n"
        '    # guide "Second line."\n'
        '    guide "第二行。"\n',
        encoding="utf-8",
    )

    extractor = make_extractor()
    assert extractor._sort_numbered_blocks_by_source_line(game_dir, tl_dir) == 1
    text = tl_file.read_text(encoding="utf-8")
    assert (
        text.index("first_11111111")
        < text.index("second_22222222")
        < text.index("third_33333333")
    )
    # strings 块移动到文件最后。
    assert text.index("translate chinese strings:") > text.index("third_33333333")
    # 缺失的位置注释被补齐。
    assert "# game/src/plot/scene.rpy:1" in text
    assert "# game/src/plot/scene.rpy:2" in text
    assert "# game/src/plot/scene.rpy:3" in text
    # 幂等：再次整理不重写。
    assert extractor._sort_numbered_blocks_by_source_line(game_dir, tl_dir) == 0


def test_sort_numbered_blocks_skips_ordered_files(tmp_path):
    """已按源行号排序的文件不应被重写。"""
    game_dir = tmp_path / "gameproj"
    tl_dir = game_dir / "game" / "tl" / "chinese"
    tl_dir.mkdir(parents=True)
    tl_file = tl_dir / "scene.rpy"
    tl_file.write_text(
        "translate chinese first_11111111:\n"
        '    # guide "First."\n'
        '    guide "第一。"\n'
        "\n"
        "translate chinese second_22222222:\n"
        '    # guide "Second."\n'
        '    guide "第二。"\n',
        encoding="utf-8",
    )
    extractor = make_extractor()
    assert extractor._sort_numbered_blocks_by_source_line(game_dir, tl_dir) == 0
    assert "first_11111111" in tl_file.read_text(encoding="utf-8")


def test_sort_numbered_blocks_handles_blank_between_location_and_header(tmp_path):
    """位置注释与块头之间存在空白行时仍能识别并按行号排序。"""
    game_dir = tmp_path / "gameproj"
    tl_dir = game_dir / "game" / "tl" / "chinese"
    tl_dir.mkdir(parents=True)
    source = game_dir / "game" / "src" / "plot" / "scene.rpy"
    source.parent.mkdir(parents=True)
    source.write_text(
        'guide "Early line."\n'
        'guide "Late line."\n',
        encoding="utf-8",
    )
    tl_file = tl_dir / "src" / "plot" / "scene.rpy"
    tl_file.parent.mkdir(parents=True)
    # 顺序颠倒，且注释与块头之间有空行。
    tl_file.write_text(
        "# game/src/plot/scene.rpy:2\n"
        "\n"
        "translate chinese late_22222222:\n"
        '    # guide "Late line."\n'
        '    guide "第二行。"\n'
        "\n"
        "# game/src/plot/scene.rpy:1\n"
        "\n"
        "translate chinese early_11111111:\n"
        '    # guide "Early line."\n'
        '    guide "第一行。"\n',
        encoding="utf-8",
    )

    extractor = make_extractor()
    assert extractor._sort_numbered_blocks_by_source_line(game_dir, tl_dir) == 1
    text = tl_file.read_text(encoding="utf-8")
    assert text.index("early_11111111") < text.index("late_22222222")


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


def test_direct_incremental_merge_filters_mixed_file_when_target_is_new(tmp_path):
    target = tmp_path / "target"
    source = tmp_path / "source"
    extractor = make_extractor()
    write_tl(
        source / "plot" / "new_signal.rpy",
        '''translate chinese new_signal_30303030:

    # guide "A fictional copper signal appears."
    guide "虚构的铜色信号出现了。"

translate chinese strings:

    old "Shared fictional switch"
    new "已翻译的虚构开关"
''',
    )

    extractor._merge_new_entries(
        target,
        source,
        set(),
        {},
        selected_block_keys={("plot/new_signal.rpy", "new_signal_30303030")},
    )

    output = (target / "plot" / "new_signal.rpy").read_text(encoding="utf-8")
    assert "translate chinese new_signal_30303030:" in output
    assert "虚构的铜色信号出现了。" in output
    assert "Shared fictional switch" not in output
    assert "已翻译的虚构开关" not in output


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


def test_filtered_new_target_write_failure_does_not_copy_mixed_source(
    tmp_path, monkeypatch
):
    game_dir = tmp_path / "fictional_game"
    target_dir = game_dir / "game" / "tl" / "chinese"
    existing = target_dir / "menus" / "dial.rpy"
    incremental = game_dir / "game" / "tl" / "chinese_new"
    mixed_delta = incremental / "updates" / "mixed_dials.rpy"
    mixed_target = target_dir / "updates" / "mixed_dials.rpy"
    write_tl(
        existing,
        'translate chinese strings:\n\n'
        '    old "Existing fictional dial"\n'
        '    new "Existing fictional dial"\n',
    )
    write_tl(
        mixed_delta,
        'translate chinese strings:\n\n'
        '    old "Existing fictional dial"\n'
        '    new "已有虚构刻度盘的增量译文"\n\n'
        '    old "New fictional dial"\n'
        '    new "新增虚构刻度盘译文"\n',
    )

    unified_module = __import__(
        "module.Extract.UnifiedExtractor", fromlist=["atomic_write_text"]
    )
    real_atomic_write = unified_module.atomic_write_text
    failed_once = False

    def fail_filtered_target_once(path, text, **kwargs):
        nonlocal failed_once
        if Path(path) == mixed_target and not failed_once:
            failed_once = True
            raise OSError("fictional filtered write interruption")
        return real_atomic_write(path, text, **kwargs)

    monkeypatch.setattr(unified_module, "atomic_write_text", fail_filtered_target_once)

    result = UnifiedExtractor().merge_incremental_folder(
        game_dir, "chinese", incremental, clean_duplicates=False
    )

    assert failed_once is True
    assert result.success is False
    assert "写入筛选后的新增翻译失败" in result.message
    assert incremental.exists()
    assert not mixed_target.exists()
    assert "Existing fictional dial" in existing.read_text(encoding="utf-8")


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


def test_equal_numbered_template_applies_missing_translation_only(tmp_path):
    game_dir = tmp_path / "fictional_game"
    target = game_dir / "game" / "tl" / "chinese" / "plot" / "relay.rpy"
    incremental = game_dir / "game" / "tl" / "chinese_new"
    delta = incremental / "plot" / "relay.rpy"
    write_tl(
        target,
        'translate chinese relay_report_45454545:\n'
        '    # guide "The fictional relay opens."\n'
        '    guide "保留的人工中继器译文。"\n'
        '    # guide "The fictional relay closes."\n'
        '    guide "The fictional relay closes."\n',
    )
    write_tl(
        delta,
        'translate chinese relay_report_45454545:\n'
        '    # guide "The fictional relay opens."\n'
        '    guide "增量中继器打开译文。"\n'
        '    # guide "The fictional relay closes."\n'
        '    guide "增量中继器关闭译文。"\n',
    )

    result = UnifiedExtractor().merge_incremental_folder(
        game_dir, "chinese", incremental, clean_duplicates=False
    )

    assert result.success is True
    merged = target.read_text(encoding="utf-8")
    assert "保留的人工中继器译文。" in merged
    assert "增量中继器打开译文。" not in merged
    assert "增量中继器关闭译文。" in merged
    assert "The fictional relay closes." not in merged.splitlines()[-1]
    assert not incremental.exists()


def test_equal_numbered_template_merges_name_and_dialogue_independently(tmp_path):
    game_dir = tmp_path / "fictional_game"
    target = game_dir / "game" / "tl" / "chinese" / "plot" / "lighthouse.rpy"
    incremental = game_dir / "game" / "tl" / "chinese_new"
    delta = incremental / "plot" / "lighthouse.rpy"
    write_tl(
        target,
        'translate chinese lighthouse_report_46464646:\n'
        '    # Character("Captain Lumen") "The fictional lighthouse is ready."\n'
        '    Character("Captain Lumen") "保留的人工灯塔对白译文。"\n',
    )
    write_tl(
        delta,
        'translate chinese lighthouse_report_46464646:\n'
        '    # Character("Captain Lumen") "The fictional lighthouse is ready."\n'
        '    Character("露明船长") "较早的增量灯塔对白译文。"\n',
    )

    result = UnifiedExtractor().merge_incremental_folder(
        game_dir, "chinese", incremental, clean_duplicates=False
    )

    assert result.success is True
    merged = target.read_text(encoding="utf-8")
    assert 'Character("露明船长") "保留的人工灯塔对白译文。"' in merged
    assert "较早的增量灯塔对白译文。" not in merged
    assert not incremental.exists()


def test_unapplied_numbered_name_translation_preserves_staging(tmp_path, monkeypatch):
    game_dir = tmp_path / "fictional_game"
    target = game_dir / "game" / "tl" / "chinese" / "plot" / "harbor.rpy"
    incremental = game_dir / "game" / "tl" / "chinese_new"
    delta = incremental / "plot" / "harbor.rpy"
    write_tl(
        target,
        'translate chinese harbor_report_47474747:\n'
        '    # Character("Keeper Sol") "The fictional harbor is quiet."\n'
        '    Character("Keeper Sol") "保留的人工港口对白译文。"\n',
    )
    write_tl(
        delta,
        'translate chinese harbor_report_47474747:\n'
        '    # Character("Keeper Sol") "The fictional harbor is quiet."\n'
        '    Character("索尔守望者") "较早的增量港口对白译文。"\n',
    )
    extractor = UnifiedExtractor()
    monkeypatch.setattr(extractor, "_merge_translations", lambda *_args, **_kwargs: [])

    result = extractor.merge_incremental_folder(
        game_dir, "chinese", incremental, clean_duplicates=False
    )

    assert result.success is False
    assert "编号块角色名译文未写入" in result.message
    assert incremental.exists()
    assert 'Character("Keeper Sol") "保留的人工港口对白译文。"' in (
        target.read_text(encoding="utf-8")
    )


def test_equal_numbered_template_preserves_staging_when_translation_is_not_applied(
    tmp_path, monkeypatch
):
    game_dir = tmp_path / "fictional_game"
    target = game_dir / "game" / "tl" / "chinese" / "plot" / "beacon.rpy"
    incremental = game_dir / "game" / "tl" / "chinese_new"
    delta = incremental / "plot" / "beacon.rpy"
    write_tl(
        target,
        'translate chinese beacon_report_56565656:\n'
        '    # guide "The fictional beacon glows."\n'
        '    guide "The fictional beacon glows."\n',
    )
    write_tl(
        delta,
        'translate chinese beacon_report_56565656:\n'
        '    # guide "The fictional beacon glows."\n'
        '    guide "虚构信标正在发光。"\n',
    )
    extractor = UnifiedExtractor()
    monkeypatch.setattr(extractor, "_merge_translations", lambda *_args, **_kwargs: [])

    result = extractor.merge_incremental_folder(
        game_dir, "chinese", incremental, clean_duplicates=False
    )

    assert result.success is False
    assert "编号块译文未写入" in result.message
    assert incremental.exists()
    assert 'guide "The fictional beacon glows."' in target.read_text(encoding="utf-8")


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

def test_changed_numbered_block_keeps_unchanged_line_translation(tmp_path):
    game_dir = tmp_path / "fictional_game"
    target = game_dir / "game" / "tl" / "chinese" / "plot" / "observatory.rpy"
    incremental = game_dir / "game" / "tl" / "chinese_new"
    delta = incremental / "plot" / "observatory.rpy"
    write_tl(
        target,
        'translate chinese observatory_report_12345678:\n'
        '    # guide "The observatory opens."\n'
        '    guide "天文台已开放。"\n'
        '    # guide "The observatory closes."\n'
        '    guide "The observatory closes."\n',
    )
    write_tl(
        delta,
        'translate chinese observatory_report_12345678:\n'
        '    # guide "The observatory opens."\n'
        '    guide "The observatory opens."\n'
        '    # guide "The observatory is closed today."\n'
        '    guide "The observatory is closed today."\n',
    )

    result = UnifiedExtractor().merge_incremental_folder(
        game_dir, "chinese", incremental, clean_duplicates=False
    )

    assert result.success is True
    merged = target.read_text(encoding="utf-8")
    # 未变语句保留旧译文。
    assert "天文台已开放。" in merged
    assert 'guide "The observatory opens."' not in merged.splitlines()[-1]
    # 变化语句保持占位待译。
    assert "The observatory is closed today." in merged
    assert "天文台今日关闭。" not in merged


def test_stale_incremental_state_is_recovered(tmp_path):
    game_dir = tmp_path / "fictional_game"
    tl_dir = game_dir / "game" / "tl" / "chinese"
    tl_dir.mkdir(parents=True)
    (tl_dir / "kept.rpy").write_text("kept translation", encoding="utf-8")
    extractor = UnifiedExtractor.__new__(UnifiedExtractor)
    extractor.logger = type(
        "TestLogger",
        (),
        {
            "info": lambda self, message: None,
            "warning": lambda self, message: None,
            "error": lambda self, message: None,
        },
    )()

    # 模拟崩溃现场：tl 被移走、只剩 journal + 临时备份。
    temp_dir = game_dir / "_temp_extract_chinese_123"
    backup = temp_dir / "_tl_backup"
    backup.mkdir(parents=True, exist_ok=True)
    (backup / "kept.rpy").write_text("kept translation", encoding="utf-8")
    import shutil
    shutil.rmtree(str(tl_dir))
    extractor._write_incremental_journal(game_dir, "chinese", temp_dir, tl_dir)

    recovered = extractor._recover_stale_incremental_state(game_dir, "chinese")

    assert recovered == tl_dir
    assert tl_dir.is_dir()
    assert (tl_dir / "kept.rpy").read_text(encoding="utf-8") == "kept translation"
    assert not extractor._incremental_journal_path(game_dir, "chinese").exists()
    assert not temp_dir.exists()


def test_regular_extract_restores_tl_on_failure(tmp_path, monkeypatch):
    game_dir = tmp_path / "fictional_game"
    tl_dir = game_dir / "game" / "tl" / "chinese"
    tl_dir.mkdir(parents=True)
    (tl_dir / "old.rpy").write_text(
        "translate chinese strings:\n\n"
        '    old "Old entry."\n'
        '    new "旧条目。"\n',
        encoding="utf-8",
    )
    extractor = UnifiedExtractor.__new__(UnifiedExtractor)
    extractor.logger = type(
        "TestLogger",
        (),
        {
            "info": lambda self, message: None,
            "warning": lambda self, message: None,
            "error": lambda self, message: None,
        },
    )()
    extractor.renpy_extractor = type("E", (), {})()
    extractor._emit_progress = lambda message, percent: None

    # 官方/自定义抽取之后，后处理强制失败。
    def fail(*args, **kwargs):
        raise RuntimeError("simulated post-process failure")

    monkeypatch.setattr(extractor, "_post_process", fail)

    class FakeConfig:
        def __init__(self):
            self.extract_use_official = True
            self.extract_use_custom = True
            self.onekey_inject_base_box = False

        def load(self):
            return self

    monkeypatch.setattr("module.Extract.UnifiedExtractor.Config", FakeConfig)
    monkeypatch.setattr(
        "module.Extract.UnifiedExtractor.rx.ExtractAllFilesInDir",
        lambda *args, **kwargs: None,
    )
    extractor._append_static_supplement_entries = lambda *args, **kwargs: 0
    extractor._append_compiled_supplement_entries = lambda *args, **kwargs: 0

    result = extractor.extract_regular(game_dir, "chinese", exe_path=None, use_official=False)

    assert result.success is False
    assert "已自动恢复原翻译目录" in result.message
    assert (tl_dir / "old.rpy").read_text(encoding="utf-8").startswith(
        "translate chinese strings:"
    )
