"""检查中英文本地化字段与占位符一致性。

    python scripts/check_localizer_parity.py

逐项对比 ``vars(LocalizerZH)`` 与 ``vars(LocalizerEN)`` 的自有字段
（跳过 dunder），输出任一侧缺失项、占位符差异与实际字段数量。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from module.Localizer.LocalizerEN import LocalizerEN
from module.Localizer.LocalizerZH import LocalizerZH

PLACEHOLDER = re.compile(r"\{([^{}]*)\}")


def own_fields(cls: type) -> dict[str, object]:
    return {key: value for key, value in vars(cls).items() if not key.startswith("__")}


def placeholders(value: object) -> set[str]:
    if not isinstance(value, str):
        return set()
    return {match for match in PLACEHOLDER.findall(value)}


def main() -> int:
    zh = own_fields(LocalizerZH)
    en = own_fields(LocalizerEN)

    missing = sorted(key for key in zh if key not in en)
    extra = sorted(key for key in en if key not in zh)
    placeholder_mismatch = sorted(
        key for key in zh if key in en and placeholders(zh[key]) != placeholders(en[key])
    )

    print(f"LocalizerZH 自有字段: {len(zh)}")
    print(f"LocalizerEN 自有字段: {len(en)}")
    print(f"缺失字段: {len(missing)}")
    for key in missing:
        print(f"  - {key}")
    print(f"中文缺失字段: {len(extra)}")
    for key in extra:
        print(f"  - {key}")
    print(f"占位符不一致字段: {len(placeholder_mismatch)}")
    for key in placeholder_mismatch:
        print(f"  - {key}: ZH={sorted(placeholders(zh[key]))} EN={sorted(placeholders(en[key]))}")

    if missing or extra or placeholder_mismatch:
        print("FAIL: 中英文字段或占位符不一致")
        return 1
    print("OK: 中英文字段集合与占位符一致")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
