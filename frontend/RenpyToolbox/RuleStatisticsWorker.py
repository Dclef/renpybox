from typing import Any

from PyQt5.QtCore import QThread
from PyQt5.QtCore import pyqtSignal

from module.Config import Config
from module.RuleStatistics import count_glossary_hit_counts
from module.RuleStatistics import count_text_preserve_hit_counts
from module.RuleStatistics import get_statistics_cache_dir
from module.RuleStatistics import load_counted_source_texts


class RuleStatisticsWorker(QThread):
    """规则统计后台线程。"""

    MODE_GLOSSARY = "glossary"
    MODE_TEXT_PRESERVE = "text_preserve"

    finished = pyqtSignal(bool, str, object)  # success, message, payload

    def __init__(
        self,
        *,
        mode: str,
        config: Config,
        entries: list[dict[str, Any]],
        parent = None,
    ):
        super().__init__(parent)
        self.mode = mode
        self.config = config
        self.entries = [dict(entry) for entry in entries if isinstance(entry, dict)]

    def run(self):
        try:
            texts = load_counted_source_texts(self.config)
            if len(texts) == 0:
                cache_dir = get_statistics_cache_dir(self.config)
                self.finished.emit(
                    False,
                    (
                        "未找到可统计的缓存条目。"
                        + (f"\n当前检查路径：{cache_dir}" if cache_dir else "")
                        + "\n请先执行一次翻译，或确认当前输出目录下存在 cache。"
                    ),
                    {
                        "cache_dir": cache_dir,
                    },
                )
                return

            if self.mode == __class__.MODE_GLOSSARY:
                counts = count_glossary_hit_counts(self.entries, texts)
            elif self.mode == __class__.MODE_TEXT_PRESERVE:
                counts = count_text_preserve_hit_counts(self.entries, texts)
            else:
                self.finished.emit(False, f"不支持的统计模式: {self.mode}", {})
                return

            self.finished.emit(
                True,
                "统计完成",
                {
                    "counts": counts,
                    "counted_item_total": len(texts),
                },
            )
        except Exception as e:
            self.finished.emit(False, str(e), {})
