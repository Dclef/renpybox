"""校对表装载耗时基准（slow 标记，默认与 CI 跳过）。

手动运行：python -m pytest tests/frontend/test_proofread_bench.py -m slow -s
不设硬阈值——先积累真实数据，阈值待真实分布出来后再定（方案验收哲学）。
"""

import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

from frontend.Proofreading.ProofreadingTableWidget import ProofreadingTableWidget
from module.Cache.CacheItem import CacheItem


APP = QApplication.instance() or QApplication([])


def _make_items(count: int) -> list[CacheItem]:
    return [
        CacheItem(
            src = f"原文第 {i} 行，包含一些长度可变的文本内容用于装载基准。",
            dst = f"译文第 {i} 行，与原文行数一致。",
        )
        for i in range(count)
    ]


@pytest.mark.slow
@pytest.mark.parametrize("rows", [100, 500, 2000])
def test_proofread_table_load_benchmark(rows: int) -> None:
    # 直接给控件喂 rows 行：测装载耗时随行数的伸缩性，
    # 为未来表格 Model/View 化（P2）提供对照基线；
    # 生产路径分页固定 100 行/页，rows=100 即现网真实页大小
    widget = ProofreadingTableWidget()
    page_items = _make_items(rows)
    warning_map: dict[int, list] = {}

    # 预热一次（首次构建有样式/字体缓存开销）
    widget.set_items(page_items, warning_map)

    samples: list[float] = []
    for _ in range(5):
        start = time.perf_counter()
        widget.set_items(page_items, warning_map)
        samples.append((time.perf_counter() - start) * 1000)

    ordered = sorted(samples)
    print(f"\n[bench] rows={rows} page_load_ms: min={ordered[0]:.1f} median={ordered[2]:.1f} max={ordered[-1]:.1f}")
    assert ordered[2] > 0  # 只断言可完成与计时有效，阈值待真实数据
