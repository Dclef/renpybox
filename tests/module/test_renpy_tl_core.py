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
