from importlib import import_module
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
