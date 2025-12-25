import sys
from enum import Enum
from typing import TypeVar

try:
    from enum import StrEnum as _NativeStrEnum  # type: ignore
except Exception:
    _NativeStrEnum = None

try:
    from typing import Self as _NativeSelf  # type: ignore
except Exception:
    _NativeSelf = None


if _NativeStrEnum is not None and _NativeSelf is not None:
    StrEnum = _NativeStrEnum
    Self = _NativeSelf
else:
    class StrEnum(str, Enum):
        """
        StrEnum 的兼容实现 (Python 3.11+ 原生支持)
        """
        def __new__(cls, value):
            if not isinstance(value, str):
                raise TypeError(f"Values of StrEnum must be strings: {value!r} is a {type(value)}")
            return str.__new__(cls, value)

        def __str__(self):
            return self.value

        def _generate_next_value_(name, start, count, last_values):
            return name.lower()
    
    # Self 类型的兼容实现
    Self = TypeVar('Self')

__all__ = ['StrEnum', 'Self']
