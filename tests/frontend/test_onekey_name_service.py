from frontend.RenpyToolbox.OneKeyNameService import OneKeyNameService


def test_categorize_term() -> None:
    assert OneKeyNameService._categorize_term("Moon City") == "地名"
    assert OneKeyNameService._categorize_term("Silver Sword") == "物品"
    assert OneKeyNameService._categorize_term("Alice", default="角色") == "角色"


def test_clean_text_for_type() -> None:
    assert OneKeyNameService._clean_text_for_type("  {color=#fff}Alice{/color}\u3000") == "Alice"
    assert OneKeyNameService._clean_text_for_type("") == ""


def test_should_ignore_extracted_name() -> None:
    assert OneKeyNameService._should_ignore_extracted_name("A") is True
    assert OneKeyNameService._should_ignore_extracted_name("A.") is True
    assert OneKeyNameService._should_ignore_extracted_name("x_y") is True
    assert OneKeyNameService._should_ignore_extracted_name("Alice") is False


def test_reset_replaces_cached_instance() -> None:
    OneKeyNameService.reset()
    first = OneKeyNameService.get()
    first._ner_model = object()
    first._ner_model_loaded = True

    OneKeyNameService.reset()
    second = OneKeyNameService.get()

    assert second is not first
    assert second._ner_model is None
    assert second._ner_model_loaded is False
