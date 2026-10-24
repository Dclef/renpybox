"""剧情蓝图用到的图片解析：把 `scene bg hall night` 这类标签还原成 game 下的文件。

自包含实现，刻意不复用 `module/Renpy/ImageResolver.py`（那边要处理 layeredimage、
ConditionSwitch 深度分支等完整语义，成本高）。这里只需要「第一张画面」足够准：

1. 定义索引：扫 `image <tag> = <expr>` 与 `image <tag>:`（ATL 块），取其中的路径字符串；
2. 文件索引：按文件名（去扩展名）建索引，`images/` 目录优先；
3. 解析：整串 → 逐级丢掉属性（`bg hall night` → `bg hall`）→ 空格/下划线变体依次试。

纯文件扫描，不依赖 Ren'Py 运行时；结果按 game_dir 进程内缓存。
"""

from __future__ import annotations

import os
import re
import threading
from pathlib import Path

MEDIA_SUFFIXES = frozenset(
    {".webp", ".png", ".jpg", ".jpeg", ".avif", ".gif", ".mp4", ".webm", ".mkv", ".avi"}
)
VIDEO_SUFFIXES = frozenset({".mp4", ".webm", ".mkv", ".avi"})
# 这些不是文件，是 Ren'Py 的颜色/占位符；当成解析失败，前端显示文字卡。
COLOR_NAMES = frozenset(
    {
        "black",
        "white",
        "transparent",
        "solid",
        "clear",
        "none",
        "red",
        "green",
        "blue",
        "yellow",
        "purple",
        "orange",
        "gray",
        "grey",
        "pink",
    }
)

_QUOTED_RE = re.compile(r'["\']([^"\']+)["\']')
_IMAGE_EQUALS_RE = re.compile(r"^image\s+(.+?)\s*=\s*(.+?)\s*$")
_IMAGE_BLOCK_RE = re.compile(r"^image\s+(.+?)\s*:\s*$")


def _normalise_tag(tag: str) -> str:
    return " ".join(str(tag or "").split()).lower()


def _candidates(tag: str) -> list[str]:
    """整串优先，再逐级丢属性（`bg hall night` → `bg hall`），最后丢分类前缀。

    Ren'Py 的图片标签约定是 `<分类> <名字>`，文件通常只按名字命名，
    所以「bg room」还要能落到 room.webp 上。
    """
    key = _normalise_tag(tag)
    if not key:
        return []
    parts = key.split()
    out: list[str] = []
    for cut in range(len(parts), 0, -1):
        prefix = " ".join(parts[:cut])
        for variant in (prefix, prefix.replace(" ", "_"), prefix.replace(" ", "")):
            if variant not in out:
                out.append(variant)
    for start in range(1, len(parts)):
        suffix = " ".join(parts[start:])
        for variant in (suffix, suffix.replace(" ", "_"), suffix.replace(" ", "")):
            if variant not in out:
                out.append(variant)
    return out


class SceneImageIndex:
    """`game/` 下的图片/视频索引与标签解析。首次使用时才建索引。"""

    def __init__(self, game_dir: Path) -> None:
        self.game_dir = Path(game_dir)
        self._files: dict[str, str] | None = None
        self._definitions: dict[str, dict] | None = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------- 索引构建
    def _rpy_files(self) -> list[Path]:
        game = self.game_dir
        if not game.is_dir():
            return []
        files: list[Path] = []
        for path in game.rglob("*.rpy"):
            relative = path.relative_to(game)
            head = relative.parts[0].lower() if relative.parts else ""
            # tl/ 里是译文脚本，cache/ 是运行时缓存；都不该参与画面解析。
            if head in {"tl", "cache"}:
                continue
            files.append(path)
        return sorted(files)

    def _build_files(self) -> dict[str, str]:
        """文件名（去扩展名，小写）→ game 相对路径；同名时 images/ 优先，再按路径排序。

        用 `os.walk` 而不是 `Path.rglob`：DarkMagic 的 game 目录有几万个素材文件，
        rglob 在 Windows 上要多花好几秒，而这条索引每次请求都可复用。
        """
        if self._files is not None:
            return self._files
        game = self.game_dir
        found: list[tuple[int, str]] = []
        if game.is_dir():
            for root, dirs, files in os.walk(game):
                dirs[:] = [name for name in dirs if name.lower() not in {"tl", "cache"}]
                for name in files:
                    suffix = os.path.splitext(name)[1].lower()
                    if suffix not in MEDIA_SUFFIXES:
                        continue
                    absolute = os.path.join(root, name)
                    relative = os.path.relpath(absolute, game).replace("\\", "/")
                    head = relative.split("/", 1)[0].lower()
                    if head in {"tl", "cache"}:
                        continue
                    rank = 0 if relative.lower().startswith("images/") else 1
                    found.append((rank, relative))
        found.sort(key=lambda item: (item[0], item[1]))
        index: dict[str, str] = {}
        for _, relative in found:
            stem = os.path.splitext(relative.rsplit("/", 1)[-1])[0].lower()
            index.setdefault(stem, relative)
        self._files = index
        return index

    def _build_definitions(self) -> dict[str, dict]:
        if self._definitions is not None:
            return self._definitions
        definitions: dict[str, dict] = {}
        for path in self._rpy_files():
            try:
                lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
            except OSError:
                continue
            for index, line in enumerate(lines):
                if line.startswith(" "):
                    continue
                equals = _IMAGE_EQUALS_RE.match(line)
                if equals:
                    tag = _normalise_tag(equals.group(1))
                    expr = equals.group(2)
                    entry = self._entry_from_expr(expr)
                    if tag and entry and tag not in definitions:
                        definitions[tag] = entry
                    continue
                block = _IMAGE_BLOCK_RE.match(line)
                if block:
                    tag = _normalise_tag(block.group(1))
                    entry = self._entry_from_atl(lines, index + 1)
                    if tag and entry and tag not in definitions:
                        definitions[tag] = entry
        self._definitions = definitions
        return definitions

    @staticmethod
    def _entry_from_expr(expr: str) -> dict | None:
        quoted = _QUOTED_RE.search(expr)
        if quoted is None:
            return None
        relative = quoted.group(1).strip().replace("\\", "/")
        if not relative:
            return None
        note = ""
        if "ConditionSwitch(" in expr:
            note = "条件分支，按默认分支推测"
        return {
            "path": relative,
            "kind": "video" if (".mp4" in expr.lower() or "Movie(" in expr) else "image",
            "note": note,
        }

    @staticmethod
    def _entry_from_atl(lines: list[str], start: int) -> dict | None:
        """ATL 块：从 `image x:` 的下一行开始，取块内第一个引号字符串。"""
        for line in lines[start:]:
            if line.strip() == "":
                continue
            if not line.startswith(" ") and not line.startswith("\t"):
                break
            quoted = _QUOTED_RE.search(line)
            if quoted is not None:
                relative = quoted.group(1).strip().replace("\\", "/")
                if not relative:
                    continue
                return {
                    "path": relative,
                    "kind": "video" if ".mp4" in relative.lower() else "image",
                    "note": "",
                }
        return None

    # ------------------------------------------------------------- 解析
    def resolve(self, tag: str) -> dict | None:
        key = _normalise_tag(tag)
        if not key or key in COLOR_NAMES:
            return None
        definitions = self._build_definitions()
        files = self._build_files()
        for candidate in _candidates(key):
            entry = definitions.get(candidate)
            if entry is not None:
                path = entry["path"]
                if path.startswith("images/") or "/" in path:
                    return {
                        "path": path,
                        "kind": entry["kind"],
                        "tag": _normalise_tag(tag),
                        "note": entry["note"],
                    }
                # 定义里只写了文件名时，补一次文件索引，避免把裸文件名当路径。
                fallback = files.get(path.rsplit("/", 1)[-1].rsplit(".", 1)[0].lower())
                return {
                    "path": fallback or path,
                    "kind": entry["kind"],
                    "tag": _normalise_tag(tag),
                    "note": entry["note"],
                }
            relative = files.get(candidate)
            if relative is not None:
                return {
                    "path": relative,
                    "kind": "video" if Path(relative).suffix.lower() in VIDEO_SUFFIXES else "image",
                    "tag": _normalise_tag(tag),
                    "note": "",
                }
        return None


_CACHE: dict[str, SceneImageIndex] = {}
_CACHE_LOCK = threading.Lock()


def get_index(game_dir: Path) -> SceneImageIndex:
    """按 game 目录缓存解析器：一次请求里可能解析几百个 label，不能反复建索引。"""
    key = str(Path(game_dir).resolve()).casefold()
    with _CACHE_LOCK:
        index = _CACHE.get(key)
        if index is None:
            index = SceneImageIndex(Path(game_dir))
            _CACHE[key] = index
        return index


def clear_indexes() -> None:
    with _CACHE_LOCK:
        _CACHE.clear()
