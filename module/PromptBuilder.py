import json
import threading
import re
from functools import lru_cache

from base.Base import Base
from base.BaseLanguage import BaseLanguage
from base.PathHelper import get_resource_path
from module.Cache.CacheItem import CacheItem
from module.Config import Config
from module.Workbench.WorkbenchData import normalize_character_cards, normalize_text, normalize_text_list, normalize_worldbook

class PromptBuilder(Base):

    # 类线程锁
    LOCK: threading.Lock = threading.Lock()
    RE_GLOSSARY_IGNORE_SEGMENTS = re.compile(r"\[[^\]]*]|\{[^}]*}")
    RE_LATIN_ONLY = re.compile(r"^[A-Za-z\s'\-]+$")

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

    def get_prompt_language_and_names(self) -> tuple[BaseLanguage.Enum, str, str]:
        """获取提示词语言，以及原文/译文语言名称。"""
        if self.config.target_language == BaseLanguage.Enum.ZH:
            return (
                BaseLanguage.Enum.ZH,
                BaseLanguage.get_name_zh(self.config.source_language),
                BaseLanguage.get_name_zh(self.config.target_language),
            )

        return (
            BaseLanguage.Enum.EN,
            BaseLanguage.get_name_en(self.config.source_language),
            BaseLanguage.get_name_en(self.config.target_language),
        )

    def build_worldbook_context(self) -> str:
        """构建世界观上下文。"""
        if getattr(self.config, "renpy_workbench_worldbook_enable", False) is not True:
            return ""

        worldbook = normalize_worldbook(getattr(self.config, "renpy_workbench_worldbook_data", {}))
        if not any(worldbook.values()):
            return ""

        if self.config.target_language == BaseLanguage.Enum.ZH:
            lines = [
                "世界观设定：",
                f"项目名：{worldbook.get('project_name', '') or '未指定'}",
                f"类型：{worldbook.get('genre', '') or '未指定'}",
                f"背景摘要：{worldbook.get('setting_summary', '') or '未指定'}",
                f"时代与环境：{worldbook.get('era_background', '') or '未指定'}",
                f"整体语气：{worldbook.get('tone_style', '') or '未指定'}",
                f"叙事规则：{worldbook.get('narrative_rules', '') or '未指定'}",
                f"格式规则：{worldbook.get('format_rules', '') or '未指定'}",
            ]
            spoiler_notes = worldbook.get("spoiler_notes", "")
            if spoiler_notes:
                lines.append(f"剧透备注（仅供译者把握身份/关系，不要外显）：{spoiler_notes}")
            return "\n".join(lines)

        lines = [
            "Worldbook Context:",
            f"Project: {worldbook.get('project_name', '') or 'Unknown'}",
            f"Genre: {worldbook.get('genre', '') or 'Unknown'}",
            f"Setting Summary: {worldbook.get('setting_summary', '') or 'Unknown'}",
            f"Era and Environment: {worldbook.get('era_background', '') or 'Unknown'}",
            f"Tone Style: {worldbook.get('tone_style', '') or 'Unknown'}",
            f"Narrative Rules: {worldbook.get('narrative_rules', '') or 'Unknown'}",
            f"Formatting Rules: {worldbook.get('format_rules', '') or 'Unknown'}",
        ]
        spoiler_notes = worldbook.get("spoiler_notes", "")
        if spoiler_notes:
            lines.append(f"Spoiler Notes (translator-only): {spoiler_notes}")
        return "\n".join(lines)

    def _text_contains_term(self, haystack: str, term: str) -> bool:
        """判断文本中是否命中候选词。"""
        full = normalize_text(haystack)
        needle = normalize_text(term)
        if full == "" or needle == "":
            return False

        if re.fullmatch(r"[A-Za-z0-9_ .'’-]+", needle):
            pattern = rf"(?<![A-Za-z0-9_]){re.escape(needle)}(?![A-Za-z0-9_])"
            return re.search(pattern, full, flags = re.IGNORECASE) is not None
        return needle.casefold() in full.casefold()

    def match_character_cards(
        self,
        srcs: list[str],
        items: list[CacheItem] | None,
    ) -> list[dict]:
        """匹配当前批次命中的角色卡。"""
        if getattr(self.config, "renpy_workbench_character_cards_enable", False) is not True:
            return []

        cards = [
            card
            for card in normalize_character_cards(getattr(self.config, "renpy_workbench_character_cards", []))
            if card.get("enabled", True)
        ]
        if cards == []:
            return []

        items = items or []
        speaker_names = {
            normalize_text(item.get_first_name_src()).casefold()
            for item in items
            if normalize_text(item.get_first_name_src()) != ""
        }
        merged_text = "\n".join(normalize_text_list(srcs, unique = False))

        matched: list[dict] = []
        for card in cards:
            name = normalize_text(card.get("name", ""))
            aliases = normalize_text_list(card.get("aliases", []))
            keywords = normalize_text_list(card.get("match_keywords", []))

            name_hits = {name.casefold()} if name else set()
            name_hits.update(alias.casefold() for alias in aliases)
            if speaker_names & name_hits:
                matched.append(card)
                continue

            tokens = normalize_text_list([name] + aliases + keywords)
            if any(self._text_contains_term(merged_text, token) for token in tokens):
                matched.append(card)

        matched.sort(
            key = lambda card: (
                0 if card.get("is_primary", False) else 1,
                normalize_text(card.get("name", "")).casefold(),
            )
        )
        return matched

    def build_character_context(
        self,
        srcs: list[str],
        items: list[CacheItem] | None,
    ) -> str:
        """构建命中角色卡上下文。"""
        matched = self.match_character_cards(srcs, items)
        if matched == []:
            return ""

        if self.config.target_language == BaseLanguage.Enum.ZH:
            blocks = ["命中角色卡："]
            for card in matched:
                lines = [
                    f"角色：{normalize_text(card.get('name', ''))}",
                ]
                translation = normalize_text(card.get("name_translation", ""))
                if translation:
                    lines.append(f"推荐译名：{translation}")
                aliases = normalize_text_list(card.get("aliases", []))
                if aliases:
                    lines.append(f"别名：{'、'.join(aliases)}")
                lines.append(f"身份：{normalize_text(card.get('identity', '')) or '未指定'}")
                lines.append(f"性格：{normalize_text(card.get('personality', '')) or '未指定'}")
                lines.append(f"说话风格：{normalize_text(card.get('speech_style', '')) or '未指定'}")
                relation = normalize_text(card.get("relationship_notes", ""))
                if relation:
                    lines.append(f"关系备注：{relation}")
                prompt_notes = normalize_text(card.get("prompt_notes", ""))
                if prompt_notes:
                    lines.append(f"翻译提示：{prompt_notes}")
                sample_lines = normalize_text_list(card.get("sample_lines", []))
                if sample_lines:
                    lines.append("代表台词：")
                    lines.extend(f"- {line}" for line in sample_lines[:4])
                blocks.append("\n".join(lines))
            return "\n\n".join(blocks)

        blocks = ["Matched Character Cards:"]
        for card in matched:
            lines = [
                f"Character: {normalize_text(card.get('name', ''))}",
                f"Identity: {normalize_text(card.get('identity', '')) or 'Unknown'}",
                f"Personality: {normalize_text(card.get('personality', '')) or 'Unknown'}",
                f"Speech Style: {normalize_text(card.get('speech_style', '')) or 'Unknown'}",
            ]
            translation = normalize_text(card.get("name_translation", ""))
            if translation:
                lines.append(f"Preferred Translation: {translation}")
            aliases = normalize_text_list(card.get("aliases", []))
            if aliases:
                lines.append(f"Aliases: {', '.join(aliases)}")
            relation = normalize_text(card.get("relationship_notes", ""))
            if relation:
                lines.append(f"Relationship Notes: {relation}")
            prompt_notes = normalize_text(card.get("prompt_notes", ""))
            if prompt_notes:
                lines.append(f"Prompt Notes: {prompt_notes}")
            sample_lines = normalize_text_list(card.get("sample_lines", []))
            if sample_lines:
                lines.append("Representative Lines:")
                lines.extend(f"- {line}" for line in sample_lines[:4])
            blocks.append("\n".join(lines))
        return "\n\n".join(blocks)

    # 构造参考上文
    def build_preceding(self, precedings: list[CacheItem]) -> str:
        if len(precedings) == 0:
            return ""

        lines = []
        for item in precedings:
            src = item.get_src().strip().replace("\n", "\\n")
            dst = (item.get_dst() or "").strip().replace("\n", "\\n")
            if dst and dst != src:
                lines.append(f"{src} -> {dst}")
            else:
                lines.append(src)

        if self.config.target_language == BaseLanguage.Enum.ZH:
            return "参考上文（原文 -> 译文）：\n" + "\n".join(lines)
        else:
            return "Preceding Context (Source -> Translation):\n" + "\n".join(lines)

    # 构造术语表
    def build_glossary(self, srcs: list[str]) -> str:
        full = "\n".join(srcs)
        # 术语匹配时忽略占位/标签段，避免 [jane_rlt2] 命中术语 "jane"。
        full_clean = __class__.RE_GLOSSARY_IGNORE_SEGMENTS.sub("", full)
        full_lower = full_clean.lower()
        full_raw_lower = full.lower()
        glossary: list[dict[str, str]] = []
        for v in self.config.glossary_data:
            src = v.get("src", "")
            if src == "":
                continue
            # 若术语本身带占位字符，按原文匹配；普通术语按清洗后文本匹配。
            target_full = full if any(ch in src for ch in "[]{}") else full_clean
            is_case_sensitive = v.get("case_sensitive", False)
            # 纯拉丁术语使用词边界匹配，避免 "an" 匹配 "Another"
            use_word_boundary = bool(__class__.RE_LATIN_ONLY.match(src)) and len(src) <= 20
            if use_word_boundary:
                flags = 0 if is_case_sensitive else re.IGNORECASE
                if re.search(r"\b" + re.escape(src) + r"\b", target_full, flags):
                    glossary.append(v)
            elif is_case_sensitive:
                if src in target_full:
                    glossary.append(v)
            else:
                target_lower = full_raw_lower if any(ch in src for ch in "[]{}") else full_lower
                if src.lower() in target_lower:
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
        full_clean = __class__.RE_GLOSSARY_IGNORE_SEGMENTS.sub("", full)
        full_lower = full_clean.lower()
        full_raw_lower = full.lower()
        glossary: list[dict[str, str]] = []
        for v in self.config.glossary_data:
            src = v.get("src", "")
            if src == "":
                continue
            target_full = full if any(ch in src for ch in "[]{}") else full_clean
            is_case_sensitive = v.get("case_sensitive", False)
            use_word_boundary = bool(__class__.RE_LATIN_ONLY.match(src)) and len(src) <= 20
            if use_word_boundary:
                flags = 0 if is_case_sensitive else re.IGNORECASE
                if re.search(r"\b" + re.escape(src) + r"\b", target_full, flags):
                    glossary.append(v)
            elif is_case_sensitive:
                if src in target_full:
                    glossary.append(v)
            else:
                target_lower = full_raw_lower if any(ch in src for ch in "[]{}") else full_lower
                if src.lower() in target_lower:
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
        # 结构化输出模式：纯文本输入 + 简要 JSON 指令（格式由 API schema 保证）
        if self.config.structured_output_enable:
            lines = "\n".join(srcs)
            if self.config.target_language == BaseLanguage.Enum.ZH:
                return (
                    "以 JSON 格式返回，包含 translations 数组，每个元素对应一行译文。"
                    "\n" + "原文："
                    "\n" + lines
                )
            else:
                return (
                    "Return JSON with a translations array, each element is the translation of the corresponding line."
                    "\n" + "Source:"
                    "\n" + lines
                )

        # 传统 JSONLINE 模式
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

    def build_single_line_instruction(self) -> str:
        """构建单行翻译模式的极简提示，避免小模型被 JSONLINE 格式拖垮。"""
        prompt_language, source_language, target_language = self.get_prompt_language_and_names()

        if prompt_language == BaseLanguage.Enum.ZH:
            return (
                f"你是游戏文本翻译器。将下面这一行{source_language}原文翻译成{target_language}。"
                "\n"
                "只输出译文文本本身，不要编号、不要 JSON、不要解释、不要额外换行。"
                "\n"
                "保留原文中的控制字符、变量、标签、占位符和代码片段（如 {name}、[player]、%s、\\n）原样不变。"
                "\n"
                "自然语言、对话、旁白和 UI 文本必须翻译；只有明确无需翻译的人名、品牌、代码或占位符可以保留。"
            )

        return (
            f"You are a game localization translator. Translate this single {source_language} line into {target_language}."
            "\n"
            "Output only the translated text itself. Do not output numbering, JSON, explanations, or extra line breaks."
            "\n"
            "Preserve control characters, variables, tags, placeholders, and code fragments exactly as-is, such as {name}, [player], %s, and \\n."
            "\n"
            "Natural language, dialogue, narration, and UI text must be translated. Only clear proper names, brands, code, or placeholders may remain unchanged."
        )

    def build_single_line_input(self, src: str) -> str:
        prompt_language, _, _ = self.get_prompt_language_and_names()
        if prompt_language == BaseLanguage.Enum.ZH:
            return "原文：\n```text\n" + src + "\n```"

        return "Source:\n```text\n" + src + "\n```"

    def build_single_line_control_samples(self, samples: list[str]) -> str:
        samples = sorted({v.strip() for v in samples if isinstance(v, str) and v.strip() != ""})
        if len(samples) == 0:
            return ""

        prompt_language, _, _ = self.get_prompt_language_and_names()
        if prompt_language == BaseLanguage.Enum.ZH:
            return "需要原样保留的控制字符示例：\n" + ", ".join(samples)

        return "Control character examples that must be preserved:\n" + ", ".join(samples)

    def generate_single_line_prompt(
        self,
        src: str,
        samples: list[str],
        precedings: list[CacheItem],
        local_flag: bool,
        item: CacheItem | None = None,
    ) -> tuple[list[dict], list[str]]:
        """生成单行翻译提示词：单请求单原文，允许模型直接输出纯文本。"""
        messages: list[dict[str, str]] = []
        extra_log: list[str] = []
        items = [item] if item is not None else None

        content = self.build_single_line_instruction()

        result = self.build_worldbook_context()
        if result != "":
            content = content + "\n" + result
            extra_log.append(result)

        result = self.build_character_context([src], items)
        if result != "":
            content = content + "\n" + result
            extra_log.append(result)

        result = self.build_retry_hint(items)
        if result != "":
            content = content + "\n" + result
            extra_log.append(result)

        if local_flag == False or self.config.enable_preceding_on_local == True:
            result = self.build_preceding(precedings)
            if result != "":
                content = content + "\n" + result
                extra_log.append(result)

        if self.config.glossary_enable == True:
            result = self.build_glossary([src])
            if result != "":
                content = content + "\n" + result
                extra_log.append(result)

        result = self.build_single_line_control_samples(samples)
        if result != "":
            content = content + "\n" + result
            extra_log.append(result)

        content = content + "\n" + self.build_single_line_input(src)
        messages.append({
            "role": "user",
            "content": content,
        })

        return messages, extra_log

    def build_retry_hint(self, items: list[CacheItem] | None) -> str:
        """为已重试的条目追加更强的翻译约束，降低原文照抄概率。"""
        if not items:
            return ""

        retry_items = [item for item in items if item is not None and item.get_retry_count() > 0]
        if retry_items == []:
            return ""

        if self.config.target_language == BaseLanguage.Enum.ZH:
            return (
                "重试要求：以下内容此前未通过结果检查。"
                "\n"
                "若原文属于自然语言文本（对话、旁白、UI、描述），本次必须完整翻译成中文。"
                "\n"
                "禁止直接复述英文/日文/韩文原文，禁止只做轻微改写，禁止输出与原文基本一致的句子。"
                "\n"
                "只有变量、标签、占位符、代码片段、明确无需翻译的人名/专有名词，才允许按规则保留原样。"
            )

        return (
            "Retry Requirement: the following content failed the previous validation."
            "\n"
            "If the source is natural language text such as dialogue, narration, UI, or descriptions, you must fully translate it into the target language."
            "\n"
            "Do not repeat the original text, do not lightly paraphrase it, and do not return a sentence that is still substantially the same as the source."
            "\n"
            "Only variables, tags, placeholders, code fragments, or clearly non-translatable proper nouns may remain unchanged."
        )

    # 生成提示词
    def generate_prompt(
        self,
        srcs: list[str],
        samples: list[str],
        precedings: list[CacheItem],
        local_flag: bool,
        items: list[CacheItem] | None = None,
    ) -> tuple[list[dict], list[str]]:
        # 初始化
        messages: list[dict[str, str]] = []
        extra_log: list[str] = []

        # === system 消息：固定指令 + 世界观/角色卡等上下文 ===
        system_content = self.build_main()

        # 工作台上下文（相对稳定，适合放在 system 中以利用 API prompt cache）
        result = self.build_worldbook_context()
        if result != "":
            system_content = system_content + "\n" + result
            extra_log.append(result)

        result = self.build_character_context(srcs, items)
        if result != "":
            system_content = system_content + "\n" + result
            extra_log.append(result)

        messages.append({
            "role": "system",
            "content": system_content,
        })

        # === user 消息：每批次变化的内容 ===
        user_content = ""

        result = self.build_retry_hint(items)
        if result != "":
            user_content = user_content + result
            extra_log.append(result)

        # 参考上文
        if local_flag == False or self.config.enable_preceding_on_local == True:
            result = self.build_preceding(precedings)
            if result != "":
                user_content = (user_content + "\n" + result) if user_content else result
                extra_log.append(result)

        # 术语表
        if self.config.glossary_enable == True:
            result = self.build_glossary(srcs)
            if result != "":
                user_content = (user_content + "\n" + result) if user_content else result
                extra_log.append(result)

        # 控制字符示例
        result = self.build_control_characters_samples(system_content, samples)
        if result != "":
            user_content = (user_content + "\n" + result) if user_content else result
            extra_log.append(result)

        # 输入
        result = self.build_inputs(srcs)
        if result != "":
            user_content = (user_content + "\n" + result) if user_content else result

        messages.append({
            "role": "user",
            "content": user_content,
        })

        return messages, extra_log

    # 生成提示词 - Sakura
    def generate_prompt_sakura(
        self,
        srcs: list[str],
        items: list[CacheItem] | None = None,
    ) -> tuple[list[dict], list[str]]:
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
        result = self.build_worldbook_context()
        if result != "":
            content_lines.append(result)
            extra_log.append(result)
        result = self.build_character_context(srcs, items)
        if result != "":
            content_lines.append(result)
            extra_log.append(result)
        result = self.build_retry_hint(items)
        if result != "":
            content_lines.append(result)
            extra_log.append(result)
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
