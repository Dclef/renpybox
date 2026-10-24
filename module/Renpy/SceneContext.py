"""按台词原文反查「这句话出现时游戏画面上是什么」。

Ren'Py 的 tl 文件里没有 scene/show —— 这些语句只存在于 game/ 下的源脚本。
所以要看画面就必须回到源脚本：

    1. tl 条目 -> 源脚本相对路径（tl/chinese/<x> 与 game/<x> 同构，路径直接对应）
    2. 台词原文 -> 源脚本行号（逐行做子串匹配；同文重复出现时用 label 消歧）
    3. 源脚本行号 -> 向上找最近的 scene，再顺序应用 scene 之后的 show/hide

第 3 步得到的是一个「静态还原」的画面：不启动游戏、不截图，因此
拿不到转场中间态、ATL 动画中间帧和 Python 里动态 set 的画面。
拿不到时就如实返回原因，不猜。"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field
from pathlib import Path

from module.Renpy.ImageResolver import ImageResolver, ResolvedImage, get_resolver

_SCENE_RE = re.compile(r"^(\s*)scene\s+(.+?)\s*$")
_SHOW_RE = re.compile(r"^(\s*)show\s+(.+?)\s*$")
_HIDE_RE = re.compile(r"^(\s*)hide\s+(.+?)\s*$")
_LABEL_RE = re.compile(r"^label\s+([\w.]+)\s*(?:\([^)]*\))?\s*:")
# scene/show 后面可以跟 with/at/behind/onlayer/as/zorder 修饰，都不是图片名
_TRAILING_RE = re.compile(r"\s+(?:with|at|behind|onlayer|as|zorder)\s+.*$", re.I)


@dataclass
class StageLayer:
    """一个立绘层（show 语句的结果）。"""

    tag: str
    kind: str
    relative: str
    note: str

    def as_dict(self) -> dict:
        return {"tag": self.tag, "kind": self.kind, "relative": self.relative, "note": self.note}


@dataclass
class Stage:
    """某一行台词对应的画面。reason 非空表示还原失败。"""

    file: str = ""
    line: int = 0
    scene_line: int = 0
    scene_tag: str = ""
    background: ResolvedImage | None = None
    layers: list[StageLayer] = field(default_factory=list)
    reason: str = ""

    def as_dict(self) -> dict:
        return {
            "file": self.file,
            "line": self.line,
            "scene_line": self.scene_line,
            "scene_tag": self.scene_tag,
            "background": (
                {
                    "kind": self.background.kind,
                    "relative": self.background.relative,
                    "note": self.background.note,
                }
                if self.background
                else None
            ),
            "layers": [layer.as_dict() for layer in self.layers],
            "reason": self.reason,
        }


def _tag_of(rest: str) -> str:
    """从 scene/show 的参数里取出图片名。

    scene dinning_room_sit2:              ← ATL 块，冒号不属于名字
    scene dojo_front1 with Dissolve(0.5)  ← with 之后都不是名字
    show alice_smile as alice_alt at right
    """
    text = rest.strip().rstrip(":").strip()
    text = _TRAILING_RE.sub("", text).split(" as ")[0].strip()
    return text.replace(" ", "_")


class SceneContextScanner:
    """把「源脚本 + 行号」还原成画面。按工程目录缓存源文件行。"""

    def __init__(self, game_dir: Path, resolver: ImageResolver) -> None:
        self.game_dir = Path(game_dir)
        self.resolver = resolver
        self._sources: dict[str, list[str]] = {}
        self._labels: dict[str, list[tuple[str, int]]] = {}

    # ---------------------------------------------------------------- 源文件
    def source_lines(self, relative: str) -> list[str]:
        cached = self._sources.get(relative)
        if cached is not None:
            return cached
        path = self._safe_path(relative)
        if path is None or not path.is_file():
            self._sources[relative] = []
            return []
        try:
            lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
        except OSError:
            lines = []
        self._sources[relative] = lines
        return lines

    def _safe_path(self, relative: str) -> Path | None:
        """只允许落在 game/ 内部的相对路径，挡住 .. 与绝对路径。"""
        raw = str(relative or "").replace("\\", "/").lstrip("/")
        if not raw or ".." in raw.split("/"):
            return None
        candidate = (self.game_dir / raw).resolve()
        try:
            candidate.relative_to(self.game_dir.resolve())
        except ValueError:
            return None
        return candidate

    def labels_of(self, relative: str) -> list[tuple[str, int]]:
        """文件内所有 label 与其行号，用于给重复台词消歧。"""
        cached = self._labels.get(relative)
        if cached is not None:
            return cached
        found = []
        for number, line in enumerate(self.source_lines(relative), 1):
            match = _LABEL_RE.match(line)
            if match:
                found.append((match.group(1), number))
        self._labels[relative] = found
        return found

    # ---------------------------------------------------------------- 定位
    def locate_line(self, relative: str, src: str, label: str = "") -> int:
        """台词原文 → 源脚本行号。0 表示找不到。"""
        text = str(src or "").strip()
        if not text:
            return 0
        lines = self.source_lines(relative)
        if not lines:
            return 0
        hits = [number for number, line in enumerate(lines, 1) if text in line]
        if not hits:
            # 有的工程会改写空白或引号，退一步按压缩空白再比一次
            collapsed = " ".join(text.split())
            hits = [number for number, line in enumerate(lines, 1) if collapsed and collapsed in " ".join(line.split())]
        if not hits:
            return 0
        if len(hits) == 1:
            return hits[0]
        if label:
            # 同文重复出现：优先取同名 label 作用域内的那一条
            labels = self.labels_of(relative)
            for index, (name, start) in enumerate(labels):
                if name != label:
                    continue
                end = labels[index + 1][1] if index + 1 < len(labels) else len(lines) + 1
                inside = [hit for hit in hits if start <= hit < end]
                if inside:
                    return inside[0]
        return hits[0]

    def stage_at(self, relative: str, line: int) -> Stage:
        """向上找 scene，再顺序应用 show/hide，得到该行的画面。"""
        stage = Stage(file=relative, line=line)
        lines = self.source_lines(relative)
        if not lines:
            stage.reason = "源脚本里没有这个文件（可能只发布了 .rpyc）"
            return stage
        if line < 1 or line > len(lines):
            stage.reason = "行号超出源脚本范围"
            return stage

        scene_index = -1
        for index in range(min(line, len(lines)) - 1, -1, -1):
            if _SCENE_RE.match(lines[index]):
                scene_index = index
                break
        if scene_index < 0:
            has_scene = any(_SCENE_RE.match(text) for text in lines)
            stage.reason = (
                "这个文件里没有 scene 语句（多半是系统界面文本），没有可还原的画面"
                if not has_scene
                else "这句话前面没有 scene 语句"
            )
            return stage

        stage.scene_line = scene_index + 1
        stage.scene_tag = _tag_of(_SCENE_RE.match(lines[scene_index]).group(2))
        stage.background = self.resolver.resolve(stage.scene_tag)

        # scene 之后到目标行之间的 show/hide：按顺序算最终在场立绘
        visible: dict[str, StageLayer] = {}
        for index in range(scene_index + 1, min(line, len(lines))):
            text = lines[index]
            shown = _SHOW_RE.match(text)
            if shown:
                raw = shown.group(2)
                # show screen / show expression / show layer 是界面与图层操作，不是立绘
                if raw.split(" ", 1)[0] in ("screen", "expression", "layer"):
                    continue
                tag = _tag_of(raw)
                # show alice_smile as alice → 同一角色换表情只替换不叠加
                target = raw.split(" as ")[-1] if " as " in raw else tag
                resolved = self.resolver.resolve(tag)
                visible[target.replace(" ", "_")] = StageLayer(
                    tag=tag, kind=resolved.kind, relative=resolved.relative, note=resolved.note
                )
                continue
            hidden = _HIDE_RE.match(text)
            if hidden:
                visible.pop(_tag_of(hidden.group(2)), None)
        stage.layers = list(visible.values())

        if not stage.background or not stage.background.ok:
            stage.reason = "背景图没能落到文件：%s" % (stage.background.note if stage.background else "未知")
        return stage


_SCANNERS: dict[str, SceneContextScanner] = {}
_SCANNERS_LOCK = threading.Lock()


def get_scanner(game_dir: Path) -> SceneContextScanner:
    """按工程目录缓存扫描器：源脚本行与 label 索引都留在实例里。"""
    key = str(Path(game_dir).resolve())
    scanner = _SCANNERS.get(key)
    if scanner is not None:
        return scanner
    with _SCANNERS_LOCK:
        scanner = _SCANNERS.get(key)
        if scanner is None:
            scanner = SceneContextScanner(Path(game_dir), get_resolver(Path(game_dir)))
            _SCANNERS[key] = scanner
        return scanner


def clear_scanners() -> None:
    """换工程或重新解包后丢弃缓存。"""
    with _SCANNERS_LOCK:
        _SCANNERS.clear()
