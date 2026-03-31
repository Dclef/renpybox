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
        LINE_ERROR_MIXED_LANGUAGE = "LINE_ERROR_MIXED_LANGUAGE"
        LINE_ERROR_SIMILARITY = "LINE_ERROR_SIMILARITY"
        LINE_ERROR_DEGRADATION = "LINE_ERROR_DEGRADATION"

    LINE_ERROR: tuple[StrEnum] = (
        Error.LINE_ERROR_KANA,
        Error.LINE_ERROR_HANGEUL,
        Error.LINE_ERROR_FAKE_REPLY,
        Error.LINE_ERROR_EMPTY_LINE,
        Error.LINE_ERROR_MIXED_LANGUAGE,
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
    RE_MULTI_SPACE = re.compile(r"\s+")
    RE_IGNORE_SEGMENTS = re.compile(r"\[[^\]\n]*\]|\{[^}\n]*\}")
    RE_LATIN_FRAGMENT = re.compile(r"[A-Za-z]{2,}")
    RE_CAMEL_CASE_TOKEN = re.compile(r"^[a-z]+[A-Z][A-Za-z]*$")
    RE_CAPITALIZED_LATIN_TOKEN = re.compile(r"^[A-Z][A-Za-z'\-]{2,}$")

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

        # 单条目达到重试阈值后，允许放宽部分容易误判的行级检查，
        # 但“原文照抄 / 空译文 / 明显退化”等硬错误仍然保留，避免直接写回未翻译内容。
        threshold_reached = (
            len(self.items) == 1
            and self.items[0].get_retry_count() >= __class__.RETRY_COUNT_THRESHOLD
        )

        # 行数检查
        if len(srcs) != len(dsts):
            return [__class__.Error.FAIL_LINE_COUNT] * len(srcs)

        # 逐行检查
        checks = self.check_lines(srcs, dsts, text_type)
        if threshold_reached:
            checks = self.relax_checks_after_retry_threshold(srcs, dsts, checks)
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

            # 相似度与退化判断前先去掉保护占位符，避免被大段占位符误判。
            src_compare = self.normalize_for_compare(src)
            dst_compare = self.normalize_for_compare(dst)

            # 当原文中不包含重复文本但是译文中包含重复文本时，判断为 退化
            if __class__.RE_DEGRADATION.search(src_compare) == None and __class__.RE_DEGRADATION.search(dst_compare) != None:
                checks.append(__class__.Error.LINE_ERROR_DEGRADATION)
                continue

            # 排除代码保护规则覆盖的文本以后再继续进行检查
            rule: re.Pattern = TextProcessor(self.config, None).get_re_sample(
                custom = self.config.text_preserve_enable,
                text_type = text_type,
            )
            if rule is not None:
                src_compare = rule.sub("", src_compare)
                dst_compare = rule.sub("", dst_compare)

            # 如果排除代码段后没有有效文本，则无需做相似度判断
            src_compare = self.normalize_for_compare(src_compare)
            dst_compare = self.normalize_for_compare(dst_compare)
            if src_compare == "" or dst_compare == "":
                checks.append(__class__.Error.NONE)
                continue

            if self.has_mixed_language_leakage(src, dst):
                checks.append(__class__.Error.LINE_ERROR_MIXED_LANGUAGE)
                continue

            # 当原文语言为日语，且译文中包含平假名或片假名字符时，判断为 假名残留
            if self.config.source_language == BaseLanguage.Enum.JA and (TextHelper.JA.any_hiragana(dst_compare) or TextHelper.JA.any_katakana(dst_compare)):
                checks.append(__class__.Error.LINE_ERROR_KANA)
                continue

            # 当原文语言为韩语，且译文中包含谚文字符时，判断为 谚文残留
            if self.config.source_language == BaseLanguage.Enum.KO and TextHelper.KO.any_hangeul(dst_compare):
                checks.append(__class__.Error.LINE_ERROR_HANGEUL)
                continue

            # 判断是否包含或相似
            is_similar = (
                src_compare in dst_compare
                or dst_compare in src_compare
                or TextHelper.check_similarity_by_jaccard(src_compare, dst_compare) > 0.80
            )

            # 对“看起来像代码/标识符/按键名”的文本，允许原样保留，避免无意义重试。
            if is_similar and self.is_likely_non_translatable_text(src_compare):
                checks.append(__class__.Error.NONE)
                continue

            if is_similar:
                # 日翻中时，只有译文至少包含一个平假名或片假名字符时，才判断为 相似
                if self.config.source_language == BaseLanguage.Enum.JA and self.config.target_language == BaseLanguage.Enum.ZH:
                    if TextHelper.JA.any_hiragana(dst_compare) or TextHelper.JA.any_katakana(dst_compare):
                        checks.append(__class__.Error.LINE_ERROR_SIMILARITY)
                        continue
                # 韩翻中时，只有译文至少包含一个谚文字符时，才判断为 相似
                elif self.config.source_language == BaseLanguage.Enum.KO and self.config.target_language == BaseLanguage.Enum.ZH:
                    if TextHelper.KO.any_hangeul(dst_compare):
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
    def normalize_for_compare(cls, text: str) -> str:
        if not isinstance(text, str):
            return ""

        # 去掉保护占位符，并压缩多余空白，避免影响后续相似度判断。
        text = cls.RE_PRESERVE_TOKEN.sub("", text)
        text = cls.RE_MULTI_SPACE.sub(" ", text)
        return text.strip()

    @classmethod
    def _strip_for_mixed_language_check(cls, text: str) -> str:
        if not isinstance(text, str):
            return ""

        text = cls.RE_PRESERVE_TOKEN.sub("", text)
        text = cls.RE_IGNORE_SEGMENTS.sub("", text)
        text = cls.RE_MULTI_SPACE.sub(" ", text)
        return text.strip()

    @classmethod
    def _is_suspicious_latin_fragment(cls, fragment: str) -> bool:
        if not isinstance(fragment, str):
            return False
        if len(fragment) < 2:
            return False
        if fragment.isupper():
            return False
        if cls.RE_CAPITALIZED_LATIN_TOKEN.fullmatch(fragment) is not None:
            return False
        if cls.RE_CAMEL_CASE_TOKEN.fullmatch(fragment) is not None:
            return False
        return any(ch.islower() for ch in fragment)

    @classmethod
    def has_mixed_language_leakage(cls, src: str, dst: str) -> bool:
        clean_src = cls._strip_for_mixed_language_check(src)
        clean_dst = cls._strip_for_mixed_language_check(dst)

        if clean_src == "" or clean_dst == "":
            return False
        if TextHelper.CJK.any(clean_dst) == False or TextHelper.Latin.any(clean_dst) == False:
            return False

        source_tokens = [
            token.lower()
            for token in cls.RE_LATIN_FRAGMENT.findall(clean_src)
            if len(token) >= 2
        ]
        if source_tokens == []:
            return False

        suspicious_count = 0
        suspicious_chars = 0

        for match in cls.RE_LATIN_FRAGMENT.finditer(clean_dst):
            fragment = match.group(0)
            if cls._is_suspicious_latin_fragment(fragment) == False:
                continue

            prev_char = clean_dst[match.start() - 1] if match.start() > 0 else ""
            next_char = clean_dst[match.end()] if match.end() < len(clean_dst) else ""
            touches_cjk = (
                (prev_char != "" and TextHelper.CJK.char(prev_char))
                or (next_char != "" and TextHelper.CJK.char(next_char))
            )
            if touches_cjk == False:
                continue

            fragment_lower = fragment.lower()
            overlaps_source = any(
                fragment_lower in token or token in fragment_lower
                for token in source_tokens
            )
            if overlaps_source == False and len(fragment) < 4:
                continue

            suspicious_count += 1
            suspicious_chars += len(fragment)

        return suspicious_count >= 2 or suspicious_chars >= 4

    @classmethod
    def relax_checks_after_retry_threshold(
        cls,
        srcs: list[str],
        dsts: list[str],
        checks: list[Error],
    ) -> list[Error]:
        """达到重试阈值后，仅放宽部分可能的误判，不放行明显未翻译结果。"""
        relaxed: list[ResponseChecker.Error] = []
        for src, dst, error in zip(srcs, dsts, checks):
            if error in cls.LINE_ERROR and cls.should_keep_line_error_after_retry_threshold(src, dst, error) == False:
                relaxed.append(cls.Error.NONE)
            else:
                relaxed.append(error)
        return relaxed

    @classmethod
    def should_keep_line_error_after_retry_threshold(cls, src: str, dst: str, error: Error) -> bool:
        """达到重试阈值后，判断哪些行级错误仍必须保留。"""
        if error in (
            cls.Error.LINE_ERROR_EMPTY_LINE,
            cls.Error.LINE_ERROR_KANA,
            cls.Error.LINE_ERROR_HANGEUL,
            cls.Error.LINE_ERROR_DEGRADATION,
            cls.Error.LINE_ERROR_FAKE_REPLY,
            cls.Error.LINE_ERROR_MIXED_LANGUAGE,
        ):
            return True

        if error != cls.Error.LINE_ERROR_SIMILARITY:
            return False

        src_compare = cls.normalize_for_compare(src).casefold()
        dst_compare = cls.normalize_for_compare(dst).casefold()
        if src_compare == "" or dst_compare == "":
            return True

        # 对于“完全照抄 / 明显包含原文”的情况，仍视为未翻译。
        return (
            src_compare == dst_compare
            or src_compare in dst_compare
            or dst_compare in src_compare
        )

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
