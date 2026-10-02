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


def test_check_drops_blank_only_preserve_tokens_and_still_flags_mismatches():
    """占位符比对必须抓到换名/丢失，且对空白差异免疫。

    这是 `compact()` 那次改写的语义底线：把过滤条件和产出的 `RE_BLANK.sub`
    合并成一次计算之后，判定的结果不能变。
    """
    item = CacheItem(text_type=CacheItem.TextType.RENPY)
    processor = TextProcessor(Config(), item)
    text_type = item.get_text_type()

    # 同一个占位符，两边只差空白 ⇒ 等价
    assert processor.check("[player] 你好", "[player]你好", text_type) is True
    # 多余空白同样不算差异
    assert processor.check("{b}Hello{/b} world", "{b}Hello{/b}  world", text_type) is True
    # 没有任何占位符的普通句子天然通过
    assert processor.check("no tokens here", "no tokens here", text_type) is True
    # 占位符被换掉必须抓到
    assert processor.check("[player] 你好", "[name] 你好", text_type) is False
    # 占位符被丢掉必须抓到
    assert processor.check("[player] 你好", "你好", text_type) is False


def test_check_runs_the_blank_sub_once_per_matched_segment(monkeypatch):
    """性能约束：每个匹配片段只能做一次 `RE_BLANK.sub`。

    语义测试抓不住这条——因为在默认规则下那个 `!= ""` 过滤本来就打不中，
    删掉它结果也不变，只有"跑了几次"会变。这里数调用次数。

    `re.Pattern.sub` 是只读属性，monkeypatch 改不动，所以替换整个 `RE_BLANK`
    对象成一个转发计数用的替身。
    """
    item = CacheItem(text_type=CacheItem.TextType.RENPY)
    processor = TextProcessor(Config(), item)
    text_type = item.get_text_type()

    calls = {"count": 0}
    real_blank = TextProcessor.RE_BLANK

    class CountingBlank:
        def sub(self, repl, string, *args, **kwargs):
            calls["count"] += 1
            return real_blank.sub(repl, string, *args, **kwargs)

    src = "[player] 你好 {b}走{/b}"
    dst = "[player] 你好 {c}走{/c}"

    # 期望值由规则自己算出来，不写死段数：默认规则当前每串匹配 3 段
    # （"[player] "、" {b}"、"{/b}"），但规则将来增删时这个用例不该失效。
    rule = processor.get_re_check(
        custom=processor.config.text_preserve_enable,
        text_type=text_type,
    )
    matched = sum(1 for _ in rule.finditer(src)) + sum(1 for _ in rule.finditer(dst))
    assert matched > 0, "规则没匹配到任何片段，用例就失去意义了"

    monkeypatch.setattr(TextProcessor, "RE_BLANK", CountingBlank())

    assert processor.check(src, dst, text_type) is False

    # 每个匹配片段一次 sub。旧写法是两倍（过滤条件一次、产出一次）。
    assert calls["count"] == matched
