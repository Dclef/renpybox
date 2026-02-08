import json
import re
import threading
from base.compat import StrEnum
from functools import lru_cache

import opencc

from base.Base import Base
from base.BaseLanguage import BaseLanguage
from base.PathHelper import get_resource_path
from module.Cache.CacheItem import CacheItem
from module.Config import Config
from module.Fixer.CodeFixer import CodeFixer
from module.Fixer.EscapeFixer import EscapeFixer
from module.Fixer.HangeulFixer import HangeulFixer
from module.Fixer.KanaFixer import KanaFixer
from module.Fixer.NumberFixer import NumberFixer
from module.Fixer.PunctuationFixer import PunctuationFixer
from module.Localizer.Localizer import Localizer
from module.Normalizer import Normalizer
from module.RubyCleaner import RubyCleaner

class TextProcessor(Base):

    # 对文本进行处理的流程为：
    # - 文本保护
    # - 正规化
    # - 清理注音
    # - 译前替换
    # - 注入姓名
    # ---- 翻译 ----
    # - 提取姓名
    # - 自动修复
    # - 译后替换
    # - 繁体输出
    # - 文本保护

    # 注意预处理和后处理的顺序应该镜像颠倒

    class RuleType(StrEnum):

        CHECK = "CHECK"
        SAMPLE = "SAMPLE"
        PREFIX = "PREFIX"
        SUFFIX = "SUFFIX"

    # 类变量
    OPENCCT2S = opencc.OpenCC("t2s")
    OPENCCS2T = opencc.OpenCC("s2tw")

    # 正则表达式
    RE_NAME = re.compile(r"^【(.*?)】\s*|\[(.*?)\]\s*", flags = re.IGNORECASE)
    RE_BLANK: re.Pattern = re.compile(r"\s+", re.IGNORECASE)

    # 类线程锁
    LOCK: threading.Lock = threading.Lock()
    CUSTOM_TEXT_PRESERVE_CACHE_LOCK: threading.Lock = threading.Lock()
    CUSTOM_TEXT_PRESERVE_CACHE: dict[int, tuple[str, ...]] = {}

    def __init__(self, config: Config, item: CacheItem) -> None:
        super().__init__()

        # 初始化
        self.config: Config = config
        self.item: CacheItem = item

        self.srcs: list[str] = []
        self.samples: list[str] = []
        self.vaild_index: set[int] = set()
        self.prefix_codes: dict[int, list[str]] = {}
        self.suffix_codes: dict[int, list[str]] = {}
        self.inline_codes: dict[int, list[tuple[str, str]]] = {}
        self.inline_preserve_re = None
        self.inline_preserve_re_text_type = None

    def _get_custom_text_preserve_patterns(self) -> tuple[str, ...]:
        cache_key = id(self.config)
        with __class__.CUSTOM_TEXT_PRESERVE_CACHE_LOCK:
            cached = __class__.CUSTOM_TEXT_PRESERVE_CACHE.get(cache_key)
        if cached is not None:
            return cached

        patterns: list[str] = []

        for item in self.config.text_preserve_data:
            src = item.get("src", "")
            if src == "":
                continue

            # Ren'Py 变量引用通常是形如 [variable] 的字面量。
            # 若直接作为正则使用，会被解释为字符组（[...]），导致误匹配与误剥离文本。
            if src.startswith("[") and src.endswith("]") and "\\" not in src:
                if re.fullmatch(rf"\[[\w{CacheItem.CJK_RANGE}.]+\]", src) is not None:
                    src = re.escape(src)
            # Ren'Py 标签常见的花括号字面量（如 {w}、{/b}）。
            # 若直接作为正则使用会报错或误匹配，这里自动转义为字面量。
            if src.startswith("{") and src.endswith("}") and "\\" not in src:
                src = re.escape(src)

            patterns.append(src)

        result = tuple(patterns)
        with __class__.CUSTOM_TEXT_PRESERVE_CACHE_LOCK:
            __class__.CUSTOM_TEXT_PRESERVE_CACHE[cache_key] = result
        return result

    @classmethod
    def reset(cls) -> None:
        cls.get_rule.cache_clear()
        with cls.CUSTOM_TEXT_PRESERVE_CACHE_LOCK:
            cls.CUSTOM_TEXT_PRESERVE_CACHE.clear()

    @classmethod
    @lru_cache(maxsize = None)
    def get_rule(cls, custom: bool, custom_data: list[str], rule_type: RuleType, text_type: CacheItem.TextType, language: BaseLanguage.Enum) -> re.Pattern[str]:
        data: list[dict[str, str]] = []
        if custom == True:
            data = custom_data
        else:
            path: str = get_resource_path("resource", "text_preserve_preset", language.lower(), f"{text_type.lower()}.json")
            try:
                with open(path, "r", encoding = "utf-8-sig") as reader:
                    data: list[str] = [v.get("src") for v in json.load(reader) if v.get("src") != ""]
            except:
                pass

        if len(data) == 0:
            return None
        elif rule_type == __class__.RuleType.CHECK:
            pattern = "|".join(data)
            return re.compile(rf"(?:{pattern})+", re.IGNORECASE)
        elif rule_type == __class__.RuleType.SAMPLE:
            pattern = "|".join(data)
            return re.compile(rf"{pattern}", re.IGNORECASE)
        elif rule_type == __class__.RuleType.PREFIX:
            pattern = "|".join(data)
            return re.compile(rf"^(?:{pattern})+", re.IGNORECASE)
        elif rule_type == __class__.RuleType.SUFFIX:
            pattern = "|".join(data)
            return re.compile(rf"(?:{pattern})+$", re.IGNORECASE)

    def get_re_check(self, custom: bool, text_type: CacheItem.TextType) -> re.Pattern:
        with __class__.LOCK:
            return __class__.get_rule(
                custom = custom,
                custom_data = self._get_custom_text_preserve_patterns() if custom == True else None,
                rule_type = __class__.RuleType.CHECK,
                text_type = text_type,
                language = Localizer.get_app_language(),
            )

    def get_re_sample(self, custom: bool, text_type: CacheItem.TextType) -> re.Pattern:
        with __class__.LOCK:
            return __class__.get_rule(
                custom = custom,
                custom_data = self._get_custom_text_preserve_patterns() if custom == True else None,
                rule_type = __class__.RuleType.SAMPLE,
                text_type = text_type,
                language = Localizer.get_app_language(),
            )

    def get_re_prefix(self, custom: bool, text_type: CacheItem.TextType) -> re.Pattern:
        with __class__.LOCK:
            return __class__.get_rule(
                custom = custom,
                custom_data = self._get_custom_text_preserve_patterns() if custom == True else None,
                rule_type = __class__.RuleType.PREFIX,
                text_type = text_type,
                language = Localizer.get_app_language(),
            )

    def get_re_suffix(self, custom: bool, text_type: CacheItem.TextType) -> re.Pattern:
        with __class__.LOCK:
            return __class__.get_rule(
                custom = custom,
                custom_data = self._get_custom_text_preserve_patterns() if custom == True else None,
                rule_type = __class__.RuleType.SUFFIX,
                text_type = text_type,
                language = Localizer.get_app_language(),
            )

    # 按规则提取文本
    def extract(self, rule: re.Pattern, line: str) -> tuple[str, list[str]]:
        codes: list[str] = []

        def repl(match: re.Match) -> str:
            codes.append(match.group(0))
            return ""
        line = rule.sub(repl, line)

        return line, codes

    # 正规化
    def normalize(self, src: str) -> str:
        return Normalizer.normalize(src)

    # 清理注音
    def clean_ruby(self, src: str) -> str:
        if self.config.clean_ruby == False:
            return src
        else:
            return RubyCleaner.clean(src, self.item.get_text_type())

    # 自动修复
    def auto_fix(self, src: str, dst: str) -> str:
        source_language = self.config.source_language
        target_language = self.config.target_language

        # 假名修复
        if source_language == BaseLanguage.Enum.JA:
            dst = KanaFixer.fix(dst)
        # 谚文修复
        elif source_language == BaseLanguage.Enum.KO:
            dst = HangeulFixer.fix(dst)

        # 代码修复
        dst = CodeFixer.fix(src, dst, self.item.get_text_type(), self.config)

        # 转义修复
        dst = EscapeFixer.fix(src, dst)

        # 数字修复
        dst = NumberFixer.fix(src, dst)

        # 标点符号修复
        dst = PunctuationFixer.fix(src, dst, source_language, target_language)

        return dst

    # 注入姓名
    def inject_name(self, srcs: list[str], item: CacheItem) -> list[str]:
        name: str = item.get_first_name_src()
        if name is not None and len(srcs) > 0:
            srcs[0] = f"【{name}】{srcs[0]}"

        return srcs

    # 提取姓名
    def extract_name(self, srcs: list[str], dsts: list[str], item: CacheItem) -> str:
        name: str = None
        if item.get_first_name_src() is not None and len(srcs) > 0:
            result: re.Match[str] = __class__.RE_NAME.search(dsts[0])
            if result is None:
                pass
            elif result.group(1) is not None:
                name = result.group(1)
            elif result.group(2) is not None:
                name = result.group(2)

            # 清理一下
            srcs[0] = __class__.RE_NAME.sub("", srcs[0])
            dsts[0] = __class__.RE_NAME.sub("", dsts[0])

        return name, srcs, dsts

    # 译前替换
    def replace_pre_translation(self, src: str) -> str:
        if self.config.pre_translation_replacement_enable == False:
            return src

        for v in self.config.pre_translation_replacement_data:
            pattern = v.get("src")
            replacement = v.get("dst")
            is_regex = v.get("regex", False)
            is_case_sensitive = v.get("case_sensitive", False)

            if is_regex:
                flags = 0 if is_case_sensitive else re.IGNORECASE
                src = re.sub(pattern, replacement, src, flags = flags)
            else:
                if is_case_sensitive:
                    src = src.replace(pattern, replacement)
                else:
                    pattern_escaped = re.escape(pattern)
                    src = re.sub(pattern_escaped, replacement, src, flags = re.IGNORECASE)

        return src

    # 译后替换
    def replace_post_translation(self, dst: str) -> str:
        if self.config.post_translation_replacement_enable == False:
            return dst

        for v in self.config.post_translation_replacement_data:
            pattern = v.get("src")
            replacement = v.get("dst")
            is_regex = v.get("regex", False)
            is_case_sensitive = v.get("case_sensitive", False)

            if is_regex:
                flags = 0 if is_case_sensitive else re.IGNORECASE
                dst = re.sub(pattern, replacement, dst, flags = flags)
            else:
                if is_case_sensitive:
                    dst = dst.replace(pattern, replacement)
                else:
                    pattern_escaped = re.escape(pattern)
                    dst = re.sub(pattern_escaped, replacement, dst, flags = re.IGNORECASE)

        return dst

    # 中文字型转换
    def convert_chinese_character_form(self, dst: str) -> str:
        if self.config.target_language != BaseLanguage.Enum.ZH:
            return dst

        if self.config.traditional_chinese_enable == True:
            return __class__.OPENCCS2T.convert(dst)
        else:
            return __class__.OPENCCT2S.convert(dst)

    # 处理前后缀代码段
    def prefix_suffix_process(self, i: int, src: str, text_type: CacheItem.TextType) -> None:
        if self.config.auto_process_prefix_suffix_preserved_text == False:
            return src

        rule: re.Pattern = self.get_re_prefix(
            custom = self.config.text_preserve_enable,
            text_type = text_type,
        )
        if rule is not None:
            src, self.prefix_codes[i] = self.extract(rule, src)

        rule: re.Pattern = self.get_re_suffix(
            custom = self.config.text_preserve_enable,
            text_type = text_type,
        )
        if rule is not None:
            src, self.suffix_codes[i] = self.extract(rule, src)

        return src

    def _build_inline_preserve_regex(self, text_type: CacheItem.TextType) -> re.Pattern | None:
        patterns: list[str] = []

        # 行内保护只使用“安全占位模式”，避免把 \\s 这类宽泛规则（会匹配空格）替换成占位符。
        if text_type == CacheItem.TextType.RENPY:
            patterns.extend([v.pattern for v in CacheItem.REGEX_RENPY])
        elif text_type == CacheItem.TextType.WOLF:
            patterns.extend([v.pattern for v in CacheItem.REGEX_WOLF])
        elif text_type == CacheItem.TextType.RPGMAKER:
            patterns.extend([v.pattern for v in CacheItem.REGEX_RPGMaker])

        # 自定义禁翻规则按开关叠加。
        if self.config.text_preserve_enable == True:
            patterns = list(self._get_custom_text_preserve_patterns()) + patterns

        if len(patterns) == 0:
            return None

        try:
            return re.compile("|".join(patterns), re.IGNORECASE)
        except re.error:
            # 合并失败时回退到首个可用规则，保证流程不受影响。
            for pattern in patterns:
                try:
                    return re.compile(pattern, re.IGNORECASE)
                except re.error:
                    continue
        return None

    def _protect_inline_tags(self, i: int, src: str, text_type: CacheItem.TextType) -> str:
        if (
            self.inline_preserve_re is None
            or self.inline_preserve_re_text_type != text_type
        ):
            self.inline_preserve_re = self._build_inline_preserve_regex(text_type)
            self.inline_preserve_re_text_type = text_type

        rule = self.inline_preserve_re
        if rule is None:
            return src

        codes: list[tuple[str, str]] = []

        def repl(match: re.Match) -> str:
            placeholder = f"__RBX_PRESERVE_{i}_{len(codes)}__"
            codes.append((placeholder, match.group(0)))
            return placeholder

        new_src = rule.sub(repl, src)
        if codes:
            self.inline_codes[i] = codes
            # 记录命中的禁翻片段，便于提示词增强
            self.samples.extend([orig for _, orig in codes if orig.strip() != ""])
        return new_src

    def _restore_inline_tags(self, i: int, dst: str) -> str:
        for placeholder, original in self.inline_codes.get(i, []):
            dst = dst.replace(placeholder, original)
        return dst

    # 预处理
    def pre_process(self) -> None:
        # 依次处理每行，顺序为：
        text_type = self.item.get_text_type()
        for i, src in enumerate(self.item.get_src().split("\n")):
            if src == "":
                pass
            elif src.strip() == "":
                pass
            else:
                # 处理前后缀代码段
                src = self.prefix_suffix_process(i, src, text_type)
                # 行内禁翻库保护
                src = self._protect_inline_tags(i, src, text_type)

                # 如果处理后的文本为空
                if src == "":
                    pass
                else:
                    # 正规化
                    src = self.normalize(src)

                    # 清理注音
                    src = self.clean_ruby(src)

                    # 译前替换
                    src = self.replace_pre_translation(src)

                    # 查找控制字符示例
                    rule: re.Pattern = self.get_re_sample(
                        custom = self.config.text_preserve_enable,
                        text_type = text_type,
                    )
                    if rule is not None:
                        self.samples.extend([v.group(0) for v in rule.finditer(src)])

                    # 补充
                    if text_type == CacheItem.TextType.MD:
                        self.samples.append("Markdown Code")

                    # 保存结果
                    self.srcs.append(src)
                    self.vaild_index.add(i)

        # 注入姓名
        self.srcs = self.inject_name(self.srcs, self.item)

    # 后处理
    def post_process(self, dsts: list[str]) -> tuple[str, str]:
        results: list[str] = []

        # 提取姓名
        name, _, dsts = self.extract_name(self.srcs, dsts, self.item)

        # 依次处理每行
        for i, src in enumerate(self.item.get_src().split("\n")):
            if src == "":
                dst = ""
            elif src.strip() == "":
                dst = src
            elif i not in self.vaild_index:
                dst = src
            else:
                # 移除模型可能额外添加的头尾空白符
                dst = dsts.pop(0).strip()
                # 还原行内标签
                dst = self._restore_inline_tags(i, dst)

                # 自动修复
                dst = self.auto_fix(src, dst)

                # 译后替换
                dst = self.replace_post_translation(dst)

                # 繁体输出
                dst = self.convert_chinese_character_form(dst)

                if i in self.prefix_codes:
                    dst = "".join(self.prefix_codes.get(i)) + dst
                if i in self.suffix_codes:
                    dst = dst + "".join(self.suffix_codes.get(i))

            # 添加结果
            results.append(dst)

        return name, "\n".join(results)

    # 检查代码段
    def check(self, src: str, dst: str, text_type: CacheItem.TextType) -> bool:
        x: list[str] = []
        y: list[str] = []
        rule: re.Pattern = self.get_re_check(
            custom = self.config.text_preserve_enable,
            text_type = text_type,
        )
        if rule is not None:
            x = [v.group(0) for v in rule.finditer(src)]
            y = [v.group(0) for v in rule.finditer(dst)]

        x = [__class__.RE_BLANK.sub("", v) for v in x if __class__.RE_BLANK.sub("", v) != ""]
        y = [__class__.RE_BLANK.sub("", v) for v in y if __class__.RE_BLANK.sub("", v) != ""]

        return x == y
