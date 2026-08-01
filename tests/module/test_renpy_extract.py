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
import py_compile
import re
import sys
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


def test_incremental_retranslates_block_repaired_from_anchored_source(tmp_path, monkeypatch):
    project = tmp_path / "fictional_project"
    source = project / "game" / "src" / "plot" / "signal.rpy"
    tl_dir = project / "game" / "tl" / "chinese"
    tl = tl_dir / "src" / "plot" / "signal.rpy"
    source.parent.mkdir(parents=True)
    tl.parent.mkdir(parents=True)
    source.write_text('guide "The fictional signal is bright."\n', encoding="utf-8")
    tl.write_text(
        '# game/src/plot/signal.rpy:1\n'
        'translate chinese signal_report_12345678:\n\n'
        '    # guide "The fictional signal is dim."\n'
        '    guide "旧的虚构信号译文。"\n',
        encoding="utf-8",
    )

    config = types.SimpleNamespace(
        extract_use_official=False,
        extract_use_custom=True,
        renpy_incremental_include_untranslated=False,
        onekey_inject_base_box=False,
    )
    monkeypatch.setattr("module.Extract.UnifiedExtractor.Config.load", lambda _self: config)

    def write_fresh_extract(output_dir, *_args, **_kwargs):
        fresh = Path(output_dir) / "src" / "plot" / "signal.rpy"
        fresh.parent.mkdir(parents=True, exist_ok=True)
        fresh.write_text(
            '# game/src/plot/signal.rpy:1\n'
            'translate chinese signal_report_12345678:\n\n'
            '    # guide "The fictional signal is bright."\n'
            '    guide "The fictional signal is bright."\n\n'
            'translate chinese strings:\n\n'
            '    old "The fictional signal is bright."\n'
            '    new "The fictional signal is bright."\n',
            encoding="utf-8",
        )

    monkeypatch.setattr(
        "module.Extract.UnifiedExtractor.rx.ExtractAllFilesInDir",
        write_fresh_extract,
    )
    monkeypatch.setattr(
        UnifiedExtractor,
        "_append_static_supplement_entries",
        lambda *_args, **_kwargs: 0,
    )
    monkeypatch.setattr(
        UnifiedExtractor,
        "_post_process",
        lambda *_args, **_kwargs: None,
    )

    result = UnifiedExtractor().extract_incremental(
        project,
        "chinese",
        use_official=False,
        output_to_separate_folder=True,
    )

    assert result.success is True
    assert result.new_strings == 1
    incremental = project / "game" / "tl" / "chinese_new" / "src" / "plot" / "signal.rpy"
    assert 'guide "The fictional signal is bright."' in incremental.read_text(
        encoding="utf-8"
    )
    assert "translate chinese strings:" not in incremental.read_text(encoding="utf-8")


def test_incremental_does_not_reextract_base_box_or_structural_placeholder(
    tmp_path, monkeypatch
):
    project = tmp_path / "fictional_ui_project"
    source = project / "game" / "src" / "menu.rpy"
    source_registered = project / "game" / "source_registered.rpy"
    tl_dir = project / "game" / "tl" / "chinese"
    base = tl_dir / "base_box" / "screens_box.rpy"
    prop = tl_dir / "res" / "meta" / "prop.rpy"
    source.parent.mkdir(parents=True)
    base.parent.mkdir(parents=True)
    prop.parent.mkdir(parents=True)
    source.write_text('_(("Window"))\n_(("USB"))\n', encoding="utf-8")
    source_registered.write_text(
        'translate chinese strings:\n\n'
        '    old "Source UI"\n    new "源码界面"\n',
        encoding="utf-8",
    )
    base.write_text(
        'translate chinese strings:\n\n    old "Window"\n    new "窗口"\n',
        encoding="utf-8",
    )
    prop.write_text(
        'translate chinese strings:\n\n    old "USB"\n    new "USB"\n',
        encoding="utf-8",
    )
    config = types.SimpleNamespace(
        extract_use_official=False,
        extract_use_custom=True,
        renpy_incremental_include_untranslated=True,
        onekey_inject_base_box=False,
    )
    monkeypatch.setattr("module.Extract.UnifiedExtractor.Config.load", lambda _self: config)

    def write_fresh_extract(output_dir, *_args, **_kwargs):
        fresh = Path(output_dir) / "src" / "menu.rpy"
        fresh.parent.mkdir(parents=True, exist_ok=True)
        fresh.write_text(
            'translate chinese strings:\n\n'
            '    old "Window"\n    new "Window"\n\n'
            '    old "USB"\n    new "USB"\n\n'
            '    old "Source UI"\n    new "Source UI"\n',
            encoding="utf-8",
        )

    monkeypatch.setattr(
        "module.Extract.UnifiedExtractor.rx.ExtractAllFilesInDir",
        write_fresh_extract,
    )
    monkeypatch.setattr(
        UnifiedExtractor,
        "_append_static_supplement_entries",
        lambda *_args, **_kwargs: 0,
    )
    monkeypatch.setattr(UnifiedExtractor, "_post_process", lambda *_args, **_kwargs: None)

    result = UnifiedExtractor().extract_incremental(
        project,
        "chinese",
        use_official=False,
        output_to_separate_folder=True,
    )

    assert result.success is True
    assert result.new_strings == 0
    incremental = project / "game" / "tl" / "chinese_new"
    assert not list(incremental.rglob("*.rpy"))


def test_direct_incremental_does_not_restore_stale_translation_after_comment_repair(
    tmp_path, monkeypatch
):
    project = tmp_path / "fictional_direct_project"
    source = project / "game" / "src" / "plot" / "beacon.rpy"
    tl_dir = project / "game" / "tl" / "chinese"
    tl = tl_dir / "src" / "plot" / "beacon.rpy"
    source.parent.mkdir(parents=True)
    tl.parent.mkdir(parents=True)
    source.write_text('pilot "The fictional beacon is blue."\n', encoding="utf-8")
    tl.write_text(
        '# game/src/plot/beacon.rpy:1\n'
        'translate chinese beacon_report_12345678:\n\n'
        '    # pilot "The fictional beacon is red."\n'
        '    pilot "旧的虚构信标译文。"\n',
        encoding="utf-8",
    )

    config = types.SimpleNamespace(
        extract_use_official=False,
        extract_use_custom=True,
        renpy_incremental_include_untranslated=False,
        onekey_inject_base_box=False,
    )
    monkeypatch.setattr("module.Extract.UnifiedExtractor.Config.load", lambda _self: config)

    def write_fresh_extract(output_dir, *_args, **_kwargs):
        fresh = Path(output_dir) / "src" / "plot" / "beacon.rpy"
        fresh.parent.mkdir(parents=True, exist_ok=True)
        fresh.write_text(
            '# game/src/plot/beacon.rpy:1\n'
            'translate chinese beacon_report_12345678:\n\n'
            '    # pilot "The fictional beacon is blue."\n'
            '    pilot "The fictional beacon is blue."\n',
            encoding="utf-8",
        )

    monkeypatch.setattr(
        "module.Extract.UnifiedExtractor.rx.ExtractAllFilesInDir",
        write_fresh_extract,
    )
    monkeypatch.setattr(
        UnifiedExtractor,
        "_append_static_supplement_entries",
        lambda *_args, **_kwargs: 0,
    )
    monkeypatch.setattr(UnifiedExtractor, "_post_process", lambda *_args, **_kwargs: None)

    result = UnifiedExtractor().extract_incremental(
        project,
        "chinese",
        use_official=False,
        output_to_separate_folder=False,
    )

    content = tl.read_text(encoding="utf-8")
    assert result.success is True
    assert result.new_strings == 1
    assert 'pilot "The fictional beacon is blue."' in content
    assert "旧的虚构信标译文。" not in content


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
    config = types.SimpleNamespace(
        input_folder="old-input",
        output_folder="old-output",
        renpy_source_translate=True,
        renpy_hook_translate=True,
    )

    apply_target, output = configure_incremental_translation_paths(
        config, project, "chinese", delta
    )

    assert Path(config.input_folder) == delta
    assert Path(config.output_folder) == project / "RenpyBox_Translation" / "chinese_new"
    assert config.renpy_source_translate is False
    assert config.renpy_hook_translate is False
    assert output == Path(config.output_folder)
    assert apply_target == project / "game" / "tl" / "chinese"

    resolved_output, resolved_target = resolve_translation_apply_paths(
        config, output, apply_target
    )
    assert resolved_output == output
    assert resolved_target == apply_target

    config.renpy_source_translate = True
    config.renpy_hook_translate = True
    main_input, main_output = configure_main_translation_paths(config, project, "chinese")
    assert Path(config.input_folder) == main_input == apply_target
    assert Path(config.output_folder) == main_output
    assert main_output == project / "RenpyBox_Translation" / "chinese"
    assert config.renpy_source_translate is False
    assert config.renpy_hook_translate is False


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


def test_onekey_character_scan_persists_project_candidates(tmp_path, monkeypatch):
    from frontend.RenpyToolbox.OneKeyTranslatePage import YiJianFanyiPage
    from module.Config import Config
    from module.Engine.Translator.ProjectAssetsRepository import ProjectAssetsRepository

    project = tmp_path / "project"
    game_dir = project / "game"
    game_dir.mkdir(parents=True)
    (game_dir / "script.rpy").write_text(
        'define alice = Character("Alice")\n'
        'alice "Hello there."\n',
        encoding="utf-8",
    )
    output_dir = project / "RenpyBox_Translation" / "chinese"
    config = types.SimpleNamespace(
        input_folder = str(game_dir / "tl" / "chinese"),
        output_folder = str(output_dir),
        cache_use_sqlite = False,
        renpy_project_path = str(project),
        renpy_game_folder = str(game_dir),
        renpy_tl_folder = str(game_dir / "tl" / "chinese"),
        glossary_data = [],
        glossary_enable = False,
        text_preserve_data = [],
        text_preserve_enable = False,
        glossary_auto_scan_cache = {},
    )
    config.save = lambda: None
    monkeypatch.setattr(Config, "load", lambda self: config)

    page = YiJianFanyiPage.__new__(YiJianFanyiPage)
    page.game_dir = str(project)
    page.tl_folder_edit = types.SimpleNamespace(text = lambda: "chinese")

    page._extract_character_names(force = True)

    assert config.glossary_data == []
    state = ProjectAssetsRepository(
        str(output_dir),
        cache_use_sqlite = False,
    ).load(config)
    assert any(
        item.get("source") == "Alice"
        for item in state.analysis_candidates.get("items", [])
    )
    assert any(
        item.get("name") == "Alice"
        for item in state.analysis_candidates.get("character_drafts", [])
    )


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


def test_onekey_defers_auto_hook_until_full_output_is_applied(
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
    page._incremental_output_dir = None
    page._start_auto_hook_supplement = lambda: None

    page._on_translation_done(None, {"success": True})

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


def test_incremental_cleanup_removes_comment_only_artifacts(tmp_path):
    incremental = tmp_path / "chinese_new"
    empty = incremental / "src" / "plot" / "empty.rpy"
    valid = incremental / "src" / "plot" / "valid.rpy"
    empty.parent.mkdir(parents=True)
    empty.write_text("# 增量抽取 - 虚拟内容\n# 来源: empty.rpy\n", encoding="utf-8")
    valid.write_text(
        'translate chinese strings:\n\n'
        '    old "Fictional option"\n    new "虚拟选项"\n',
        encoding="utf-8",
    )
    extractor = UnifiedExtractor.__new__(UnifiedExtractor)
    extractor.logger = types.SimpleNamespace(warning=lambda *args, **kwargs: None)

    removed = extractor._remove_empty_incremental_artifacts(incremental)

    assert removed == 1
    assert not empty.exists()
    assert valid.exists()


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


def test_incremental_merge_keeps_literal_backslash_quote_distinct(tmp_path):
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
    assert content.count('old "- Training Bot') == 2
    assert '\\\\\\"Copper Finch' in content


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


def test_static_candidates_reject_atl_image_tags(tmp_path):
    project = tmp_path / "project"
    source = project / "game" / "res" / "art" / "mono.rpy"
    source.parent.mkdir(parents=True)
    source.write_text(
        "image mono sample:\n"
        "    contains:\n"
        "        'character pose frame'\n"
        "    side 'tl t l c':\n"
        "    show text 'Visible overlay text'\n",
        encoding="utf-8",
    )

    candidates = rx.collect_static_source_strings(project)

    assert "character pose frame" not in candidates
    assert "tl t l c" not in candidates
    assert candidates["Visible overlay text"] == "res/art/mono.rpy"


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
        "_collect_glossary_candidate_sets",
        lambda *args, **kwargs: ({text}, set(), 0),
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


def test_hook_name_discovery_ignores_compiled_only_identifiers(tmp_path, monkeypatch):
    from module.Extract import ReplaceGenerator as generator

    game = tmp_path / "game"
    game.mkdir()
    seen = []
    monkeypatch.setattr(
        generator,
        "_collect_glossary_candidate_sets",
        lambda *args, **kwargs: (
            {"Captain Rowan"},
            {"WidgetEngine", "Crew Roster"},
            3,
        ),
    )
    monkeypatch.setattr(generator, "_get_tl_covered_strings", lambda *args: set())
    monkeypatch.setattr(generator, "_load_glossary_map", lambda: {})
    monkeypatch.setattr(
        generator,
        "_detect_missing_character_names",
        lambda items: seen.append(set(items)) or set(),
    )

    entries, stats = generator.collect_hook_translation_entries(
        game,
        "chinese",
        write_manifest=False,
        auto_update_glossary=False,
    )

    assert {entry["src"] for entry in entries} == {
        "Captain Rowan",
        "WidgetEngine",
        "Crew Roster",
    }
    assert seen == [{"Captain Rowan"}]
    assert stats["rpy_candidate_count"] == 1
    assert stats["compiled_candidate_count"] == 2
    assert stats["filtered_technical_count"] == 3


def test_hook_filter_keeps_readable_text_with_dynamic_placeholders():
    from module.Extract import ReplaceGenerator as generator

    candidates = {
        "Rank: [pilot.rank]",
        "[crew.navigator]'s route continues in the next chapter.",
        "The expedition will return in a future release.",
        "Narrative.",
        "Midday (debut).",
        "[crew.navigator]",
    }

    assert generator._filter_valid_strings(candidates) == {
        "Rank: [pilot.rank]",
        "[crew.navigator]'s route continues in the next chapter.",
        "The expedition will return in a future release.",
        "Narrative.",
        "Midday (debut).",
    }


def test_compiled_string_scan_uses_constants_without_executing_module(tmp_path):
    from module.Extract import ReplaceGenerator as generator

    game = tmp_path / "game"
    saga = game / "saga"
    saga.mkdir(parents=True)
    marker = tmp_path / "module-was-executed.txt"
    source = saga / "chapter.py"
    source.write_text(
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('unexpected')\n"
        "HEADING = 'Crew Roster'\n"
        "NOTICE = \"[crew.scout]'s expedition continues in a future release.\"\n",
        encoding="utf-8",
    )
    compiled = saga / "chapter.pyc"
    py_compile.compile(str(source), cfile=str(compiled), doraise=True)
    source.unlink()

    strings = generator._extract_compiled_python_strings(
        game,
        python_executable=sys.executable,
    )

    assert "Crew Roster" in strings
    assert "[crew.scout]'s expedition continues in a future release." in strings
    assert not marker.exists()


def test_compiled_string_scan_cache_invalidates_when_bytecode_changes(tmp_path):
    from module.Extract import ReplaceGenerator as generator

    game = tmp_path / "game"
    saga = game / "saga"
    saga.mkdir(parents=True)
    source = saga / "notice.py"
    compiled = saga / "notice.pyc"
    cache = tmp_path / "compiled-cache.json"

    source.write_text("LABEL = 'Observatory Deck'\n", encoding="utf-8")
    py_compile.compile(str(source), cfile=str(compiled), doraise=True)
    first = generator._extract_compiled_python_strings(
        game,
        cache_path=cache,
        python_executable=sys.executable,
    )

    source.write_text("LABEL = 'Navigation Gallery'\n", encoding="utf-8")
    py_compile.compile(str(source), cfile=str(compiled), doraise=True)
    second = generator._extract_compiled_python_strings(
        game,
        cache_path=cache,
        python_executable=sys.executable,
    )

    assert "Observatory Deck" in first
    assert "Navigation Gallery" in second


def test_compiled_scan_skips_import_names_but_keeps_data_tuples(tmp_path):
    from module.Extract import ReplaceGenerator as generator

    game = tmp_path / "game"
    saga = game / "saga"
    saga.mkdir(parents=True)
    source = saga / "schedule.py"
    source.write_text(
        "from imaginary_widgets import Widget, Renderable\n"
        "TIMES = ('Morning Watch', 'Evening Watch')\n",
        encoding="utf-8",
    )
    compiled = saga / "schedule.pyc"
    py_compile.compile(str(source), cfile=str(compiled), doraise=True)
    source.unlink()

    strings = generator._extract_compiled_python_strings(
        game,
        python_executable=sys.executable,
    )

    assert {"Morning Watch", "Evening Watch"} <= strings
    assert "Widget" not in strings
    assert "Renderable" not in strings


def test_compiled_scan_skips_class_metadata_but_keeps_class_ui_text(tmp_path):
    from module.Extract import ReplaceGenerator as generator

    game = tmp_path / "game"
    saga = game / "saga"
    saga.mkdir(parents=True)
    source = saga / "panel.py"
    source.write_text(
        "class TelescopePanel:\n"
        "    HEADING = 'Observation Schedule'\n",
        encoding="utf-8",
    )
    compiled = saga / "panel.pyc"
    py_compile.compile(str(source), cfile=str(compiled), doraise=True)
    source.unlink()

    strings = generator._extract_compiled_python_strings(
        game,
        python_executable=sys.executable,
    )

    assert "TelescopePanel" not in strings
    assert "Observation Schedule" in strings


def test_compiled_technical_filter_rejects_code_but_keeps_ui_text():
    from module.Extract import ReplaceGenerator as generator

    candidates = {
        "uniform sampler2D starlight;",
        "void paint(vec2 uv) {\n    gl_FragColor = texture2D(starlight, uv);\n}",
        '<polygon fill="#fff" /></svg>',
        "v_tex_coord = a_tex_coord;",
        "const float samples = 10.;",
        "107 to 215",
        '".*", line \\d+',
        ", subpixel=True)",
        "C+",
        'viewBox="0 0 32 32"',
        "CAMslut <stats@camslut.dc>",
        "Invalid listener",
        "zip() argument 2 is shorter than argument 1",
        "xoffset yoffset rotate xzoom zoom",
        "<PPV:",
        "The observatory story will return in a future release.",
        "Crew Roster",
    }

    assert {
        text for text in candidates if not generator._is_compiled_technical_text(text)
    } == {
        "The observatory story will return in a future release.",
        "Crew Roster",
    }


def test_valid_string_filter_skips_save_page_markers():
    from module.Extract.ReplaceGenerator import _filter_valid_strings

    assert _filter_valid_strings({"A{#auto_page}", "Q{#quick_page}", "Save"}) == {
        "Save"
    }


def test_candidate_sets_drop_compiled_only_identifiers_but_keep_source_ui(tmp_path, monkeypatch):
    from module.Extract import ReplaceGenerator as generator

    game = tmp_path / "game"
    game.mkdir()
    monkeypatch.setattr(
        generator,
        "_extract_all_strings_regex",
        lambda *args, **kwargs: {"Back", "Audio", "Age: [who.age]"},
    )
    monkeypatch.setattr(
        generator,
        "_extract_compiled_python_strings",
        lambda *args, **kwargs: {
            "Back",
            "Audio",
            "Age: [who.age]",
            "Angelica",
            "Arousable",
            "const float samples = 10.;",
            "C+",
        },
    )

    rpy_candidates, compiled_candidates, technical = (
        generator._collect_glossary_candidate_sets(game, tl_name="chinese")
    )

    assert rpy_candidates == {"Back", "Audio", "Age: [who.age]"}
    # Source-present UI and dynamic labels stay; bytecode-only identifiers,
    # shader constants and grade marks are dropped.
    assert compiled_candidates == {"Back", "Audio", "Age: [who.age]"}
    assert technical == 4


def test_tl_coverage_includes_builtin_ui_pack(tmp_path):
    from module.Extract.ReplaceGenerator import _get_tl_covered_strings

    game = tmp_path / "game"
    base_box = game / "tl" / "chinese" / "base_box"
    base_box.mkdir(parents=True)
    (base_box / "common_box.rpy").write_text(
        "translate chinese strings:\n"
        '    old "font size"\n'
        '    new "字体大小"\n'
        "\n"
        '    old "Audio"\n'
        '    new "音频"\n',
        encoding="utf-8",
    )

    covered = _get_tl_covered_strings(game, "chinese")

    assert "font size" in covered
    assert "Audio" in covered


def test_uncovered_filter_treats_trimmed_and_fragment_chunks_as_covered():
    from module.Extract.ReplaceGenerator import _filter_uncovered_candidates

    covered = {
        "Go away... ",
        "your bank!\n\n",
        (
            "Adds outlines around buttons making them easier to spot at the "
            "expense of visuals.\n\nTurn this off to have a more pleasant viewing"
        ),
        "Audio Filename:",
    }
    candidates = {
        "Go away...",
        "your bank!",
        "Turn this off to have a more pleasant viewing",
        "Audio",
        "Dance.",
        "Age: [who.age]",
    }

    uncovered = _filter_uncovered_candidates(candidates, covered)

    assert uncovered == {"Audio", "Dance.", "Age: [who.age]"}


def test_replace_rule_preserves_interpolated_values():
    from module.Extract import ReplaceGenerator as generator

    rule = generator._build_interpolated_replace_rule(
        "[crew.scout] reached Rank [profile.rank].",
        "[crew.scout]已达到[profile.rank]级。",
    )

    assert rule is not None
    pattern, replacement = rule
    assert re.sub(pattern, replacement, "Nova reached Rank 7.") == "Nova已达到7级。"


def test_replace_rule_consumes_interpolation_at_end_of_source():
    from module.Extract import ReplaceGenerator as generator

    rule = generator._build_interpolated_replace_rule(
        "Level: [level]",
        "[level] ranks",
    )

    assert rule is not None
    pattern, replacement = rule
    assert re.sub(pattern, replacement, "Level: 27") == "27 ranks"


def test_replace_scan_collects_dynamic_label_text(tmp_path):
    from module.Extract import ReplaceGenerator as generator

    game = tmp_path / "game"
    source = game / "src" / "gui" / "profile.rpy"
    source.parent.mkdir(parents=True)
    source.write_text("screen profile(who):\n    label 'Rank: [who.rank]'\n", encoding="utf-8")

    strings = generator._extract_all_strings_regex(game)

    assert "Rank: [who.rank]" in strings


def test_static_scan_routes_screen_label_literal_to_standard_tl(tmp_path):
    game = tmp_path / "game"
    source = game / "src" / "gui" / "profile.rpy"
    source.parent.mkdir(parents=True)
    source.write_text(
        "screen profile(who):\n"
        "    label 'Rank: [who.rank]'\n"
        "\n"
        "label internal_route(default_name='debug_value'):\n"
        "    return\n",
        encoding="utf-8",
    )

    strings = rx.collect_static_source_strings(tmp_path)

    assert strings["Rank: [who.rank]"] == "src/gui/profile.rpy"
    assert "debug_value" not in strings

    extractor = UnifiedExtractor.__new__(UnifiedExtractor)
    extractor.logger = types.SimpleNamespace(info=lambda *args, **kwargs: None)
    tl_dir = tmp_path / "generated" / "game" / "tl" / "chinese"
    assert extractor._append_static_supplement_entries(
        tmp_path, tl_dir, "chinese", candidates=strings
    ) == 1
    output = (tl_dir / "src" / "gui" / "profile.rpy").read_text(encoding="utf-8")
    assert 'old "Rank: [who.rank]"' in output
    assert 'new "Rank: [who.rank]"' in output


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


def test_compiled_supplement_entries_written_natively_unique(tmp_path):
    from module.Extract.UnifiedExtractor import UnifiedExtractor

    extractor = UnifiedExtractor.__new__(UnifiedExtractor)
    extractor.logger = types.SimpleNamespace(
        info=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
        debug=lambda *args, **kwargs: None,
    )
    game = tmp_path / "game"
    game.mkdir()
    tl_dir = tmp_path / "tl" / "chinese"
    tl_dir.mkdir(parents=True)

    candidates = {
        "Virtual (first-time).",
        "Another virtual notice.",
        "Dummy label.",
    }
    added = extractor._append_compiled_supplement_entries(
        game, tl_dir, "chinese", candidates=candidates
    )

    assert added == 3
    output = tl_dir / "zz_renpybox_compiled_strings.rpy"
    content = output.read_text(encoding="utf-8")
    assert 'old "Virtual (first-time)."' in content
    assert content.count('old "Virtual (first-time)."') == 1

    # 再次运行只补新增，绝不重复写入已有 old。
    added2 = extractor._append_compiled_supplement_entries(
        game,
        tl_dir,
        "chinese",
        candidates=candidates | {"Second run only."},
    )
    assert added2 == 1
    content2 = output.read_text(encoding="utf-8")
    assert content2.count('old "Virtual (first-time)."') == 1
    assert 'old "Second run only."' in content2


def test_compiled_supplement_flows_into_incremental_folder(tmp_path):
    from module.Extract.UnifiedExtractor import UnifiedExtractor

    extractor = UnifiedExtractor.__new__(UnifiedExtractor)
    extractor.logger = types.SimpleNamespace(
        info=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
        debug=lambda *args, **kwargs: None,
    )
    game = tmp_path / "game"
    game.mkdir()
    tl_dir = tmp_path / "_temp" / "game" / "tl" / "chinese"

    candidates = {"Virtual (first-time)."}
    extractor._append_compiled_supplement_entries(
        game, tl_dir, "chinese", candidates=candidates
    )
    incremental_dir = tmp_path / "game" / "tl" / "chinese_new"
    extractor._extract_new_entries_to_folder(
        tl_dir, incremental_dir, candidates, "chinese"
    )

    output = incremental_dir / "zz_renpybox_compiled_strings.rpy"
    assert output.exists()
    content = output.read_text(encoding="utf-8")
    assert 'translate chinese strings:' in content
    assert 'old "Virtual (first-time)."' in content
    assert 'new "Virtual (first-time)."' in content


def test_incremental_selection_keeps_compiled_candidates(tmp_path):
    from module.Extract.UnifiedExtractor import UnifiedExtractor

    extractor = UnifiedExtractor.__new__(UnifiedExtractor)
    selected = extractor._select_incremental_originals(
        extracted_originals=set(),
        existing_string_originals={"Old covered entry."},
        block_originals=set(),
        static_candidates={},
        tl_dir=tmp_path,
        trusted_originals=set(),
        compiled_candidates={"Virtual (first-time).", "Old covered entry."},
    )

    assert selected == {"Virtual (first-time)."}


def test_dedupe_string_translations_removes_cross_file_duplicate_old(tmp_path):
    from module.Extract.ReplaceGenerator import dedupe_string_translations

    tl = tmp_path / "tl" / "chinese"
    first = tl / "a.rpy"
    second = tl / "b.rpy"
    work = tl / "miss" / "miss_ready_replace.rpy"
    first.parent.mkdir(parents=True)
    work.parent.mkdir(parents=True)
    first.write_text(
        "translate chinese strings:\n\n"
        '    old "Virtual (first-time)."\n'
        '    new "虚拟译文A。"\n',
        encoding="utf-8",
    )
    second.write_text(
        "translate chinese strings:\n\n"
        '    old "Virtual (first-time)."\n'
        '    new "虚拟译文B。"\n',
        encoding="utf-8",
    )
    work.write_text(
        "translate chinese strings:\n\n"
        '    old "Virtual (first-time)."\n'
        '    new "虚拟译文C。"\n',
        encoding="utf-8",
    )

    removed = dedupe_string_translations(tl, "chinese")

    assert removed == 2
    assert 'old "Virtual (first-time)."' in first.read_text(encoding="utf-8")
    assert 'old "Virtual (first-time)."' not in second.read_text(encoding="utf-8")
    assert 'old "Virtual (first-time)."' not in work.read_text(encoding="utf-8")


def test_dedupe_keeps_translated_entry_over_placeholder(tmp_path):
    from module.Extract.ReplaceGenerator import dedupe_string_translations

    tl = tmp_path / "tl" / "chinese"
    placeholder_file = tl / "a_placeholder.rpy"
    translated_file = tl / "b_translated.rpy"
    placeholder_file.parent.mkdir(parents=True)
    placeholder_file.write_text(
        "translate chinese strings:\n\n"
        '    old "Virtual dynamic message."\n'
        '    new "Virtual dynamic message."\n',
        encoding="utf-8",
    )
    translated_file.write_text(
        "translate chinese strings:\n\n"
        '    old "Virtual dynamic message."\n'
        '    new "虚拟动态消息。"\n',
        encoding="utf-8",
    )

    removed = dedupe_string_translations(tl, "chinese")

    assert removed == 1
    assert 'old "Virtual dynamic message."' not in placeholder_file.read_text(encoding="utf-8")
    assert 'old "Virtual dynamic message."' in translated_file.read_text(encoding="utf-8")


def test_dedupe_preserves_unique_entries(tmp_path):
    from module.Extract.ReplaceGenerator import dedupe_string_translations

    tl = tmp_path / "tl" / "chinese"
    first = tl / "a.rpy"
    second = tl / "b.rpy"
    first.parent.mkdir(parents=True)
    first.write_text(
        "translate chinese strings:\n\n"
        '    old "Virtual unique A."\n'
        '    new "虚拟唯一A。"\n',
        encoding="utf-8",
    )
    second.write_text(
        "translate chinese strings:\n\n"
        '    old "Virtual unique B."\n'
        '    new "虚拟唯一B。"\n',
        encoding="utf-8",
    )

    removed = dedupe_string_translations(tl, "chinese")

    assert removed == 0
    assert 'old "Virtual unique A."' in first.read_text(encoding="utf-8")
    assert 'old "Virtual unique B."' in second.read_text(encoding="utf-8")


def test_hook_skips_compiled_strings_written_natively(tmp_path, monkeypatch):
    from module.Extract import ReplaceGenerator as generator

    game = tmp_path / "game"
    tl_file = (
        game
        / "tl"
        / "chinese"
        / "zz_renpybox_compiled_strings.rpy"
    )
    tl_file.parent.mkdir(parents=True)
    tl_file.write_text(
        "translate chinese strings:\n\n"
        '    old "Virtual (first-time)."\n'
        '    new "虚拟首次。"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        generator,
        "_collect_glossary_candidate_sets",
        lambda *args, **kwargs: (set(), {"Virtual (first-time)."}, 0),
    )
    monkeypatch.setattr(generator, "_load_glossary_map", lambda: {})
    monkeypatch.setattr(generator, "_detect_missing_character_names", lambda items: set())

    entries, stats = generator.collect_hook_translation_entries(
        game,
        "chinese",
        write_manifest=False,
        auto_update_glossary=False,
    )

    assert entries == []
    assert stats["missing_count"] == 0


def test_runtime_write_incremental_only_appends_missing(tmp_path):
    from module.Extract.RenpyExtractor import RenpyExtractor

    extractor = RenpyExtractor.__new__(RenpyExtractor)
    extractor.logger = types.SimpleNamespace(
        info=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
    )
    project = tmp_path / "project"
    tl_dir = project / "game" / "tl" / "chinese"
    tl_dir.mkdir(parents=True)
    (tl_dir / "existing.rpy").write_text(
        "translate chinese strings:\n\n"
        '    old "Already covered string."\n'
        '    new "已覆盖字符串。"\n',
        encoding="utf-8",
    )
    runtime_data = {
        "dialogues": {
            "game/script.rpy": [
                ["virtual_start", "", "Virtual dialogue line.", 1],
            ]
        },
        "strings": {
            "game/script.rpy": [
                ["Already covered string.", "已覆盖字符串。"],
                ["Virtual runtime string.", "虚拟运行时字符串。"],
            ]
        },
    }

    extractor._write_runtime_tl(
        project, "chinese", runtime_data, generate_empty=False, incremental=True
    )

    script = (tl_dir / "script.rpy").read_text(encoding="utf-8")
    assert 'translate chinese virtual_start:' in script
    assert 'old "Virtual runtime string."' in script
    assert 'old "Already covered string."' not in script
    assert (
        (tl_dir / "existing.rpy").read_text(encoding="utf-8").count(
            'old "Already covered string."'
        )
        == 1
    )
