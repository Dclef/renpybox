from module.Renpy.renpy_extract import ExtractFromFile, remove_repeat_extracted_from_tl
from module.Renpy import renpy_extract as rx
from module.Extract.ReplaceGenerator import (
    _extract_relaxed_english_line_literals,
    _try_load_regex_cache,
    filter_replace_pairs_covered_by_tl,
    render_replace_script,
)
from module.Extract.UnifiedExtractor import UnifiedExtractor
import types
from enum import Enum
from pathlib import Path


def extract_from_text(tmp_path, content: str, filter_length: int = 20) -> set[str]:
    path = tmp_path / "script.rpy"
    path.write_text(content, encoding="utf-8")
    return ExtractFromFile(str(path), True, filter_length, False, False, False)


def test_extract_from_file_keeps_short_menu_options_with_suffixes(tmp_path):
    content = '''menu:
    "Option A"(_choice='a'):
        jump label_a
    "Option B":
        pass
    "Option C" if player.money >= 20:
        jump label_c
    "Option D":
        pass
menu location_hall.choice:
    "Option E" if event.peek(choice='e', who=character):
        return event.emit(choice='e', who=character)
    "Option F":
        pass
'''

    result = extract_from_text(tmp_path, content)

    assert {"Option A", "Option B", "Option C", "Option D", "Option E", "Option F"} <= result
    assert "a" not in result
    assert "e" not in result


def test_extract_from_file_ignores_contraction_apostrophes_inside_double_quotes(tmp_path):
    content = '''"You're, ain't"
'''

    result = extract_from_text(tmp_path, content, filter_length=9999)

    assert result == set()


def test_extract_from_file_keeps_double_quoted_dialogue_with_nested_single_quotes(tmp_path):
    content = '''speaker "I've got thirty seconds to calibrate the console and prime its 'aux-power' gauge."
'''

    result = extract_from_text(tmp_path, content, filter_length=4)

    assert "I've got thirty seconds to calibrate the console and prime its 'aux-power' gauge." in result
    assert "ve got thirty seconds to calibrate the console and prime its " not in result
    assert "o-power" not in result


def test_extract_from_file_keeps_double_quoted_dialogue_with_contractions(tmp_path):
    content = '''speaker "Oh, captain... it's a triple signal!"
'''

    result = extract_from_text(tmp_path, content, filter_length=4)

    assert "Oh, captain... it's a triple signal!" in result
    assert "s a triple signal!" not in result


def test_extract_from_file_ignores_single_quoted_control_conditions(tmp_path):
    content = '''if state == 'start':
    pass
elif state == 'middle':
    pass
while state == 'loop':
    pass
if ready: 'Inline translatable text'
'''

    result = extract_from_text(tmp_path, content, filter_length=5)

    assert {"start", "middle", "loop"}.isdisjoint(result)
    assert "Inline translatable text" in result


def test_extract_from_file_keeps_single_quoted_display_text_outside_double_quotes(tmp_path):
    content = '''show text 'Single quoted display text'
'''

    result = extract_from_text(tmp_path, content, filter_length=4)

    assert "Single quoted display text" in result



def test_replace_text_relaxed_scan_ignores_apostrophes_in_dialogue():
    line = 'speaker "I\'ve got forty seconds to refill the engine and prime its \'aux-drive\' gauge."'

    result = _extract_relaxed_english_line_literals(line)

    assert "I've got forty seconds to refill the engine and prime its 'aux-drive' gauge." in result
    assert 've got forty seconds to refill the engine and prime its ' not in result
    assert 'aux-drive' not in result
    assert _extract_relaxed_english_line_literals("show text 'Standalone display text'") == {"Standalone display text"}


def test_incremental_coverage_ignores_translate_block_comments(tmp_path):
    translation_file = tmp_path / "dialogue.rpy"
    translation_file.write_text(
        'translate chinese scene_demo:\n'
        '    # narrator "I won\'t decline."\n'
        '    narrator "Already translated"\n',
        encoding="utf-8",
    )
    extractor = UnifiedExtractor.__new__(UnifiedExtractor)
    extractor.logger = types.SimpleNamespace(debug=lambda *args, **kwargs: None)

    covered = extractor._get_all_originals(tmp_path)

    assert "I will reconsider." not in covered


def test_incremental_selection_uses_blocks_for_coverage_but_keeps_menu_exception(tmp_path):
    tl_dir = tmp_path / "tl" / "chinese"
    ano = tl_dir / "src" / "plot" / "chapter_beta.rpy"
    dialogue = tl_dir / "src" / "plot" / "dialogue.rpy"
    ano.parent.mkdir(parents=True)
    ano.write_text("", encoding="utf-8")
    dialogue.write_text(
        'translate chinese scene_demo:\n\n'
        '    # narrator "Already translated dialogue."\n'
        '    narrator "已经翻译的对话。"\n\n'
        'translate chinese scene_same_text:\n\n'
        '    # narrator "I can proceed."\n'
        '    narrator "我不介意。"\n',
        encoding="utf-8",
    )

    extractor = UnifiedExtractor.__new__(UnifiedExtractor)
    extracted = {"Already translated dialogue.", "I can proceed.", "Brand new text."}
    selected = extractor._select_incremental_originals(
        extracted_originals=extracted,
        existing_string_originals=set(),
        block_originals={"Already translated dialogue.", "I can proceed."},
        static_candidates={"I can proceed.": "src/plot/chapter_beta.rpy"},
        tl_dir=tl_dir,
    )

    assert selected == {"I can proceed.", "Brand new text."}


def test_pending_strings_placeholder_survives_equal_dialogue_coverage():
    pending = {"I can proceed.", "Synthetic dialogue placeholder."}
    existing_strings = {"I can proceed."}
    block_originals = {"I can proceed.", "Synthetic dialogue placeholder."}

    pending -= block_originals - existing_strings

    assert pending == {"I can proceed."}


def test_static_supplement_accepts_official_comment_missing_closing_parenthesis(tmp_path):
    tl_dir = tmp_path / "tl" / "chinese"
    target = tl_dir / "src" / "plot" / "chapter_beta.rpy"
    target.parent.mkdir(parents=True)
    target.write_text(
        'translate chinese chapter_beta_demo:\n\n'
        '    # narrator "( The portal is finally open! "\n'
        '    narrator "（传送门终于打开了！）"\n',
        encoding="utf-8",
    )
    extractor = UnifiedExtractor.__new__(UnifiedExtractor)

    assert extractor._is_covered_by_file_block(
        "( The portal is finally open! )", {"( The portal is finally open! "}
    )


def test_cleanup_removes_truncated_comment_duplicate_but_keeps_menu_string(tmp_path):
    target = tmp_path / "chapter_beta.rpy"
    target.write_text(
        'translate chinese scene_demo:\n\n'
        '    # narrator "( The portal is finally open! "\n'
        '    narrator "（传送门终于打开了！）"\n\n'
        'translate chinese strings:\n\n'
        '    old "( The portal is finally open! )"\n'
        '    new "（传送门终于打开了！）"\n\n'
        '    old "I can proceed."\n'
        '    new "我不介意。"\n',
        encoding="utf-8",
    )
    extractor = UnifiedExtractor.__new__(UnifiedExtractor)
    extractor.logger = types.SimpleNamespace(debug=lambda *args, **kwargs: None)

    assert extractor._remove_strings_covered_by_truncated_block_comment(tmp_path) == 1
    content = target.read_text(encoding="utf-8")
    assert 'old "( The portal is finally open! )"' not in content
    assert 'old "I can proceed."' in content


def test_incremental_repairs_official_comment_from_anchored_source_line(tmp_path):
    project = tmp_path / "project"
    source = project / "game" / "src" / "plot" / "chapter_beta.rpy"
    tl = project / "game" / "tl" / "chinese" / "src" / "plot" / "chapter_beta.rpy"
    source.parent.mkdir(parents=True)
    tl.parent.mkdir(parents=True)
    source.write_text(
        'narrator "( We finally crossed the portal with [story.partner]! )"\n',
        encoding="utf-8",
    )
    tl.write_text(
        '# game/src/plot/chapter_beta.rpy:1\n'
        'translate chinese chapter_beta_demo:\n\n'
        '    # narrator "( We finally crossed the portal with [story.partner]! "\n'
        '    narrator "（我们终于穿过传送门了！）"\n',
        encoding="utf-8",
    )
    extractor = UnifiedExtractor.__new__(UnifiedExtractor)
    extractor.logger = types.SimpleNamespace(debug=lambda *args, **kwargs: None)

    assert extractor._repair_block_comments_from_source(
        project, project / "game" / "tl" / "chinese"
    ) == 1
    repaired = tl.read_text(encoding="utf-8")
    assert '# narrator "( We finally crossed the portal with [story.partner]! )"' in repaired


def test_comment_repair_does_not_cross_from_strings_entry_into_dialogue(tmp_path):
    project = tmp_path / "project"
    source = project / "game" / "src" / "plot" / "chapter_beta.rpy"
    tl = project / "game" / "tl" / "chinese" / "src" / "plot" / "chapter_beta.rpy"
    source.parent.mkdir(parents=True)
    tl.parent.mkdir(parents=True)
    source.write_text(
        'menu:\n    "Proceed.":\n        pass\n'
        'narrator "Dialogue remains unchanged."\n',
        encoding="utf-8",
    )
    tl.write_text(
        'translate chinese strings:\n\n'
        '    # game/src/plot/chapter_beta.rpy:2\n'
        '    old "Proceed."\n'
        '    new "继续。"\n\n'
        '# game/src/plot/chapter_beta.rpy:4\n'
        'translate chinese chapter_beta_demo:\n\n'
        '    # narrator "Dialogue remains unchanged."\n'
        '    narrator "对话保持不变。"\n',
        encoding="utf-8",
    )
    extractor = UnifiedExtractor.__new__(UnifiedExtractor)

    assert extractor._repair_block_comments_from_source(
        project, project / "game" / "tl" / "chinese"
    ) == 0
    content = tl.read_text(encoding="utf-8")
    assert '# narrator "Dialogue remains unchanged."' in content


def test_collect_block_originals_accepts_legacy_enum_string_form(tmp_path, monkeypatch):
    class LegacyKind(Enum):
        LABEL = "LABEL"

    translation_file = tmp_path / "dialogue.rpy"
    translation_file.write_text(
        'translate chinese scene_demo:\n\n'
        '    # narrator "Already translated dialogue."\n'
        '    narrator "已经翻译的对话。"\n',
        encoding="utf-8",
    )
    item = types.SimpleNamespace(
        get_src=lambda: "Already translated dialogue.",
        get_extra_field=lambda: {"renpy": {"block": {"kind": LegacyKind.LABEL}}},
    )

    from module.Extract import UnifiedExtractor as ux

    monkeypatch.setattr(ux, "parse_tl_document", lambda lines: object())
    monkeypatch.setattr(
        ux.RenpyTlItemExtractor,
        "extract",
        lambda self, doc, path: [item],
    )
    extractor = UnifiedExtractor.__new__(UnifiedExtractor)
    extractor.logger = types.SimpleNamespace(debug=lambda *args, **kwargs: None)

    assert extractor._collect_block_originals(tmp_path) == {"Already translated dialogue."}


def test_onekey_incremental_translation_uses_delta_but_applies_to_main_tl(tmp_path):
    from frontend.RenpyToolbox.OneKeyTranslatePage import (
        configure_incremental_translation_paths,
        configure_main_translation_paths,
        resolve_translation_apply_paths,
    )

    project = tmp_path / "project"
    delta = project / "game" / "tl" / "chinese_new"
    config = types.SimpleNamespace(input_folder="old-input", output_folder="old-output")

    apply_target, output = configure_incremental_translation_paths(
        config, project, "chinese", delta
    )

    assert Path(config.input_folder) == delta
    assert Path(config.output_folder) == project / "RenpyBox_Translation" / "chinese_new"
    assert output == Path(config.output_folder)
    assert apply_target == project / "game" / "tl" / "chinese"

    resolved_output, resolved_target = resolve_translation_apply_paths(
        config, output, apply_target
    )
    assert resolved_output == output
    assert resolved_target == apply_target

    main_input, main_output = configure_main_translation_paths(config, project, "chinese")
    assert Path(config.input_folder) == main_input == apply_target
    assert Path(config.output_folder) == main_output
    assert main_output == project / "RenpyBox_Translation" / "chinese"


def test_onekey_full_apply_ignores_stale_incremental_target(tmp_path):
    from frontend.RenpyToolbox.OneKeyTranslatePage import (
        resolve_translation_apply_paths,
    )

    current_output = tmp_path / "current-output"
    current_target = tmp_path / "current-input"
    stale_target = tmp_path / "previous-project" / "game" / "tl" / "chinese"
    config = types.SimpleNamespace(
        input_folder=str(current_target), output_folder=str(current_output)
    )

    output, target = resolve_translation_apply_paths(
        config, incremental_output=None, incremental_target=stale_target
    )

    assert output == current_output
    assert target == current_target


def test_onekey_defers_auto_hook_while_incremental_output_is_unmerged(
    tmp_path, monkeypatch
):
    from frontend.RenpyToolbox import OneKeyTranslatePage as page_module

    scheduled = []
    monkeypatch.setattr(
        page_module.QTimer,
        "singleShot",
        lambda delay, callback: scheduled.append((delay, callback)),
    )
    page = page_module.YiJianFanyiPage.__new__(page_module.YiJianFanyiPage)
    page._auto_hook_running = False
    page._onekey_translation_started = True
    page._auto_hook_pending = True
    page._incremental_output_dir = tmp_path / "translated-delta"
    page._start_auto_hook_supplement = lambda: None

    page._on_translation_done(None, None)

    assert page._auto_hook_pending is True
    assert scheduled == []


def test_replace_text_rebuilds_outdated_regex_cache(tmp_path):
    cache_path = tmp_path / "regex_extracted.json"
    cache_path.write_text(
        '{"version": 1, "file_count": 1, "max_mtime_ns": 1, "strings": ["stale fragment"]}',
        encoding="utf-8",
    )

    assert _try_load_regex_cache(cache_path, file_count=1, max_mtime_ns=1) is None


def test_incremental_merge_cleans_staging_folder_and_base_box_placeholders(tmp_path):
    game_dir = tmp_path / "project"
    tl_dir = game_dir / "game" / "tl" / "chinese"
    staging_dir = game_dir / "game" / "tl" / "chinese_new"
    base_box = tl_dir / "base_box"
    base_box.mkdir(parents=True)
    staging_dir.mkdir(parents=True)

    (base_box / "screens_box.rpy").write_text(
        'translate chinese strings:\n\n    old "Back"\n    new "\u8fd4\u56de"\n',
        encoding="utf-8",
    )
    hud = tl_dir / "src" / "gui" / "hud.rpy"
    hud.parent.mkdir(parents=True)
    hud.write_text(
        'translate chinese strings:\n\n    old "Back"\n    new "回来"\n',
        encoding="utf-8",
    )
    staging = staging_dir / "src" / "plot" / "new_text.rpy"
    staging.parent.mkdir(parents=True)
    staging.write_text(
        'translate chinese strings:\n\n    old "New menu text"\n    new "\u65b0\u83dc\u5355\u6587\u672c"\n',
        encoding="utf-8",
    )

    extractor = UnifiedExtractor.__new__(UnifiedExtractor)
    extractor.logger = types.SimpleNamespace(
        debug=lambda *args, **kwargs: None,
        info=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
    )
    result = extractor.merge_incremental_folder(game_dir, "chinese", staging_dir, clean_duplicates=True)

    assert result.success
    assert not staging_dir.exists()
    assert 'old "Back"' not in hud.read_text(encoding="utf-8")
    assert 'new "回来"' in (base_box / "screens_box.rpy").read_text(encoding="utf-8")
    assert 'old "New menu text"' in (tl_dir / "src" / "plot" / "new_text.rpy").read_text(encoding="utf-8")


def test_incremental_merge_removes_empty_block_after_truncated_duplicate(tmp_path):
    game_dir = tmp_path / "project"
    tl_dir = game_dir / "game" / "tl" / "chinese"
    staging_dir = game_dir / "game" / "tl" / "chinese_new"
    target = tl_dir / "src" / "plot" / "chapter_delta.rpy"
    staging = staging_dir / "src" / "plot" / "chapter_extra.rpy"
    target.parent.mkdir(parents=True)
    staging.parent.mkdir(parents=True)
    target.write_text(
        'translate chinese chapter_delta_demo:\n\n'
        '    # narrator "( The route is finally open! "\n'
        '    narrator "（路线终于开放了！）"\n\n'
        'translate chinese strings:\n\n'
        '    old "( The route is finally open! )"\n'
        '    new "（路线终于开放了！）"\n',
        encoding="utf-8",
    )
    staging.write_text(
        'translate chinese strings:\n\n'
        '    old "Additional route."\n'
        '    new "附加路线。"\n',
        encoding="utf-8",
    )
    extractor = UnifiedExtractor.__new__(UnifiedExtractor)
    extractor.logger = types.SimpleNamespace(
        debug=lambda *args, **kwargs: None,
        info=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
    )

    result = extractor.merge_incremental_folder(
        game_dir, "chinese", staging_dir, clean_duplicates=True
    )

    assert result.success
    content = target.read_text(encoding="utf-8")
    assert 'old "( The route is finally open! )"' not in content
    assert "translate chinese strings:" not in content


def test_incremental_merge_reuses_strings_block_and_keeps_source_location(tmp_path):
    game_dir = tmp_path / "project"
    tl_dir = game_dir / "game" / "tl" / "chinese"
    staging_dir = game_dir / "game" / "tl" / "chinese_new"
    target = tl_dir / "src" / "plot" / "chapter_beta.rpy"
    staging = staging_dir / "src" / "plot" / "chapter_beta.rpy"
    target.parent.mkdir(parents=True)
    staging.parent.mkdir(parents=True)
    target.write_text(
        'translate chinese strings:\n\n    old "Existing"\n    new "已有"\n',
        encoding="utf-8",
    )
    staging.write_text(
        'translate chinese strings:\n\n'
        '    # game/src/plot/chapter_beta.rpy:1635\n'
        '    old "I can proceed."\n'
        '    new "我不介意。"\n',
        encoding="utf-8",
    )

    extractor = UnifiedExtractor.__new__(UnifiedExtractor)
    extractor.logger = types.SimpleNamespace(
        debug=lambda *args, **kwargs: None,
        info=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
    )
    result = extractor.merge_incremental_folder(
        game_dir, "chinese", staging_dir, clean_duplicates=False
    )

    assert result.success
    content = target.read_text(encoding="utf-8")
    assert content.count("translate chinese strings:") == 1
    assert "# 增量合并" not in content
    assert "# game/src/plot/chapter_beta.rpy:1635" in content
    assert 'old "I can proceed."' in content


def test_removes_strings_already_registered_by_game_source(tmp_path):
    game_dir = tmp_path / "project"
    source = game_dir / "game" / "src" / "renpy" / "confirm.rpy"
    translated = game_dir / "game" / "tl" / "chinese" / "src" / "renpy" / "confirm.rpy"
    source.parent.mkdir(parents=True)
    translated.parent.mkdir(parents=True)
    duplicate = "To review the continued operation of this demo you can go to:"
    source.write_text(
        "translate chinese strings:\n\n"
        f'    old "{duplicate}"\n'
        '    new "源码已经注册"\n',
        encoding="utf-8",
    )
    translated.write_text(
        "translate chinese strings:\n\n"
        "    # game/src/renpy/confirm.rpy:6\n"
        f'    old "{duplicate}"\n'
        '    new "重复生成"\n\n'
        '    old "Only in TL"\n'
        '    new "只在翻译目录"\n',
        encoding="utf-8",
    )

    extractor = UnifiedExtractor.__new__(UnifiedExtractor)
    removed = extractor._remove_source_registered_string_duplicates(
        game_dir, game_dir / "game" / "tl" / "chinese", "chinese"
    )

    assert removed == 1
    content = translated.read_text(encoding="utf-8")
    assert duplicate not in content
    assert "# game/src/renpy/confirm.rpy:6" not in content
    assert 'old "Only in TL"' in content


def test_incremental_merge_canonicalizes_double_escaped_quote_duplicates(tmp_path):
    game_dir = tmp_path / "project"
    tl_dir = game_dir / "game" / "tl" / "chinese"
    staging_dir = game_dir / "game" / "tl" / "chinese_new"
    target = tl_dir / "src" / "mini" / "pc.rpy"
    staging = staging_dir / "src" / "mini" / "pc.rpy"
    target.parent.mkdir(parents=True)
    staging.parent.mkdir(parents=True)

    target.write_text(
        'translate chinese strings:\n\n'
        '    old "- Training Bot \\"Copper Finch\\""\n'
        '    new "训练机器人『铜雀』"\n',
        encoding="utf-8",
    )
    staging.write_text(
        'translate chinese strings:\n\n'
        '    old "- Training Bot \\\\\\"Copper Finch\\\\\\""\n'
        '    new "- 训练机器人 \\\\"铜雀\\\\""\n',
        encoding="utf-8",
    )

    extractor = UnifiedExtractor.__new__(UnifiedExtractor)
    extractor.logger = types.SimpleNamespace(
        debug=lambda *args, **kwargs: None,
        info=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
    )
    result = extractor.merge_incremental_folder(
        game_dir, "chinese", staging_dir, clean_duplicates=True
    )

    assert result.success
    content = target.read_text(encoding="utf-8")
    assert content.count('old "- Training Bot') == 1
    assert '\\\\\\"Copper Finch' not in content


def test_incremental_static_supplement_reaches_corresponding_tl_file(tmp_path, monkeypatch):
    project = tmp_path / "project"
    source = project / "game" / "src" / "plot" / "chapter_beta.rpy"
    source.parent.mkdir(parents=True)
    source.write_text(
        'menu:\n'
        '    "That signal is making me uneasy.":\n'
        '        pass\n'
        '    "I can proceed."(_choice=\'poly\'):\n'
        '        jump poly\n',
        encoding="utf-8",
    )

    extractor = UnifiedExtractor.__new__(UnifiedExtractor)
    extractor.logger = types.SimpleNamespace(
        info=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
        debug=lambda *args, **kwargs: None,
    )
    tl_dir = project / "_temp" / "game" / "tl" / "chinese"

    assert extractor._append_static_supplement_entries(project, tl_dir, "chinese") == 2
    output = tl_dir / "src" / "plot" / "chapter_beta.rpy"
    content = output.read_text(encoding="utf-8")
    assert 'old "I can proceed."' in content

    incremental_dir = project / "game" / "tl" / "chinese_new"
    extractor._extract_new_entries_to_folder(
        tl_dir, incremental_dir, {"I can proceed."}, "chinese"
    )
    incremental = incremental_dir / "src" / "plot" / "chapter_beta.rpy"
    assert incremental.exists()
    assert 'old "I can proceed."' in incremental.read_text(encoding="utf-8")


def test_global_dedup_keeps_menu_string_equal_to_dialogue_comment(tmp_path):
    dialogue = tmp_path / "dialogue.rpy"
    menu = tmp_path / "menu.rpy"
    dialogue.write_text(
        'translate chinese scene_demo:\n\n'
        '    # narrator "I can proceed."\n'
        '    narrator "我不介意。"\n',
        encoding="utf-8",
    )
    menu.write_text(
        'translate chinese strings:\n\n'
        '    old "I can proceed."\n'
        '    new "我不介意。"\n',
        encoding="utf-8",
    )

    remove_repeat_extracted_from_tl(str(tmp_path), is_py2=False)

    assert 'old "I can proceed."' in menu.read_text(encoding="utf-8")



def test_static_supplement_uses_first_source_file_for_duplicate_menu_text(tmp_path):
    project = tmp_path / "project"
    first_source = project / "game" / "src" / "chapter01.rpy"
    second_source = project / "game" / "src" / "chapter02.rpy"
    first_source.parent.mkdir(parents=True)
    first_source.write_text(
        "menu:\n"
        "    \"Continue route.\"(_choice='continue'):\n"
        "        pass\n",
        encoding="utf-8",
    )
    second_source.write_text(
        "menu:\n"
        "    \"Continue route.\"(_choice='continue'):\n"
        "        pass\n"
        '    narrator "Signal says \\"ready\\"."\n',
        encoding="utf-8",
    )

    candidates = rx.collect_static_source_strings(project)
    assert candidates["Continue route."] == "src/chapter01.rpy"
    assert candidates['Signal says "ready".'] == "src/chapter02.rpy"

    extractor = UnifiedExtractor.__new__(UnifiedExtractor)
    extractor.logger = types.SimpleNamespace(info=lambda *args, **kwargs: None)
    tl_dir = project / "_temp" / "game" / "tl" / "chinese"
    assert extractor._append_static_supplement_entries(project, tl_dir, "chinese") >= 1

    first_tl = tl_dir / "src" / "chapter01.rpy"
    second_tl = tl_dir / "src" / "chapter02.rpy"
    assert 'old "Continue route."' in first_tl.read_text(encoding="utf-8")
    assert 'old "Continue route."' not in second_tl.read_text(encoding="utf-8")

    dialogue_tl = tl_dir / "dialogue.rpy"
    dialogue_tl.write_text(
        'translate chinese scene_demo:\n'
        '    # narrator "Continue route."\n'
        '    narrator "Existing dialogue"\n',
        encoding="utf-8",
    )
    assert extractor._remove_string_duplicates_with_blocks(tl_dir) == 0
    assert 'old "Continue route."' in first_tl.read_text(encoding="utf-8")


def test_replace_text_relaxed_scan_matches_standard_extractor_for_control_lines():
    assert _extract_relaxed_english_line_literals("if state == 'start':") == set()
    assert _extract_relaxed_english_line_literals("if ready: 'Inline translatable text'") == {"Inline translatable text"}


def test_regular_extract_appends_static_supplement_entries(tmp_path, monkeypatch):
    project = tmp_path / "project"
    source = project / "game" / "script.rpy"
    source.parent.mkdir(parents=True)
    source.write_text(
        "label start:\n"
        "    show text 'Standalone display text'\n",
        encoding="utf-8",
    )

    from module.Extract import UnifiedExtractor as ux

    monkeypatch.setattr(
        ux.Config,
        "load",
        lambda self: types.SimpleNamespace(
            extract_use_official=False,
            extract_use_custom=True,
            onekey_inject_base_box=False,
            renpy_remove_string_duplicates=False,
            export_structured_json=False,
            export_trans_json=False,
        ),
    )
    monkeypatch.setattr(rx, "ExtractAllFilesInDir", lambda *args, **kwargs: None)

    extractor = UnifiedExtractor.__new__(UnifiedExtractor)
    extractor.logger = types.SimpleNamespace(
        info=lambda *args, **kwargs: None,
        debug=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
        error=lambda *args, **kwargs: None,
    )
    extractor.renpy_extractor = None
    extractor._progress_callback = None
    extractor._last_suspicious_manifest = None
    extractor._last_suspicious_removed_count = 0

    result = extractor.extract_regular(project, "chinese", use_official=False)

    assert result.success
    output = project / "game" / "tl" / "chinese" / "script.rpy"
    assert 'old "Standalone display text"' in output.read_text(encoding="utf-8")


def test_static_candidates_prefer_menu_location_and_keep_short_choices(tmp_path):
    project = tmp_path / "project"
    dialogue = project / "game" / "src" / "plot" / "chapter_alpha.rpy"
    menu = project / "game" / "src" / "plot" / "chapter_beta.rpy"
    dialogue.parent.mkdir(parents=True)
    dialogue.write_text('narrator "Proceed."\n', encoding="utf-8")
    menu.write_text(
        'menu:\n'
        '    "Proceed."(_choice=\'route\'):\n'
        '        pass\n'
        '    "Decline.":\n'
        '        pass\n'
        '    "Review map." if can_review:\n'
        '        pass\n',
        encoding="utf-8",
    )

    candidates = rx.collect_static_source_strings(project)

    assert candidates["Proceed."] == "src/plot/chapter_beta.rpy"
    assert candidates["Decline."] == "src/plot/chapter_beta.rpy"
    assert candidates["Review map."] == "src/plot/chapter_beta.rpy"

    target = project / "game" / "tl" / "chinese" / "src" / "plot" / "chapter_beta.rpy"
    target.parent.mkdir(parents=True)
    target.write_text(
        'translate chinese chapter_beta_dialogue:\n\n'
        '    # narrator "Proceed."\n'
        '    narrator "继续。"\n',
        encoding="utf-8",
    )
    extractor = UnifiedExtractor.__new__(UnifiedExtractor)
    extractor.logger = types.SimpleNamespace(info=lambda *args, **kwargs: None)

    added = extractor._append_static_supplement_entries(
        project, project / "game" / "tl" / "chinese", "chinese"
    )

    content = target.read_text(encoding="utf-8")
    assert added >= 2
    assert 'old "Proceed."' in content
    assert 'old "Decline."' in content


def test_static_menu_candidates_accept_single_quoted_choices(tmp_path):
    project = tmp_path / "project"
    source = project / "game" / "src" / "plot" / "chapter_gamma.rpy"
    source.parent.mkdir(parents=True)
    source.write_text(
        "menu:\n"
        "    'Proceed.':\n"
        "        pass\n"
        "    'Pilot\\'s route.' if route_ready:\n"
        "        pass\n",
        encoding="utf-8",
    )

    candidates = rx.collect_static_menu_strings(project)

    assert candidates["Proceed."] == "src/plot/chapter_gamma.rpy"
    assert candidates["Pilot's route."] == "src/plot/chapter_gamma.rpy"


def test_static_source_scan_opens_original_file_read_only(monkeypatch):
    opened_modes = []

    def fake_open(path, mode, encoding):
        opened_modes.append(mode)
        return rx.io.StringIO('label start:\n    narrator "Read only source text."\n')

    monkeypatch.setattr(rx.io, "open", fake_open)

    rx.ExtractFromFile(
        "readonly.rpy",
        is_open_filter=True,
        filter_length=4,
        is_skip_underline=False,
        is_py2=False,
        skip_translate_block=True,
        remove_duplicates=False,
    )

    assert opened_modes == ["r"]


def test_replace_hook_unwraps_previous_generated_hook_on_reload():
    script = render_replace_script([("old", "new")])

    assert 'while getattr(_renpybox_replace_text_previous, "_renpybox_auto_hook", False)' in script
    assert "_renpybox_seen_hooks" in script
    assert "if _renpybox_next_hook is _renpybox_replace_text_previous" in script
    assert "renpybox_replace_text_auto._renpybox_auto_hook = True" in script
    assert "renpybox_replace_text_auto._renpybox_previous = _renpybox_replace_text_previous" in script
    assert "_renpybox_previous=_renpybox_replace_text_previous" in script


def test_replace_hook_omits_text_now_covered_by_normal_tl(tmp_path):
    game = tmp_path / "game"
    tl_file = game / "tl" / "chinese" / "src" / "menu" / "pref.rpy"
    tl_file.parent.mkdir(parents=True)
    tl_file.write_text(
        'translate chinese strings:\n\n'
        '    old "Turn this off to have a more pleasant viewing experience."\n'
        '    new "关闭此选项可获得更愉悦的浏览体验。"\n',
        encoding="utf-8",
    )

    pairs = filter_replace_pairs_covered_by_tl(
        [("Turn this off", "关闭此选项"), ("Hook only", "仅钩子")],
        game,
        "chinese",
    )

    assert pairs == [("Hook only", "仅钩子")]


def test_replace_hook_omits_untranslated_old_placeholder(tmp_path):
    game = tmp_path / "game"
    tl_file = game / "tl" / "chinese" / "src" / "menu" / "slot.rpy"
    tl_file.parent.mkdir(parents=True)
    tl_file.write_text(
        'translate chinese strings:\n\n'
        '    old "Q{#quick_page}"\n'
        '    new "Q{#quick_page}"\n',
        encoding="utf-8",
    )

    pairs = filter_replace_pairs_covered_by_tl(
        [("Q{#quick_page}", "Q页"), ("Hook only", "仅钩子")], game, "chinese"
    )

    assert pairs == [("Hook only", "仅钩子")]


def test_replace_hook_keeps_pair_from_miss_work_file(tmp_path):
    game = tmp_path / "game"
    miss_file = game / "tl" / "chinese" / "miss" / "miss_ready_replace.rpy"
    miss_file.parent.mkdir(parents=True)
    miss_file.write_text(
        'translate chinese strings:\n\n'
        '    old "Hook only"\n'
        '    new "仅钩子"\n',
        encoding="utf-8",
    )

    pairs = filter_replace_pairs_covered_by_tl(
        [("Hook only", "仅钩子")], game, "chinese"
    )

    assert pairs == [("Hook only", "仅钩子")]


def test_hook_entries_keep_static_source_missing_from_tl(tmp_path, monkeypatch):
    from module.Extract import ReplaceGenerator as generator

    text = "Standalone display text"
    game = tmp_path / "game"
    game.mkdir()
    monkeypatch.setattr(
        generator,
        "collect_glossary_candidate_texts",
        lambda *args, **kwargs: {text},
    )
    monkeypatch.setattr(
        generator.rx,
        "collect_static_source_strings",
        lambda *args, **kwargs: {text: "script.rpy"},
    )
    monkeypatch.setattr(generator, "_get_tl_covered_strings", lambda *args: set())
    monkeypatch.setattr(generator, "_load_glossary_map", lambda: {})
    monkeypatch.setattr(generator, "_detect_missing_character_names", lambda items: set())

    entries, stats = generator.collect_hook_translation_entries(
        game,
        "chinese",
        write_manifest=False,
        auto_update_glossary=False,
    )

    assert [entry["src"] for entry in entries] == [text]
    assert stats["missing_count"] == 1


def test_menu_string_is_incremental_even_when_dialogue_block_exists(tmp_path):
    project = tmp_path / "project"
    source = project / "game" / "src" / "plot" / "chapter_beta.rpy"
    target = project / "game" / "tl" / "chinese" / "src" / "plot" / "chapter_beta.rpy"
    source.parent.mkdir(parents=True)
    target.parent.mkdir(parents=True)
    source.write_text('menu:\n    "Proceed.":\n        pass\n', encoding="utf-8")
    target.write_text(
        'translate chinese chapter_beta_dialogue:\n\n'
        '    # narrator "Proceed."\n'
        '    narrator "继续。"\n',
        encoding="utf-8",
    )
    extractor = UnifiedExtractor.__new__(UnifiedExtractor)

    selected = extractor._select_incremental_originals(
        {"Proceed."}, set(), {"Proceed."},
        {"Proceed.": "src/plot/chapter_beta.rpy"},
        project / "game" / "tl" / "chinese",
    )

    assert selected == {"Proceed."}


def test_incremental_menu_string_uses_real_menu_file_and_line(tmp_path):
    project = tmp_path / "project"
    source_chapter_alpha = project / "game" / "src" / "plot" / "chapter_alpha.rpy"
    source_chapter_beta = project / "game" / "src" / "plot" / "chapter_beta.rpy"
    extracted = project / "temp" / "src" / "plot" / "chapter_alpha.rpy"
    target = project / "game" / "tl" / "chinese_new"
    source_chapter_alpha.parent.mkdir(parents=True)
    extracted.parent.mkdir(parents=True)
    source_chapter_alpha.write_text('narrator "Proceed."\n', encoding="utf-8")
    source_chapter_beta.write_text(
        'narrator "Proceed."\nmenu:\n    "Proceed."(_choice="route"):\n        pass\n',
        encoding="utf-8",
    )
    extracted.write_text(
        'translate chinese chapter_alpha_dialogue:\n\n'
        '    # narrator "Proceed."\n'
        '    narrator "Proceed."\n\n'
        'translate chinese strings:\n\n'
        '    old "Proceed."\n'
        '    new "Proceed."\n',
        encoding="utf-8",
    )
    extractor = UnifiedExtractor.__new__(UnifiedExtractor)
    extractor.logger = types.SimpleNamespace(warning=lambda *args, **kwargs: None)

    extractor._extract_new_entries_to_folder(
        project / "temp", target, {"Proceed."}, "chinese", project
    )

    assert not (target / "src" / "plot" / "chapter_alpha.rpy").exists()
    content = (target / "src" / "plot" / "chapter_beta.rpy").read_text(encoding="utf-8")
    assert content.count('old "Proceed."') == 1
    assert "# game/src/plot/chapter_beta.rpy:3" in content
