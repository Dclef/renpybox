import time

class TaskLimiter:

    def __init__(self, rps: int, rpm: int) -> None:
        self.rps = rps
        self.rpm = rpm
        self.unlimited = (self.rps <= 0 and self.rpm <= 0)

        if self.unlimited:
            self.max_tokens = float("inf")
            self.rate_per_second = float("inf")
            self.available_tokens = float("inf")
            self.last_request_time = time.time()
        else:
            self.max_tokens = self._calculate_max_tokens()
            self.rate_per_second = self._calculate_stricter_rate()
            self.available_tokens = self.max_tokens
            self.last_request_time = time.time()

    # 计算最大令牌数
    def _calculate_max_tokens(self) -> float:
        per_second_rps = self.rps if self.rps > 0 else float("inf")
        per_second_rpm = (self.rpm / 60) if self.rpm > 0 else float("inf")
        limit = min(per_second_rps, per_second_rpm)
        if limit == float("inf"):
            return float("inf")
        return max(limit, 1.0)

    # 计算每秒恢复的请求额度
    def _calculate_stricter_rate(self) -> float:
        per_second_rps = self.rps if self.rps > 0 else float("inf")
        per_second_rpm = (self.rpm / 60) if self.rpm > 0 else float("inf")
        limit = min(per_second_rps, per_second_rpm)
        if limit == float("inf"):
            return float("inf")
        return max(limit, 1.0)

    # 等待直到有足够的请求额度
    def wait(self) -> None:
        if self.unlimited or self.rate_per_second == float("inf"):
            return

        current_time = time.time()
        elapsed_time = current_time - self.last_request_time

        # 恢复额度
        self.available_tokens = self.available_tokens + elapsed_time * self.rate_per_second
        self.available_tokens = min(self.available_tokens, self.max_tokens)

        # 如果额度不足，等待
        if self.available_tokens < 1:
            sleep_time = (1 - self.available_tokens) / self.rate_per_second
            if sleep_time > 0:
                time.sleep(sleep_time)
            self.available_tokens = 1

        # 扣减令牌
        self.available_tokens = self.available_tokens - 1

        # 更新最后请求时间
        self.last_request_time = time.time()
