import pytest

from module.Engine.TaskRequester import TaskRequester
from module.Response.ResponseDecoder import DecodedTranslation, ResponseDecoder


def test_structured_output_reorders_indexed_records():
    result = ResponseDecoder().decode_result(
        """{
            "translations": [
                {"request_index": 1, "text": "two"},
                {"request_index": 0, "text": "one"}
            ],
            "new_glossary": [{"src": "猫", "dst": "cat"}]
        }""",
        expected_count = 2,
        structured = True,
    )

    assert result.translations == (
        DecodedTranslation(request_index = 0, text = "one"),
        DecodedTranslation(request_index = 1, text = "two"),
    )
    assert result.indexed_records == result.translations
    assert result.dsts == ["one", "two"]
    assert result.new_glossary == ({"src": "猫", "dst": "cat"},)
    assert result.glossarys == [{"src": "猫", "dst": "cat"}]
    assert result.method == "STRUCTURED"


def test_jsonline_output_reorders_indexed_records_inside_markdown_fence():
    result = ResponseDecoder().decode_result(
        """```jsonline
{"request_index":2,"text":"three"}
{"request_index":0,"text":"one"}
{"request_index":1,"text":"two"}
```""",
        expected_count = 3,
    )

    assert result.translations == (
        DecodedTranslation(request_index = 0, text = "one"),
        DecodedTranslation(request_index = 1, text = "two"),
        DecodedTranslation(request_index = 2, text = "three"),
    )
    assert result.method == "MARKDOWN_JSONLINE"


@pytest.mark.parametrize(
    ("response", "expected_count", "structured"),
    (
        (
            '{"request_index":0,"text":"one"}\n'
            '{"request_index":0,"text":"duplicate"}',
            2,
            False,
        ),
        ('{"request_index":0,"text":"missing one"}', 2, False),
        (
            '{"request_index":-1,"text":"negative"}\n'
            '{"request_index":0,"text":"zero"}',
            2,
            False,
        ),
        (
            '{"request_index":0,"text":"zero"}\n'
            '{"request_index":2,"text":"out of range"}',
            2,
            False,
        ),
        ('{"request_index":0.0,"text":"float"}', 1, False),
        ('{"request_index":"0","text":"numeric string"}', 1, False),
        ('{"request_index":true,"text":"boolean"}', 1, False),
        (
            '{"request_index":1,"text":"one based"}\n'
            '{"request_index":2,"text":"one based"}',
            2,
            False,
        ),
        (
            '{"request_index":0,"text":"zero"}\n'
            '{"request_index":1,"text":"one"}\n'
            '{"request_index":2,"text":"extra"}',
            2,
            False,
        ),
        ('{"request_index":0,"text":42}', 1, False),
        ('{"request_index":0}', 1, False),
        ('{"text":"missing index"}', 1, False),
        ('{"request_index":0,"text":"ok","comment":"extra field"}', 1, False),
        (
            '{"request_index":0,"text":"first"} '
            '{"request_index":0,"text":"second"}',
            1,
            False,
        ),
        ('{"0":"legacy positional value"}', 1, False),
        ('{"index":1,"translation":"legacy fields"}', 1, False),
        (
            '{"translations":['
            '{"request_index":0,"text":"zero"},'
            '{"request_index":0,"text":"duplicate"}]}' ,
            2,
            True,
        ),
        (
            '{"translations":[{"request_index":1,"text":"one based"}]}',
            1,
            True,
        ),
        (
            '{"translations":[{"request_index":"0","text":"string index"}]}',
            1,
            True,
        ),
    ),
)
def test_invalid_indexed_responses_are_rejected(response, expected_count, structured):
    result = ResponseDecoder().decode_result(
        response,
        expected_count = expected_count,
        structured = structured,
    )

    assert result.translations == ()
    assert result.dsts == []
    assert result.method == "JSON_FAIL"


def test_missing_jsonline_record_is_not_padded():
    result = ResponseDecoder().decode_result(
        '{"request_index":0,"text":"only record"}',
        expected_count = 3,
    )

    assert result.translations == ()
    assert result.dsts == []


def test_json_repair_can_fix_syntax_but_cannot_invent_request_index():
    repaired = ResponseDecoder().decode_result(
        "{'request_index': 0, 'text': 'fixed syntax'}",
        expected_count = 1,
    )
    missing_index = ResponseDecoder().decode_result(
        "{'text': 'must still fail'}",
        expected_count = 1,
    )

    assert repaired.translations == (DecodedTranslation(0, "fixed syntax"),)
    assert missing_index.translations == ()
    assert missing_index.method == "JSON_FAIL"


def test_translation_text_that_contains_json_is_not_reinterpreted():
    nested = '{"request_index":7,"text":"literal"}'
    result = ResponseDecoder().decode_result(
        '{"request_index":0,"text":"{\\"request_index\\":7,\\"text\\":\\"literal\\"}"}',
        expected_count = 1,
    )

    assert result.translations == (DecodedTranslation(0, nested),)


def test_plain_text_requires_explicit_single_line_mode():
    disabled = ResponseDecoder().decode_result("hello", expected_count = 1)
    enabled = ResponseDecoder().decode_result(
        "hello",
        expected_count = 1,
        allow_plain_text_single = True,
    )
    multiline = ResponseDecoder().decode_result(
        "first\nsecond",
        expected_count = 1,
        allow_plain_text_single = True,
    )
    batch = ResponseDecoder().decode_result(
        "hello",
        expected_count = 2,
        allow_plain_text_single = True,
    )

    assert disabled.translations == ()
    assert enabled.translations == (DecodedTranslation(0, "hello"),)
    assert enabled.method == "PLAIN_TEXT"
    assert multiline.translations == ()
    assert batch.translations == ()


def test_single_plain_text_allows_renpy_placeholders():
    for value in ("{w}", "[eh]"):
        result = ResponseDecoder().decode_result(
            value,
            expected_count = 1,
            allow_plain_text_single = True,
        )
        assert result.translations == (DecodedTranslation(0, value),)


def test_structured_and_jsonline_protocols_are_not_interchangeable():
    structured_as_jsonline = ResponseDecoder().decode_result(
        '{"translations":[{"request_index":0,"text":"hello"}]}',
        expected_count = 1,
    )
    jsonline_as_structured = ResponseDecoder().decode_result(
        '{"request_index":0,"text":"hello"}',
        expected_count = 1,
        structured = True,
    )

    assert structured_as_jsonline.translations == ()
    assert jsonline_as_structured.translations == ()


def test_task_requester_schema_and_direct_provider_adapter_use_indexed_records():
    item_schema = TaskRequester.TRANSLATION_RESULT_SCHEMA["properties"]["translations"]["items"]
    assert item_schema["required"] == ["request_index", "text"]
    assert item_schema["properties"]["request_index"] == {
        "type": "integer",
        "minimum": 0,
    }
    assert item_schema["properties"]["text"] == {"type": "string"}
    assert item_schema["additionalProperties"] is False

    response = TaskRequester._build_translation_jsonline_response(None, ["one", "two"])
    decoded = ResponseDecoder().decode_result(response, expected_count = 2)
    assert decoded.translations == (
        DecodedTranslation(0, "one"),
        DecodedTranslation(1, "two"),
    )
