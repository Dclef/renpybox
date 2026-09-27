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
