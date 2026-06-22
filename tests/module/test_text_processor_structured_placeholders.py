from module.Cache.CacheItem import CacheItem
from module.Config import Config
from module.TextProcessor import TextProcessor


def test_honorific_bridge_uses_structured_tokens_and_reuses_placeholder_token():
    item = CacheItem(
        src="Mr.[eh] took [eh]'s hat",
        text_type=CacheItem.TextType.RENPY,
    )
    processor = TextProcessor(Config(), item)

    processor.pre_process()

    assert processor.srcs == ["Mr.<n0/> took <n0/>'s hat"]


def test_structured_token_restore_handles_exact_and_spaced_variants():
    restored = TextProcessor._replace_bridge_token_with_placeholder(
        "< n0 /> says <n0/>",
        "<n0/>",
        "[eh]",
    )

    assert restored == "[eh] says [eh]"


def test_name_extraction_does_not_remove_inline_square_brackets():
    item = CacheItem(src="source [eh] text", name_src="Alice")
    processor = TextProcessor(Config(), item)

    name, srcs, dsts = processor.extract_name(
        ["source [eh] text"],
        ["translated [eh] text"],
        item,
    )

    assert name is None
    assert srcs == ["source [eh] text"]
    assert dsts == ["translated [eh] text"]
