"""按目录命名约定给角色找头像图片，不做 AI、不联网。

Ren'Py 工程的头像散落在几个约定俗成的目录里，命名也不统一：

    images/faces/face_azumi.webp
    images/headshots/hs_airi.png
    images/portraits/airi.png
    images/portraits/airi_bg.png     ← 横版 CG，不能当头像

所以解析分两步：先按「目录优先级 + 去掉前缀的文件名」建索引，再按形状过滤。
**形状过滤是必须的**：portraits/ 里混着大量 1920×1080 的剧情 CG，只按文件名
匹配会把背景图贴到角色卡上（实测 DarkMagic 的 portraits 里 43 张只有 23 张是竖图）。

降级链的最后一级是 None，交给前端画首字色块兜底；这里不生成任何图片，
只返回 game/ 下的相对路径，前端直接走已有的 `/api/proofreading/asset?path=` 取图。
"""

from __future__ import annotations

import os
import threading
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from base.Base import Base

# 目录优先级：靠前的先命中，靠后的只在前面的目录全落空时才用。
AVATAR_DIRS: tuple[str, ...] = ("faces", "headshots", "portraits", "avatars", "chars", "sprites")
# 文件名前缀，索引时统一剥掉，`face_azumi` 和 `azumi` 才是同一个角色。
AVATAR_PREFIXES: tuple[str, ...] = ("face_", "hs_", "portrait_", "avatar_", "head_", "char_")
AVATAR_EXTENSIONS: tuple[str, ...] = (".webp", ".png", ".jpg", ".jpeg", ".avif", ".gif")
# 只接受竖图或接近正方形的图；横图（宽高比 < 1.05）几乎都是 CG 背景。
AVATAR_MIN_ASPECT = 1.05
# 角色名里的头衔/称谓词：查图时去掉它们再试一次（`Lady Thief Sakimi` → `sakimi`）。
TITLE_WORDS: frozenset[str] = frozenset(
    {
        "lady", "lord", "miss", "mrs", "mr", "ms", "sir", "madam", "master", "mistress",
        "the", "thief", "queen", "king", "princess", "prince", "captain", "doctor",
        "teacher", "student", "granny", "aunt", "uncle", "young", "old",
    }
)
# 头像解析要排除的运行时目录
EXCLUDED_DIRS = frozenset({"cache", "saves", "__pycache__", "tl"})


@dataclass(frozen = True)
class Avatar:
    """一张可用的头像。kind 是命中的目录名，relative 是相对 game/ 的路径（/ 分隔）。

    前端拿 relative 拼到已有的 `GET /api/proofreading/asset?path=` 上取图。
    """

    kind: str
    relative: str
    width: int
    height: int

    def as_dict(self) -> dict[str, str | int]:
        """给角色卡用的字典形态。

        同时给出 relative 和 relative_path：前者是施工单规定的正式字段名，
        后者是早期草稿里的旧名，两个都带一份避免读取方对不上。
        """
        return {
            "kind": self.kind,
            "relative": self.relative,
            "relative_path": self.relative,
            "width": self.width,
            "height": self.height,
        }


@dataclass(frozen = True)
class _Candidate:
    """索引里的一条候选：目录名 + 相对路径。"""

    kind: str
    relative_path: str


def _normalize_key(value: str) -> str:
    """把角色名压成文件名主体的样子：小写、空格/连字符转下划线、去掉引号和方括号。

    方括号是 Ren'Py 的插值写法（`[ffairy]`），角色扫描记录的变量名就长这样，
    查图前要剥掉才能对上 `face_ffairy.webp`。
    """
    text = (value or "").strip().lower()
    for char in ("'", "’", '"', "[", "]", "{", "}"):
        text = text.replace(char, "")
    text = text.replace(" ", "_").replace("-", "_")
    return text


def _strip_prefix(stem: str) -> str:
    """剥掉一层已知前缀（只剥一层，`face_head_chef` → `head_chef`）。"""
    lowered = stem.lower()
    for prefix in AVATAR_PREFIXES:
        if lowered.startswith(prefix) and len(lowered) > len(prefix):
            return stem[len(prefix):]
    return stem


def _measure(path: Path) -> tuple[int, int]:
    """读图片宽高；读不出来返回 (0, 0)，调用方按「不可用」处理。"""
    try:
        from PIL import Image
    except ImportError:  # pragma: no cover - 项目依赖里已装 Pillow，这里只做兜底
        return (0, 0)
    try:
        with Image.open(path) as image:
            width, height = image.size
        return (int(width), int(height))
    except Exception:
        return (0, 0)


class AvatarIndex(Base):
    """某个 game/ 目录下的头像索引，建一次可以反复按名字查。"""

    def __init__(self, game_dir: Path) -> None:
        self.game_dir = Path(game_dir)
        # 规范化文件名主体 -> 候选列表（已按目录优先级、路径序排好）
        self._index: dict[str, list[_Candidate]] = {}
        # 相对路径 -> (宽, 高)；读图有成本，同一个文件只读一次
        self._sizes: dict[str, tuple[int, int]] = {}
        self._built = False
        self._build_index()

    # ---------------------------------------------------------------- 索引
    def _build_index(self) -> None:
        """遍历约定的头像目录，按「目录优先级 + 文件名主体」建立候选表。"""
        if self._built:
            return
        self._built = True
        priority = {name: rank for rank, name in enumerate(AVATAR_DIRS)}
        entries: list[tuple[int, str, str, str]] = []
        root = str(self.game_dir)
        if not self.game_dir.is_dir():
            return

        for directory, subdirs, files in os.walk(root):
            subdirs[:] = [name for name in subdirs if name.casefold() not in EXCLUDED_DIRS]
            parts = Path(directory).relative_to(self.game_dir).parts
            # 目录链里最靠前的那个约定目录名决定优先级（images/faces → faces）
            kind = next(
                (part.casefold() for part in parts if part.casefold() in priority),
                "",
            )
            if kind == "":
                continue
            for name in files:
                stem, suffix = os.path.splitext(name)
                if suffix.lower() not in AVATAR_EXTENSIONS:
                    continue
                key = _normalize_key(_strip_prefix(stem))
                if key == "":
                    continue
                relative = (Path(directory, name)).relative_to(self.game_dir).as_posix()
                entries.append((priority[kind], key, kind, relative))

        # 同一 key 下按「目录优先级 → 相对路径」稳定排序，取第一个形状合格的
        entries.sort()
        index: dict[str, list[_Candidate]] = {}
        for _, key, kind, relative in entries:
            index.setdefault(key, []).append(_Candidate(kind, relative))
        self._index = index
        self.debug(f"[AvatarResolver] 索引 {len(entries)} 张候选图 / {len(index)} 个名字")

    # ---------------------------------------------------------------- 查找
    def lookup(self, name: str, aliases: Sequence[str] = ()) -> Avatar | None:
        """按角色名找头像；形状不合格的候选逐级降级，全落空返回 None。

        aliases 传角色的 Ren'Py 变量名（`ffairy`、`dark_fairy`）。美术文件常按
        变量名命名而不是显示名（`Flower Fairy` 的图叫 `face_ffairy.webp`），
        变量名来自 `define <var> = Character("...")`，是确定的对应关系，不算猜。
        """
        for candidate in self._rank_candidates(name, aliases):
            size = self._size_of(candidate.relative_path)
            if size is None:
                continue
            return Avatar(candidate.kind, candidate.relative_path, size[0], size[1])
        return None

    def resolve(self, name: str, aliases: Sequence[str] = ()) -> Avatar | None:
        """按角色名解析头像；与 lookup 等价，提供更直观的入口。"""
        return self.lookup(name, aliases)

    def _rank_candidates(self, name: str, aliases: Sequence[str] = ()) -> list[_Candidate]:
        """把所有候选 key 的命中汇总后排序：key 精确度 > 目录优先级 > 路径。

        key 精确度优先是有意的：`Airi` 精确命中 headshots/hs_airi.png，而它的
        变量名 `mom` 在 faces 里也有一张 face_mom.webp，同一个人但文件名对不上，
        该用精确的那张。横版 CG 由形状过滤挡掉，不需要靠目录顺序兜底。
        """
        ranked: list[tuple[int, int, str, _Candidate]] = []
        for rank, key in enumerate(self._lookup_keys(name, aliases)):
            for candidate in self._index.get(key, ()):
                ranked.append((rank, self._priority_of(candidate.kind), candidate.relative_path, candidate))
        ranked.sort()
        return [item[3] for item in ranked]

    @staticmethod
    def _priority_of(kind: str) -> int:
        """目录优先级序号；未知目录排最后。"""
        try:
            return AVATAR_DIRS.index(kind)
        except ValueError:
            return len(AVATAR_DIRS)

    @staticmethod
    def _lookup_keys(name: str, aliases: Sequence[str] = ()) -> list[str]:
        """角色名到文件名的候选 key，从精确到宽松。

        顺序即优先级：显示名精确命中 > 变量名 > 名字变形。只做有依据的推断，
        不做模糊匹配：
        - 变量名：`ffairy` → `face_ffairy.webp`（来自 Character 定义）；
        - 首字母缩写：`Dark Fairy Queen` → `df_queen`（美术文件确实这么命名）；
        - 去掉头衔词：`Lady Thief Sakimi` → `thief_sakimi` / `sakimi`。
        乱猜会匹到别的角色的图，比没有头像更糟。
        """
        keys: list[str] = []

        def push(value: str) -> None:
            if value and value not in keys:
                keys.append(value)

        words = [word for word in _normalize_key(name).split("_") if word]
        # 显示名精确命中排最前：变量名里有 mom/sister/doctor 这类通用角色词，
        # 让它们先于显示名出手，容易把别的角色的图抢过来。
        push("_".join(words))
        for alias in aliases:
            push(_normalize_key(_strip_prefix(_normalize_key(alias))))
        if len(words) >= 3:
            push("".join(word[0] for word in words[:-1]) + "_" + words[-1])
        # 头衔词只是称呼的一部分，不算名字本身
        rest = [word for word in words if word not in TITLE_WORDS]
        if rest and rest != words:
            push("_".join(rest))
            if len(rest) == 1:
                push(rest[0])
        return keys

    def _size_of(self, relative_path: str) -> tuple[int, int] | None:
        """返回合格图片的宽高；读不出或宽高比不合格时返回 None。"""
        size = self._sizes.get(relative_path)
        if size is None:
            size = _measure(self.game_dir / relative_path)
            # 读不出来的也记下来，避免同一个坏文件被反复打开
            self._sizes[relative_path] = size
        width, height = size
        if width <= 0 or height <= 0:
            return None
        if height / width < AVATAR_MIN_ASPECT:
            # 横图（多半是 CG 背景）：尺寸已缓存，但每次仍然判定为不合格
            return None
        return (width, height)

    @property
    def name_count(self) -> int:
        """索引里有多少个不同的名字主体。"""
        return len(self._index)

    def clear(self) -> None:
        """丢弃索引与尺寸缓存；换工程或解包出新资源后调用。"""
        self._index = {}
        self._sizes = {}
        self._built = False


_INSTANCES: dict[str, AvatarIndex] = {}
_INSTANCES_LOCK = threading.Lock()


def build_index(game_dir: Path) -> AvatarIndex:
    """建立（或复用缓存的）头像索引；模块级入口，调用方不感知实例缓存。"""
    return resolve(game_dir)


def resolve(game_dir: Path) -> AvatarIndex:
    """按 game/ 目录缓存索引：建索引要扫全工程，不能每个角色都重建。"""
    root = _normalize_game_dir(game_dir)
    key = str(root.resolve()) if root is not None else str(game_dir)
    instance = _INSTANCES.get(key)
    if instance is not None:
        return instance
    with _INSTANCES_LOCK:
        instance = _INSTANCES.get(key)
        if instance is None:
            instance = AvatarIndex(root if root is not None else Path(game_dir))
            _INSTANCES[key] = instance
        return instance


def clear() -> None:
    """清空全部工程的索引缓存。"""
    with _INSTANCES_LOCK:
        for instance in _INSTANCES.values():
            instance.clear()
        _INSTANCES.clear()


def _normalize_game_dir(game_dir: Path) -> Path | None:
    """允许传工程根目录或 game 目录。"""
    try:
        root = Path(game_dir)
    except (TypeError, ValueError):
        return None
    if root.name.lower() != "game" and (root / "game").is_dir():
        root = root / "game"
    return root if root.is_dir() else None
