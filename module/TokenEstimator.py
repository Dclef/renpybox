import dataclasses
import copy
import json

try:
    import tiktoken
except Exception:  # 可选依赖缺失时使用 UTF-8 字节近似，不阻断页面加载。
    tiktoken = None

from base.Base import Base
from module.Cache.CacheItem import CacheItem
from module.Cache.CacheManager import CacheManager
from module.Config import Config
from module.PromptBuilder import PromptBuilder
from module.Engine.Translator.ProjectAssetsRepository import ProjectAssetsRepository
from module.TextProcessor import TextProcessor


@dataclasses.dataclass
class TokenEstimate:
    total_source_tokens: int = 0
    estimated_input_tokens: int = 0
    estimated_output_tokens: int = 0
    estimated_cost: float = 0.0
    batch_count: int = 0
    untranslated_count: int = 0


class TokenEstimator:

    def __init__(self, config: Config, platform: dict, items: list[CacheItem]) -> None:
        self.config = config
        self.platform = platform
        self.items = items
        self.encoder = self._get_encoder()

    @staticmethod
    def _get_encoder():
        """按安装版本选择编码器，旧版 tiktoken 不支持时使用字节近似。"""
        if tiktoken is None:
            return None
        for name in ("o200k_base", "cl100k_base"):
            try:
                return tiktoken.get_encoding(name)
            except Exception:
                continue
        return None

    def _count_tokens(self, text: str) -> int:
        text = str(text or "")
        if text == "":
            return 0
        if self.encoder is not None:
            try:
                return len(self.encoder.encode(text))
            except Exception:
                pass
        return max(1, (len(text.encode("utf-8")) + 3) // 4)

    def estimate(self) -> TokenEstimate:
        untranslated = [
            item for item in self.items
            if item.get_status() == Base.TranslationStatus.UNTRANSLATED
            and item.get_src()
            and item.get_src().strip()
        ]

        if not untranslated:
            return TokenEstimate()

        total_source_tokens = sum(self._count_tokens(item.get_src()) for item in untranslated)

        line_limit = max(1, self.config.token_threshold)
        if (
            getattr(self.config, "single_line_translation_enable", False)
            and self.platform.get("api_format")
            not in (Base.APIFormat.DEEPL, Base.APIFormat.DEEPLX)
        ):
            line_limit = 1
        token_limit = max(64, self.config.token_threshold * 16)
        batches = self._estimate_batches(untranslated, line_limit, token_limit)
        batch_count = len(batches)

        estimated_input_tokens = self._estimate_batch_prompt_tokens(batches)

        output_ratio = getattr(self.config, "token_estimation_output_ratio", 1.2)
        estimated_output_tokens = int(total_source_tokens * output_ratio)

        input_price = float(self.platform.get("input_price_per_million", 0) or 0)
        output_price = float(self.platform.get("output_price_per_million", 0) or 0)
        estimated_cost = (
            estimated_input_tokens * input_price + estimated_output_tokens * output_price
        ) / 1_000_000

        return TokenEstimate(
            total_source_tokens=total_source_tokens,
            estimated_input_tokens=estimated_input_tokens,
            estimated_output_tokens=estimated_output_tokens,
            estimated_cost=estimated_cost,
            batch_count=batch_count,
            untranslated_count=len(untranslated),
        )

    def _estimate_prompt_overhead(self) -> int:
        try:
            builder = PromptBuilder(self.config)
            main_prompt = builder.build_main()
            return self._count_tokens(main_prompt) + 50
        except Exception:
            return 300

    def _estimate_batch_prompt_tokens(self, batches: list[list[CacheItem]]) -> int:
        """按真实批次估算完整请求，尽量复用实际提示词生成链路。"""
        try:
            # 从稳定的项目资产目录读取一次，保证增量输出与主输出使用同一资产。
            working = copy.deepcopy(self.config)
            ProjectAssetsRepository.from_config(working).load_into_config(working)
            builder = PromptBuilder(working)
            total = 0
            local_flag = str(self.platform.get("api_url", "")).lower().startswith((
                "http://localhost",
                "https://localhost",
                "http://127.",
                "https://127.",
            ))
            for batch in batches:
                if not batch:
                    continue

                # TranslatorTask 会先经过 TextProcessor，再把控制字符样本、
                # 结构化占位符和桥接 token 交给 PromptBuilder。这里使用副本
                # 执行同一预处理，避免估算漏掉真实请求中的保护开销。
                copied_items = [CacheItem.from_dict(item.asdict()) for item in batch]
                srcs: list[str] = []
                samples: list[str] = []
                processed_srcs: list[list[str]] = []
                processed_samples: list[list[str]] = []
                for item in copied_items:
                    processor = TextProcessor(working, item)
                    processor.pre_process()
                    item_srcs = list(processor.srcs)
                    item_samples = list(processor.samples)
                    processed_srcs.append(item_srcs)
                    processed_samples.append(item_samples)
                    srcs.extend(item_srcs)
                    samples.extend(item_samples)

                if not srcs:
                    continue

                preceding = self._estimate_preceding_items(batch)
                single_line = (
                    getattr(working, "single_line_translation_enable", False)
                    and self.platform.get("api_format")
                    not in (Base.APIFormat.DEEPL, Base.APIFormat.DEEPLX)
                )

                if single_line:
                    # 单行模式每一行都是独立请求，不能把整批 JSON 包装
                    # 误算成一次请求。
                    for item, item_srcs, item_samples in zip(
                        copied_items,
                        processed_srcs,
                        processed_samples,
                    ):
                        for src in item_srcs:
                            messages, _ = builder.generate_single_line_prompt(
                                src = src,
                                samples = item_samples,
                                precedings = preceding,
                                local_flag = local_flag,
                                item = item,
                            )
                            total += self._count_messages_tokens(messages)
                    continue

                if self.platform.get("api_format") == Base.APIFormat.SAKURALLM:
                    messages, _ = builder.generate_prompt_sakura(
                        srcs,
                        items = copied_items,
                    )
                else:
                    messages, _ = builder.generate_prompt(
                        srcs,
                        samples,
                        preceding,
                        local_flag,
                        items = copied_items,
                    )
                total += self._count_messages_tokens(messages)
            return total
        except Exception:
            return len(batches) * self._estimate_prompt_overhead()

    def _count_messages_tokens(self, messages: list[dict]) -> int:
        """估算聊天协议的角色、分隔符和 JSON 序列化开销。"""
        total = 0
        for message in messages or []:
            role = str(message.get("role", ""))
            content = str(message.get("content", ""))
            total += self._count_tokens(role) + self._count_tokens(content) + 4
        # 不同兼容接口的 chat wrapper 略有差异，保留一个小的固定尾部。
        wire = json.dumps(messages or [], ensure_ascii = False, separators = (",", ":"))
        return total + self._count_tokens(wire) // 20 + 2

    def _estimate_preceding_items(self, batch: list[CacheItem]) -> list[CacheItem]:
        """按 CacheManager 的同文件/标点规则选取参考上文。"""
        threshold = max(0, int(getattr(self.config, "preceding_lines_threshold", 0) or 0))
        if not batch or threshold <= 0:
            return []
        first_index = None
        for index, item in enumerate(self.items):
            if item is batch[0]:
                first_index = index
                break
        if first_index is None:
            return []
        result: list[CacheItem] = []
        file_path = batch[-1].get_file_path()
        punctuation = CacheManager.END_LINE_PUNCTUATION
        for item in reversed(self.items[:first_index]):
            if item.get_status() == Base.TranslationStatus.EXCLUDED:
                continue
            if item.get_file_path() != file_path:
                break
            src = item.get_src().strip()
            if not src:
                continue
            if src.endswith(tuple(punctuation)):
                result.append(item)
                if len(result) >= threshold:
                    break
        return list(reversed(result))

    def _estimate_batches(
        self,
        items: list[CacheItem],
        line_limit: int,
        token_limit: int,
    ) -> list[list[CacheItem]]:
        batches: list[list[CacheItem]] = []
        current: list[CacheItem] = []
        current_lines = 0
        current_tokens = 0

        for item in items:
            src = item.get_src()
            item_lines = sum(1 for line in src.splitlines() if line.strip())
            item_tokens = self._count_tokens(src)

            if current_lines > 0 and (
                current_lines + item_lines > line_limit
                or current_tokens + item_tokens > token_limit
                or item.get_file_path() != current[-1].get_file_path()
            ):
                batches.append(current)
                current = []
                current_lines = 0
                current_tokens = 0

            current.append(item)
            current_lines += item_lines
            current_tokens += item_tokens

        if current_lines > 0:
            batches.append(current)

        return batches or [[]]
