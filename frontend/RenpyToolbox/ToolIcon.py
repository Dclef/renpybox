from enum import Enum
from functools import lru_cache
from pathlib import Path

from PyQt5.QtCore import QByteArray, QRectF
from PyQt5.QtSvg import QSvgRenderer
from qfluentwidgets import FluentIconBase, Theme, isDarkTheme

from base.PathHelper import get_resource_path


@lru_cache(maxsize=64)
def _themed_svg(path: str, color: str) -> QByteArray:
    """读取 SVG 并缓存主题色替换结果。"""
    content = Path(path).read_text(encoding="utf-8")
    return QByteArray(content.replace("currentColor", color).encode("utf-8"))


class ToolIcon(FluentIconBase, Enum):
    """Ren'Py 工具箱使用的 Lucide 矢量图标。"""

    CONTINUE = "rotate-ccw"
    ONE_KEY = "wand-sparkles"
    PROOFREAD = "clipboard-check"
    APPLY = "folder-input"
    FONT = "type"
    ADD_LANGUAGE = "languages"
    DEFAULT_LANGUAGE = "globe"
    EXTRACT_TL = "file-down"
    DIRECT_RPY = "file-pen-line"
    HOOK = "webhook"
    SOURCE = "file-code"
    SUPPLEMENT = "file-plus"
    JSON = "braces"
    GLOSSARY = "book-open-text"
    PRESERVE = "shield-ban"
    HONORIFIC = "variable"
    STRUCTURE = "table-2"
    BATCH = "list-checks"
    NAME = "users-round"
    PACK = "archive"
    REPAIR = "wrench"
    FORMAT = "text-align-start"
    ANDROID = "smartphone"
    HTML = "file-input"

    def path(self, theme: Theme = Theme.AUTO) -> str:
        del theme
        return get_resource_path(
            "resource",
            "icons",
            "toolbox",
            f"{self.value}.svg",
        )

    def render(
        self,
        painter,
        rect,
        theme: Theme = Theme.AUTO,
        indexes=None,
        **attributes,
    ) -> None:
        del indexes
        del attributes
        dark = isDarkTheme() if theme == Theme.AUTO else theme == Theme.DARK
        color = "#F2F2F2" if dark else "#202020"
        renderer = QSvgRenderer(_themed_svg(self.path(theme), color))
        renderer.render(painter, QRectF(rect))
