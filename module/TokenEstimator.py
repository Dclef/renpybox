import dataclasses
import math

import tiktoken

from base.Base import Base
from module.Cache.CacheItem import CacheItem
from module.Config import Config
from module.PromptBuilder import PromptBuilder


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
        self.encoder = tiktoken.get_encoding("o200k_base")

    def estimate(self) -> TokenEstimate:
        untranslated = [
            item for item in self.items
            if item.get_status() == Base.TranslationStatus.UNTRANSLATED
            and item.get_src()
            and item.get_src().strip()
        ]

        if not untranslated:
            return TokenEstimate()

        total_source_tokens = sum(item.get_token_count() for item in untranslated)

        prompt_overhead = self._estimate_prompt_overhead()

        line_limit = max(1, self.config.token_threshold)
        token_limit = max(64, self.config.token_threshold * 16)
        batch_count = self._estimate_batch_count(untranslated, line_limit, token_limit)

        estimated_input_tokens = total_source_tokens + (batch_count * prompt_overhead)

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
            return len(self.encoder.encode(main_prompt)) + 50
        except Exception:
            return 300

    def _estimate_batch_count(
        self,
        items: list[CacheItem],
        line_limit: int,
        token_limit: int,
    ) -> int:
        batch_count = 0
        current_lines = 0
        current_tokens = 0

        for item in items:
            src = item.get_src()
            item_lines = sum(1 for line in src.splitlines() if line.strip())
            item_tokens = item.get_token_count()

            if current_lines > 0 and (
                current_lines + item_lines > line_limit
                or current_tokens + item_tokens > token_limit
            ):
                batch_count += 1
                current_lines = 0
                current_tokens = 0

            current_lines += item_lines
            current_tokens += item_tokens

        if current_lines > 0:
            batch_count += 1

        return max(1, batch_count)
