from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import pytest

from module.Extract.UnifiedExtractor import UnifiedExtractor
from module.Renpy import renpy_extract as rx
from module.Renpy.renpy_tl_core import escape_tl_string


def config_for_extraction(monkeypatch, *, official=True, custom=True):
    config = SimpleNamespace(
        extract_use_official=official,
        extract_use_custom=custom,
        text_preserve_enable=False,
        onekey_inject_base_box=False,
        renpy_incremental_include_untranslated=False,
    )
    monkeypatch.setattr("module.Extract.UnifiedExtractor.Config.load", lambda _self: config)
    monkeypatch.setattr(rx, "is_python2_from_game_dir", lambda _path: False)
    monkeypatch.setattr(UnifiedExtractor, "_post_process", lambda *_args: None)
    return config


def test_supplement_skips_only_dialogue_occurrences_and_keeps_source_readonly(tmp_path, monkeypatch):
    config = config_for_extraction(monkeypatch)
    # 该用例断言“任意函数调用里的同文文本”也能被补充抽取兜底——属于宽扫描语义，
    # 精准模式（默认）不会抓 custom_display(...)，因此显式切到 aggressive。
    config.extract_supplement_mode = "aggressive"
    source = tmp_path / "game" / "script.rpy"
    source.parent.mkdir()
    source.write_text(
        'label start:\n'
        '    narrator "Only the official dialogue."\n'
        '    narrator "Shared with a screen."\n'
        '    narrator "Shared with a menu."\n'
        '    narrator "Shared with a function."\n'
        'screen details():\n'
        '    text "Shared with a screen."\n'
        'menu:\n'
        '    "Shared with a menu." if available:\n'
        '        pass\n'
        'python:\n'
        '    custom_display("Shared with a function.")\n',
        encoding="utf-8",
    )
    original_bytes = source.read_bytes()
    tl_dir = tmp_path / "game" / "tl" / "chinese"

    def official(_exe, _language, **_kwargs):
        tl_dir.mkdir(parents=True, exist_ok=True)
        (tl_dir / "script.rpy").write_text("\n".join(
            f'translate chinese scene_{index}:\n    # narrator "{text}"\n    narrator "Translation {index}"\n'
            for index, text in enumerate([
                "Only the official dialogue.", "Shared with a screen.",
                "Shared with a menu.", "Shared with a function.",
            ])
        ), encoding="utf-8")

    extractor = UnifiedExtractor(SimpleNamespace(official_extract=official))
    result = extractor.extract_regular(tmp_path, "chinese", "game.exe")
    assert result.success, result.message
    originals = extractor._get_string_originals(tl_dir)
    assert "Only the official dialogue." not in originals
    assert {"Shared with a screen.", "Shared with a menu.", "Shared with a function."} <= originals
    assert source.read_bytes() == original_bytes


def test_failed_official_extract_keeps_broad_incremental_candidates(tmp_path, monkeypatch):
    config = config_for_extraction(monkeypatch)
    # 该用例断言“任意函数调用里的文本”也能被补充抽取兜底——属于宽扫描语义，
    # 精准模式（默认）不会抓 unknown_display，因此显式切到 aggressive。
    config.extract_supplement_mode = "aggressive"
    source = tmp_path / "game" / "script.rpy"
    source.parent.mkdir()
    source.write_text('python:\n    unknown_display("A previously unknown display.")\n', encoding="utf-8")

    def official(*_args, **_kwargs):
        raise RuntimeError("synthetic official failure")

    extractor = UnifiedExtractor(SimpleNamespace(official_extract=official))
    result = extractor.extract_incremental(tmp_path, "chinese", "game.exe")
    assert result.success, result.message
    assert extractor.official_extraction_status == "failed"
    assert "A previously unknown display." in extractor._get_string_originals(result.incremental_dir)


def test_official_success_does_not_discard_unknown_custom_renderers(tmp_path):
    selected = UnifiedExtractor()._select_incremental_originals(
        {"Official menu", "Custom display"}, set(), set(), {}, tmp_path,
        menu_candidates=set(), trusted_originals={"Official menu"},
    )
    assert selected == {"Official menu", "Custom display"}


def test_large_strings_selection_is_linear_and_preserves_escaped_originals(tmp_path, monkeypatch):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    selected = {'Say "hello"\nnext line\\tail', "Candidate 9999"}
    originals = ['Say "hello"\nnext line\\tail'] + [f"Candidate {i}" for i in range(10000)]
    (source_dir / "large.rpy").write_text(
        'translate chinese strings:\n' + "".join(
            f'    # renpybox: replace-only\n    old "{escape_tl_string(original)}"\n    new "{escape_tl_string(original)}"\n\n'
            for original in originals
        ), encoding="utf-8",
    )
    def no_ast(*_args, **_kwargs):
        raise AssertionError("simple strings must not allocate a full AST")
    monkeypatch.setattr("module.Extract.UnifiedExtractor.parse_tl_document", no_ast)
    extractor = UnifiedExtractor()
    target = tmp_path / "selected"
    extractor._extract_new_entries_to_folder(source_dir, target, selected, "chinese")
    result = extractor._fast_scan_strings_file(target / "large.rpy")
    assert result is not None
    assert result[0] == selected
    assert (target / "large.rpy").read_text(encoding="utf-8").count("replace-only") == 2


def test_static_supplement_reads_each_source_once_for_many_candidates(tmp_path, monkeypatch):
    source = tmp_path / "game" / "script.rpy"
    source.parent.mkdir()
    candidates = {f"Unique text {i}": "script.rpy" for i in range(1000)}
    source.write_text("\n".join(f'text "{text}"' for text in candidates), encoding="utf-8")
    reads = Counter()
    real_read = Path.read_text
    def read(path, *args, **kwargs):
        reads[path] += 1
        return real_read(path, *args, **kwargs)
    monkeypatch.setattr(Path, "read_text", read)
    extractor = UnifiedExtractor()
    count = extractor._append_static_supplement_entries(
        tmp_path, tmp_path / "game" / "tl" / "chinese", "chinese",
        candidates=candidates, menu_candidates=set(),
    )
    assert count == 1000
    assert reads[source] == 1


def test_cancelling_regular_extraction_restores_old_translation(tmp_path, monkeypatch):
    config_for_extraction(monkeypatch)
    tl_dir = tmp_path / "game" / "tl" / "chinese"
    tl_dir.mkdir(parents=True)
    previous = b'translate chinese strings:\n    old "Original"\n    new "Kept"\n'
    (tl_dir / "script.rpy").write_bytes(previous)
    cancelled = False
    def official(*_args, **_kwargs):
        nonlocal cancelled
        tl_dir.mkdir(parents=True, exist_ok=True)
        (tl_dir / "script.rpy").write_text("partial output", encoding="utf-8")
        cancelled = True
    extractor = UnifiedExtractor(SimpleNamespace(official_extract=official))
    extractor.set_cancel_callback(lambda: cancelled)
    result = extractor.extract_regular(tmp_path, "chinese", "game.exe")
    assert not result.success
    assert (tl_dir / "script.rpy").read_bytes() == previous


def test_official_progress_and_cancellation_are_passed_when_supported():
    calls = {}
    extractor = UnifiedExtractor.__new__(UnifiedExtractor)
    extractor._cancel_callback = lambda: False
    extractor._progress_callback = None
    class Official:
        def official_extract(self, exe, language, *, generate_empty=False, force=False, should_stop=None, progress_callback=None):
            calls.update(exe=exe, language=language, generate_empty=generate_empty,
                         force=force, stopped=should_stop(), progress=progress_callback)
    extractor.renpy_extractor = Official()
    extractor._run_official_extract("game.exe", "chinese")
    assert calls["language"] == "chinese"
    assert calls["stopped"] is False
    assert calls["progress"] is not None


def test_legacy_official_signature_still_works():
    extractor = UnifiedExtractor.__new__(UnifiedExtractor)
    extractor._cancel_callback = lambda: False
    class Legacy:
        def official_extract(self, exe, language, *, generate_empty=False, force=False):
            return exe, language, generate_empty, force
    extractor.renpy_extractor = Legacy()
    assert extractor._run_official_extract("game.exe", "chinese") == (
        "game.exe", "chinese", False, True
    )


def test_cancelling_incremental_selection_restores_previous_delta(tmp_path, monkeypatch):
    config_for_extraction(monkeypatch, custom=False)
    tl_dir = tmp_path / "game" / "tl" / "chinese"
    tl_dir.mkdir(parents=True)
    previous = 'translate chinese strings:\n    old "Old entry"\n    new "Old translation"\n'
    (tl_dir / "script.rpy").write_text(previous, encoding="utf-8")
    delta = tmp_path / "game" / "tl" / "chinese_new"
    delta.mkdir()
    (delta / "previous.rpy").write_text("Previous pending translation", encoding="utf-8")
    def official(*_args, **_kwargs):
        tl_dir.mkdir(parents=True, exist_ok=True)
        (tl_dir / "script.rpy").write_text(
            'translate chinese strings:\n    old "New entry"\n    new "New entry"\n', encoding="utf-8"
        )
    def cancel_during_selection(self, _source, target, *_args, **_kwargs):
        (target / "partial.rpy").write_text("partial", encoding="utf-8")
        raise rx.ExtractionCancelled("synthetic cancellation")
    monkeypatch.setattr(UnifiedExtractor, "_extract_new_entries_to_folder", cancel_during_selection)
    extractor = UnifiedExtractor(SimpleNamespace(official_extract=official))
    result = extractor.extract_incremental(tmp_path, "chinese", "game.exe")
    assert not result.success
    assert (tl_dir / "script.rpy").read_text(encoding="utf-8") == previous
    assert (delta / "previous.rpy").read_text(encoding="utf-8") == "Previous pending translation"
    assert not (delta / "partial.rpy").exists()


def test_scan_cancellation_propagates_before_source_mutation(tmp_path):
    path = tmp_path / "script.rpy"
    path.write_text('text "Retained content"\n', encoding="utf-8")
    with pytest.raises(rx.ExtractionCancelled):
        rx.ExtractFromFile(str(path), True, 4, False, False, True, False, should_stop=lambda: True)
    assert path.read_text(encoding="utf-8") == 'text "Retained content"\n'
