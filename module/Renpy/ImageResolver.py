"""把 Ren'Py 的 image tag 落成 game/ 下的真实文件。

校对台要显示的「这句台词当时的画面」在源脚本里只是一个图片名，而这个名字
可能来自三种完全不同的写法：

    scene dojo_front1                          ← 直接就是文件名
    image dojo_front1 = ConditionSwitch(...)   ← 运行时按变量选分支
    image video_xxx = Movie(play='movies/x.mp4')  ← 实际是视频

只按文件名去找，实测命中 85.4%；把 image 定义解析一遍之后是 98.0%。
剩下的 2% 是游戏自身的坏引用（名字既没有定义也没有同名文件）。

ConditionSwitch 的分支要按变量求值才知道选哪个，这里不执行脚本，固定按
「默认分支优先」挑一个能落地的分支，并在 note 里写明推测依据，界面据此
如实告诉用户「这是推测，游戏里的实际画面可能随剧情变量变化」。
"""

from __future__ import annotations

import collections
import os
import re
import threading
from dataclasses import dataclass
from pathlib import Path

IMAGE_EXT = (".webp", ".png", ".jpg", ".jpeg", ".avif", ".gif")
VIDEO_EXT = (".mp4", ".webm", ".mkv", ".avi")

# image <tag> = <expr>  或  image <tag>:  (ATL 块)
_DEF_RE = re.compile(r"^(\s*)image\s+([A-Za-z_][\w ]*?)\s*(=|:)\s*(.*)$")
_QUOTED_RE = re.compile(r'"([^"\n]*)"|\'([^\'\n]*)\'')
_CS_RE = re.compile(r"ConditionSwitch\s*\(", re.I)
_MOVIE_RE = re.compile(r"Movie\s*\(", re.I)

# 分支层数上限：防止 ConditionSwitch → 定义 → ConditionSwitch 的死循环
_MAX_DEPTH = 4


@dataclass(frozen=True)
class ResolvedImage:
    """一个图片名的落地结果。relative 为空表示没能落到文件。"""

    kind: str  # image / video / none
    relative: str  # game/ 下的相对路径（posix 分隔符）
    note: str  # 命中方式或失败原因，直接给界面显示

    @property
    def ok(self) -> bool:
        return bool(self.relative)


def _tag_key(tag: str) -> str:
    return str(tag).strip().replace(" ", "_").lower()


def _paren_balance(text: str) -> int:
    """未闭合的括号层数：用来判断多行 image 定义到哪里结束。"""
    depth, quote, index = 0, None, 0
    while index < len(text):
        char = text[index]
        if quote:
            if char == "\\":
                index += 2
                continue
            if char == quote:
                quote = None
        elif char in "\"'":
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        index += 1
    return depth


def _split_top(text: str) -> list[str]:
    """按最外层逗号切分，忽略括号与引号内部的逗号。"""
    parts: list[str] = []
    buffer, depth, quote = "", 0, None
    for char in text:
        if quote:
            buffer += char
            if char == quote:
                quote = None
            continue
        if char in "\"'":
            quote = char
            buffer += char
            continue
        if char in "([":
            depth += 1
        elif char in ")]":
            depth -= 1
        if char == "," and depth == 0:
            parts.append(buffer)
            buffer = ""
            continue
        buffer += char
    if buffer.strip():
        parts.append(buffer)
    return [part.strip() for part in parts if part.strip()]


class ImageResolver:
    """某个工程目录下的图片名解析器。

    构造时建索引（约 17k 个文件的 walk + 136 个 .rpy 的定义解析），
    所以按 game_dir 缓存实例，只在绑定新工程时重建。
    """

    def __init__(self, game_dir: Path) -> None:
        self.game_dir = Path(game_dir)
        self._by_relative: dict[str, str] = {}
        self._by_stem: dict[str, list[str]] = collections.defaultdict(list)
        self._definitions: dict[str, dict] = {}
        self._sources: dict[str, list[str]] = {}
        self._build_index()
        self._build_definitions()

    # ---------------------------------------------------------------- 索引
    def _build_index(self) -> None:
        root = str(self.game_dir)
        for directory, subdirs, files in os.walk(root):
            # 缓存与存档目录里不会有被游戏引用的美术资源
            subdirs[:] = [name for name in subdirs if name not in ("cache", "saves", "__pycache__")]
            for name in files:
                suffix = os.path.splitext(name)[1].lower()
                if suffix not in IMAGE_EXT and suffix not in VIDEO_EXT:
                    continue
                absolute = os.path.join(directory, name)
                relative = os.path.relpath(absolute, root).replace("\\", "/")
                self._by_relative[relative.lower()] = relative
                stem = os.path.splitext(name)[0].replace(" ", "_").lower()
                self._by_stem[stem].append(relative)

    def _read(self, relative: str) -> list[str]:
        cached = self._sources.get(relative)
        if cached is not None:
            return cached
        try:
            text = (self.game_dir / relative).read_text(encoding="utf-8-sig", errors="replace")
            lines = text.splitlines()
        except OSError:
            lines = []
        self._sources[relative] = lines
        return lines

    def _build_definitions(self) -> None:
        for directory, subdirs, files in os.walk(str(self.game_dir)):
            subdirs[:] = [name for name in subdirs if name not in ("cache", "saves", "__pycache__")]
            for name in files:
                if not name.endswith(".rpy"):
                    continue
                relative = os.path.relpath(os.path.join(directory, name), str(self.game_dir)).replace("\\", "/")
                lines = self._read(relative)
                index = 0
                while index < len(lines):
                    match = _DEF_RE.match(lines[index])
                    if not match:
                        index += 1
                        continue
                    indent, tag, operator, rest = (
                        match.group(1),
                        match.group(2).strip(),
                        match.group(3),
                        match.group(4),
                    )
                    body = [rest]
                    cursor = index
                    if operator == "=":
                        # 多行调用：括号没闭合就继续吃下一行
                        while _paren_balance(" ".join(body)) > 0 and cursor + 1 < len(lines):
                            cursor += 1
                            body.append(lines[cursor])
                    else:
                        # ATL 块：吃缩进更深的行
                        base = len(indent)
                        while cursor + 1 < len(lines):
                            following = lines[cursor + 1]
                            if not following.strip():
                                cursor += 1
                                body.append("")
                                continue
                            if len(following) - len(following.lstrip()) <= base:
                                break
                            cursor += 1
                            body.append(following)
                    self._definitions[_tag_key(tag)] = {
                        "text": "\n".join(body),
                        "file": relative,
                        "line": index + 1,
                    }
                    index = cursor + 1

    # ---------------------------------------------------------------- 查找
    def _lookup_file(self, tag: str) -> str | None:
        raw = str(tag).strip().strip("\"'").replace("\\", "/")
        if not raw:
            return None
        lowered = raw.lower()
        if lowered in self._by_relative:
            return self._by_relative[lowered]
        candidates = self._by_stem.get(_tag_key(raw))
        if candidates:
            # 同名文件在多个目录时取路径序第一个，保证同一 tag 每次解析结果一致
            return sorted(candidates)[0]
        return None

    def _kind_of(self, relative: str) -> str:
        return "video" if os.path.splitext(relative)[1].lower() in VIDEO_EXT else "image"

    def resolve(self, tag: str, depth: int = 0) -> ResolvedImage:
        """把一个 scene/show 用的图片 tag 落成真实文件。"""
        name = str(tag or "").strip()
        if not name or name.lower() == "black":
            return ResolvedImage("none", "", "黑屏（scene black）" if name else "没有图片名")
        if depth > _MAX_DEPTH:
            return ResolvedImage("none", "", "嵌套层级过深")

        definition = self._definitions.get(_tag_key(name))
        if not definition:
            found = self._lookup_file(name)
            if found:
                return ResolvedImage(self._kind_of(found), found, "直接命中同名文件")
            return ResolvedImage("none", "", "没有定义，也没有同名文件")

        text = definition["text"]
        if _MOVIE_RE.search(text):
            for quoted in _QUOTED_RE.findall(text):
                path = quoted[0] or quoted[1]
                found = self._lookup_file(path)
                if found:
                    return ResolvedImage(self._kind_of(found), found, "Movie 视频")
            return ResolvedImage("none", "", "Movie 定义里没有可用的视频文件")

        if _CS_RE.search(text):
            return self._resolve_condition_switch(name, text, depth)

        # 其它写法（path / animate / Composite / LayeredImage ...）：
        # 取定义里第一个能落地的字符串，落不了就递归
        for quoted in _QUOTED_RE.findall(text):
            candidate = quoted[0] or quoted[1]
            if not candidate:
                continue
            found = self._lookup_file(candidate)
            if found:
                return ResolvedImage(self._kind_of(found), found, "定义取自 %s" % os.path.basename(definition["file"]))
            nested = self.resolve(candidate, depth + 1)
            if nested.ok:
                return ResolvedImage(nested.kind, nested.relative, nested.note)
        return ResolvedImage("none", "", "定义里的文件都不存在")

    def _resolve_condition_switch(self, name: str, text: str, depth: int) -> ResolvedImage:
        """ConditionSwitch(条件, 图片, 条件, 图片, ...) → 默认分支优先。"""
        try:
            inner = text[text.index("(") + 1 :].rsplit(")", 1)[0]
        except ValueError:
            return ResolvedImage("none", "", "ConditionSwitch 结构无法解析")
        parts = _split_top(inner)
        branches = [
            (parts[index].strip().strip("\"'"), parts[index + 1].strip().strip("\"'"))
            for index in range(0, len(parts) - 1, 2)
        ]
        if not branches:
            return ResolvedImage("none", "", "ConditionSwitch 没有分支")
        # Ren'Py 的默认分支约定写成字面量 "True"，等价于 else
        ordered = sorted(branches, key=lambda pair: 0 if pair[0].strip().lower() == "true" else 1)
        for condition, display in ordered:
            nested = self.resolve(display, depth + 1)
            if nested.ok:
                return ResolvedImage(
                    nested.kind,
                    nested.relative,
                    "%d 个分支里取「%s」这一支（推测）" % (len(branches), condition),
                )
        return ResolvedImage("none", "", "ConditionSwitch 所有分支都没落地")

    def definition_of(self, tag: str) -> dict | None:
        """调试用：返回 tag 的定义位置。"""
        return self._definitions.get(_tag_key(tag))

    @property
    def definition_count(self) -> int:
        return len(self._definitions)


_INSTANCES: dict[str, ImageResolver] = {}
_INSTANCES_LOCK = threading.Lock()


def get_resolver(game_dir: Path) -> ImageResolver:
    """按工程目录缓存解析器：建索引要扫全工程，不能每个请求重建。"""
    key = str(Path(game_dir).resolve())
    instance = _INSTANCES.get(key)
    if instance is not None:
        return instance
    with _INSTANCES_LOCK:
        instance = _INSTANCES.get(key)
        if instance is None:
            instance = ImageResolver(Path(game_dir))
            _INSTANCES[key] = instance
        return instance


def clear_resolvers() -> None:
    """解包出新文件或换工程后可以主动丢弃缓存。"""
    with _INSTANCES_LOCK:
        _INSTANCES.clear()
