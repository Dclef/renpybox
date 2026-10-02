"""译文里混入系统提示词段落时必须判为异常回复。

真实故障：一次翻译把提示词的 5 个段落按连续 request_index 逐条填回，
写进了游戏的 script.rpy。相似度检查因 dst/src 长度比越过 3.0 而提前
返回“不相似”，其余三道检查也都不针对这种情况，于是全部放行。
"""

from pathlib import Path

import pytest

from base.Base import Base
from base.BaseLanguage import BaseLanguage
from module.Cache.CacheItem import CacheItem
from module.Config import Config
from module.PromptBuilder import PromptBuilder
from module.Response.ResponseChecker import ResponseChecker
from module.Text.TextHelper import TextHelper


PROMPT_ROOT = Path(__file__).resolve().parents[3] / "resource" / "prompt"
PROMPT_TITLE_FILES = (
    *PromptBuilder.MODE_FILES.values(),
    "engineering.txt",
    *PromptBuilder.PROTOCOL_FILES.values(),
    *PromptBuilder.STYLE_FILES.values(),
)


# 实际泄漏进游戏文件的五段（截断保留特征），与提示词段落一一对应
LEAKED_SECTIONS = (
    "基础模式：COMMON\n你是专业的游戏本地化译者。将英文文本忠实、准确、自然地翻译成中文。",
    "### 不可覆盖的工程协议\n本节以及紧随其后的输出协议高于基础模式、写作风格。",
    "### 输出协议：STRUCTURED\n只返回一个 JSON 对象（类型：json_object），不要使用 Markdown。",
    "### 写作风格：R18\n忠实保留原作中成人、粗俗、暴力或敏感内容的语义与强度。",
    "控制字符示例：\n{/b}, {b}",
)

ENGLISH_SECTIONS = (
    "### Base Mode: COMMON\nYou are a professional game localization translator.",
    "### Non-Overridable Engineering Protocol\nThis section outranks the base mode.",
    "### Output Protocol: STRUCTURED\nReturn exactly one JSON object.",
    "### Writing Style: R18\nPreserve the semantics and intensity of adult content.",
    "Control Characters Samples:\n{/b}, {b}",
)

# 含提示词词汇但属于正常译文，不得误判
INNOCENT_TRANSLATIONS = (
    "你好，今天天气不错。",
    "下午好。这是新闻。",
    "复制 Markdown",
    "将 traceback.txt 文件复制到剪贴板，作为 Markdown 用于 Discord。",
    "基础训练已完成",
    "他说：输出协议已经准备好了吗",
    "这是一种写作风格的选择",
    "开始游戏",
    "{b}加粗{/b}文本",
    "",
)


# 从实际提示词资源读取标题，避免测试与资源文件各维护一份标题清单。
def _load_prompt_title_cases():
    cases = []
    for language in ("zh", "en"):
        language_root = PROMPT_ROOT / language
        for filename in PROMPT_TITLE_FILES:
            path = language_root / filename
            lines = path.read_text(encoding="utf-8-sig").splitlines()
            cases.append((language, filename, lines[0] if lines else ""))
    return tuple(cases)


PROMPT_TITLE_CASES = _load_prompt_title_cases()


@pytest.mark.parametrize("dst", LEAKED_SECTIONS)
def test_detects_leaked_chinese_prompt_sections(dst):
    assert ResponseChecker.has_prompt_echo(dst) is True


@pytest.mark.parametrize("dst", ENGLISH_SECTIONS)
def test_detects_leaked_english_prompt_sections(dst):
    assert ResponseChecker.has_prompt_echo(dst) is True


@pytest.mark.parametrize("dst", INNOCENT_TRANSLATIONS)
def test_does_not_flag_normal_translations(dst):
    assert ResponseChecker.has_prompt_echo(dst) is False


def test_non_string_input_is_not_flagged():
    assert ResponseChecker.has_prompt_echo(None) is False
    assert ResponseChecker.has_prompt_echo(123) is False


@pytest.mark.parametrize(
    ("language", "filename", "title"),
    PROMPT_TITLE_CASES,
    ids=lambda value: str(value),
)
def test_prompt_resource_titles_are_recognized(language, filename, title):
    assert title.lstrip().startswith("###"), f"{language}/{filename}: 缺少标题行"
    assert ResponseChecker.has_prompt_echo(title), f"{language}/{filename}: {title}"


@pytest.mark.parametrize("target_language", (BaseLanguage.Enum.ZH, BaseLanguage.Enum.EN))
def test_single_line_control_sample_titles_are_recognized(target_language):
    builder = PromptBuilder(Config(target_language=target_language))
    title_and_samples = builder.build_single_line_control_samples(["{b}"])

    assert ResponseChecker.has_prompt_echo(title_and_samples)


def test_similarity_check_alone_cannot_catch_prompt_echo():
    """锁定根因：长度比越过 3.0 时相似度检查提前放行。

    这里必须用现场原始长度（117 字对 32 字，比值 3.65），截断样本的
    长度比不足 3.0，就复现不出「因为太长所以被放行」这个失效路径。
    """
    src = "Good afternoon. Here's the news."
    dst = (
        "基础模式：COMMON\n你是专业的游戏本地化译者。将英文文本忠实、准确、自然地"
        "翻译成中文，保持人物语气、叙事视角、情绪强度和上下文一致性。完整翻译对话、"
        "旁白、界面文字和描述性内容；代码、专有品牌以及明确无需翻译的内容按工程协议处理。"
    )

    assert len(dst) / len(src) > 3.0
    assert ResponseChecker.has_prompt_echo(dst) is True
    # 原有四道检查全部放行，所以必须有独立的回显拦截。
    assert ResponseChecker.has_high_similarity(src, dst) is False
    assert ResponseChecker.has_translation_error_marker(dst) is False
    assert ResponseChecker.has_mixed_language_leakage(src, dst) is False
    assert ResponseChecker.RE_DEGRADATION.search(dst) is None


def test_disjoint_characters_short_circuit_skips_the_expensive_measures(monkeypatch):
    """字符集不相交必须真的跳过 SequenceMatcher 与 2-gram Jaccard。

    真实项目 57564 对里 62% 落在这条支上，整轮从 3.9s 降到 2.0s。
    只断言返回值是锁不住这个优化的——没有短路时 `SequenceMatcher`
    与 Jaccard 对不相交的两串本来也返回 0，测试照样绿。这里把两个昂贵
    度量换成会炸的替身，短路一旦被删掉就会立刻失败。
    """
    calls: list[str] = []

    def _boom_sequence(x: str, y: str) -> float:
        calls.append("sequence")
        raise AssertionError("字符集不相交时不该再跑 SequenceMatcher")

    def _boom_jaccard(x: str, y: str, n: int = 2) -> float:
        calls.append("jaccard")
        raise AssertionError("字符集不相交时不该再跑 2-gram Jaccard")

    monkeypatch.setattr(TextHelper, "check_similarity_by_sequence", _boom_sequence)
    monkeypatch.setattr(TextHelper, "check_similarity_by_ngram_jaccard", _boom_jaccard)

    src = "A quick brown fox jumps over the lazy dog"
    dst = "敏捷的棕色狐狸跳过那只懒惰的狗"
    assert not (set(src) & set(dst))
    assert 0.3 < len(dst) / len(src) < 3.0
    assert ResponseChecker.has_high_similarity(src, dst) is False
    assert calls == []


def test_disjoint_characters_short_circuit_still_keeps_similar_texts_caught():
    """字符集不相交可以提前判 False，但不能吃掉真相似。

    `has_high_similarity` 在长度比之后加了一道 `set(src) & set(dst)` 短路：
    中日文与英文互不相交的真实数据有 62% 落在这一支。它的正确性依赖
    "没有公共字符 ⇒ 子串包含 / SequenceMatcher / 2-gram Jaccard 三种算法
    都必然返回 0"，所以这个测试同时钉住两侧：不相交的一对判 False，
    只共用一个字符的高相似仍必须判 True。
    """
    disjoint_src = "A quick brown fox jumps over the lazy dog"
    disjoint_dst = "敏捷的棕色狐狸跳过那只懒惰的狗"
    assert not (set(disjoint_src) & set(disjoint_dst))
    assert 0.3 < len(disjoint_dst) / len(disjoint_src) < 3.0
    assert ResponseChecker.has_high_similarity(disjoint_src, disjoint_dst) is False

    # 只共用一个字符 '!'，但整体仍是高相似，必须照旧判 True。
    near_src = "Open the door quick."
    near_dst = "Open the door quick!"
    assert set(near_src) & set(near_dst)
    assert TextHelper.check_similarity_by_sequence(near_src, near_dst) > 0.90
    assert ResponseChecker.has_high_similarity(near_src, near_dst) is True


def test_disjoint_characters_short_circuit_is_conservative_for_contained_text():
    """短路必须落在子串包含判定之后，且不能改变单字符短文本的既有结论。

    `src == dst` 的早返回在短路之前，所以 `"?"`/`"."` 这类单字符串
    仍按"完全一致"判 True；曾试过用 2-gram 交集为空做剪枝，那会把
    这 354 对真值翻成 False，已被否决。
    """
    assert ResponseChecker.has_high_similarity("?", "?") is True
    assert ResponseChecker.has_high_similarity("...", "...") is True

    # 一方是另一方的子串必然共用字符，短路不得把它误判成不相似。
    # 这里的子串比例 10/12 已经越过 0.85 门槛，所以命中的是子串分支。
    contained_src = "hello there"
    contained_dst = "hello there!"
    assert set(contained_src) & set(contained_dst)
    assert len(contained_src) / len(contained_dst) > 0.85
    assert ResponseChecker.has_high_similarity(contained_src, contained_dst) is True


def _make_item(src: str, dst: str) -> CacheItem:
    item = CacheItem.from_dict({
        "src": src,
        "dst": dst,
        "status": Base.TranslationStatus.TRANSLATED,
    })
    return item


def test_check_lines_reports_fake_reply_for_prompt_echo():
    src = "Good afternoon. Here's the news."
    dst = LEAKED_SECTIONS[0]
    item = _make_item(src, dst)
    checker = ResponseChecker(Config(), [item])

    checks = checker.check_lines(
        [src],
        [dst],
        CacheItem.TextType.RENPY,
        line_items=[item],
    )

    assert checks == [ResponseChecker.Error.LINE_ERROR_FAKE_REPLY]


def test_prompt_echo_beats_rule_filter_shortcut():
    """短原文会命中 RuleFilter/LanguageFilter 直接放行，回显必须先判。"""
    src = "..."
    dst = LEAKED_SECTIONS[2]
    item = _make_item(src, dst)
    checker = ResponseChecker(Config(), [item])

    checks = checker.check_lines(
        [src],
        [dst],
        CacheItem.TextType.RENPY,
        line_items=[item],
    )

    assert checks == [ResponseChecker.Error.LINE_ERROR_FAKE_REPLY]


@pytest.mark.parametrize(
    ("src", "dst"),
    (
        ("Output Protocol: JSON", "输出协议：JSON"),
        ("Writing Style: Literary", "写作风格：文学"),
        ("Non-Overridable Engineering Protocol", "不可覆盖的工程协议"),
    ),
)
def test_prompt_heading_translation_is_not_fake_reply(src, dst):
    assert ResponseChecker.has_prompt_echo(src) is True
    assert ResponseChecker.has_prompt_echo(dst) is True

    item = _make_item(src, dst)
    checker = ResponseChecker(Config(), [item])
    checks = checker.check_lines(
        [src],
        [dst],
        CacheItem.TextType.RENPY,
        line_items=[item],
    )

    assert checks == [ResponseChecker.Error.NONE]
