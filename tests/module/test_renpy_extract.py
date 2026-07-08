from module.Renpy.renpy_extract import ExtractFromFile


def extract_from_text(tmp_path, content: str, filter_length: int = 20) -> set[str]:
    path = tmp_path / "script.rpy"
    path.write_text(content, encoding="utf-8")
    return ExtractFromFile(str(path), True, filter_length, False, False, False)


def test_extract_from_file_keeps_short_menu_options_with_suffixes(tmp_path):
    content = '''menu:
    "Option A"(_choice='a'):
        jump label_a
    "Option B":
        pass
    "Option C" if player.money >= 20:
        jump label_c
    "Option D":
        pass
menu location_hall.choice:
    "Option E" if event.peek(choice='e', who=character):
        return event.emit(choice='e', who=character)
    "Option F":
        pass
'''

    result = extract_from_text(tmp_path, content)

    assert {"Option A", "Option B", "Option C", "Option D", "Option E", "Option F"} <= result
    assert "a" not in result
    assert "e" not in result


def test_extract_from_file_ignores_contraction_apostrophes_inside_double_quotes(tmp_path):
    content = '''"You're, ain't"
'''

    result = extract_from_text(tmp_path, content, filter_length=9999)

    assert result == set()


def test_extract_from_file_ignores_single_quoted_control_conditions(tmp_path):
    content = '''if state == 'start':
    pass
elif state == 'middle':
    pass
while state == 'loop':
    pass
if ready: 'Inline translatable text'
'''

    result = extract_from_text(tmp_path, content, filter_length=5)

    assert {"start", "middle", "loop"}.isdisjoint(result)
    assert "Inline translatable text" in result