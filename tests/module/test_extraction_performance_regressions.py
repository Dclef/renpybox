import csv
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import pytest

from module.Extract import UnifiedExtractor as unified_extractor_module
from module.Extract.UnifiedExtractor import (
    _cache_get,
    _cache_put,
    _RESULT_CACHE_MAX_ENTRIES,
    UnifiedExtractor,
)
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
    assert result.cancelled is True
    assert "已自动恢复原翻译目录" in result.message
    assert (tl_dir / "script.rpy").read_bytes() == previous


def test_cancelling_official_failure_is_not_logged_as_error(tmp_path, monkeypatch):
    config_for_extraction(monkeypatch, custom=False)
    tl_dir = tmp_path / "game" / "tl" / "chinese"
    tl_dir.mkdir(parents=True)
    previous = b'translate chinese strings:\n    old "Original"\n    new "Kept"\n'
    (tl_dir / "script.rpy").write_bytes(previous)
    cancelled = False

    def official(*_args, **_kwargs):
        nonlocal cancelled
        cancelled = True
        raise RuntimeError("官方抽取已取消")

    extractor = UnifiedExtractor(SimpleNamespace(official_extract=official))
    info_messages = []
    error_messages = []
    extractor.logger = SimpleNamespace(
        info=info_messages.append,
        error=error_messages.append,
        warning=lambda *_args, **_kwargs: None,
        debug=lambda *_args, **_kwargs: None,
    )
    extractor.set_cancel_callback(lambda: cancelled)

    result = extractor.extract_regular(tmp_path, "chinese", "game.exe")

    assert result.success is False
    assert result.cancelled is True
    assert error_messages == []
    assert any("常规抽取已取消" in message for message in info_messages)
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


def test_backfill_failure_must_not_be_reported_as_success(tmp_path, monkeypatch):
    """H1：_merge_translations 的失败列表不能再被丢弃后照报 success=True。

    旧实现丢弃返回值，用户 TL 里留着"抽到原文但译文没写回去"的半成品，
    界面却显示抽取成功，游戏里仍是英文。
    """
    config = config_for_extraction(monkeypatch)
    tl_dir = tmp_path / "game" / "tl" / "chinese"
    tl_dir.mkdir(parents=True)
    previous = (
        'translate chinese strings:\n'
        '    old "Kept entry"\n'
        '    new "保留的译文"\n'
    )
    (tl_dir / "script.rpy").write_text(previous, encoding="utf-8")

    def official(*_args, **_kwargs):
        tl_dir.mkdir(parents=True, exist_ok=True)
        (tl_dir / "script.rpy").write_text(
            'translate chinese strings:\n'
            '    old "Kept entry"\n'
            '    new "保留的译文"\n'
            '\n'
            '    old "Brand new entry"\n'
            '    new "Brand new entry"\n',
            encoding="utf-8",
        )

    monkeypatch.setattr(
        UnifiedExtractor,
        "_merge_translations",
        lambda *_a, **_k: ["回填翻译失败 script.rpy: synthetic boom"],
    )
    extractor = UnifiedExtractor(SimpleNamespace(official_extract=official))
    result = extractor.extract_incremental(
        tmp_path, "chinese", "game.exe", output_to_separate_folder=False
    )

    assert result.success is False
    assert "回填已有翻译未完整完成" in result.message
    # 失败时 finally 必须把原 TL 目录从备份移回：用户已有译文一条都不能少
    # （本轮抽取新增的条目允许留在里面，用户重来一轮即可）。
    assert (tl_dir / "script.rpy").exists()
    restored = (tl_dir / "script.rpy").read_text(encoding="utf-8")
    assert 'old "Kept entry"' in restored
    assert 'new "保留的译文"' in restored


def test_preserve_filter_deletions_are_recoverable(tmp_path):
    """保留库过滤是物理删除：删掉的条目必须能原样恢复回来。

    旧实现直接 write_text 抹掉 old/new 对，只留一条进度文本，译文只能重新花钱
    再翻一遍。should_skip_text 还会误判 Café / OK_2 之类的正常文本。
    """
    game_dir = tmp_path / "fictional_game"
    tl_dir = game_dir / "game" / "tl" / "chinese"
    tl_dir.mkdir(parents=True)
    target = tl_dir / "script.rpy"
    target.write_text(
        'translate chinese strings:\n'
    '\n'
    '    old "Alice"\n'
    '    new "爱丽丝"\n'
    '\n'
    '    old "A regular sentence worth translating."\n'
    '    new "一句值得翻译的普通句子。"\n',
        encoding="utf-8",
    )

    extractor = UnifiedExtractor()
    removed, manifest_path = extractor._filter_tl_files(
        tl_dir, "chinese", {"Alice"}
    )

    assert removed == 1
    surviving = target.read_text(encoding="utf-8")
    assert 'old "Alice"' not in surviving
    assert 'old "A regular sentence worth translating."' in surviving

    # 清单里必须记录被删的原文与译文，否则恢复后是空的。
    assert manifest_path is not None and manifest_path.exists()
    manifest_text = manifest_path.read_text(encoding="utf-8-sig")
    assert "Alice" in manifest_text
    assert "爱丽丝" in manifest_text
    assert "preserve_set" in manifest_text
    # 未被删除的条目绝不能进清单。
    assert "worth translating" not in manifest_text

    # 走真实恢复入口：勾选 restore=1 后应把 Alice 的原文+译文写回同一个文件。
    rows = list(csv.DictReader(manifest_path.read_text(encoding="utf-8-sig").splitlines()))
    assert rows and all(row["restore"] == "0" for row in rows)
    with manifest_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        for row in rows:
            row["restore"] = "1"
            writer.writerow(row)

    result = extractor.restore_flagged_suspicious_entries(
        game_dir, "chinese", manifest_path
    )

    assert result.success is True
    recovered = target.read_text(encoding="utf-8")
    assert 'old "Alice"' in recovered
    assert 'new "爱丽丝"' in recovered


def test_preserve_filter_reports_failed_file_instead_of_silent_pass(tmp_path, monkeypatch):
    """单个文件过滤失败不能再被裸 except 吞掉。"""
    tl_dir = tmp_path / "chinese"
    tl_dir.mkdir()
    (tl_dir / "script.rpy").write_text(
        'translate chinese strings:\n    old "Alice"\n    new "爱丽丝"\n',
        encoding="utf-8",
    )

    def boom(*_args, **_kwargs):
        raise OSError("synthetic write failure")

    monkeypatch.setattr(
        "module.Extract.UnifiedExtractor.atomic_write_text", boom
    )
    extractor = UnifiedExtractor()
    errors = []
    monkeypatch.setattr(extractor.logger, "error", lambda message: errors.append(message))

    removed, _manifest = extractor._filter_tl_files(tl_dir, "chinese", {"Alice"})

    assert removed == 1  # 清单照留，用户知道有条目被判定为要删
    assert any("应用保留库过滤失败" in message for message in errors)
    # 源文件必须保持原样（原子写失败不会留下半截文件）。
    assert (tl_dir / "script.rpy").read_text(encoding="utf-8").endswith('new "爱丽丝"\n')


def test_backup_run_dirs_never_collide_within_one_post_process(tmp_path):
    """同一秒内连续两轮过滤，各自的清单不能互相覆盖。

    保留库过滤和布尔表达式过滤在 _post_process 里先后跑，时间戳只到秒。
    run_dir 重名时后写的 restore_manifest.csv 会覆盖前一份，被删的译文就
    永远恢复不回来了。
    """
    tl_dir = tmp_path / "chinese"
    tl_dir.mkdir()

    first = UnifiedExtractor()._write_suspicious_backup(
        tl_dir,
        "chinese",
        {"script.rpy": [{"line": 1, "old": "Alice", "new": "爱丽丝", "reason": "preserve_set"}]},
    )
    second = UnifiedExtractor()._write_suspicious_backup(
        tl_dir,
        "chinese",
        {"script.rpy": [{"line": 9, "old": "x == True", "new": "", "reason": "suspicious_bool_expr"}]},
    )

    assert first != second
    assert first.exists() and second.exists()
    assert "Alice" in first.read_text(encoding="utf-8-sig")
    assert "x == True" in second.read_text(encoding="utf-8-sig")


def test_scan_cancellation_propagates_before_source_mutation(tmp_path):
    path = tmp_path / "script.rpy"
    path.write_text('text "Retained content"\n', encoding="utf-8")
    with pytest.raises(rx.ExtractionCancelled):
        rx.ExtractFromFile(str(path), True, 4, False, False, True, False, should_stop=lambda: True)
    assert path.read_text(encoding="utf-8") == 'text "Retained content"\n'


def test_result_caches_stay_bounded_across_projects():
    """换一个项目不能让三个结果缓存无限增长。

    缓存键带 tl 目录签名，目录一改就必然 miss，可没人来删旧条目：用户每换一个
    项目就留一份编号块指纹和 strings 集合（实测项目 62 个 rpy / 60229 条），
    长时间切换项目会把内存吃满。命中时还要按 LRU 重排，否则"最近用的"会被淘汰。
    """
    overflow = _RESULT_CACHE_MAX_ENTRIES + 5
    for name in (
        "_STRING_ORIGINALS_CACHE",
        "_NUMBERED_FINGERPRINTS_CACHE",
        "_EXISTING_TRANSLATIONS_CACHE",
    ):
        cache = getattr(unified_extractor_module, name)
        cache.clear()
        try:
            for index in range(overflow):
                _cache_put(cache, (f"project-{index}", "sig"), index)
            assert len(cache) == _RESULT_CACHE_MAX_ENTRIES, (
                f"{name} 超过上限：{len(cache)} > {_RESULT_CACHE_MAX_ENTRIES}"
            )

            # 最旧的已淘汰，最新的还在。
            assert _cache_get(cache, ("project-0", "sig")) is None
            assert _cache_get(cache, (f"project-{overflow - 1}", "sig")) == overflow - 1

            # 命中会把条目挪到末尾，所以再插一个就该淘汰当前最旧的（即 project-1）。
            _cache_put(cache, ("newcomer", "sig"), "x")
            assert _cache_get(cache, ("project-1", "sig")) is None
            assert _cache_get(cache, ("newcomer", "sig")) == "x"
        finally:
            cache.clear()
