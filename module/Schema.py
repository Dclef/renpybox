from pydantic import BaseModel


class TranslationResult(BaseModel):
    """结构化输出 schema：translations 数组按行对应原文。"""
    translations: list[str]
