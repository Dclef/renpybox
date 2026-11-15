"""Real cross-file fixtures; no models, user games, configuration or databases."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from module.Extract.UnifiedExtractor import UnifiedExtractor
from module.OneKey.flow import apply_full_translation, apply_translation_files_transactionally
from module.Renpy import base_box_conflicts as service
from module.Renpy.renpy_tl_core import escape_tl_string
from module.Tool.FontReplacer import FontReplacer


def strings(old="Back", new="", language="chinese"):
    return (f"translate {language} strings:\n"
            f'    old "{escape_tl_string(old)}"\n'
            f'    new "{escape_tl_string(new)}"\n')


def put(root, rel, text):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8") if isinstance(text, str) else text)
    return path


def snapshot(root):
    return {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def unique(root):
    seen = {}
    for path, text in service.read_tree(root).items():
        for item in service.entries(path, text):
            assert item.key not in seen, (seen.get(item.key), item)
            seen[item.key] = item
    return seen


def extractor():
    instance = UnifiedExtractor.__new__(UnifiedExtractor)
    instance.logger = SimpleNamespace(**{level: lambda *a, **kw: None
                                        for level in ("debug", "info", "warning", "error")})
    return instance


def test_both_entrypoints_identical_and_second_injection_is_noop(tmp_path):
    first = tmp_path / "extract" / "game" / "tl" / "chinese"
    second = tmp_path / "font" / "game" / "tl" / "chinese"
    for root in (first, second):
        put(root, "custom/screens.rpy", "# manual note\n" + strings(new="手工返回")
            + '\nscreen local_panel():\n    text "Keep local screen"\n')
    assert extractor()._deploy_builtin_ui_pack(first, "chinese") > 0
    assert FontReplacer().deploy_builtin_font_pack(str(second.parents[1]), "chinese")[0]
    assert service.read_tree(first) == service.read_tree(second)
    assert snapshot(first / "fonts") == snapshot(second / "fonts")
    assert (first / "fonts/SourceHanSansCN-Bold.ttf").is_file()
    before = snapshot(first)
    assert extractor()._deploy_builtin_ui_pack(first, "chinese") > 0
    assert snapshot(first) == before
    items = unique(first)
    assert items[("chinese", "strings", "Back")].value == "手工返回"
    assert "manual note" in (first / "custom/screens.rpy").read_text(encoding="utf-8")
    assert "screen local_panel" in (first / "custom/screens.rpy").read_text(encoding="utf-8")


@pytest.mark.parametrize("inject_first", [True, False])
def test_full_apply_and_injection_order_preserve_manual_translation(tmp_path, inject_first):
    target = tmp_path / "project/game/tl/chinese"
    output = tmp_path / "output"
    file = put(output, "menus/screens.rpy", strings(new="手工返回"))
    if inject_first:
        extractor()._deploy_builtin_ui_pack(target, "chinese")
    assert apply_translation_files_transactionally([file], output, target) == 1
    if not inject_first:
        extractor()._deploy_builtin_ui_pack(target, "chinese")
    assert unique(target)[("chinese", "strings", "Back")].value == "手工返回"


def test_different_effective_user_values_fail_before_any_write(tmp_path):
    target = tmp_path / "project/game/tl/chinese"
    put(target, "menus/a.rpy", strings(new="手工甲"))
    put(target, "other/a.rpy", strings(new="手工乙"))
    before = snapshot(tmp_path)
    with pytest.raises(service.TranslationConflict) as error:
        extractor()._deploy_builtin_ui_pack(target, "chinese")
    assert "menus" in str(error.value) and "other" in str(error.value)
    assert ":2" in str(error.value)
    assert snapshot(tmp_path) == before


def test_managed_manual_value_is_not_overwritten_by_another_valid_user_value(tmp_path):
    target = tmp_path / "project/game/tl/chinese"
    put(target, "base_box/screens_box.rpy", strings(new="人工模板值"))
    put(target, "menus.rpy", strings(new="另一个人工值"))
    before = snapshot(tmp_path)
    with pytest.raises(service.TranslationConflict):
        extractor()._deploy_builtin_ui_pack(target, "chinese")
    assert snapshot(tmp_path) == before


def test_escaped_old_and_language_identity_and_identical_templates(tmp_path):
    target = tmp_path / "game/tl/chinese"
    templates = tmp_path / "templates"
    old = 'Say "Hi"\\n [player]'
    put(templates, "screens_box.rpy", strings(old, "默认值"))
    put(templates, "common_box.rpy", strings(old, "默认值"))
    put(target, "one/screens.rpy", strings(old, "人工值") + strings(old, "French", "french"))
    put(target, "two/screens.rpy", strings("Independent", "独立"))
    service.inject_base_box(target, "chinese", templates)
    items = unique(target)
    assert items[("chinese", "strings", old)].value == "人工值"
    assert items[("french", "strings", old)].value == "French"
    assert items[("chinese", "strings", "Independent")].value == "独立"
    before = snapshot(target)
    service.inject_base_box(target, "chinese", templates)
    assert snapshot(target) == before


def test_game_source_reservation_never_deletes_screens_or_common(tmp_path):
    game = tmp_path / "game"
    target = game / "tl/chinese"
    screens = put(game, "screens.rpy", strings(new="源码已有译文")
                  + '\nscreen demo():\n    text "Keep"\n')
    common = put(game, "common.rpy", 'define untouched = True\n')
    before = (screens.read_bytes(), common.read_bytes())
    extractor()._deploy_builtin_ui_pack(target, "chinese")
    assert (screens.read_bytes(), common.read_bytes()) == before
    assert ("chinese", "strings", "Back") not in unique(target)


def test_only_changed_or_known_orphan_compiled_files_are_removed(tmp_path):
    target = tmp_path / "project/game/tl/chinese"
    put(target, "menus.rpy", strings())
    put(target, "menus.rpyc", b"obsolete")
    put(target, "base_box/screens_box.rpyc", b"orphan-managed")
    orphan = put(target, "compiled_only.rpyc", b"only-copy")
    user_orphan = put(target, "base_box/user_plugin.rpyc", b"user-only-copy")
    other = put(target.parents[1], "story.rpyc", b"game-only-copy")
    extractor()._deploy_builtin_ui_pack(target, "chinese")
    assert not (target / "menus.rpyc").exists()
    assert not (target / "base_box/screens_box.rpyc").exists()
    assert orphan.read_bytes() == b"only-copy"
    assert user_orphan.read_bytes() == b"user-only-copy"
    assert other.read_bytes() == b"game-only-copy"


def test_write_failure_restores_scripts_compiled_files_and_created_paths(tmp_path, monkeypatch):
    target = tmp_path / "game/tl/chinese"
    first = put(target, "existing.rpy", strings("Existing", "原有值"))
    compiled = put(target, "existing.rpyc", b"compiled-original")
    new = target / "nested/new.rpy"
    put(target, "unrelated.rpy", "# keep user notes\n")
    put(target.parents[1], "compiled_only.rpyc", b"game-only")
    before = snapshot(tmp_path)
    real_replace = service.os.replace
    failed = False

    def fail_once(source, destination):
        nonlocal failed
        if Path(destination) == new and not failed:
            assert first.read_bytes() == strings("Existing", "新值").encode()
            assert not compiled.exists()
            failed = True
            raise OSError("simulated write failure")
        return real_replace(source, destination)

    real_copy = service.shutil.copy2
    backups = []

    def inspect_backup(source, destination, *args, **kwargs):
        if str(destination).endswith(".bak"):
            assert not Path(destination).is_relative_to(tmp_path / "game")
            backups.append(Path(destination))
        return real_copy(source, destination, *args, **kwargs)

    monkeypatch.setattr(service.shutil, "copy2", inspect_backup)
    monkeypatch.setattr(service.os, "replace", fail_once)
    with pytest.raises(service.TransactionFailure) as error:
        service.commit_changes({first: strings("Existing", "新值").encode(), compiled: None,
                                new: strings("New", "新增").encode()}, allowed_roots=[target])
    assert failed and not error.value.rollback_failed
    assert len(backups) == 2
    assert all(not path.exists() for path in backups)
    assert snapshot(tmp_path) == before
    assert not new.parent.exists()


def test_full_preflight_sees_untouched_files_and_global_labels(tmp_path):
    target = tmp_path / "project/game/tl/chinese"
    output = tmp_path / "output"
    put(target, "a.rpy", 'translate chinese story_123:\n    "One"\n')
    file = put(output, "other/a.rpy", 'translate chinese story_123:\n    "Two"\n')
    before = snapshot(tmp_path)
    with pytest.raises(service.TranslationConflict):
        apply_translation_files_transactionally([file], output, target)
    assert snapshot(tmp_path) == before


def test_unrelated_duplicate_is_rejected_without_cleanup(tmp_path):
    target = tmp_path / "game/tl/chinese"
    put(target, "a.rpy", strings("Custom", "相同"))
    put(target, "b.rpy", strings("Custom", "相同"))
    before = snapshot(tmp_path)
    with pytest.raises(service.TranslationConflict):
        extractor()._deploy_builtin_ui_pack(target, "chinese")
    assert snapshot(tmp_path) == before


def test_old_output_cache_cannot_replace_template(tmp_path):
    target = tmp_path / "game/tl/chinese"
    output = tmp_path / "output"
    managed = put(target, "base_box/screens_box.rpy", strings(new="人工模板"))
    stale = put(output, "base_box/screens_box.rpy", strings(new="过期缓存"))
    before = managed.read_bytes()
    assert apply_translation_files_transactionally([stale], output, target) == 0
    assert managed.read_bytes() == before


@pytest.mark.parametrize("clean", [True, False])
def test_incremental_preflight_resolves_template_and_checks_whole_target(tmp_path, clean):
    project = tmp_path / "project"
    target = project / "game/tl/chinese"
    delta = project / "game/tl/chinese_new"
    extractor()._deploy_builtin_ui_pack(target, "chinese")
    put(delta, "new/menu.rpy", strings(new="增量人工返回") + strings("Custom item", "新增"))
    put(delta, "base_box/screens_box.rpy", strings(new="过期缓存"))
    compiled_only = put(target, "only.rpyc", b"preserve")
    result = extractor().merge_incremental_folder(project, "chinese", delta, clean_duplicates=clean)
    assert result.success, result.message
    items = unique(target)
    assert items[("chinese", "strings", "Back")].value == "增量人工返回"
    assert items[("chinese", "strings", "Custom item")].value == "新增"
    assert compiled_only.read_bytes() == b"preserve"
    assert not delta.exists()


@pytest.mark.parametrize("kind", ["strings", "label"])
def test_incremental_conflict_keeps_target_and_delta_byte_identical(tmp_path, kind):
    project = tmp_path / "project"
    target = project / "game/tl/chinese"
    delta = project / "game/tl/chinese_new"
    extractor()._deploy_builtin_ui_pack(target, "chinese")
    if kind == "strings":
        put(target, "manual.rpy", strings(new="第一人工值"))
        put(delta, "other.rpy", strings(new="第二人工值"))
    else:
        put(target, "a.rpy", 'translate chinese same_label:\n    "One"\n')
        put(delta, "b.rpy", 'translate chinese same_label:\n    "Two"\n')
    before = snapshot(project)
    result = extractor().merge_incremental_folder(project, "chinese", delta, clean_duplicates=False)
    assert not result.success
    assert snapshot(project) == before


def test_incremental_commit_failure_rolls_back_main_and_staging(tmp_path, monkeypatch):
    project = tmp_path / "project"
    target = project / "game/tl/chinese"
    delta = project / "game/tl/chinese_new"
    put(target, "original.rpy", strings("Existing", "原有"))
    put(delta, "first.rpy", strings("First", "一"))
    put(delta, "second.rpy", strings("Second", "二"))
    before = snapshot(project)
    real_replace = service.os.replace
    failed = False

    def fail_once(src, dest):
        nonlocal failed
        if Path(dest) == target / "second.rpy" and not failed:
            assert (target / "first.rpy").is_file()
            assert "一" in (target / "first.rpy").read_text(encoding="utf-8")
            failed = True
            raise OSError("simulated final commit failure")
        return real_replace(src, dest)

    monkeypatch.setattr(service.os, "replace", fail_once)
    result = extractor().merge_incremental_folder(project, "chinese", delta, clean_duplicates=False)
    assert failed and not result.success
    assert snapshot(project) == before


def test_local_sdk_lint_on_isolated_fixture(tmp_path):
    sdk = Path(os.environ.get("RENPY_TEST_SDK", "D:/renpy study/renpy-8.5.3-sdk"))
    if not (sdk / "renpy.exe").is_file():
        pytest.skip("Set RENPY_TEST_SDK to run the real Ren'Py lint integration")
    project = tmp_path / "sdk_fixture"
    game = project / "game"
    put(game, "script.rpy", 'label start:\n    "Fixture line."\n    return\n')
    python_blocks = ('translate chinese python:\n    basebox_fixture_a = True\n'
                     'translate chinese python:\n    basebox_fixture_b = True\n')
    put(game, "runtime_init.rpy", python_blocks)
    assert service.entries(Path("runtime_init.rpy"), python_blocks) == []
    put(game, "options.rpy", 'define config.name = "BaseBox temporary fixture"\n'
        'define config.version = "1"\ndefine config.save_directory = None\n')
    target = game / "tl/chinese"
    put(target, "user.rpy", strings(new="手工返回").replace(
        'old "Back"', r'old "\u0042ack"'))
    assert FontReplacer().deploy_builtin_font_pack(str(game), "chinese")[0]
    assert FontReplacer().deploy_builtin_font_pack(str(game), "chinese")[0]
    output = tmp_path / "full-output"
    file = put(output, "save.rpy", strings("Save", "手工保存"))
    assert apply_full_translation(config=SimpleNamespace(), output_files=[file],
                                  output_dir=output, input_dir=target)[0]
    delta = tmp_path / "delta"
    put(delta, "load.rpy", strings("Load", "手工读取"))
    merged = extractor().merge_incremental_folder(project, "chinese", delta, clean_duplicates=False)
    assert merged.success, merged.message
    report = project / "lint-report.txt"
    env = dict(os.environ, SDL_VIDEODRIVER="dummy", SDL_AUDIODRIVER="dummy")
    result = subprocess.run([str(sdk / "renpy.exe"), str(project), "lint", str(report)],
                            capture_output=True, timeout=60, env=env)
    put(project, "sdk-exit-code.txt", str(result.returncode))
    logs = result.stdout.decode("utf-8", errors="replace") + result.stderr.decode("utf-8", errors="replace")
    for name in ("errors.txt", "traceback.txt"):
        if (project / name).is_file():
            logs += (project / name).read_text(encoding="utf-8", errors="replace")
    assert result.returncode == 0, logs
    assert report.is_file(), logs
    logs += report.read_text(encoding="utf-8-sig", errors="replace")
    assert "Ren'Py" in logs and "1 dialogue" in logs, logs
    assert (game / "script.rpyc").is_file()
    assert "translation already exists" not in logs.lower(), logs
    assert "defined twice" not in logs.lower(), logs

@pytest.mark.parametrize("mode", ["builtin", "custom", "mixed"])
def test_managed_templates_never_enter_llm_reader(tmp_path, monkeypatch, mode):
    from module.Config import Config
    from module.File.RENPY import RENPY
    import module.Extract.RpyExtractionSettings as settings
    target = tmp_path / "input"
    managed = put(target, "nested/base_box/screens_box.rpy", strings(new=""))
    config = Config()
    config.input_folder, config.output_folder = str(target), str(tmp_path / "output")
    monkeypatch.setattr(settings, "selection_for_path", lambda *a: (None, mode, {}))
    assert RENPY(config).read_from_path([str(managed)]) == []


def test_managed_cache_entries_cannot_write_template_output(tmp_path):
    from module.Config import Config
    from module.File.RENPY import RENPY
    from module.Cache.CacheItem import CacheItem
    config = Config()
    config.input_folder, config.output_folder = str(tmp_path / "input"), str(tmp_path / "output")
    managed = put(Path(config.input_folder), "base_box/screens_box.rpy", strings(new="人工"))
    cached = SimpleNamespace(get_file_type=lambda: CacheItem.FileType.RENPY,
                             get_file_path=lambda: "base_box/screens_box.rpy")
    before = managed.read_bytes()
    RENPY(config).write_to_path([cached])
    assert not (Path(config.output_folder) / "base_box/screens_box.rpy").exists()
    assert managed.read_bytes() == before


def test_full_replacement_does_not_hide_existing_manual_conflict(tmp_path):
    target = tmp_path / "game/tl/chinese"
    output = tmp_path / "output"
    put(target, "base_box/screens_box.rpy", strings(new="返回"))
    put(target, "user.rpy", strings(new="人工甲"))
    incoming = put(output, "user.rpy", strings(new="人工乙"))
    before = snapshot(tmp_path)
    with pytest.raises(service.TranslationConflict):
        apply_full_translation(config=SimpleNamespace(), output_files=[incoming],
                               output_dir=output, input_dir=target)
    assert snapshot(tmp_path) == before



def test_full_placeholder_overlay_preserves_previous_manual_template_value(tmp_path):
    target = tmp_path / "game/tl/chinese"
    output = tmp_path / "output"
    put(target, "base_box/screens_box.rpy", strings(new="返回"))
    put(target, "user.rpy", strings(new="原有人工作品"))
    incoming = put(output, "user.rpy", strings(new=""))
    apply_translation_files_transactionally([incoming], output, target)
    assert unique(target)[("chinese", "strings", "Back")].value == "原有人工作品"


def test_commented_header_and_single_quoted_old_are_seen(tmp_path):
    target = tmp_path / "game/tl/chinese"
    put(target, "base_box/screens_box.rpy", strings(new="返回"))
    path = put(target, "user.rpy", "translate chinese strings: # keep header note\n"
               "    old\t'Back' # old note\n    new '人工' # new note\n")
    changes, _ = service.plan_tree(target)
    service.commit_changes(changes, allowed_roots=[target])
    assert unique(target)[("chinese", "strings", "Back")].value == "人工"
    text = path.read_text(encoding="utf-8")
    assert "keep header note" in text and "old note" in text and "new note" in text



def test_runtime_escaped_identity_uses_shared_scanner_and_preserves_raw_new(tmp_path):
    target = tmp_path / "game/tl/chinese"
    templates = tmp_path / "templates"
    put(templates, "screens_box.rpy", strings("Back Again", "默认"))
    put(target, "user.rpy", 'translate chinese strings:\n'
        r'    old "\u0042ack   Again"' + '\n'
        r'    new r"Keep  two spaces and \t"' + '\n')
    service.inject_base_box(target, "chinese", templates)
    items = unique(target)
    assert items[("chinese", "strings", "Back Again")].value == r"Keep  two spaces and \t"
    text = (target / "base_box/screens_box.rpy").read_text(encoding="utf-8")
    assert r'new r"Keep  two spaces and \t"' in text



def test_staged_merge_preserves_declined_candidate_recording(tmp_path):
    from module.Extract.ReplaceGenerator import load_declined_candidates, record_declined_candidates
    project = tmp_path / "project"
    target = project / "game/tl/chinese"
    source = project / "game/tl/chinese_new"
    delta = tmp_path / "translated-output"
    put(target, "existing.rpy", strings("Existing", "原有"))
    put(source, "new.rpy", strings("Translated", "") + strings("Declined", ""))
    put(delta, "new.rpy", strings("Translated", "已翻译"))
    record_declined_candidates(project, "chinese", {"Prior declined"})
    result = extractor().merge_incremental_folder(project, "chinese", delta, clean_duplicates=False)
    assert result.success, result.message
    assert load_declined_candidates(project, "chinese") == {"Prior declined", "Declined"}



@pytest.mark.parametrize("backslashes, expected_success", [(2, False), (3, True)])
def test_local_sdk_escape_fixture_requires_escaped_quote(tmp_path, backslashes, expected_success):
    sdk = Path(os.environ.get("RENPY_TEST_SDK", "D:/renpy study/renpy-8.5.3-sdk"))
    if not (sdk / "renpy.exe").is_file():
        pytest.skip("Set RENPY_TEST_SDK to run the real Ren'Py lint integration")
    project = tmp_path / "escape_fixture"
    game = project / "game"
    put(game, "script.rpy", 'label start:\n    "Fixture line."\n    return\n')
    put(game, "options.rpy", 'define config.name = "Escape temporary fixture"\n'
        'define config.save_directory = None\n')
    escaped_quote = "\\" * backslashes + '"'
    translated = '- Training Bot ' + escaped_quote + 'Copper Finch' + escaped_quote
    text = 'translate chinese strings:\n    old "Fixture"\n    new "' + translated + '"\n'
    put(game, "tl/chinese/fixture.rpy", text)
    report = project / "lint-report.txt"
    env = dict(os.environ, SDL_VIDEODRIVER="dummy", SDL_AUDIODRIVER="dummy")
    result = subprocess.run([str(sdk / "renpy.exe"), str(project), "lint", str(report)],
                            capture_output=True, timeout=60, env=env)
    put(project, "sdk-exit-code.txt", str(result.returncode))
    logs = result.stdout.decode("utf-8", errors="replace") + result.stderr.decode("utf-8", errors="replace")
    if expected_success:
        assert result.returncode == 0 and report.is_file(), logs
        assert not (project / "errors.txt").exists()
    else:
        assert result.returncode != 0, logs
        errors = (project / "errors.txt").read_text(encoding="utf-8-sig", errors="replace")
        assert "could not parse string." in errors.lower(), errors


@pytest.mark.parametrize("key", ["base_box_conflict", "base_box_unsafe_syntax", "base_box_transaction_failed"])
def test_english_onekey_keeps_specific_localized_paths_and_lines(monkeypatch, key):
    from module.OneKey import flow
    from module.Localizer.LocalizerEN import LocalizerEN
    localizer = LocalizerEN()
    monkeypatch.setattr(flow.Localizer, "get", lambda: localizer)
    monkeypatch.setattr(flow.Localizer, "get_app_language", lambda: flow.BaseLanguage.Enum.EN)
    message = getattr(localizer, key).format(details="user/a.rpy:2, user/b.rpy:5",
                                            path="user/a.rpy", line=2, error="write failed",
                                            rollback="user/a.rpy:2", backup="safe-temp-backup")
    assert flow._localize_merge_failure(message) == message
    result = SimpleNamespace(success=False, message="提取失败: " + message, cancelled=False)
    assert flow._localize_extraction_base_result(result, False) == message
