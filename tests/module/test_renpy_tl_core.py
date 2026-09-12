from module.Renpy.renpy_tl_core import escape_tl_string, unescape_tl_string


def test_translation_string_escape_round_trip_preserves_backslashes() -> None:
    original = 'Path C:\\games\\demo\\file "quoted"\n下一行'

    encoded = escape_tl_string(original)

    assert encoded == 'Path C:\\\\games\\\\demo\\\\file \\"quoted\\"\\n下一行'
    assert unescape_tl_string(encoded) == original
