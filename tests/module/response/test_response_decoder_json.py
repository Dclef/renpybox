from module.Response.ResponseDecoder import ResponseDecoder


def test_jsonline_extracts_translation_from_extra_key_object():
    result = ResponseDecoder().decode_result(
        '{"index":1,"translation":"hello"}',
        expected_count=1,
    )

    assert result.dsts == ["hello"]
    assert result.method == "JSONLINE"


def test_structured_output_accepts_dict_items():
    result = ResponseDecoder().decode_result(
        '{"translations":[{"id":"a","text":"one"},{"index":2,"translation":"two"}]}',
        expected_count=2,
        structured=True,
    )

    assert result.dsts == ["one", "two"]
    assert result.method == "STRUCTURED"


def test_nested_json_string_is_sanitized_to_translation_leaf():
    result = ResponseDecoder().decode_result(
        '{"0":"{\\"index\\":1,\\"translation\\":\\"nested\\"}"}',
        expected_count=1,
    )

    assert result.dsts == ["nested"]
    assert result.method == "JSONLINE"


def test_explicit_json_failure_does_not_fall_back_to_numbered_text():
    result = ResponseDecoder().decode_result(
        '{"index":1,"comment":"1. polluted"}',
        expected_count=1,
    )

    assert result.dsts == []
    assert result.method == "JSON_FAIL"


def test_numbered_text_is_not_used_as_batch_fallback():
    result = ResponseDecoder().decode_result(
        "1. polluted",
        expected_count=1,
    )

    assert result.dsts == []
    assert result.method == "FAIL"


def test_single_plain_text_allows_renpy_brace_and_square_placeholders():
    brace_result = ResponseDecoder().decode_result(
        "{w}",
        expected_count=1,
        allow_plain_text_single=True,
    )
    square_result = ResponseDecoder().decode_result(
        "[eh]",
        expected_count=1,
        allow_plain_text_single=True,
    )

    assert brace_result.dsts == ["{w}"]
    assert brace_result.method == "PLAIN_TEXT"
    assert square_result.dsts == ["[eh]"]
    assert square_result.method == "PLAIN_TEXT"
