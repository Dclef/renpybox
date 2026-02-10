import re

from base.BaseLanguage import BaseLanguage
from module.Text.TextHelper import TextHelper

class LanguageFilter():

    # Ren'Py 可翻译文本里常见的占位符/标签片段
    # 语言检测时应忽略这些片段，避免 [mcname] 里的拉丁字母干扰源语言判断。
    RE_IGNORE_SEGMENTS: re.Pattern = re.compile(r"\[[^\]]*\]|\{[^}]*\}")

    ESC_LBRACKET = "__RBX_ESC_LBRACKET__"
    ESC_RBRACKET = "__RBX_ESC_RBRACKET__"

    @classmethod
    def _clean_for_language_detect(cls, src: str) -> str:
        text = src or ""
        # 保护 Ren'Py 的 [[ / ]] 字面量方括号，避免被占位符正则误删。
        text = text.replace("[[", cls.ESC_LBRACKET).replace("]]", cls.ESC_RBRACKET)
        text = cls.RE_IGNORE_SEGMENTS.sub("", text)
        return text.replace(cls.ESC_LBRACKET, "[").replace(cls.ESC_RBRACKET, "]")

    def filter(src: str, source_language: BaseLanguage.Enum) -> bool:
        # 获取语言判断函数
        if source_language == BaseLanguage.Enum.ZH:
            func = TextHelper.CJK.any
        elif source_language == BaseLanguage.Enum.EN:
            func = TextHelper.Latin.any
        else:
            func = getattr(TextHelper, source_language).any

        # 跳过占位符/标签后再做语言判断，避免误保留非源语言文本
        cleaned_src = LanguageFilter._clean_for_language_detect(src)

        # 返回值 True 表示需要过滤（即需要排除）
        if callable(func) != True:
            return False
        else:
            return not func(cleaned_src)
