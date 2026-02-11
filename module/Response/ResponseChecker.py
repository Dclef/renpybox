import re
from base.compat import StrEnum

from base.Base import Base
from base.BaseLanguage import BaseLanguage
from module.Text.TextHelper import TextHelper
from module.Cache.CacheItem import CacheItem
from module.Config import Config
from module.Filter.RuleFilter import RuleFilter
from module.Filter.LanguageFilter import LanguageFilter
from module.TextProcessor import TextProcessor

class ResponseChecker(Base):

    class Error(StrEnum):

        NONE = "NONE"
        UNKNOWN = "UNKNOWN"
        FAIL_DATA = "FAIL_DATA"
        FAIL_LINE_COUNT = "FAIL_LINE_COUNT"
        LINE_ERROR_KANA = "LINE_ERROR_KANA"
        LINE_ERROR_HANGEUL = "LINE_ERROR_HANGEUL"
        LINE_ERROR_FAKE_REPLY = "LINE_ERROR_FAKE_REPLY"
        LINE_ERROR_EMPTY_LINE = "LINE_ERROR_EMPTY_LINE"
        LINE_ERROR_SIMILARITY = "LINE_ERROR_SIMILARITY"
        LINE_ERROR_DEGRADATION = "LINE_ERROR_DEGRADATION"

    LINE_ERROR: tuple[StrEnum] = (
        Error.LINE_ERROR_KANA,
        Error.LINE_ERROR_HANGEUL,
        Error.LINE_ERROR_FAKE_REPLY,
        Error.LINE_ERROR_EMPTY_LINE,
        Error.LINE_ERROR_SIMILARITY,
        Error.LINE_ERROR_DEGRADATION,
    )

    # 重试次数阈值
    RETRY_COUNT_THRESHOLD: int = 2

    # 退化检测规则
    RE_DEGRADATION = re.compile(r"(.{1,3})\1{16,}", flags = re.IGNORECASE)
    # 代码/条件表达式（不应要求“必须翻译”）
    RE_LOGIC_EXPRESSION = re.compile(
        r"(==|!=|<=|>=|&&|\|\||\b(and|or|not|True|False|None)\b)",
        flags = re.IGNORECASE,
    )
    # 标识符/版本号/资源键（含数字或连接符）
    RE_IDENTIFIER_WITH_SYMBOL = re.compile(
        r"^[A-Za-z_][A-Za-z0-9_.:-]*[0-9_.:-][A-Za-z0-9_.:-]*$",
        flags = re.IGNORECASE,
    )
    # 常见按键名
    RE_KEY_NAME = re.compile(
        r"^(Ctrl|Alt|Shift|Esc|Enter|Tab|Space|Backspace|Delete|Insert|Home|End|PageUp|PageDown|Up|Down|Left|Right|F\d{1,2})$",
        flags = re.IGNORECASE,
    )
    # 单词型专有名（首字母大写或全大写）
    RE_PROPER_NOUN_TOKEN = re.compile(
        r"^(?:[A-Z][A-Za-z'\-]{2,}|[A-Z]{2,})$",
        flags = re.IGNORECASE,
    )
    # 行内占位符一致性检查
    RE_PRESERVE_TOKEN = re.compile(r"__RBX_PRESERVE_\d+_\d+__", flags = re.IGNORECASE)

    def __init__(self, config: Config, items: list[CacheItem]) -> None:
        super().__init__()

        # 初始化
        self.items = items
        self.config = config

    # 检查
    def check(self, srcs: list[str], dsts: list[str], text_type: CacheItem.TextType) -> list[str]:
        # 数据解析失败
        if len(dsts) == 0 or all(v == "" or v == None for v in dsts):
            return [__class__.Error.FAIL_DATA] * len(srcs)

        # 当翻译任务为单条目任务，且此条目已经是第二次单独重试时，直接返回，不进行后续判断
        if len(self.items) == 1 and self.items[0].get_retry_count() >= __class__.RETRY_COUNT_THRESHOLD:
            return [__class__.Error.NONE] * len(srcs)

        # 行数检查
        if len(srcs) != len(dsts):
            return [__class__.Error.FAIL_LINE_COUNT] * len(srcs)

        # 逐行检查
        checks = self.check_lines(srcs, dsts, text_type)
        if any(v != __class__.Error.NONE for v in checks):
            return checks

        # 默认无错误
        return [__class__.Error.NONE] * len(srcs)

    # 逐行检查错误
    def check_lines(self, srcs: list[str], dsts: list[str], text_type: CacheItem.TextType) -> list[Error]:
        checks: list[__class__.Error] = []
        for src, dst in zip(srcs, dsts):
            src = src.strip()
            dst = dst.strip()

            # 原文不为空而译文为空时，判断为错误翻译
            if src != "" and dst == "":
                checks.append(__class__.Error.LINE_ERROR_EMPTY_LINE)
                continue

            # 原文内容符合规则过滤条件时，判断为正确翻译
            if RuleFilter.filter(src) == True:
                checks.append(__class__.Error.NONE)
                continue

            # 原文内容符合语言过滤条件时，判断为正确翻译
            if LanguageFilter.filter(src, self.config.source_language) == True:
                checks.append(__class__.Error.NONE)
                continue

            # 行内占位符必须成对且一一对应，避免半截占位符写回文件。
            src_preserves = __class__.RE_PRESERVE_TOKEN.findall(src)
            dst_preserves = __class__.RE_PRESERVE_TOKEN.findall(dst)
            if src_preserves != []:
                if sorted(src_preserves) != sorted(dst_preserves):
                    checks.append(__class__.Error.LINE_ERROR_FAKE_REPLY)
                    continue
            elif "__RBX_PRESERVE_" in dst:
                checks.append(__class__.Error.LINE_ERROR_FAKE_REPLY)
                continue

            # 当原文中不包含重复文本但是译文中包含重复文本时，判断为 退化
            if __class__.RE_DEGRADATION.search(src) == None and __class__.RE_DEGRADATION.search(dst) != None:
                checks.append(__class__.Error.LINE_ERROR_DEGRADATION)
                continue

            # 排除代码保护规则覆盖的文本以后再继续进行检查
            rule: re.Pattern = TextProcessor(self.config, None).get_re_sample(
                custom = self.config.text_preserve_enable,
                text_type = text_type,
            )
            if rule is not None:
                src = rule.sub("", src)
                dst = rule.sub("", dst)

            # 如果排除代码段后没有有效文本，则无需做相似度判断
            if src == "" or dst == "":
                checks.append(__class__.Error.NONE)
                continue

            # 当原文语言为日语，且译文中包含平假名或片假名字符时，判断为 假名残留
            if self.config.source_language == BaseLanguage.Enum.JA and (TextHelper.JA.any_hiragana(dst) or TextHelper.JA.any_katakana(dst)):
                checks.append(__class__.Error.LINE_ERROR_KANA)
                continue

            # 当原文语言为韩语，且译文中包含谚文字符时，判断为 谚文残留
            if self.config.source_language == BaseLanguage.Enum.KO and TextHelper.KO.any_hangeul(dst):
                checks.append(__class__.Error.LINE_ERROR_HANGEUL)
                continue

            # 判断是否包含或相似
            is_similar = src in dst or dst in src or TextHelper.check_similarity_by_jaccard(src, dst) > 0.80

            # 对“看起来像代码/标识符/按键名”的文本，允许原样保留，避免无意义重试。
            if is_similar and self.is_likely_non_translatable_text(src):
                checks.append(__class__.Error.NONE)
                continue

            if is_similar:
                # 日翻中时，只有译文至少包含一个平假名或片假名字符时，才判断为 相似
                if self.config.source_language == BaseLanguage.Enum.JA and self.config.target_language == BaseLanguage.Enum.ZH:
                    if TextHelper.JA.any_hiragana(dst) or TextHelper.JA.any_katakana(dst):
                        checks.append(__class__.Error.LINE_ERROR_SIMILARITY)
                        continue
                # 韩翻中时，只有译文至少包含一个谚文字符时，才判断为 相似
                elif self.config.source_language == BaseLanguage.Enum.KO and self.config.target_language == BaseLanguage.Enum.ZH:
                    if TextHelper.KO.any_hangeul(dst):
                        checks.append(__class__.Error.LINE_ERROR_SIMILARITY)
                        continue
                # 其他情况，只要原文译文相同或相似就可以判断为 相似
                else:
                    checks.append(__class__.Error.LINE_ERROR_SIMILARITY)
                    continue

            # 默认为无错误
            checks.append(__class__.Error.NONE)

        # 返回结果
        return checks

    @classmethod
    def is_likely_non_translatable_text(cls, text: str) -> bool:
        s = text.strip()
        if s == "":
            return True

        # 逻辑表达式（含变量、比较符、布尔运算）
        if cls.RE_LOGIC_EXPRESSION.search(s) is not None and re.search(r"[A-Za-z_]\w*", s) is not None:
            return True

        # 标识符、版本号、资源键（如 DesertStalkerEA-100001）
        if cls.RE_IDENTIFIER_WITH_SYMBOL.fullmatch(s) is not None:
            return True

        # 常见按键名
        if cls.RE_KEY_NAME.fullmatch(s) is not None:
            return True

        # 单词型专有名词（如 Spatium）
        words = s.split()
        if len(words) == 1 and cls.RE_PROPER_NOUN_TOKEN.fullmatch(words[0]) is not None:
            return True

        # 邮箱/句柄类文本（如 Karl Casey @ White Bat Audio）
        if "@" in s and not s.startswith("@"):
            return True

        return False
