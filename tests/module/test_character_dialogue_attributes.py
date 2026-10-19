"""Ren'Py say statements with persistent/temporary image attributes."""
from __future__ import annotations

import pytest

from module.Workbench.CharacterScanner import CharacterScanner


@pytest.mark.parametrize("statement", [
    'e happy "Hello there."',
    'e happy -sad "Hello there." with dissolve',
    'e @ sad "Hello there."',
    'e happy @ sad -blush "Hello there."',
    "e happy 'Hello there.'",
    'e "Hello there."',
])
def test_dialogue_parser_accepts_image_attributes(statement):
    match = CharacterScanner.RE_DIALOGUE_LINE.search(statement)
    assert match is not None
    assert match.group("speaker") == "e"
    assert match.group("quote")[1:-1] == "Hello there."


@pytest.mark.parametrize("statement", [
    'e happy\n"Not the same line."',
    'e\n"Not the same line."',
    'e = "A Python assignment."',
    '# e happy "A commented line."',
])
def test_dialogue_parser_does_not_cross_lines_or_match_code(statement):
    assert CharacterScanner.RE_DIALOGUE_LINE.search(statement) is None


def test_attribute_only_speakers_keep_names_counts_and_samples(tmp_path):
    game = tmp_path / "game"
    game.mkdir()
    (game / "characters.rpy").write_text(
        'define e = Character("Eileen")\ndefine l = Character("Lucy")\ndefine m = Character("Mona")\n',
        encoding="utf-8",
    )
    (game / "script.rpy").write_text(
        'label start:\n    e happy "Hello there."\n    l @ sad "Hi there."\n    m "Plain line."\n',
        encoding="utf-8",
    )
    result = CharacterScanner().scan_project(tmp_path)
    assert result.names == {"Eileen", "Lucy", "Mona"}
    assert result.speaker_counts == {"Eileen": 1, "Lucy": 1, "Mona": 1}
    assert result.speaker_samples["Eileen"] == ["Hello there."]
    assert result.speaker_samples["Lucy"] == ["Hi there."]
