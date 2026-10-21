import zipfile
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace

import pytest

from module.Tool.ErrorRepairer import ErrorRepairer


error_repairer_module = import_module("module.Tool.ErrorRepairer")


def _quote_errors(repairer: ErrorRepairer, tmp_path, content: str):
    script = tmp_path / "script.rpy"
    script.write_text(content, encoding="utf-8")
    return repairer.check_file(
        str(script),
        check_syntax=False,
        check_indent=False,
        check_indent_level=False,
        check_quotes=True,
        check_dialogue_quotes=True,
    )


def _translation_errors(repairer: ErrorRepairer, tmp_path, content: str):
    script = tmp_path / "translation.rpy"
    script.write_text(content, encoding="utf-8")
    errors = repairer.check_file(
        str(script),
        check_syntax=False,
        check_indent=False,
        check_indent_level=False,
        check_quotes=False,
        check_dialogue_quotes=False,
        check_translation_issues=True,
    )
    return script, errors


def test_repairs_only_inner_unescaped_quotes_with_exact_output() -> None:
    repairer = ErrorRepairer()

    repaired, changed = repairer.repair_unescaped_dialogue_quotes(
        'new "他说"你好"，然后走了"\r\n'
    )

    assert changed is True
    assert repaired == 'new "他说\\"你好\\"，然后走了"\r\n'


def test_repair_preserves_spacing_and_does_not_touch_quoted_comment() -> None:
    repaired, changed = ErrorRepairer().repair_unescaped_dialogue_quotes(
        '    e\t"He said "hello" today"  # keep "comment"\n'
    )

    assert changed is True
    assert repaired == '    e\t"He said \\"hello\\" today"  # keep "comment"\n'


def test_preserves_curly_quotes_inside_a_normal_string(tmp_path) -> None:
    script = tmp_path / "strings.rpy"
    original = 'new "他说“你好”，然后走了"\n'
    script.write_text(original, encoding="utf-8")

    success, fix_count = ErrorRepairer().auto_fix_file(
        str(script),
        fix_indent=False,
        fix_quotes=True,
        fix_dialogue_quotes=True,
    )

    assert success is True
    assert fix_count == 0
    assert script.read_text(encoding="utf-8") == original


def test_normalizes_only_outer_curly_delimiters() -> None:
    repaired, changed = ErrorRepairer().repair_curly_string_delimiters(
        'new “他说“你好”，然后走了” # 保留“注释”\n'
    )

    assert changed is True
    assert repaired == 'new "他说“你好”，然后走了" # 保留“注释”\n'


def test_auto_fix_is_idempotent(tmp_path) -> None:
    script = tmp_path / "strings.rpy"
    script.write_text('old "He said "hello" today"\n', encoding="utf-8")
    repairer = ErrorRepairer()

    first_success, first_count = repairer.auto_fix_file(
        str(script),
        fix_indent=False,
        fix_quotes=True,
        fix_dialogue_quotes=True,
    )
    first_output = script.read_text(encoding="utf-8")
    second_success, second_count = repairer.auto_fix_file(
        str(script),
        fix_indent=False,
        fix_quotes=True,
        fix_dialogue_quotes=True,
    )

    assert first_success is True
    assert first_count == 1
    assert first_output == 'old "He said \\"hello\\" today"\n'
    assert second_success is True
    assert second_count == 0
    assert script.read_text(encoding="utf-8") == first_output


def test_apostrophe_inside_double_quoted_text_is_not_an_error(tmp_path) -> None:
    errors = _quote_errors(ErrorRepairer(), tmp_path, 'old "I don\'t know"\n')

    assert errors == []


@pytest.mark.parametrize(
    "line",
    [
        '$ values = ("one", "two")\n',
        'value = "one" "two"\n',
        'e "one" "two"\n',
        '    "Choice" if persistent.seen_intro:\n',
        '    textbutton "Start" action Return("start")\n',
        'e "Hello" # translator wrote "greeting"\n',
        '    """docstring with "quoted" text"""\n',
        "new 'I don't know'\n",
    ],
)
def test_quote_repair_fails_closed_for_ambiguous_or_legal_lines(line: str) -> None:
    repaired, changed = ErrorRepairer().repair_unescaped_dialogue_quotes(line)

    assert changed is False
    assert repaired == line


def test_scanner_ignores_legal_python_menu_screen_comments_and_triple_quotes(tmp_path) -> None:
    content = (
        '$ values = ("one", "two")\n'
        'value = "one" "two"\n'
        'e "one" "two"\n'
        '    "Choice" if persistent.seen_intro:\n'
        '    textbutton "Start" action Return("start")\n'
        'e "Hello" # translator wrote "greeting"\n'
        '    """docstring with "quoted" text"""\n'
    )

    assert _quote_errors(ErrorRepairer(), tmp_path, content) == []


def test_scanner_reports_repairable_and_unterminated_translation_strings(tmp_path) -> None:
    errors = _quote_errors(
        ErrorRepairer(),
        tmp_path,
        'old "He said "hello" today"\nnew "unterminated\n',
    )

    assert [(error["line"], error["type"]) for error in errors] == [
        (1, "quotes"),
        (2, "quotes"),
    ]


def test_placeholder_scan_uses_counter_and_distinguishes_issue_types(tmp_path) -> None:
    _, errors = _translation_errors(
        ErrorRepairer(),
        tmp_path,
        '''translate schinese strings:
    old "Hi [name] [name]"
    new "你好 [name]"

    old "Score [score]"
    new "分数 [score] [bonus]"

    old "Welcome [player_name]"
    new "欢迎 [玩家名]"

    old "Literal [[player_name]] and [kept]"
    new "字面 [[玩家名]] 和 [kept]"
''',
    )

    placeholder_errors = [
        error for error in errors if error["type"].startswith("placeholder_")
    ]
    assert [(error["line"], error["type"]) for error in placeholder_errors] == [
        (3, "placeholder_missing"),
        (6, "placeholder_extra"),
        (9, "placeholder_rewritten"),
    ]
    assert placeholder_errors[0]["placeholders"] == {"[name]": 1}
    assert placeholder_errors[1]["placeholders"] == {"[bonus]": 1}
    assert placeholder_errors[2]["rewrites"] == [
        {"source": "[player_name]", "target": "[玩家名]", "count": 1}
    ]


def test_placeholder_and_linebreak_scan_supports_dialogue_translation_blocks(tmp_path) -> None:
    _, errors = _translation_errors(
        ErrorRepairer(),
        tmp_path,
        '''translate schinese start_abcd:
    # e "Hello [name]\\nAgain"
    e "你好 [name]"
''',
    )

    assert [(error["line"], error["type"]) for error in errors] == [
        (3, "linebreak_mismatch"),
    ]
    assert errors[0]["source_count"] == 1
    assert errors[0]["target_count"] == 0


def test_placeholder_scan_supports_single_quoted_old_new_pairs(tmp_path) -> None:
    _, errors = _translation_errors(
        ErrorRepairer(),
        tmp_path,
        "translate schinese strings:\n    old 'Hi [name]'\n    new '你好'\n",
    )

    assert [(error["line"], error["type"]) for error in errors] == [
        (3, "placeholder_missing"),
    ]
    assert errors[0]["placeholders"] == {"[name]": 1}


def test_empty_new_is_legal_and_extra_empty_literal_is_reported(tmp_path) -> None:
    _, errors = _translation_errors(
        ErrorRepairer(),
        tmp_path,
        '''translate schinese strings:
    old "Pending [name]\\n"
    new ""

    old "Done"
    new "完成" ""

translate schinese start_abcd:
    # e "Silent"
    e ""
    # e "Spoken"
    e "说完了" ""
    # e "Condition"
    e "选项" if persistent.route == ""
    # e "Condition extra"
    e "选项" if persistent.route == "" ""
''',
    )

    assert [(error["line"], error["type"]) for error in errors] == [
        (6, "extra_empty_string"),
        (12, "extra_empty_string"),
        (16, "extra_empty_string"),
    ]
    assert all(error["count"] == 1 for error in errors)


def test_empty_translate_strings_blocks_are_reported_and_removed(tmp_path) -> None:
    script = tmp_path / "screens.rpy"
    script.write_text(
        "translate chinese strings:\n\n"
        "translate chinese strings:\n"
        '    old "Keep"\n'
        '    new "保留"\n\n'
        "translate chinese strings:\n"
        "    # generated placeholder\n\n",
        encoding="utf-8",
    )
    repairer = ErrorRepairer()

    errors = repairer.check_file(
        str(script),
        check_indent=False,
        check_indent_level=False,
        check_quotes=False,
        check_dialogue_quotes=False,
        check_translation_issues=False,
    )

    assert [(error["line"], error["type"]) for error in errors] == [
        (1, "empty_block"),
        (7, "empty_block"),
    ]

    success, fixed = repairer.auto_fix_file(
        str(script),
        fix_indent=False,
        fix_indent_level=False,
        fix_quotes=False,
        fix_dialogue_quotes=False,
    )

    assert success is True
    assert fixed == 2
    assert script.read_text(encoding="utf-8") == (
        "translate chinese strings:\n"
        '    old "Keep"\n'
        '    new "保留"\n\n'
        '    # generated placeholder\n\n'
    )


def test_lint_empty_block_fix_removes_all_empty_blocks(monkeypatch, tmp_path) -> None:
    game_dir = tmp_path / "game"
    tl_dir = game_dir / "tl" / "chinese"
    tl_dir.mkdir(parents=True)
    script = tl_dir / "screens.rpy"
    script.write_text(
        "translate chinese strings:\n\n"
        "translate chinese strings:\n\n"
        '    old "Keep"\n'
        '    new "保留"\n',
        encoding="utf-8",
    )
    game_exe = tmp_path / "game.exe"
    game_exe.write_text("", encoding="utf-8")
    outputs = iter([
        'File "game/tl/chinese/screens.rpy", line 1: '
        "translate strings statement expects a non-empty block",
        "",
    ])
    repairer = ErrorRepairer()
    monkeypatch.setattr(repairer, "exec_renpy_lint", lambda _path: next(outputs))

    success, fixed = repairer.fix_by_lint(str(game_exe))

    assert success is True
    assert fixed == 1
    assert script.read_text(encoding="utf-8") == (
        "translate chinese strings:\n"
        "\n"
        '    old "Keep"\n'
        '    new "保留"\n'
    )


def test_scan_reports_same_file_duplicate_without_writing(tmp_path) -> None:
    content = '''translate schinese strings:
    old "Same"
    new "相同"

    old "Same"
    new "再次"
'''
    script, errors = _translation_errors(ErrorRepairer(), tmp_path, content)

    assert [error["type"] for error in errors] == ["duplicate_old_new"]
    assert errors[0]["line"] == 5
    assert errors[0]["first_line"] == 2
    assert script.read_text(encoding="utf-8") == content


def test_folder_scan_reports_cross_file_duplicates_per_language_without_writing(tmp_path) -> None:
    first = tmp_path / "a.rpy"
    second = tmp_path / "b.rpy"
    other_language = tmp_path / "c.rpy"
    first.write_text(
        'translate schinese strings:\n    old "Same"\n    new "甲"\n',
        encoding="utf-8",
    )
    second.write_text(
        'translate schinese strings:\n    old "Same"\n    new "乙"\n',
        encoding="utf-8",
    )
    other_language.write_text(
        'translate french strings:\n    old "Same"\n    new "Pareil"\n',
        encoding="utf-8",
    )
    before = {path: path.read_bytes() for path in (first, second, other_language)}

    report = ErrorRepairer().check_folder(
        str(tmp_path),
        check_syntax=False,
        check_indent=False,
        check_indent_level=False,
        check_quotes=False,
        check_dialogue_quotes=False,
        check_translation_issues=True,
    )

    duplicate = report[str(second)][0]
    assert duplicate["type"] == "duplicate_old_new"
    assert duplicate["first_file"] == str(first)
    assert str(other_language) not in report
    assert {path: path.read_bytes() for path in before} == before


def test_translation_folder_resolution_excludes_source_scripts(tmp_path) -> None:
    game_dir = tmp_path / "game"
    translation_dir = game_dir / "tl" / "chinese"
    translation_dir.mkdir(parents=True)
    source = game_dir / "script.rpy"
    generated = translation_dir / "script.rpy"
    source.write_text('new "Broken "source""\n', encoding="utf-8")
    generated.write_text(
        'translate chinese strings:\n'
        '    old "Hello [name]"\n'
        '    new "你好"\n',
        encoding="utf-8",
    )

    resolved = ErrorRepairer.resolve_translation_folder(game_dir)
    report = ErrorRepairer().check_folder(str(resolved))

    assert resolved == game_dir / "tl"
    assert str(source) not in report
    assert str(generated) in report
    assert report[str(generated)][0]["type"] == "placeholder_missing"


def test_lint_filter_keeps_only_translation_directory_errors(tmp_path) -> None:
    translation_dir = tmp_path / "game" / "tl" / "chinese"
    translation_dir.mkdir(parents=True)
    errors = [
        {"file": "game/tl/chinese/dialogue.rpy", "line": 3},
        {"file": "game/script.rpy", "line": 8},
        {"file": "other.rpy", "line": 1},
        {"raw": "warning without a file"},
    ]

    filtered = ErrorRepairer.filter_lint_errors(errors, translation_dir)

    assert filtered == [errors[0]]


def test_parse_real_renpy_lint_report_and_split_groups(tmp_path) -> None:
    """Ren'Py 的报告是 `path:line 消息`（不是 Python 的 `File ..., line N:`），并按译文/源码分组。"""
    translation_dir = tmp_path / "game" / "tl" / "chinese"
    translation_dir.mkdir(parents=True)
    report = (
        "\ufeffRen'Py 8.2.0 lint report, generated at: Wed Oct 21 21:28:05 2026\n"
        "\n"
        "game/tl/chinese/tlcase.rpy:3 'nosuchimage_tl' is not an image.\n"
        "\n"
        "game/tl/chinese/翻译测试.rpy : this file contains orphan translations at line 1 (id abcd).\n"
        "\n"
        "tl/chinese/翻译测试.rpy contains non-ASCII characters in its filename.\n"
        "\n"
        "game/zz_lintcase.rpyc:2 'nosuchimage' is not an image.\n"
        "\n"
        'File "game/tl/chinese/broken.rpy", line 1: end of line expected.\n'
        "\n"
        "Statistics:\n"
        "\n"
        "The game contains 2 menus, 0 images, and 23 screens.\n"
    )
    errors = ErrorRepairer().parse_lint_errors(report)
    tl_errors, source_errors = ErrorRepairer.split_lint_errors(errors, translation_dir)

    assert [(item["file"], item["line"], item.get("type")) for item in tl_errors] == [
        ("game/tl/chinese/tlcase.rpy", 3, "missing_image"),
        ("game/tl/chinese/翻译测试.rpy", 0, "orphan_translation"),
        ("tl/chinese/翻译测试.rpy", 0, "non_ascii_filename"),
        ("game/tl/chinese/broken.rpy", 1, "syntax_error"),
    ]
    # 已编译脚本按 .rpyc 报出来，只认 .rpy 会把它丢掉；统计行不能被当成问题。
    assert [(item["file"], item["line"]) for item in source_errors] == [("game/zz_lintcase.rpyc", 2)]


def test_split_lint_errors_drops_runtime_speaker_noise(tmp_path) -> None:
    """「运行时变量当角色名」是 lint 的常见误报：译文组不该留，源码侧重复的也丢掉。"""
    translation_dir = tmp_path / "game" / "tl" / "chinese"
    translation_dir.mkdir(parents=True)
    hint = "Could not evaluate 'suspect1' in the who part of a say statement."
    errors = [
        {"file": "game/tl/chinese/events3.rpy", "line": 3171, "type": "who_unresolved", "message": hint},
        {"file": "game/events3.rpy", "line": 1693, "type": "who_unresolved", "message": hint},
        {"file": "game/tl/chinese/broken.rpy", "line": 1, "type": "syntax_error", "message": "end of line expected."},
        {"file": "game/events3.rpy", "line": 2, "type": "missing_image", "message": "'x' is not an image."},
    ]
    tl_errors, source_errors = ErrorRepairer.split_lint_errors(errors, translation_dir)

    # 译文只留真问题（语法错误 / 孤儿译文 / 文件名），who 提示一条都不进。
    assert [item["file"] for item in tl_errors] == ["game/tl/chinese/broken.rpy"]
    assert [(item["file"], item["type"]) for item in source_errors] == [
        ("game/events3.rpy", "who_unresolved"),
        ("game/events3.rpy", "missing_image"),
    ]


def test_syntax_scan_reports_malformed_translation_headers_and_else(tmp_path) -> None:
    script = tmp_path / "translation.rpy"
    script.write_text(
        "translate chinese strings\n"
        "    old \"Hello\"\n"
        "    new \"你好\"\n"
        "else\n",
        encoding="utf-8",
    )

    errors = ErrorRepairer().check_file(
        str(script),
        check_indent=False,
        check_indent_level=False,
        check_quotes=False,
        check_dialogue_quotes=False,
        check_translation_issues=False,
    )

    assert [(error["line"], error["message"]) for error in errors] == [
        (1, "translate 语句缺少冒号"),
        (4, "控制流语句缺少冒号"),
    ]

def test_translation_scan_never_writes_the_source_file(tmp_path) -> None:
    content = '''translate schinese strings:
    old "Hi [name]\\n"
    new "你好 [名字]" ""
'''
    script = tmp_path / "translation.rpy"
    script.write_text(content, encoding="utf-8")
    before = script.read_bytes()

    ErrorRepairer().check_file(str(script))

    assert script.read_bytes() == before


def test_export_report_preserves_full_path_and_structured_details(tmp_path) -> None:
    report_path = tmp_path / "report.xlsx"
    source_path = str(tmp_path / "nested" / "translation.rpy")
    report = {
        source_path: [{
            "line": 8,
            "type": "placeholder_missing",
            "message": "译文缺少原文占位符",
            "content": 'new "你好"',
            "placeholders": {"[name]": 2},
            "source_line": 7,
        }],
    }

    ErrorRepairer().export_error_report(report, str(report_path))

    from openpyxl import load_workbook

    sheet = load_workbook(report_path).active
    assert [cell.value for cell in sheet[1]] == [
        "文件", "行号", "错误类型", "错误信息", "内容", "详情",
    ]
    assert sheet.cell(2, 1).value == source_path
    assert '"[name]": 2' in sheet.cell(2, 6).value
    assert '"source_line": 7' in sheet.cell(2, 6).value


def _patch_lint_runtime(monkeypatch, tmp_path, result) -> str:
    game_exe = tmp_path / "sample.exe"
    python_exe = tmp_path / "python.exe"
    game_py = tmp_path / "sample.py"
    for path in (game_exe, python_exe, game_py):
        path.write_text("", encoding="utf-8")

    monkeypatch.setattr(
        error_repairer_module,
        "get_python_path_from_game_path",
        lambda _path: str(python_exe),
    )
    monkeypatch.setattr(
        error_repairer_module,
        "get_py_path",
        lambda _path: str(game_py),
    )
    monkeypatch.setattr(error_repairer_module.subprocess, "run", lambda *args, **kwargs: result)
    return str(game_exe)


def test_exec_lint_distinguishes_clean_run_from_failure(monkeypatch, tmp_path) -> None:
    clean_game = _patch_lint_runtime(
        monkeypatch,
        tmp_path,
        SimpleNamespace(returncode=0, stdout="", stderr=""),
    )
    assert ErrorRepairer().exec_renpy_lint(clean_game) == ""

    failed_game = _patch_lint_runtime(
        monkeypatch,
        tmp_path,
        SimpleNamespace(returncode=1, stdout="", stderr="launcher failed"),
    )
    assert ErrorRepairer().exec_renpy_lint(failed_game) is None


@pytest.mark.parametrize(
    "error_type",
    [
        "",
        "unterminated_string",
        "unknown_statement",
        "expected_statement",
        "empty_block",
        "duplicate_translation",
    ],
)
def test_lint_fixer_unknown_or_destructive_types_never_write(tmp_path, error_type: str) -> None:
    script = tmp_path / "script.rpy"
    original = 'old "Keep me"\nnew "保留我"\n'
    script.write_text(original, encoding="utf-8")

    changed = ErrorRepairer()._fix_single_lint_error(str(script), 1, error_type)

    assert changed is False
    assert script.read_text(encoding="utf-8") == original


def test_fix_by_lint_stops_on_unknown_error_without_writing(monkeypatch, tmp_path) -> None:
    game_dir = tmp_path / "game"
    game_dir.mkdir()
    script = game_dir / "script.rpy"
    original = 'label start:\n    "Keep me"\n'
    script.write_text(original, encoding="utf-8")
    repairer = ErrorRepairer()
    monkeypatch.setattr(
        repairer,
        "exec_renpy_lint",
        lambda _path: '"game/script.rpy", line 2: unknown statement',
    )

    success, fixed = repairer.fix_by_lint(str(tmp_path / "sample.exe"))

    assert success is False
    assert fixed == 0
    assert script.read_text(encoding="utf-8") == original


def test_fix_by_lint_repairs_one_safe_error_then_relints(monkeypatch, tmp_path) -> None:
    game_dir = tmp_path / "game"
    game_dir.mkdir()
    script = game_dir / "script.rpy"
    script.write_text('new "He said "hello" today"\n', encoding="utf-8")
    outputs = iter([
        '"game/script.rpy", line 1: end of line expected',
        "",
    ])
    repairer = ErrorRepairer()
    monkeypatch.setattr(repairer, "exec_renpy_lint", lambda _path: next(outputs))

    success, fixed = repairer.fix_by_lint(str(tmp_path / "sample.exe"))

    assert success is True
    assert fixed == 1
    assert script.read_text(encoding="utf-8") == 'new "He said \\"hello\\" today"\n'


def test_parse_lint_error_preserves_file_paths_with_spaces() -> None:
    [error] = ErrorRepairer().parse_lint_errors(
        'File "C:\\Games\\My Game\\game\\script.rpy", line 7: end of line expected'
    )

    assert error["file"] == "C:\\Games\\My Game\\game\\script.rpy"
    assert error["line"] == 7
    assert error["type"] == "syntax_error"


def test_scan_folder_reads_and_parses_each_file_once(tmp_path, monkeypatch) -> None:
    """每个 .rpy 只读一次、只解析一次：旧实现会各做三次。"""
    import builtins
    from pathlib import Path

    repairer = ErrorRepairer()
    for index in range(3):
        script = tmp_path / f"script_{index}.rpy"
        # 行首 Tab 触发 indent 错误，用于确认结果仍然完整。
        script.write_text("\tnew \"文本 %d\"\n" % index, encoding="utf-8")

    opened: list[Path] = []
    parsed: list[int] = []
    real_open = builtins.open
    original_parse = error_repairer_module.parse_tl_document

    def counting_open(file, *args, **kwargs):
        opened.append(Path(file))
        return real_open(file, *args, **kwargs)

    def counting_parse(lines, **kwargs):
        parsed.append(len(lines))
        return original_parse(lines, **kwargs)

    monkeypatch.setattr(builtins, "open", counting_open)
    monkeypatch.setattr(error_repairer_module, "parse_tl_document", counting_parse)

    result = repairer.scan_folder(str(tmp_path))

    assert result.scanned_files == 3
    assert result.total_files == 3
    assert result.budget_exhausted is False
    assert len(opened) == 3
    assert parsed == [1, 1, 1]
    assert sum(
        1
        for errors in result.errors.values()
        for error in errors
        if error["type"] == "indent"
    ) == 3


def test_scan_folder_stops_at_file_budget(tmp_path) -> None:
    repairer = ErrorRepairer()
    for index in range(5):
        (tmp_path / f"script_{index}.rpy").write_text(
            "\tnew \"文本 %d\"\n" % index, encoding="utf-8"
        )

    result = repairer.scan_folder(str(tmp_path), max_files=2)

    assert result.scanned_files == 2
    assert result.total_files == 5
    assert result.budget_exhausted is True
    assert len(result.errors) == 2


def test_scan_folder_stops_when_cancelled(tmp_path, monkeypatch) -> None:
    repairer = ErrorRepairer()
    script = tmp_path / "script.rpy"
    original = b'\tnew "text"\n'
    script.write_bytes(original)

    def unexpected_enumeration(*args, **kwargs):
        pytest.fail("Cancellation before enumeration must not walk the directory")

    monkeypatch.setattr(repairer, "get_rpy_files", unexpected_enumeration)
    result = repairer.scan_folder(str(tmp_path), should_cancel=lambda: True)

    assert result.scanned_files == 0
    assert result.total_files == 0
    assert result.total_files_known is False
    assert result.budget_exhausted is True
    assert result.errors == {}
    assert script.read_bytes() == original


def test_scan_folder_empty_directory_has_known_total(tmp_path) -> None:
    result = ErrorRepairer().scan_folder(str(tmp_path))

    assert result.total_files == result.scanned_files == 0
    assert result.total_files_known is True
    assert result.budget_exhausted is False
    assert result.errors == {}


@pytest.mark.parametrize(("limits", "total_known"), [
    ({"deadline": 0}, False),
    ({"max_files": 0}, True),
    ({"max_bytes": 0}, True),
])
def test_scan_folder_budget_stop_is_not_an_empty_scan(tmp_path, limits, total_known) -> None:
    script = tmp_path / "script.rpy"
    original = b'\tnew "text"\n'
    script.write_bytes(original)

    result = ErrorRepairer().scan_folder(str(tmp_path), **limits)

    assert result.budget_exhausted is True
    assert result.total_files_known is total_known
    assert result.total_files == (1 if total_known else 0)
    assert result.scanned_files == result.scanned_bytes == 0
    assert result.errors == {}
    assert script.read_bytes() == original


def test_scan_folder_cancel_during_enumeration_has_unknown_total(tmp_path, monkeypatch) -> None:
    lexical = import_module("module.Tool.LexicalFs")
    script = tmp_path / "script.rpy"
    original = b'\tnew "text"\n'
    script.write_bytes(original)
    cancelled = False
    original_link_check = lexical.is_link_or_reparse

    def link_check(path):
        nonlocal cancelled
        if path == script:
            cancelled = True
        return original_link_check(path)

    monkeypatch.setattr(lexical, "is_link_or_reparse", link_check)
    result = ErrorRepairer().scan_folder(str(tmp_path), should_cancel=lambda: cancelled)

    assert cancelled is True
    assert result.total_files == result.scanned_files == result.scanned_bytes == 0
    assert result.total_files_known is False
    assert result.budget_exhausted is True
    assert result.errors == {}
    assert script.read_bytes() == original


def test_scan_folder_cancel_keeps_only_completed_files_and_never_writes(tmp_path, monkeypatch) -> None:
    originals = {}
    for index in range(3):
        script = tmp_path / f"script_{index}.rpy"
        originals[script] = f'\tnew "text {index}"\n'.encode()
        script.write_bytes(originals[script])
    original_parse = error_repairer_module.parse_tl_document
    cancelled = False
    parsed = 0

    def parsing(lines, *, checkpoint):
        nonlocal cancelled, parsed
        parsed += 1
        if parsed == 2:
            cancelled = True
        return original_parse(lines, checkpoint=checkpoint)

    monkeypatch.setattr(error_repairer_module, "parse_tl_document", parsing)
    result = ErrorRepairer().scan_folder(str(tmp_path), should_cancel=lambda: cancelled)

    assert parsed == 2
    assert result.total_files == 3
    assert result.total_files_known is True
    assert result.scanned_files == 1
    assert result.budget_exhausted is True
    assert list(result.errors) == [str(tmp_path / "script_0.rpy")]
    assert any(error["type"] == "indent" for error in result.errors[str(tmp_path / "script_0.rpy")])
    assert set(tmp_path.iterdir()) == set(originals)
    assert all(script.read_bytes() == original for script, original in originals.items())


@pytest.mark.parametrize("stage", ["enumerate", "stat", "read"])
@pytest.mark.parametrize("error_type", [PermissionError, FileNotFoundError])
def test_scan_folder_io_errors_fail_instead_of_reporting_clean(tmp_path, monkeypatch, stage, error_type) -> None:
    import builtins

    repairer = ErrorRepairer()
    script = tmp_path / "script.rpy"
    original = b'\tnew "text"\n'
    script.write_bytes(original)
    failure = error_type("simulated scan I/O failure")

    def fail(*args, **kwargs):
        raise failure

    if stage == "enumerate":
        monkeypatch.setattr(repairer, "get_rpy_files", fail)
    else:
        monkeypatch.setattr(repairer, "get_rpy_files", lambda *args, **kwargs: [script])
        if stage == "stat":
            original_stat = type(script).stat

            def stat(path, *args, **kwargs):
                if path == script:
                    raise failure
                return original_stat(path, *args, **kwargs)

            monkeypatch.setattr(type(script), "stat", stat)
        else:
            original_open = builtins.open

            def opening(file, *args, **kwargs):
                if file == script:
                    raise failure
                return original_open(file, *args, **kwargs)

            monkeypatch.setattr(builtins, "open", opening)

    with pytest.raises(RuntimeError, match="扫描未完成") as caught:
        repairer.scan_folder(str(tmp_path))

    assert caught.value.__cause__ is failure
    assert script.read_bytes() == original


@pytest.mark.parametrize("method", ["_iter_translation_pairs", "_scan_extra_empty_strings", "_scan_translation_issues"])
def test_translation_helpers_can_cancel_fallback_parsing(monkeypatch, method) -> None:
    repairer = ErrorRepairer()
    original_parse = error_repairer_module.parse_tl_document
    parsing = False
    cancelled_during_parse = False

    class Cancelled(BaseException):
        pass

    def checkpoint():
        nonlocal cancelled_during_parse
        cancelled_during_parse = parsing
        raise Cancelled()

    def parse(lines, **kwargs):
        nonlocal parsing
        parsing = True
        try:
            return original_parse(lines, **kwargs)
        finally:
            parsing = False

    monkeypatch.setattr(error_repairer_module, "parse_tl_document", parse)
    lines = ['translate chinese strings:', '    old "Hello"', '    new "你好"']
    args = (lines, "script.rpy") if method == "_scan_translation_issues" else (lines,)
    with pytest.raises(Cancelled):
        list(getattr(repairer, method)(*args, checkpoint=checkpoint))

    assert cancelled_during_parse is True


def test_large_single_file_cancels_during_parse_without_writing(tmp_path, monkeypatch):
    script = tmp_path / "large.rpy"
    original = ('translate chinese strings:\n' + '    old "Hello [name]"\n    new "你好 [name]"\n' * 5000).encode()
    script.write_bytes(original)
    parse = error_repairer_module.parse_tl_document
    cancelled = False
    checkpoints = 0

    def parsing(lines, *, checkpoint):
        def tick():
            nonlocal cancelled, checkpoints
            checkpoints += 1
            if checkpoints == 3:
                cancelled = True
            checkpoint()
        return parse(lines, checkpoint=tick)

    monkeypatch.setattr(error_repairer_module, "parse_tl_document", parsing)
    result = ErrorRepairer().scan_folder(str(tmp_path), should_cancel=lambda: cancelled)
    assert checkpoints == 3
    assert result.budget_exhausted and result.scanned_files == 0
    assert result.errors == {}
    assert script.read_bytes() == original


def test_single_file_progress_is_throttled_and_pairs_built_once(tmp_path, monkeypatch):
    script = tmp_path / "large.rpy"
    script.write_text('translate chinese strings:\n' + ''.join(
        f'    old "Hello {i} [name]"\n    new "你好 {i} [name]"\n' for i in range(1200)
    ), encoding="utf-8")
    clock_value = 0.0

    def clock():
        nonlocal clock_value
        clock_value += 0.05
        return clock_value

    monkeypatch.setattr(error_repairer_module, "time", SimpleNamespace(monotonic=clock))
    repairer = ErrorRepairer()
    pair = repairer._iter_translation_pairs
    calls = 0

    def pairs(*args, **kwargs):
        nonlocal calls
        calls += 1
        yield from pair(*args, **kwargs)

    monkeypatch.setattr(repairer, "_iter_translation_pairs", pairs)
    updates = []
    result = repairer.scan_folder(str(tmp_path), check_indent_level=False, on_progress=updates.append)
    assert result.scanned_files == 1 and result.errors == {}
    assert calls == 1
    assert {event["phase"] for event in updates} >= {"parse", "check", "translation"}
    assert all(b["elapsed"] - a["elapsed"] >= 0.2 - 1e-9 for a, b in zip(updates, updates[1:]))
    completion = [event["scanned_files"] + event["fraction"] for event in updates]
    assert completion == sorted(completion)


def test_repair_backup_preserves_bytes_newlines_and_body_tabs(tmp_path):
    script = tmp_path / "tabs.rpy"
    original = b'translate chinese strings:\r\n\told "A\tB"\r\n\tnew "A\tB"\r\n'
    script.write_bytes(original)
    assert ErrorRepairer().auto_fix_file(str(script), fix_empty_blocks=False) == (True, 2)
    assert script.read_bytes() == original.replace(b'\r\n\t', b'\r\n    ')
    [backup] = list(tmp_path.glob("tabs.rpy.*.bak"))
    assert backup.read_bytes() == original
    assert ErrorRepairer().auto_fix_file(str(script), fix_empty_blocks=False) == (True, 0)
    assert list(tmp_path.glob("*.bak")) == [backup]


def test_repair_write_failure_leaves_original_and_backup(tmp_path, monkeypatch):
    script = tmp_path / "tabs.rpy"
    original = b'\tnew "Keep me"\n'
    script.write_bytes(original)
    atomic_module = import_module("module.File.AtomicWrite")

    def fail_replace(*args):
        raise OSError("simulated replacement failure")

    monkeypatch.setattr(atomic_module.os, "replace", fail_replace)
    assert ErrorRepairer().auto_fix_file(str(script)) == (False, 0)
    assert script.read_bytes() == original
    [backup] = list(tmp_path.glob("*.bak"))
    assert backup.read_bytes() == original
    assert not list(tmp_path.glob("*.tmp"))


def test_repair_refuses_invalid_encoding_without_losing_bytes(tmp_path):
    script = tmp_path / "broken.rpy"
    script.write_bytes(b'\tnew "\xff"\n')
    assert ErrorRepairer().auto_fix_file(str(script)) == (False, 0)
    assert script.read_bytes() == b'\tnew "\xff"\n'
    assert not list(tmp_path.glob("*.bak"))


@pytest.mark.parametrize("cancel", [False, True])
def test_lint_timeout_and_cancel_reap_real_child(tmp_path, monkeypatch, cancel):
    import asyncio
    import sys

    script = tmp_path / "sleeping_game.py"
    script.write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
    monkeypatch.setattr(error_repairer_module, "get_python_path_from_game_path", lambda _: sys.executable)
    monkeypatch.setattr(error_repairer_module, "get_py_path", lambda _: str(script))
    processes = []
    popen = error_repairer_module.subprocess.Popen

    def launch(*args, **kwargs):
        child = popen(*args, **kwargs)
        processes.append(child)
        return child

    monkeypatch.setattr(error_repairer_module.subprocess, "Popen", launch)
    calls = 0

    def checkpoint():
        nonlocal calls
        calls += 1
        if cancel and calls == 3:
            raise asyncio.CancelledError()

    repairer = ErrorRepairer()
    if cancel:
        with pytest.raises(asyncio.CancelledError):
            repairer.exec_renpy_lint(str(tmp_path / "game.exe"), checkpoint=checkpoint)
    else:
        assert repairer.exec_renpy_lint(
            str(tmp_path / "game.exe"), checkpoint=checkpoint, timeout=0.1,
        ) is None
    assert len(processes) == 1 and processes[0].poll() is not None
    assert not (tmp_path / "lint_errors.txt").exists()


def test_repair_cancel_inside_file_leaves_original(tmp_path):
    import asyncio

    script = tmp_path / "large.rpy"
    original = b'\tnew "A"\n' * 1000
    script.write_bytes(original)
    calls = 0

    def checkpoint():
        nonlocal calls
        calls += 1
        # Four callbacks read the file; then cancel while building repaired lines.
        if calls == 6:
            raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        ErrorRepairer().auto_fix_file(str(script), checkpoint=checkpoint)
    assert script.read_bytes() == original
    assert not list(tmp_path.glob("*.bak"))


def test_repair_backup_failure_prevents_write(tmp_path, monkeypatch):
    import builtins
    from pathlib import Path

    script = tmp_path / "tabs.rpy"
    original = b'\tnew "A"\n'
    script.write_bytes(original)
    real_open = builtins.open

    def open_without_backup(path, *args, **kwargs):
        if Path(path).suffix == ".bak":
            raise OSError("backup disk full")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", open_without_backup)
    assert ErrorRepairer().auto_fix_file(str(script)) == (False, 0)
    assert script.read_bytes() == original


def _syntax_errors(repairer: ErrorRepairer, tmp_path, content: str):
    script = tmp_path / "syntax.rpy"
    script.write_text(content, encoding="utf-8")
    return repairer.check_file(
        str(script),
        check_indent=False,
        check_indent_level=False,
        check_quotes=False,
        check_dialogue_quotes=False,
        check_translation_issues=False,
    )


def _indent_level_errors(repairer: ErrorRepairer, script):
    return repairer.check_file(
        str(script),
        check_syntax=False,
        check_indent=False,
        check_indent_level=True,
        check_quotes=False,
        check_dialogue_quotes=False,
        check_translation_issues=False,
    )


def test_classify_issue_type_maps_each_kind_to_a_fix_mode() -> None:
    classify = error_repairer_module.classify_issue_type

    assert classify("indent") == "auto"
    assert classify("empty_block") == "auto"
    assert classify("duplicate_old_new") == "auto"
    assert classify("unescaped_dialogue_quotes") == "auto"
    assert classify("indentation_level") == "conditional"
    assert classify("quotes") == "conditional"
    assert classify("syntax") == "manual"
    assert classify("placeholder_missing") == "manual"
    assert classify("extra_empty_string") == "manual"
    # 未知类型一律按人工处理，不允许被自动修掉。
    assert classify("brand_new_type") == "manual"
    # 类上暴露同一份集合与分类函数，供 API/UI 两种引用方式使用。
    assert ErrorRepairer.AUTO_FIX_TYPES == error_repairer_module.AUTO_FIX_TYPES
    assert ErrorRepairer.MANUAL_TYPES == error_repairer_module.MANUAL_TYPES
    assert ErrorRepairer.classify_issue_type("quotes") == "conditional"


def test_syntax_scan_ignores_screen_label_displayables(tmp_path) -> None:
    content = (
        "init -501 screen say(who, what):\n"
        '    label "[char_name]" xalign 0.5 yalign 0.5 ypos 327 text_font "wqy.ttf"\n'
        "    label char_name xalign 0.5 text_bold True\n"
        "    label shop_info[\"title\"] text_size 80\n"
        '    label _("Display")\n'
        "    label title\n"
        "screen plain():\n"
        "    label \"没有属性的展示文本\"\n"
    )

    assert _syntax_errors(ErrorRepairer(), tmp_path, content) == []


def test_syntax_scan_still_reports_real_label_statements_without_colon(tmp_path) -> None:
    errors = _syntax_errors(ErrorRepairer(), tmp_path, 'label start\n    e "hi"\n')

    assert [(error["line"], error["message"]) for error in errors] == [
        (1, "label 语句缺少冒号"),
    ]


def test_syntax_scan_ignores_multiline_parenthesized_conditions(tmp_path) -> None:
    content = (
        "label start:\n"
        '    if (renpy.get_screen("say") and\n'
        '            wait_event(["proceed"]) > 0 and\n'
        "            is_evening()):\n"
        "        pass\n"
        "    elif (is_in_progress(\n"
        '            "x@1")):\n'
        "        pass\n"
        "    else:\n"
        "        pass\n"
    )

    assert _syntax_errors(ErrorRepairer(), tmp_path, content) == []


def test_syntax_scan_still_reports_conditions_that_never_get_a_colon(tmp_path) -> None:
    content = (
        "label start:\n"
        "    if (a and\n"
        "            b)\n"
        "        pass\n"
        "    while True\n"
        "        pass\n"
    )

    errors = _syntax_errors(ErrorRepairer(), tmp_path, content)

    assert [(error["line"], error["message"]) for error in errors] == [
        (3, "控制流语句缺少冒号"),
        (5, "控制流语句缺少冒号"),
    ]


def test_syntax_scan_ignores_colons_that_only_exist_inside_comments(tmp_path) -> None:
    content = (
        'translate chinese strings:  # 头注释里的冒号不算语句冒号\n'
        '    old "a"\n'
        '    new "b"\n'
        "label start:  # note: 这里的冒号在注释里\n"
        '    e "hi"\n'
    )

    assert _syntax_errors(ErrorRepairer(), tmp_path, content) == []


def test_indentation_level_is_skipped_for_source_scripts_without_translate_blocks(tmp_path) -> None:
    source = tmp_path / "screens.rpy"
    source.write_text('screen test():\n  text "错位两格"\n', encoding="utf-8")

    # 源脚本没有 translate 块：缩进层级检查全是误报，不应上报。
    assert _indent_level_errors(ErrorRepairer(), source) == []

    translation = tmp_path / "translation.rpy"
    translation.write_text(
        'translate chinese strings:\n'
        '    old "a"\n'
        '    new "b"\n'
        "\n"
        "screen test():\n"
        '  text "错位两格"\n',
        encoding="utf-8",
    )

    # 同一处错位出现在 tl 文件里仍然要报。
    errors = _indent_level_errors(ErrorRepairer(), translation)
    assert [(error["line"], error["type"]) for error in errors] == [
        (6, "indentation_level"),
    ]


def test_auto_fix_removes_trailing_spaces_and_keeps_other_content(tmp_path) -> None:
    script = tmp_path / "spaces.rpy"
    script.write_text('label start:  \n    e "hi" \t\n\tnew "x"\n', encoding="utf-8")

    assert ErrorRepairer().auto_fix_file(
        str(script), fix_trailing_spaces=True, fix_empty_blocks=False,
    ) == (True, 3)
    assert script.read_text(encoding="utf-8") == 'label start:\n    e "hi"\n    new "x"\n'
    assert ErrorRepairer().auto_fix_file(
        str(script), fix_trailing_spaces=True, fix_empty_blocks=False,
    ) == (True, 0)


def test_trailing_space_fix_is_opt_in(tmp_path) -> None:
    script = tmp_path / "spaces.rpy"
    content = 'label start:  \n    e "hi"  \n'
    script.write_text(content, encoding="utf-8")

    assert ErrorRepairer().auto_fix_file(str(script), fix_empty_blocks=False) == (True, 0)
    assert script.read_text(encoding="utf-8") == content


def test_auto_fix_comments_same_file_duplicate_pairs(tmp_path) -> None:
    script = tmp_path / "dup.rpy"
    script.write_text(
        'translate chinese strings:\n'
        '    old "Same"\n'
        '    new "甲"\n'
        "\n"
        '    old "Same"\n'
        '    new "乙"\n'
        "\n"
        '    old "Other"\n'
        '    new "丙"\n',
        encoding="utf-8",
    )

    assert ErrorRepairer().auto_fix_file(
        str(script), fix_empty_blocks=False, fix_duplicates=True,
    ) == (True, 1)
    assert script.read_text(encoding="utf-8") == (
        'translate chinese strings:\n'
        '    old "Same"\n'
        '    new "甲"\n'
        "\n"
        '    # old "Same"\n'
        '    # new "乙"\n'
        "\n"
        '    old "Other"\n'
        '    new "丙"\n'
    )
    [backup] = list(tmp_path.glob("dup.rpy.*.bak"))
    assert ErrorRepairer().auto_fix_file(
        str(script), fix_empty_blocks=False, fix_duplicates=True,
    ) == (True, 0)
    assert list(tmp_path.glob("dup.rpy.*.bak")) == [backup]


def test_fix_duplicates_clears_duplicate_scan_errors(tmp_path) -> None:
    script = tmp_path / "dup.rpy"
    script.write_text(
        'translate chinese strings:\n'
        '    old "Same"\n'
        '    new "甲"\n'
        '    old "Same"\n'
        '    new "乙"\n',
        encoding="utf-8",
    )
    repairer = ErrorRepairer()

    before = repairer.scan_folder(str(tmp_path))
    assert before.issues_by_type == {"duplicate_old_new": 1}
    assert before.fixable_count == 1

    assert repairer.auto_fix_file(
        str(script), fix_empty_blocks=False, fix_duplicates=True,
    ) == (True, 1)
    assert repairer.scan_folder(str(tmp_path)).errors == {}


def test_fix_duplicate_strings_comments_cross_file_duplicates(tmp_path) -> None:
    first = tmp_path / "a.rpy"
    second = tmp_path / "b.rpy"
    first_content = 'translate chinese strings:\n    old "Same"\n    new "甲"\n'
    second_content = (
        'translate chinese strings:\n'
        '    old "Same"\n'
        '    new "乙"\n'
        "\n"
        '    old "Only"\n'
        '    new "丙"\n'
    )
    first.write_text(first_content, encoding="utf-8")
    second.write_text(second_content, encoding="utf-8")

    assert ErrorRepairer().fix_duplicate_strings(str(tmp_path)) == (1, [str(second)])
    assert first.read_text(encoding="utf-8") == first_content
    assert second.read_text(encoding="utf-8") == (
        'translate chinese strings:\n'
        '    # old "Same"\n'
        '    # new "乙"\n'
        "\n"
        '    old "Only"\n'
        '    new "丙"\n'
    )
    # 第一条保留、后续注释后才能幂等：第二次不该再有改动。
    assert ErrorRepairer().fix_duplicate_strings(str(tmp_path)) == (0, [])
    assert not list(tmp_path.glob("a.rpy.*.bak"))
    [backup] = list(tmp_path.glob("b.rpy.*.bak"))
    assert backup.read_text(encoding="utf-8") == second_content


def test_fix_duplicate_strings_drops_emptied_strings_block_only(tmp_path) -> None:
    first = tmp_path / "a.rpy"
    second = tmp_path / "b.rpy"
    first.write_text('translate chinese strings:\n    old "Same"\n    new "甲"\n', encoding="utf-8")
    second.write_text(
        'translate chinese strings:\n'
        '    old "Same"\n'
        '    new "乙"\n'
        "\n"
        "translate chinese start_1:\n"
        '    # e "Same"\n'
        '    e "同一"\n',
        encoding="utf-8",
    )

    assert ErrorRepairer().fix_duplicate_strings(str(tmp_path)) == (1, [str(second)])
    # 空块只移除块头，重复译文保留为文件级注释，编号对话块保持原样。
    assert second.read_text(encoding="utf-8") == (
        '    # old "Same"\n'
        '    # new "乙"\n'
        '\n'
        "translate chinese start_1:\n"
        '    # e "Same"\n'
        '    e "同一"\n'
    )


def test_folder_scan_result_has_backward_compatible_defaults() -> None:
    result = error_repairer_module.FolderScanResult({}, 0, 0, 0, False)

    assert result.total_files_known is True
    assert result.issues_by_type == {}
    assert result.environment_issues == []
    assert result.fixable_count == 0
    assert result.manual_count == 0


def test_scan_folder_summarizes_fixable_and_manual_issues(tmp_path) -> None:
    (tmp_path / "indent.rpy").write_text('\tnew "A"\n', encoding="utf-8")
    (tmp_path / "syntax.rpy").write_text("label start\n    pass\n", encoding="utf-8")

    result = ErrorRepairer().scan_folder(str(tmp_path))

    assert result.issues_by_type == {"indent": 1, "syntax": 1}
    assert result.fixable_count == 1
    assert result.manual_count == 1
    assert result.environment_issues == []
    assert result.budget_exhausted is False


def _make_incremental_project(tmp_path):
    translation = tmp_path / "game" / "tl" / "chinese"
    leftover = tmp_path / "game" / "tl" / "chinese_new"
    translation.mkdir(parents=True)
    leftover.mkdir(parents=True)
    strings = (
        'translate chinese strings:\n'
        '    old "Hello"\n'
        '    new "你好"\n'
        "\n"
        '    old "Bye"\n'
        '    new "再见"\n'
    )
    (translation / "script.rpy").write_text(strings, encoding="utf-8")
    (leftover / "strings.rpy").write_text(strings, encoding="utf-8")
    return translation, leftover, strings


def test_detect_environment_issues_finds_unmerged_incremental_folder(tmp_path) -> None:
    translation, leftover, _ = _make_incremental_project(tmp_path)
    repairer = ErrorRepairer()

    issues = repairer.detect_environment_issues(translation)

    assert len(issues) == 1
    issue = issues[0]
    assert issue["type"] == issue["kind"] == "incremental_leftover"
    assert issue["language"] == "chinese"
    assert issue["path"] == str(leftover)
    assert issue["issue_count"] == 2
    assert issue["actions"] == ["merge", "move"]
    assert "chinese_new" in issue["message"]
    assert "2 条重复译文" in issue["message"]
    # 从 tl 目录、从项目根出发也要能识别（扫描入口可能停在任意一层）。
    assert repairer.detect_environment_issues(tmp_path / "game" / "tl")[0]["language"] == "chinese"
    assert repairer.detect_environment_issues(tmp_path)[0]["language"] == "chinese"
    # 没有 tl 祖先的普通目录不做无端猜测。
    unrelated = tmp_path / "unrelated"
    unrelated.mkdir()
    assert repairer.detect_environment_issues(unrelated) == []


def test_detect_environment_issues_ignores_leftover_without_scripts(tmp_path) -> None:
    (tmp_path / "game" / "tl" / "chinese_new").mkdir(parents=True)

    assert ErrorRepairer().detect_environment_issues(tmp_path / "game" / "tl") == []


def test_scan_folder_reports_environment_issues_unless_disabled(tmp_path) -> None:
    translation, _, _ = _make_incremental_project(tmp_path)
    repairer = ErrorRepairer()

    enabled = repairer.scan_folder(str(translation))
    assert [issue["language"] for issue in enabled.environment_issues] == ["chinese"]
    assert enabled.environment_issues[0]["issue_count"] == 2
    assert enabled.errors == {}

    disabled = repairer.scan_folder(str(translation), detect_environment=False)
    assert disabled.environment_issues == []


def test_fix_environment_issue_move_relocates_leftover(tmp_path) -> None:
    translation, leftover, strings = _make_incremental_project(tmp_path)
    repairer = ErrorRepairer()
    issue = repairer.detect_environment_issues(translation)[0]

    result = repairer.fix_environment_issue(issue, "move")

    assert result["ok"] is True
    assert result["action"] == "move"
    assert result["path"] == str(leftover)
    assert not leftover.exists()
    assert [path.name for path in (translation.parent).iterdir()] == ["chinese"]
    [moved] = list((tmp_path / "_renpybox_backup").iterdir())
    assert moved.name.startswith("chinese_new_")
    assert (moved / "strings.rpy").read_text(encoding="utf-8") == strings
    assert str(moved) in result["message"]


def test_fix_environment_issue_merge_passes_project_root(tmp_path, monkeypatch) -> None:
    translation, leftover, _ = _make_incremental_project(tmp_path)
    extractor_module = import_module("module.Extract.UnifiedExtractor")
    calls = {}

    def fake_merge(
        self, game_dir, tl_name, incremental_dir=None, *,
        clean_duplicates=True, config_snapshot=None, target_tl_dir=None,
    ):
        calls.update(
            game_dir=game_dir,
            tl_name=tl_name,
            incremental_dir=incremental_dir,
            clean_duplicates=clean_duplicates,
            target_tl_dir=target_tl_dir,
        )
        return SimpleNamespace(success=True, message="")

    monkeypatch.setattr(
        extractor_module.UnifiedExtractor, "merge_incremental_folder", fake_merge,
    )
    repairer = ErrorRepairer()
    issue = repairer.detect_environment_issues(translation)[0]

    result = repairer.fix_environment_issue(issue, "merge")

    assert result["ok"] is True
    assert result["action"] == "merge"
    assert "chinese" in result["message"]
    assert calls == {
        "game_dir": tmp_path,
        "tl_name": "chinese",
        "incremental_dir": leftover,
        "clean_duplicates": True,
        "target_tl_dir": translation,
    }
    assert result["backup"] in result["message"]
    assert Path(result["backup"]).is_file()


def test_fix_environment_issue_reports_failures_without_raising(tmp_path, monkeypatch) -> None:
    translation, leftover, _ = _make_incremental_project(tmp_path)
    extractor_module = import_module("module.Extract.UnifiedExtractor")
    repairer = ErrorRepairer()
    issue = repairer.detect_environment_issues(translation)[0]

    def failing_merge(self, game_dir, tl_name, incremental_dir=None, **kwargs):
        return SimpleNamespace(success=False, message="增量恢复路径不匹配")

    monkeypatch.setattr(
        extractor_module.UnifiedExtractor, "merge_incremental_folder", failing_merge,
    )
    failed = repairer.fix_environment_issue(issue, "merge")
    assert failed["ok"] is False
    assert "增量恢复路径不匹配" in failed["message"]
    assert leftover.is_dir()

    def exploding_merge(self, *args, **kwargs):
        raise RuntimeError("模拟崩溃")

    monkeypatch.setattr(
        extractor_module.UnifiedExtractor, "merge_incremental_folder", exploding_merge,
    )
    crashed = repairer.fix_environment_issue(issue, "merge")
    assert crashed["ok"] is False
    assert "模拟崩溃" in crashed["message"]

    assert repairer.fix_environment_issue(issue, "explode")["ok"] is False
    missing = repairer.fix_environment_issue(
        {"path": str(tmp_path / "missing_new"), "language": "chinese"}, "move",
    )
    assert missing["ok"] is False
    assert "失败" in missing["message"]
    # 失败不移动/删除残留目录；合并前写的只有 zip 备份，并在失败消息里给出位置。
    assert leftover.is_dir()
    assert failed["backup"] in failed["message"]
    assert crashed["backup"] in crashed["message"]
    backups = list((tmp_path / "_renpybox_backup").iterdir())
    assert backups and all(path.suffix == ".zip" for path in backups)


def test_fix_duplicate_strings_prefers_later_translated_entry(tmp_path) -> None:
    first = tmp_path / "a.rpy"
    second = tmp_path / "b.rpy"
    third = tmp_path / "c.rpy"
    first.write_text(
        'translate chinese strings:\n'
        '    old "Same"\n'
        '    new ""\n'
        "\n"
        '    old "Echo"\n'
        '    new "Echo"\n',
        encoding="utf-8",
    )
    second.write_text(
        'translate chinese strings:\n'
        '    old "Same"\n'
        '    new "同一"\n'
        "\n"
        '    old "Echo"\n'
        '    new "回声"\n',
        encoding="utf-8",
    )
    third_content = 'translate chinese strings:\n    old "Same"\n    new "另一个"\n'
    third.write_text(third_content, encoding="utf-8")

    count, files = ErrorRepairer().fix_duplicate_strings(str(tmp_path))

    assert (count, files) == (3, [str(first), str(third)])
    # 空译文与 new==old 的占位被注释，只移除空块头，第一条有效译文保留。
    assert first.read_text(encoding="utf-8") == (
        '    # old "Same"\n'
        '    # new ""\n'
        '\n'
        '    # old "Echo"\n'
        '    # new "Echo"\n'
    )
    assert second.read_text(encoding="utf-8") == (
        'translate chinese strings:\n'
        '    old "Same"\n'
        '    new "同一"\n'
        "\n"
        '    old "Echo"\n'
        '    new "回声"\n'
    )
    assert third.read_text(encoding="utf-8") == '    # old "Same"\n    # new "另一个"\n'
    [third_backup] = list(tmp_path.glob("c.rpy.*.bak"))
    assert third_backup.read_text(encoding="utf-8") == third_content
    assert ErrorRepairer().fix_duplicate_strings(str(tmp_path)) == (0, [])
    assert ErrorRepairer().scan_folder(str(tmp_path)).errors == {}


def test_fix_duplicate_strings_keeps_first_when_all_untranslated(tmp_path) -> None:
    first = tmp_path / "a.rpy"
    second = tmp_path / "b.rpy"
    first_content = 'translate chinese strings:\n    old "Same"\n    new ""\n'
    first.write_text(first_content, encoding="utf-8")
    second.write_text('translate chinese strings:\n    old "Same"\n    new "Same"\n', encoding="utf-8")

    assert ErrorRepairer().fix_duplicate_strings(str(tmp_path)) == (1, [str(second)])
    assert first.read_text(encoding="utf-8") == first_content


def test_auto_fix_duplicates_prefers_translated_entry_in_same_file(tmp_path) -> None:
    script = tmp_path / "dup.rpy"
    script.write_text(
        'translate chinese strings:\n'
        '    old "Same"\n'
        '    new ""\n'
        "\n"
        '    old "Same"\n'
        '    new "乙"\n',
        encoding="utf-8",
    )

    assert ErrorRepairer().auto_fix_file(
        str(script), fix_empty_blocks=False, fix_duplicates=True,
    ) == (True, 1)
    assert script.read_text(encoding="utf-8") == (
        'translate chinese strings:\n'
        '    # old "Same"\n'
        '    # new ""\n'
        "\n"
        '    old "Same"\n'
        '    new "乙"\n'
    )
    assert ErrorRepairer().auto_fix_file(
        str(script), fix_empty_blocks=False, fix_duplicates=True,
    ) == (True, 0)


def test_fix_duplicate_strings_reports_each_file_and_stops_before_guarded_write(tmp_path) -> None:
    for name in ("a", "b", "c"):
        (tmp_path / f"{name}.rpy").write_text(
            f'translate chinese strings:\n    old "Same"\n    new "{name}"\n', encoding="utf-8",
        )
    original_c = (tmp_path / "c.rpy").read_text(encoding="utf-8")
    reported: list[tuple[str, int]] = []
    guard_calls = {"n": 0}

    def before_write() -> None:
        guard_calls["n"] += 1
        if guard_calls["n"] == 3:
            raise RuntimeError("项目已切换")

    with pytest.raises(RuntimeError, match="项目已切换"):
        ErrorRepairer().fix_duplicate_strings(
            str(tmp_path),
            before_write=before_write,
            on_file=lambda path, count: reported.append((path, count)),
        )

    assert reported == [(str(tmp_path / "b.rpy"), 1)]
    assert (tmp_path / "c.rpy").read_text(encoding="utf-8") == original_c
    assert not list(tmp_path.glob("c.rpy.*.bak"))


def test_fix_duplicate_strings_rechecks_guard_after_backup_before_replace(tmp_path) -> None:
    (tmp_path / "a.rpy").write_text(
        'translate chinese strings:\n    old "Same"\n    new "甲"\n', encoding="utf-8",
    )
    duplicate = tmp_path / "b.rpy"
    original = 'translate chinese strings:\n    old "Same"\n    new "乙"\n'
    duplicate.write_text(original, encoding="utf-8")
    guard_calls = {"n": 0}

    def switch_owner_after_backup() -> None:
        guard_calls["n"] += 1
        if guard_calls["n"] == 2:
            raise RuntimeError("项目已切换")

    with pytest.raises(RuntimeError, match="项目已切换"):
        ErrorRepairer().fix_duplicate_strings(
            str(tmp_path), before_write=switch_owner_after_backup,
        )

    assert duplicate.read_text(encoding="utf-8") == original
    [backup] = list(tmp_path.glob("b.rpy.*.bak"))
    assert backup.read_text(encoding="utf-8") == original


def _stub_config_load(monkeypatch) -> None:
    # 真实合并会读全局配置；测试里只用默认值，避免依赖用户 config.json。
    config_module = import_module("module.Config")
    monkeypatch.setattr(config_module.Config, "load", lambda self, *args, **kwargs: self)


def _zip_files(archive: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(archive) as bundle:
        return {
            info.filename: bundle.read(info)
            for info in bundle.infolist()
            if not info.is_dir()
        }


def test_fix_environment_issue_real_merge_archives_originals_first(tmp_path, monkeypatch) -> None:
    _stub_config_load(monkeypatch)
    translation, leftover, strings = _make_incremental_project(tmp_path)
    leftover_content = strings + "\n    old \"Fresh\"\n    new \"新的\"\n"
    (leftover / "strings.rpy").write_text(leftover_content, encoding="utf-8")
    originals = {
        "chinese/script.rpy": (translation / "script.rpy").read_bytes(),
        "chinese_new/strings.rpy": (leftover / "strings.rpy").read_bytes(),
    }
    repairer = ErrorRepairer()
    issue = repairer.detect_environment_issues(translation)[0]

    result = repairer.fix_environment_issue(issue, "merge")

    assert result["ok"] is True, result
    archive = Path(result["backup"])
    assert archive.parent == tmp_path / "_renpybox_backup"
    assert archive.suffix == ".zip"
    assert archive.name in result["message"]
    assert _zip_files(archive) == originals
    assert not leftover.exists()
    merged = "".join(path.read_text(encoding="utf-8") for path in translation.rglob("*.rpy"))
    assert '"Fresh"' in merged and "新的" in merged


def test_fix_environment_issue_merge_targets_nonstandard_tl_layout(tmp_path, monkeypatch) -> None:
    _stub_config_load(monkeypatch)
    project = tmp_path / "proj"
    translation = project / "tl" / "chinese"
    leftover = project / "tl" / "chinese_new"
    translation.mkdir(parents=True)
    leftover.mkdir(parents=True)
    main_content = 'translate chinese strings:\n    old "Hello"\n    new "你好"\n'
    leftover_content = 'translate chinese strings:\n    old "Fresh"\n    new "新的"\n'
    (translation / "script.rpy").write_text(main_content, encoding="utf-8")
    (leftover / "fresh.rpy").write_text(leftover_content, encoding="utf-8")
    originals = {
        "chinese/script.rpy": (translation / "script.rpy").read_bytes(),
        "chinese_new/fresh.rpy": (leftover / "fresh.rpy").read_bytes(),
    }
    repairer = ErrorRepairer()
    [issue] = repairer.detect_environment_issues(translation)

    result = repairer.fix_environment_issue(issue, "merge")

    assert result["ok"] is True, result
    assert not (project / "game").exists()
    assert not leftover.exists()
    merged = "".join(path.read_text(encoding="utf-8") for path in translation.rglob("*.rpy"))
    assert '"Fresh"' in merged and '"Hello"' in merged
    assert _zip_files(Path(result["backup"])) == originals


def test_fix_environment_issue_aborts_merge_when_backup_fails(tmp_path, monkeypatch) -> None:
    translation, leftover, strings = _make_incremental_project(tmp_path)
    extractor_module = import_module("module.Extract.UnifiedExtractor")
    merged = []

    def failing_archive(archive, sources):
        raise OSError("磁盘已满")

    monkeypatch.setattr(ErrorRepairer, "_archive_dirs", staticmethod(failing_archive))
    monkeypatch.setattr(
        extractor_module.UnifiedExtractor, "merge_incremental_folder",
        lambda self, *args, **kwargs: merged.append(args),
    )
    repairer = ErrorRepairer()
    issue = repairer.detect_environment_issues(translation)[0]

    result = repairer.fix_environment_issue(issue, "merge")

    assert result["ok"] is False
    assert "备份失败" in result["message"] and "磁盘已满" in result["message"]
    assert "backup" not in result
    assert merged == []
    assert (leftover / "strings.rpy").read_text(encoding="utf-8") == strings
    assert (translation / "script.rpy").read_text(encoding="utf-8") == strings


def test_archive_dirs_removes_partial_zip_on_failure(tmp_path, monkeypatch) -> None:
    source = tmp_path / "chinese"
    source.mkdir()
    (source / "a.rpy").write_text("x", encoding="utf-8")
    archive = tmp_path / "backup" / "merge.zip"

    def broken_write(self, *args, **kwargs):
        raise OSError("写入失败")

    monkeypatch.setattr(zipfile.ZipFile, "write", broken_write)
    with pytest.raises(OSError, match="写入失败"):
        ErrorRepairer._archive_dirs(archive, [source])
    assert not archive.exists()


def test_merge_incremental_folder_explicit_target_skips_game_tl(tmp_path, monkeypatch) -> None:
    _stub_config_load(monkeypatch)
    extractor_module = import_module("module.Extract.UnifiedExtractor")
    project = tmp_path / "proj"
    translation = project / "tl" / "chinese"
    leftover = project / "tl" / "chinese_new"
    translation.mkdir(parents=True)
    leftover.mkdir(parents=True)
    (translation / "script.rpy").write_text(
        'translate chinese strings:\n    old "Hello"\n    new "你好"\n', encoding="utf-8",
    )
    (leftover / "fresh.rpy").write_text(
        'translate chinese strings:\n    old "Fresh"\n    new "新的"\n', encoding="utf-8",
    )

    result = extractor_module.UnifiedExtractor().merge_incremental_folder(
        project, "chinese", clean_duplicates=True, target_tl_dir=translation,
    )

    assert result.success is True, result.message
    assert result.tl_dir == translation
    # 未传 incremental_dir 时按显式目标目录推导同级 <lang>_new。
    assert result.incremental_dir == leftover
    assert not leftover.exists()
    assert not (project / "game").exists()
    merged = "".join(path.read_text(encoding="utf-8") for path in translation.rglob("*.rpy"))
    assert '"Fresh"' in merged


def test_merge_incremental_folder_journal_recovery_scoped_to_standard_layout(tmp_path, monkeypatch) -> None:
    extractor_module = import_module("module.Extract.UnifiedExtractor")
    recovered = []
    monkeypatch.setattr(
        extractor_module.UnifiedExtractor,
        "_recover_stale_incremental_state",
        lambda self, game_dir, tl_name: recovered.append((game_dir, tl_name)),
    )
    snapshot = SimpleNamespace(
        renpy_project_path="", renpy_game_folder="", renpy_tl_folder="", input_folder="", output_folder="",
    )
    extractor = extractor_module.UnifiedExtractor()
    missing = tmp_path / "missing_new"

    extractor.merge_incremental_folder(tmp_path, "chinese", missing, config_snapshot=snapshot)
    extractor.merge_incremental_folder(
        tmp_path, "chinese", missing, target_tl_dir=tmp_path / "game" / "tl" / "chinese",
    )
    assert recovered == [(tmp_path, "chinese"), (tmp_path, "chinese")]

    extractor.merge_incremental_folder(
        tmp_path, "chinese", missing, target_tl_dir=tmp_path / "tl" / "chinese",
    )
    assert len(recovered) == 2
    assert not (tmp_path / "game").exists()
