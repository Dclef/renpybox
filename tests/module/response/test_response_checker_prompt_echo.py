"""译文里混入系统提示词段落时必须判为异常回复。

真实故障：一次翻译把提示词的 5 个段落按连续 request_index 逐条填回，
写进了游戏的 script.rpy。相似度检查因 dst/src 长度比越过 3.0 而提前
返回“不相似”，其余三道检查也都不针对这种情况，于是全部放行。
"""

import pytest

from base.Base import Base
from module.Cache.CacheItem import CacheItem
from module.Config import Config
from module.Response.ResponseChecker import ResponseChecker


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
