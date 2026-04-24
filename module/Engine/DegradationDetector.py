class DegradationDetector:
    """
    流式输出退化检测器。

    检测三种重复退化模式：
    - Period 1: 单字符连续重复 (AAAA...)
    - Period 2: 双字符交替循环 (ABAB...)
    - Period 3: 三字符循环 (ABCABC...)

    灵感来源：LinguaGacha 的流式退化检测器。
    当前作为工具类提供，可在未来流式请求中用于提前中断退化的输出。
    """

    # 触发退化判定的重复次数阈值
    THRESHOLD: int = 50

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._last: str = ""
        self._second_last: str = ""
        self._third_last: str = ""
        self._period_1_run: int = 0
        self._period_2_run: int = 0
        self._period_3_run: int = 0
        self._degraded: bool = False

    @property
    def is_degraded(self) -> bool:
        return self._degraded

    def feed(self, text: str) -> bool:
        """
        逐字符喂入文本，检测退化。

        Args:
            text: 新增的流式输出文本片段。

        Returns:
            True 表示检测到退化，应中断输出。
        """
        if self._degraded:
            return True

        for ch in text:
            if ch.isspace():
                continue

            # Period 1: 单字符连续重复
            if ch == self._last:
                self._period_1_run += 1
            else:
                self._period_1_run = 1

            # Period 2: AB 交替循环（当前字符 == 倒数第二个，且倒数第二个 != 倒数第一个）
            if (
                self._second_last != ""
                and ch == self._second_last
                and self._second_last != self._last
            ):
                self._period_2_run += 1
            else:
                self._period_2_run = 0

            # Period 3: ABC 循环（当前 == 倒数第三个，且三者互不相同）
            if (
                self._third_last != ""
                and ch == self._third_last
                and self._third_last != self._second_last
                and self._second_last != self._last
                and self._third_last != self._last
            ):
                self._period_3_run += 1
            else:
                self._period_3_run = 0

            # 滑动窗口
            self._third_last = self._second_last
            self._second_last = self._last
            self._last = ch

            # 判定
            if (
                self._period_1_run >= self.THRESHOLD
                or self._period_2_run >= self.THRESHOLD
                or self._period_3_run >= self.THRESHOLD
            ):
                self._degraded = True
                return True

        return False

    def check_window(self, text: str, window_size: int = 512) -> bool:
        """
        对已有文本的尾部窗口做一次性退化检测（非流式场景）。

        Args:
            text: 完整的输出文本。
            window_size: 检查的尾部字符数。

        Returns:
            True 表示尾部存在退化。
        """
        tail = text[-window_size:] if len(text) > window_size else text
        detector = DegradationDetector()
        return detector.feed(tail)
