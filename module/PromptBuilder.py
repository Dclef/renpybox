import json
import threading
from functools import lru_cache

from base.Base import Base
from base.BaseLanguage import BaseLanguage
from base.PathHelper import get_resource_path
from module.Cache.CacheItem import CacheItem
from module.Config import Config

class PromptBuilder(Base):

    # 类线程锁
    LOCK: threading.Lock = threading.Lock()

    def __init__(self, config: Config) -> None:
        super().__init__()

        # 初始化
        self.config: Config = config

    @classmethod
    def reset(cls) -> None:
        cls.get_base.cache_clear()
        cls.get_prefix.cache_clear()
        cls.get_suffix.cache_clear()
        cls.get_suffix_glossary.cache_clear()

    @classmethod
    @lru_cache(maxsize = None)
    def get_base(cls, language: BaseLanguage.Enum) -> str:
        with open(get_resource_path("resource", "prompt", language.lower(), "base.txt"), "r", encoding = "utf-8-sig") as reader:
            return reader.read().strip()

    @classmethod
    @lru_cache(maxsize = None)
    def get_prefix(cls, language: BaseLanguage.Enum) -> str:
        with open(get_resource_path("resource", "prompt", language.lower(), "prefix.txt"), "r", encoding = "utf-8-sig") as reader:
            return reader.read().strip()

    @classmethod
    @lru_cache(maxsize = None)
    def get_suffix(cls, language: BaseLanguage.Enum) -> str:
        with open(get_resource_path("resource", "prompt", language.lower(), "suffix.txt"), "r", encoding = "utf-8-sig") as reader:
            return reader.read().strip()

    @classmethod
    @lru_cache(maxsize = None)
    def get_suffix_glossary(cls, language: BaseLanguage.Enum) -> str:
        with open(get_resource_path("resource", "prompt", language.lower(), "suffix_glossary.txt"), "r", encoding = "utf-8-sig") as reader:
            return reader.read().strip()

    # 获取主提示词
    def build_main(self) -> str:
        # 判断提示词语言
        if self.config.target_language == BaseLanguage.Enum.ZH:
            prompt_language = BaseLanguage.Enum.ZH
            source_language = BaseLanguage.get_name_zh(self.config.source_language)
            target_language = BaseLanguage.get_name_zh(self.config.target_language)
        else:
            prompt_language = BaseLanguage.Enum.EN
            source_language = BaseLanguage.get_name_en(self.config.source_language)
            target_language = BaseLanguage.get_name_en(self.config.target_language)

        with __class__.LOCK:
            # 前缀
            prefix = __class__.get_prefix(prompt_language)

            # 基本
            if prompt_language == BaseLanguage.Enum.ZH and self.config.custom_prompt_zh_enable == True:
                base = self.config.custom_prompt_zh_data
            elif prompt_language == BaseLanguage.Enum.EN and self.config.custom_prompt_en_enable == True:
                base = self.config.custom_prompt_en_data
            else:
                base = __class__.get_base(prompt_language)

            # 后缀
            if self.config.auto_glossary_enable == False:
                suffix = __class__.get_suffix(prompt_language)
            else:
                suffix = __class__.get_suffix_glossary(prompt_language)

        # 组装提示词
        full_prompt = prefix + "\n" + base + "\n" + suffix
        full_prompt = full_prompt.replace("{source_language}", source_language)
        full_prompt = full_prompt.replace("{target_language}", target_language)

        return full_prompt

    # 构造参考上文
    def build_preceding(self, precedings: list[CacheItem]) -> str:
        if len(precedings) == 0:
            return ""
        elif self.config.target_language == BaseLanguage.Enum.ZH:
            return (
                "参考上文："
                + "\n" + "\n".join([item.get_src().strip().replace("\n", "\\n") for item in precedings])
            )
        else:
            return (
                "Preceding Context:"
                + "\n" + "\n".join([item.get_src().strip().replace("\n", "\\n") for item in precedings])
            )

    # 构造术语表
    def build_glossary(self, srcs: list[str]) -> str:
        full = "\n".join(srcs)
        full_lower = full.lower()
        glossary: list[dict[str, str]] = []
        for v in self.config.glossary_data:
            src = v.get("src", "")
            is_case_sensitive = v.get("case_sensitive", False)
            if is_case_sensitive:
                if src in full:
                    glossary.append(v)
            else:
                if src.lower() in full_lower:
                    glossary.append(v)

        # 构建文本
        result = []
        for item in glossary:
            src = item.get("src", "")
            dst = item.get("dst", "")
            info = item.get("info", "")

            if info == "":
                result.append(f"{src} -> {dst}")
            else:
                result.append(f"{src} -> {dst} #{info}")

        # 返回结果
        if result == []:
            return ""
        elif self.config.target_language == BaseLanguage.Enum.ZH:
            return (
                "术语表 <术语原文> -> <术语译文> #<术语信息>:"
                + "\n" + "\n".join(result)
            )
        else:
            return (
                "Glossary <Original Term> -> <Translated Term> #<Term Information>:"
                + "\n" + "\n".join(result)
            )

    # 构造术语表
    def build_glossary_sakura(self, srcs: list[str]) -> str:
        full = "\n".join(srcs)
        full_lower = full.lower()
        glossary: list[dict[str, str]] = []
        for v in self.config.glossary_data:
            src = v.get("src", "")
            is_case_sensitive = v.get("case_sensitive", False)
            if is_case_sensitive:
                if src in full:
                    glossary.append(v)
            else:
                if src.lower() in full_lower:
                    glossary.append(v)

        # 构建文本
        result = []
        for item in glossary:
            src = item.get("src", "")
            dst = item.get("dst", "")
            info = item.get("info", "")

            if info == "":
                result.append(f"{src}->{dst}")
            else:
                result.append(f"{src}->{dst} #{info}")

        # 返回结果
        if result == []:
            return ""
        else:
            return "\n".join(result)

    # 构建控制字符示例
    def build_control_characters_samples(self, main: str, samples: list[str]) -> str:
        samples = {v.strip() for v in samples if v.strip() != ""}

        if len(samples) == 0:
            return ""

        if (
            "控制字符必须在译文中原样保留" not in main
            and "code must be preserved in the translation as they are" not in main
        ):
            return ""

        # 判断提示词语言
        if self.config.target_language == BaseLanguage.Enum.ZH:
            prefix: str = "控制字符示例："
        else:
            prefix: str = "Control Characters Samples:"

        return prefix + "\n" + ", ".join(samples)

    # 构建输入
    def build_inputs(self, srcs: list[str]) -> str:
        inputs = "\n".join(
            json.dumps({str(i): line}, indent = None, ensure_ascii = False)
            for i, line in enumerate(srcs)
        )

        if self.config.target_language == BaseLanguage.Enum.ZH:
            return (
                "输入："
                "\n" + "```jsonline"
                "\n" + f"{inputs}"
                "\n" + "```"
            )
        else:
            return (
                "Input:"
                "\n" + "```jsonline"
                "\n" + f"{inputs}"
                "\n" + "```"
            )

    # 生成提示词
    def generate_prompt(self, srcs: list[str], samples: list[str], precedings: list[CacheItem], local_flag: bool) -> tuple[list[dict], list[str]]:
        # 初始化
        messages: list[dict[str, str]] = []
        extra_log: list[str] = []

        # 基础提示词
        content = self.build_main()

        # 参考上文
        if local_flag == False or self.config.enable_preceding_on_local == True:
            result = self.build_preceding(precedings)
            if result != "":
                content = content + "\n" + result
                extra_log.append(result)

        # 术语表
        if self.config.glossary_enable == True:
            result = self.build_glossary(srcs)
            if result != "":
                content = content + "\n" + result
                extra_log.append(result)

        # 控制字符示例
        result = self.build_control_characters_samples(content, samples)
        if result != "":
            content = content + "\n" + result
            extra_log.append(result)

        # 输入
        result = self.build_inputs(srcs)
        if result != "":
            content = content + "\n" + result

        # 构建提示词列表
        messages.append({
            "role": "user",
            "content": content,
        })

        return messages, extra_log

    # 生成提示词 - Sakura
    def generate_prompt_sakura(self, srcs: list[str]) -> tuple[list[dict], list[str]]:
        # 初始化
        messages: list[dict[str, str]] = []
        extra_log: list[str] = []

        # 构建系统提示词
        messages.append({
            "role": "system",
            "content": "你是一个轻小说翻译模型，可以流畅通顺地将多种语言（日文、英文、韩文等）翻译成简体中文，并联系上下文正确使用人称代词，不擅自添加原文中没有的代词。即使原文是英文游戏内容，也要完整翻译成中文。"
        })

        content_lines = [
            "只输出 JSONLINE，每行一个 JSON 对象，格式为 {\"序号\":\"译文\"}。",
            "输入是 JSONLINE 包装，值为原文文本；不要翻译 JSON 结构或序号。",
            "输出行数必须与输入行数一致，不要附加原文/英文/解释。",
            "保留原文中的控制字符/标签/变量（如 {w}、{...}、[...]）原样输出。",
            "【重要】游戏 UI 文本（如 NEW GAME, CONTINUE, OPTIONS）必须翻译成中文（如 新游戏、继续、选项）。",
            "【重要】对话和描述性内容必须完整翻译，不可保留英文原文。",
            "【允许】人名可以保留英文或音译为中文，由模型自行判断。",
        ]
        if self.config.glossary_enable == True:
            result = self.build_glossary_sakura(srcs)
            if result != "":
                content_lines.append("术语表（可空）：")
                content_lines.append(result)
                extra_log.append(result)

        content_lines.append(self.build_inputs(srcs))
        content = "\n".join(content_lines)

        # 构建提示词列表
        messages.append({
            "role": "user",
            "content": content,
        })

        return messages, extra_log

    # 生成提示词 - Sakura 格式化重试
    def generate_prompt_sakura_format_retry(self, srcs: list[str], raw_reply: str) -> tuple[list[dict], list[str]]:
        # 初始化
        messages: list[dict[str, str]] = []
        extra_log: list[str] = []

        messages.append({
            "role": "system",
            "content": "你是翻译结果的格式整理助手，只输出 JSONLINE。"
        })

        content_lines = [
            "把“模型回复内容”整理成 JSONLINE 输出。",
            "每行一个 JSON 对象，格式为 {\"序号\":\"译文\"}，序号从 0 开始。",
            "输出行数必须与输入行数一致，缺失行用空字符串补齐。",
            "如果出现中英双语，优先中文行，忽略英文行。",
            "保留控制字符/标签/变量（如 {w}、{...}、[...]）原样输出。",
            self.build_inputs(srcs),
            "模型回复内容：",
            raw_reply,
        ]
        content = "\n".join(content_lines)

        messages.append({
            "role": "user",
            "content": content,
        })

        return messages, extra_log
