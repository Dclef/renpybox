from module.Renpy.renpy_tl_core import escape_tl_string, unescape_tl_string


def test_translation_string_escape_round_trip_preserves_backslashes() -> None:
    original = 'Path C:\\games\\demo\\file "quoted"\n下一行'

    encoded = escape_tl_string(original)

    assert encoded == 'Path C:\\\\games\\\\demo\\\\file \\"quoted\\"\\n下一行'
    assert unescape_tl_string(encoded) == original


def test_replace_only_marker_is_scoped_to_one_entry():
    from module.Renpy.renpy_tl_core import has_replace_only_marker
    lines = ["translate chinese strings:", "", "    # renpybox: replace-only", '    old "A"', '    new "甲"', "", '    old "B"', '    new "乙"']
    assert has_replace_only_marker(lines, 3)
    assert not has_replace_only_marker(lines, 7)


def test_tl_extractor_marks_supplement_entries_for_proofreading_group():
    from module.Renpy.renpy_tl_core import parse_tl_document
    from module.Renpy.renpy_tl_io import RenpyTlItemExtractor
    doc = parse_tl_document([
        "translate chinese strings:", "", "    # renpybox: replace-only",
        '    old "Supplement"', '    new "补充"', "", '    old "Official"', '    new "官方"',
    ])
    items = RenpyTlItemExtractor().extract(doc, "strings.rpy")
    assert items[0].get_extra_field()["renpy"]["replace_only"] is True
    assert items[1].get_extra_field()["renpy"].get("replace_only", False) is False


def _label_block(indices: list[int], orphans: list[tuple[str, int]] | None = None) -> list[str]:
    """构造 Ren'Py 生成式 label 块：模板注释在前，译文语句在后。"""
    lines = ["translate chinese start:", ""]
    for index in indices:
        lines.append("    # game/script.rpy:%d" % index)
        lines.append('    # e "Line %d"' % index)
        lines.append('    e "译文 %d"' % index)
        for kind, value in orphans or []:
            if kind == "template" and value == index:
                lines.append('    # e "孤模板 %d"' % index)
            elif kind == "target" and value == index:
                lines.append('    e "孤译文 %d"' % index)
    lines.append("")
    return lines


def _reference_lcs_mapping(templates, targets) -> dict[int, int]:
    """整表 LCS 对齐：与优化前实现的等价参考。"""
    from module.Renpy.renpy_tl_core import statements_equal

    if not templates or not targets:
        return {}

    n = len(templates)
    m = len(targets)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            if statements_equal(templates[i], targets[j]):
                dp[i][j] = dp[i + 1][j + 1] + 1
            else:
                dp[i][j] = max(dp[i + 1][j], dp[i][j + 1])

    mapping: dict[int, int] = {}
    i = 0
    j = 0
    while i < n and j < m:
        if statements_equal(templates[i], targets[j]):
            mapping[templates[i].line_no] = targets[j].line_no
            i += 1
            j += 1
            continue
        if dp[i + 1][j] >= dp[i][j + 1]:
            i += 1
        else:
            j += 1
    return mapping


def _split_statements(block):
    from module.Renpy.renpy_tl_core import TlStmtKind

    return (
        [s for s in block.statements if s.stmt_kind == TlStmtKind.TEMPLATE and s.strict_key != ""],
        [s for s in block.statements if s.stmt_kind == TlStmtKind.TARGET and s.strict_key != ""],
    )


def test_match_tpl_to_target_matches_aligned_pairs_positionally() -> None:
    from module.Renpy.renpy_tl_core import match_tpl_to_target, parse_tl_document

    doc = parse_tl_document(_label_block(list(range(200))))
    templates, targets = _split_statements(doc.blocks[0])

    assert match_tpl_to_target(doc.blocks[0]) == {
        template.line_no: target.line_no
        for template, target in zip(templates, targets)
    }
    assert match_tpl_to_target(doc.blocks[0]) == _reference_lcs_mapping(templates, targets)


def test_banded_lcs_fallback_agrees_with_full_lcs_on_drifted_blocks() -> None:
    """漂移在带宽内时，带宽受限 DP 必须给出与整表相同的对齐。"""
    import random

    from module.Renpy.renpy_tl_core import (
        LCS_BAND,
        _banded_lcs_mapping,
        _exact_lcs_mapping,
        parse_tl_document,
    )

    rng = random.Random(19)
    for _ in range(40):
        size = rng.randint(2, 30)
        orphans: list[tuple[str, int]] = []
        for index in range(size):
            roll = rng.random()
            if roll < 0.15:
                orphans.append(("template", index))
            elif roll < 0.3:
                orphans.append(("target", index))
        doc = parse_tl_document(_label_block(list(range(size)), orphans))
        block = doc.blocks[0]
        templates, targets = _split_statements(block)

        # 抽样只覆盖“漂移不超过带宽”的输入；超出带宽的对齐按设计不再穷举。
        assert max(len(templates), len(targets)) - min(len(templates), len(targets)) <= LCS_BAND
        assert _exact_lcs_mapping(templates, targets) == _banded_lcs_mapping(
            templates, targets
        )


def test_large_label_block_matching_completes_without_quadratic_blowup() -> None:
    import time
    import tracemalloc

    from module.Renpy.renpy_tl_core import match_tpl_to_target, parse_tl_document

    block = parse_tl_document(_label_block(list(range(4000)))).blocks[0]

    tracemalloc.start()
    started = time.perf_counter()
    mapping = match_tpl_to_target(block)
    elapsed = time.perf_counter() - started
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    # 优化前：4,000 对约 36 秒、峰值约 521 MB（合成夹具，本机实测）。
    assert len(mapping) == 4000
    assert elapsed < 10.0, f"扫描耗时 {elapsed:.2f}s"
    assert peak < 160 * 1024 * 1024, f"峰值内存 {peak / 1e6:.1f}MB"



def test_replace_only_marker_allows_rpy_and_rpyc_location_comments():
    from module.Renpy.renpy_tl_core import has_replace_only_marker
    for location in ('# game/script.rpy:12', '# script.rpyc:12'):
        lines = ['# renpybox: replace-only', location, 'old "Hello"']
        assert has_replace_only_marker(lines, 2)


def _loose_writeback_lines() -> list[str]:
    """两条 LABEL 译文，语句形状刻意不同。

    骨架哈希把每个字面量换成同一个占位符，所以 `e "X"` 与 `e "Y"` 的骨架完全相同——
    想让"指向错行"被拦下来，必须让两条语句的形状本身不同（一条说话、一条音效），
    否则错配后的骨架照样对得上，测试就成了假绿。
    """
    return [
        'translate chinese start:',
        '',
        '    # e "First line"',
        '    e "译文一"',
        '',
        '    # nvl "Second line"',
        '    nvl "译文二"',
        '',
    ]


def _loose_items_from(lines: list[str]):
    from module.Renpy.renpy_tl_core import parse_tl_document
    from module.Renpy.renpy_tl_io import RenpyTlItemExtractor

    return RenpyTlItemExtractor().extract(parse_tl_document(lines), 'scene.rpy')


def _drop_digest(item) -> None:
    """抹掉 digest，模拟旧版 RenpyBox 写下的缓存行。"""
    renpy = item.get_extra_field()['renpy']
    assert isinstance(renpy, dict)
    renpy.pop('digest', None)


def _retarget(item, *, template_line: int | None = None, target_line: int | None = None) -> None:
    renpy = item.get_extra_field()['renpy']
    assert isinstance(renpy, dict)
    renpy['pair'] = dict(renpy['pair'])
    if template_line is not None:
        renpy['pair']['template_line'] = template_line
    if target_line is not None:
        renpy['pair']['target_line'] = target_line


def test_loose_writeback_rejects_item_whose_target_line_shape_differs():
    """digest 预检：条目指向形状不同的 target_line 时必须整条拒收，不能写错行。

    宽松路径放弃了 template_raw_sha1 / ast_key 这些强校验，唯一还能确认"这条 target_line
    属于这条 item"的依据就是骨架哈希与字面量数量。以前两者都不看，只要行号在范围内就
    直接改写——两次抽取（严格失败后 AST 重建）产生的错配条目会把译文写进别人的那一行，
    而 applied 照数上报。拒收后由 find_unapplied_translations 报出"未生效"，比静默写错行安全。
    """
    from module.Renpy.renpy_tl_io import RenpyTlLineUpdater

    lines = _loose_writeback_lines()
    items = _loose_items_from(lines)
    assert [item.get_src() for item in items] == ['First line', 'Second line']

    # 第二条（nvl）自称要写第 4 行（第一条 e 的 target_line），但 digest 仍按它自己那条
    # 记录。两条都只有一个字面量，所以只有骨架哈希能发现它认错了行；再抹掉字面量数量，
    # 并只提交这一条——否则它会被"同一 target_line 已被前一条写过"那项拦下，
    # 骨架校验删掉也照样能过，就测不出它到底有没有承重。
    renpy = items[1].get_extra_field()['renpy']
    assert isinstance(renpy, dict)
    assert renpy['digest']['target_string_count'] == 1
    renpy['digest'].pop('target_string_count')
    _retarget(items[1], target_line=4)
    items[1].set_dst('第二条译文')

    applied, skipped = RenpyTlLineUpdater().apply_items_to_lines_loose(lines, [items[1]])

    assert applied == 0, "指向别人 target_line 的条目不应被应用"
    assert skipped == 1
    assert lines[3] == '    e "译文一"', "被拒收的条目不得写进任何一行"
    assert lines[6] == '    nvl "译文二"'


def test_loose_writeback_rejects_item_whose_target_line_literal_count_differs():
    """字面量数量预检：骨架对得上但字面量个数不同时也要拒收。

    刻意用 `e "Name" "Body"` 这种真正的两个字面量语句。`e "Body {name}"` 里的 `{name}`
    仍在引号内部，扫描器只认得到 1 个字面量——造夹具时别把它当成两个字面量。
    """
    from module.Renpy.renpy_tl_io import RenpyTlLineUpdater

    lines = [
        'translate chinese start:',
        '',
        '    # e "First line"',
        '    e "译文一"',
        '',
        '    # e "Someone" "Second line"',
        '    e "某人" "译文二"',
        '',
    ]
    items = _loose_items_from(lines)
    assert len(items) == 2

    # 抹掉骨架哈希，只留字面量数量：这样这条校验才有判别力，也证明它是骨架缺失时的兜底
    # 而不是永远轮不到的死分支（build_line_skeleton 每个字面量都替换成同一个占位符，
    # 骨架一旦能比对，数量就已经被它蕴含了）。
    renpy = items[1].get_extra_field()['renpy']
    assert isinstance(renpy, dict)
    assert renpy['digest']['target_string_count'] == 2
    renpy['digest'].pop('target_skeleton_sha1')
    # 指到第 4 行 `e "译文一"`：那行只有 1 个字面量，本条目记的是 2 个。
    # 这里只交给这一条，避免和另一条抢同一行时把"谁拒收"搅混。
    _retarget(items[1], target_line=4)
    items[1].set_dst('第二条译文')

    applied, skipped = RenpyTlLineUpdater().apply_items_to_lines_loose(lines, [items[1]])

    assert applied == 0, "字面量数量对不上时不应被应用"
    assert skipped == 1
    assert lines[3] == '    e "译文一"', "被拒收的条目不得改写任何一行"
    assert lines[6] == '    e "某人" "译文二"'


def test_loose_writeback_rejects_item_whose_template_line_changed():
    """模板行预检：模板行被改过说明行号整体漂移，整条拒收而不是照着旧模板改写。"""
    from module.Renpy.renpy_tl_io import RenpyTlLineUpdater

    lines = _loose_writeback_lines()
    items = _loose_items_from(lines)

    # 模板行指到别人的模板注释：target 行本身没问题，但 base_code 会取自模板行，
    # 于是译文被套在错误的代码形状上。
    _retarget(items[1], template_line=3)
    items[0].set_dst('第一条译文')
    items[1].set_dst('第二条译文')

    applied, skipped = RenpyTlLineUpdater().apply_items_to_lines_loose(lines, items)

    assert applied == 1, "模板行漂移时不应被应用"
    assert skipped == 1
    assert lines[3] == '    e "第一条译文"'
    assert lines[6] == '    nvl "译文二"', "被拒收的条目不得改写任何一行"


def test_loose_writeback_never_lets_a_second_item_overwrite_one_target_line():
    """同行覆盖检测：两条无 digest 的旧缓存条目认领同一行时，先到者保留，后到者拒收。"""
    from module.Renpy.renpy_tl_io import RenpyTlLineUpdater

    lines = _loose_writeback_lines()
    items = _loose_items_from(lines)
    assert len(items) == 2

    # 两条都失去 digest（骨架比对无从下手），并让第二条也指向第 4 行。
    for item in items:
        _drop_digest(item)
    _retarget(items[1], target_line=4)
    items[0].set_dst('第一条译文')
    items[1].set_dst('第二条译文')

    applied, skipped = RenpyTlLineUpdater().apply_items_to_lines_loose(lines, items)

    assert applied == 1, "已写过的行不得被第二条覆盖"
    assert skipped == 1
    assert lines[3] == '    e "第一条译文"'
    assert lines[6] == '    nvl "译文二"'


def test_loose_writeback_still_applies_items_without_digest():
    """digest 缺失时必须照常写回：老缓存不能因为"无法校验"就整批失效。"""
    from module.Renpy.renpy_tl_io import RenpyTlLineUpdater

    lines = _loose_writeback_lines()
    items = _loose_items_from(lines)
    for item in items:
        _drop_digest(item)
    items[0].set_dst('第一条译文')
    items[1].set_dst('第二条译文')

    applied, skipped = RenpyTlLineUpdater().apply_items_to_lines_loose(lines, items)

    assert applied == 2
    assert skipped == 0
    assert lines[3] == '    e "第一条译文"'
    assert lines[6] == '    nvl "第二条译文"'


def test_parse_tl_document_never_raises_on_broken_text():
    """热路径上的解析器必须继续容忍畸形输入，不能因为加校验就改变行为。"""
    from module.Renpy.renpy_tl_core import parse_tl_document

    document = parse_tl_document(['translate chinese start:', '', '    e "未闭合'])

    assert len(document.blocks) == 1


def test_validate_tl_document_rejects_unterminated_quote():
    """未闭合引号在解析器眼里只是"这行没有字符串"，必须在校验器里被拦下。"""
    import pytest

    from module.Renpy.renpy_tl_core import TlSyntaxError, validate_tl_document

    text = "\n".join(
        [
            "translate chinese start:",
            "",
            '    e "第一条"',
            '    e "译文" + "未闭合',
            "",
        ]
    )

    with pytest.raises(TlSyntaxError) as excinfo:
        validate_tl_document(text)

    # 报错的行号必须指向真正出问题的那行，否则提示对用户毫无意义。
    assert "第 4 行" in str(excinfo.value)


def test_validate_tl_document_accepts_ordinary_tl_text():
    """常见形态必须零误报：带占位符、带转义、带 Ren'Py 标记、行内注释都要过。"""
    from module.Renpy.renpy_tl_core import validate_tl_document

    text = "\n".join(
        [
            "translate chinese strings:",
            "",
            "    # game/scripts/lab.rpy:12",
            '    old "Hello, [player_name]!"',
            '    new "你好，[player_name]！"',
            "",
            "translate chinese start:",
            "",
            '    # renpybox: replace-only',
            '    # e "She said \\"yes\\"."',
            '    e "她说了\\"是\\"。"',
            "    $ flag = True  # 带行内注释",
            '    python:',
            '        store.name = "x"',
            "",
        ]
    )

    document = validate_tl_document(text)

    assert len(document.blocks) == 2


def test_validate_tl_document_accepts_backslash_before_closing_quote_escape():
    """末尾的转义反斜杠不应被当成"未闭合"——它自己就是合法的字面量内容。"""
    from module.Renpy.renpy_tl_core import validate_tl_document

    text = "\n".join(
        [
            "translate chinese strings:",
            "",
            '    old "C:\\\\path\\\\"',
            '    new "C:\\\\路径\\\\"',
            "",
        ]
    )

    assert len(validate_tl_document(text).blocks) == 1


def test_atomic_write_text_validator_failure_leaves_target_untouched(tmp_path):
    """校验失败时目标文件必须保持原样——这正是 validator 存在的意义。"""
    import pytest

    from module.File.AtomicWrite import atomic_write_text
    from module.Renpy.renpy_tl_core import validate_tl_document

    target = tmp_path / "broken.rpy"
    target.write_text('translate chinese start:\n\n    e "原有译文"\n', encoding="utf-8")

    with pytest.raises(ValueError):
        atomic_write_text(
            target,
            'translate chinese start:\n\n    e "新译文" + "未闭合\n',
            validator=validate_tl_document,
        )

    assert 'e "原有译文"' in target.read_text(encoding="utf-8")
    assert list(tmp_path.iterdir()) == [target], "临时文件必须被清理"
