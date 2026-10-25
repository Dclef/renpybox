"""剧情蓝图扫描：把 `game/**/*.rpy` 的 label 与 `tl/<lang>` 的翻译块整理成一份结构化数据。

数据口径（与施工单契约一致，前端 `storyBlueprintView.mjs` 里还会再算一次同样的状态）：

- `say` = 该 label 体内的对白行数；`zh` = 该 label 的 `translate` 块里含真中文的行数；
- `tl_blocks` = 该 label 的 translate 块总数。`tl_blocks > 0 且 zh == 0` 就是「占位」：
  翻译文件看着是满的，实际每行 new 都是英文原文，游戏里等于没翻；
- `edges` 只画真实控制流：菜单选项里的 jump（menu）与 label 体内的 jump（jump）；
  `call` / `return` 不画，因为它们在蓝图上看不出「去哪」。
"""

from __future__ import annotations

import re
from pathlib import Path

from module.Story.SceneImageIndex import get_index
from module.Story.TranslationIndex import TranslationIndex

CJK_RE = re.compile(r"[\u3400-\u9fff\uf900-\ufaff]")
# Ren'Py 文本标记：卡片标题里出现只会干扰阅读（`{b}Soldier{b}`）。
# 不匹配 `[mom]` 这类插值 —— 它是角色名占位，删掉会得到「是的， 。」这种断句。
MARKUP_RE = re.compile(r"\{[^{}]*\}")
# 只有标点/省略号的「标题」等于没标题，应退回 label 名。
NOISE_TITLE_RE = re.compile(r"^[\s.\u2026,!?~\-—_]+$")
LABEL_RE = re.compile(r"^label\s+([A-Za-z_][\w.]*)\s*(?:\([^)]*\))?\s*:")
TRANSLATE_RE = re.compile(r"^translate\s+(\S+)\s+(\S+)\s*:")
BLOCK_LABEL_RE = re.compile(r"^(.*)_([0-9a-f]{8})$")
JUMP_RE = re.compile(r"^jump\s+([A-Za-z_][\w.]*)\s*$")
MENU_RE = re.compile(r"^\s*menu\b")
SCENE_RE = re.compile(r"^\s*scene\s+(.+?)\s*$")
SHOW_RE = re.compile(r"^\s*show\s+(.+?)\s*$")
HIDE_RE = re.compile(r"^\s*hide\s+(.+?)\s*$")
QUOTED_LINE_RE = re.compile(r'^(["\'])(.*)\1$')
SAY_RE = re.compile(r'^(?:([A-Za-z_][\w.]*)\s+)?(["\'])(.*)\2(?:\s+with\s+[\w.]+)?\s*$')
# Ren'Py 里 `"Soldier" "台词"` 表示「用引号指定显示名的旁白」，说话人在引号里。
SAY_NAMED_RE = re.compile(r'^(["\'])(.*?)\1\s+(["\'])(.*)\3(?:\s+with\s+[\w.]+)?\s*$')
OLD_RE = re.compile(r'^\s*old\s+(["\'])(.*)\1\s*$')
NEW_RE = re.compile(r'^\s*new\s+(["\'])(.*)\1\s*$')

# 这些语句即使「标识符 + 引号字符串」也不该算成对白。
STATEMENT_WORDS = frozenset(
    {
        "play",
        "queue",
        "stop",
        "scene",
        "show",
        "hide",
        "with",
        "voice",
        "window",
        "define",
        "default",
        "image",
        "transform",
        "style",
        "init",
        "python",
        "jump",
        "call",
        "return",
        "if",
        "elif",
        "else",
        "while",
        "for",
        "menu",
        "label",
        "translate",
        "pause",
        "extend",
        "nvl",
        "centered",
        "layeredimage",
        "renpy",
        "persistent",
    }
)
# 场景语句里 `scene bg hall night with dissolve` 的尾巴，截断后再当图片标签。
SCENE_TRAILERS = (" with ", " at ", " behind ", " onlayer ", " as ", " zorder ")
# `show` 的首词落在这里说明它不是「按标签查文件」的画面语句：
# `show screen x` / `show layer master` 是界面层，`show expression "..."` / `show text "..."`
# 是内联表达式，都交给 SceneImageIndex 也解析不出文件。只认剩下的媒体标签。
SHOW_NON_MEDIA_PREFIXES = frozenset({"screen", "layer", "expression", "text", "image", "window"})


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" \t"))


def _strip_comment(line: str) -> str:
    """去掉行尾注释（不处理字符串里的 #，RPY 里极少见）。"""
    index = line.find("#")
    return line[:index] if index >= 0 else line


def _unquote(body: str) -> str:
    text = body.strip()
    if len(text) >= 2 and text[0] in "\"'" and text[-1] == text[0]:
        return text[1:-1]
    return text


def _say_text(line: str) -> str | None:
    """一行对白的文本（去掉说话人与引号）；不是对白返回 None。"""
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    named = SAY_NAMED_RE.match(stripped)
    if named is not None:
        # `"Soldier" "台词"`：说话人在引号里，后半段才是台词。
        return named.group(4)
    match = SAY_RE.match(stripped)
    if match is None:
        return None
    speaker = (match.group(1) or "").lower()
    if speaker in STATEMENT_WORDS:
        return None
    return match.group(3)


def _say_speaker(line: str) -> str:
    """对白的说话人名（`kimiko "..."` → kimiko）；旁白返回空串。"""
    stripped = line.strip()
    named = SAY_NAMED_RE.match(stripped)
    if named is not None:
        return clean_say(named.group(2))
    match = SAY_RE.match(stripped)
    if match is None:
        return ""
    speaker = (match.group(1) or "")
    return "" if speaker.lower() in STATEMENT_WORDS else speaker


def clean_say(text: str) -> str:
    """去掉 Ren'Py 文本标记 `{b}` 后的对白，供标题/预览使用。

    `[mom]` 这类插值是角色名占位，删掉会让中文变成「是的， 。」，因此保留。
    """
    text = MARKUP_RE.sub(" ", text)
    text = " ".join(text.split())
    # 去掉标记后常留下 `Hey !` 这种标点前空格。
    return re.sub(r"\s+([,.!?;:，。！？；：])", r"\1", text)


def is_noise_title(text: str) -> bool:
    """`...`、`?!`、纯空白这类对白当标题没有任何辨识度。"""
    stripped = text.strip()
    return not stripped or NOISE_TITLE_RE.match(stripped) is not None


def _cut_trailers(rest: str) -> str:
    """把 `with dissolve` / `at center` 这类尾巴截掉，剩下纯图片标签。"""
    for trailer in SCENE_TRAILERS:
        cut = rest.find(trailer)
        if cut >= 0:
            rest = rest[:cut].strip()
    return rest


def _scene_tag(line: str) -> str | None:
    match = SCENE_RE.match(_strip_comment(line))
    if match is None:
        return None
    return _cut_trailers(match.group(1).strip()) or None


def _show_tag(line: str) -> str | None:
    """一行 `show` 里的媒体标签；不是「按标签查文件」的画面语句返回 None。

    真实工程里大量画面只有 `show xxx`（`scene` 全是 `scene black` 之类的黑场），
    所以必须把 show 也收进来。这些形态一律跳过：
    `show screen flower_fx_out(out_dur=0.9)`（界面层）、`show layer master`、
    `show expression "images/logo.png"`（内联表达式，路径在字符串里，前端缓存不到
    这个 tag）、`show text "..."`、`show image "..."`（同 expression 的内联写法）。
    `show e happy at center zorder 3` 这类则保留 `e happy` 交给文件索引解析。
    """
    match = SHOW_RE.match(_strip_comment(line))
    if match is None:
        return None
    rest = match.group(1).strip()
    if not rest:
        return None
    head = rest.split(None, 1)[0].lower()
    if head in SHOW_NON_MEDIA_PREFIXES:
        return None
    return _cut_trailers(rest) or None


def _resolve_show_image(index, shows: list[str]) -> tuple[dict | None, int]:
    """show 兜底：取最后一条能落到文件的 show（label 结束时观众看到的画面）。

    返回 (图片, 可解析的不同图片数)。数量按落到的文件去重 —— 同一个 tag 反复
    `show` 很多次（真实工程里一段能 show 几十张立绘/插图）只算一张。
    """
    found: dict | None = None
    seen: set[str] = set()
    for tag in shows:
        resolved = index.resolve(tag)
        if resolved is None:
            continue
        key = resolved["path"]
        if key not in seen:
            seen.add(key)
        found = resolved
    return found, len(seen)


def _resolve_label_image(
    index,
    scenes: list[str],
    shows: list[str],
) -> tuple[dict | None, int]:
    """一个 label 的画面：scene 优先，show 兜底，都没有才是 None。

    `image.source` 说明这张图是怎么来的 —— 不少工程（例如只拿 show 铺插画的
    欧美 galgame）根本没有可用的 scene，前端得让用户知道看到的是场景里的演出图，
    不是背景。
    """
    show_image, show_count = _resolve_show_image(index, shows)
    for tag in scenes:
        resolved = index.resolve(tag)
        if resolved is not None:
            return {**resolved, "source": "scene"}, show_count
    if show_image is not None:
        return {**show_image, "source": "show"}, show_count
    return None, show_count


def _game_rpy_files(game_dir: Path) -> list[Path]:
    if not game_dir.is_dir():
        return []
    files: list[Path] = []
    for path in game_dir.rglob("*.rpy"):
        relative = path.relative_to(game_dir)
        head = relative.parts[0].lower() if relative.parts else ""
        if head in {"tl", "cache"}:
            continue
        files.append(path)
    return sorted(files)


def _tl_rpy_files(tl_dir: Path) -> list[Path]:
    if not tl_dir.is_dir():
        return []
    return sorted(tl_dir.rglob("*.rpy"))


def _parse_labels(path: Path, game_dir: Path) -> list[dict]:
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return []
    relative = path.relative_to(game_dir).as_posix()
    chapter = relative[: -len(".rpy")] if relative.endswith(".rpy") else relative
    starts = [
        (index, LABEL_RE.match(line).group(1))
        for index, line in enumerate(lines)
        if LABEL_RE.match(line)
    ]
    labels: list[dict] = []
    seen: set[str] = set()
    for position, (start, name) in enumerate(starts):
        end = starts[position + 1][0] if position + 1 < len(starts) else len(lines)
        if name in seen:
            continue
        seen.add(name)
        labels.append(
            {
                "id": name,
                "chapter": chapter,
                "file": relative,
                "line": start + 1,
                "end_line": end,
                "body": lines[start + 1 : end],
                "body_start": start + 1,
            }
        )
    return labels


def _label_says_and_scenes(body: list[str]) -> tuple[int, list[str], list[str], list[str]]:
    """返回 (对白行数, 前几行对白文本, label 体内所有 scene 标签, 结束时的 show 层)。

    scene 要收集全部而不是只看第一条：多数剧本开头先 `scene black with fade`
    黑场，真正的画面在后面；解析时按顺序试到第一张能落到文件的图。

    只靠 `show` 铺插画的工程（scene 全是黑场）得靠第四项才能拿到画面：按出现
    顺序维护「当前还显示着哪些 show」—— `scene` 会清屏（即使是 scene black），
    `hide` 会把对应 tag（含 `eileen happy` 这种带属性的）收走，最后留下来的
    才是这个 label 结束时观众看到的画面。
    """
    says: list[str] = []
    scenes: list[str] = []
    visible: list[str] = []
    for line in body:
        scene_tag = _scene_tag(line)
        if scene_tag is not None:
            if not scene_tag.lower().startswith("expression"):
                scenes.append(scene_tag)
            visible.clear()
        else:
            show_tag = _show_tag(line)
            if show_tag is not None:
                visible.append(show_tag.lower())
            else:
                hidden = _hide_tag(line)
                if hidden is not None:
                    _drop_visible(visible, hidden)
        text = _say_text(line)
        if text is not None:
            says.append(text)
    return len(says), says, scenes, visible


def _hide_tag(line: str) -> str | None:
    """`hide eileen` 这类隐藏画面的标签；`hide screen` 等界面指令返回 None。"""
    match = HIDE_RE.match(_strip_comment(line))
    if match is None:
        return None
    rest = match.group(1).strip()
    if not rest:
        return None
    head = rest.split(None, 1)[0].lower()
    if head in SHOW_NON_MEDIA_PREFIXES:
        return None
    return _cut_trailers(rest) or None


def _drop_visible(visible: list[str], hidden: str) -> None:
    """`hide eileen` 也要把 `eileen happy` 收走：Ren'Py 按基础 tag 隐藏整张图。"""
    key = " ".join(hidden.split()).lower()
    visible[:] = [
        tag for tag in visible if tag != key and not tag.startswith(f"{key} ")
    ]


def _label_media(body: list[str]) -> tuple[list[str], list[str]]:
    """(label 体内所有 scene, label 结束时仍可见的 show 标签)。"""
    _, _, scenes, visible = _label_says_and_scenes(body)
    return scenes, visible


def _menu_jumps(body: list[str], body_start: int) -> list[dict]:
    """顶层菜单里每个带 jump 的选项：一条 menu 边。嵌套菜单按施工单跳过。"""
    edges: list[dict] = []
    index = 0
    while index < len(body):
        line = body[index]
        if not MENU_RE.match(line):
            index += 1
            continue
        menu_indent = _indent(line)
        index += 1
        option_indent: int | None = None
        while index < len(body):
            current = body[index]
            stripped = current.strip()
            if not stripped or stripped.startswith("#"):
                index += 1
                continue
            indent = _indent(current)
            if indent <= menu_indent:
                break
            if not (stripped.endswith(":") and stripped[0] in "\"'"):
                index += 1
                continue
            if option_indent is None:
                option_indent = indent
            if indent != option_indent:
                index += 1
                continue
            option_src = _unquote(stripped[:-1].strip())
            jump_target: tuple[str, int] | None = None
            index += 1
            while index < len(body):
                inner = body[index]
                inner_stripped = inner.strip()
                if not inner_stripped or inner_stripped.startswith("#"):
                    index += 1
                    continue
                inner_indent = _indent(inner)
                if inner_indent <= indent:
                    break
                if MENU_RE.match(inner):
                    # 选项 body 里的嵌套菜单：整块跳过（只认第一层）。
                    nested_indent = _indent(inner)
                    index += 1
                    while index < len(body):
                        deep = body[index]
                        if deep.strip() and _indent(deep) <= nested_indent:
                            break
                        index += 1
                    continue
                match = JUMP_RE.match(inner_stripped)
                if match is not None and jump_target is None:
                    jump_target = (match.group(1), body_start + index + 1)
                index += 1
            if jump_target is not None:
                edges.append(
                    {
                        "to": jump_target[0],
                        "kind": "menu",
                        "option_src": option_src,
                        "line": jump_target[1],
                    }
                )
    return edges


def _label_jumps(body: list[str], body_start: int) -> list[dict]:
    """label 体自身的 jump（缩进与 body 同级）；菜单内的由 _menu_jumps 负责。"""
    edges: list[dict] = []
    base_indent: int | None = None
    for offset, line in enumerate(body):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if base_indent is None:
            base_indent = _indent(line)
        indent = _indent(line)
        if indent != base_indent:
            continue
        match = JUMP_RE.match(stripped)
        if match is None:
            continue
        edges.append(
            {"to": match.group(1), "kind": "jump", "option_src": None, "line": body_start + offset + 1}
        )
    return edges


def _scan_translations(tl_dir: Path, language: str, labels: set[str]) -> dict:
    zh_per_label: dict[str, int] = {}
    blocks_per_label: dict[str, int] = {}
    lines_map: dict[str, str] = {}
    strings_map: dict[str, str] = {}
    language_key = language.strip()

    for path in _tl_rpy_files(tl_dir):
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        index = 0
        while index < len(lines):
            match = TRANSLATE_RE.match(lines[index])
            if match is None:
                index += 1
                continue
            lang, block_id = match.group(1), match.group(2)
            block_start = index + 1
            index += 1
            while index < len(lines) and (lines[index].strip() == "" or lines[index].startswith((" ", "\t"))):
                index += 1
            if lang != language_key:
                continue
            block = lines[block_start:index]
            if block_id == "strings":
                _scan_strings(block, strings_map)
                continue
            label_match = BLOCK_LABEL_RE.match(block_id)
            label = label_match.group(1) if label_match else block_id
            if label not in labels:
                continue
            blocks_per_label[label] = blocks_per_label.get(label, 0) + 1
            last_comment: str | None = None
            for line in block:
                stripped = line.strip()
                if not stripped:
                    continue
                if stripped.startswith("#"):
                    last_comment = stripped[1:].strip()
                    continue
                new_text = _say_text(stripped)
                if new_text is None:
                    continue
                if not CJK_RE.search(new_text):
                    continue
                zh_per_label[label] = zh_per_label.get(label, 0) + 1
                if last_comment:
                    src_text = _say_text(last_comment)
                    if src_text and src_text != new_text:
                        lines_map.setdefault(src_text, new_text)
                last_comment = None
    return {
        "zh_per_label": zh_per_label,
        "blocks_per_label": blocks_per_label,
        "lines_map": lines_map,
        "strings_map": strings_map,
    }


def _scan_strings(block: list[str], strings_map: dict[str, str]) -> None:
    pending_old: str | None = None
    for line in block:
        old = OLD_RE.match(line)
        if old is not None:
            pending_old = old.group(2)
            continue
        new = NEW_RE.match(line)
        if new is not None and pending_old is not None:
            destination = new.group(2)
            if destination and CJK_RE.search(destination) and destination != pending_old:
                strings_map.setdefault(pending_old, destination)
            pending_old = None


def _pick_title(
    says: list[str],
    dsts: list[str | None],
    lines_map: dict[str, str],
) -> tuple[str, str | None]:
    """挑一句能代表这个 label 的对白当标题。

    首句经常是 `...`、`?!`、`Wow!` 这种没有任何信息量的短句（1012 个 label 里
    311 个是纯省略号），直接拿来当标题会导致大纲里一大片重复、看不出剧情。
    所以跳过噪音句，取第一句「有实义」的对白；全都没有时退回首句原文。
    """
    fallback: tuple[str, str | None] | None = None
    for index, text in enumerate(says):
        dst = dsts[index] if index < len(dsts) else None
        dst = dst or lines_map.get(text)
        if fallback is None:
            fallback = (text, dst)
        cleaned = clean_say(dst or text)
        if not is_noise_title(cleaned) and len(cleaned) >= 4:
            return text, dst
    return fallback or ("", None)


def _status(done: int, say: int) -> str:
    if say <= 0 or done <= 0:
        return "todo"
    return "done" if done >= say else "part"


def scan(
    game_dir: Path,
    tl_dir: Path,
    language: str,
    translations: TranslationIndex | None = None,
) -> dict:
    """返回契约里的 stats / chapters / nodes / edges（不含 ok / project）。

    `translations` 是应用翻译缓存建出来的译文索引；有它就以缓存为准统计进度
    （游戏里实际显示的译文），没有就退回 tl 文件口径。
    """
    game_dir = Path(game_dir)
    labels: list[dict] = []
    for path in _game_rpy_files(game_dir):
        labels.extend(_parse_labels(path, game_dir))

    label_ids = {item["id"] for item in labels}
    translations = translations or TranslationIndex.empty()
    from_cache = len(translations) > 0
    translated = _scan_translations(Path(tl_dir), language or "chinese", label_ids)
    zh_per_label = translated["zh_per_label"]
    blocks_per_label = translated["blocks_per_label"]
    lines_map = translated["lines_map"]
    strings_map = translated["strings_map"]
    index = get_index(game_dir)

    nodes: list[dict] = []
    edges: list[dict] = []
    seen_edges: set[tuple] = set()
    for item in labels:
        body = item["body"]
        say, says, scenes, shows = _label_says_and_scenes(body)
        zh = int(zh_per_label.get(item["id"], 0))
        blocks = int(blocks_per_label.get(item["id"], 0))
        # 缓存里的译文按出现顺序取：同文件重复的同一句也能各自计数。
        cache_zh = 0
        dsts: list[str | None] = []
        for text in says:
            dst = translations.take(item["file"], text)
            dsts.append(dst)
            if dst:
                cache_zh += 1
        effective = cache_zh if from_cache else zh
        title_src, title_zh = _pick_title(says, dsts, lines_map)
        image, show_count = _resolve_label_image(index, scenes, shows)
        nodes.append(
            {
                "id": item["id"],
                "chapter": item["chapter"],
                "file": item["file"],
                "line": item["line"],
                "end_line": item["end_line"],
                "title_zh": title_zh,
                "title_src": title_src,
                "say": say,
                "zh": zh,
                "cache_zh": cache_zh,
                "progress": effective,
                "tl_blocks": blocks,
                "image": image,
                # 只回一个数字而不是数组：前端只需要「这段有几张演出图」这个提示，
                # 全量列表既撑大 payload 又得改渲染逻辑。
                "show_image_count": show_count,
                "status": _status(effective, say),
                "placeholder": blocks > 0 and effective == 0,
            }
        )
        for edge in (
            _menu_jumps(body, item["body_start"]) + _label_jumps(body, item["body_start"])
        ):
            target = edge["to"]
            if target not in label_ids:
                continue
            key = (item["id"], target, edge["kind"], edge.get("option_src") or "")
            if key in seen_edges:
                continue
            seen_edges.add(key)
            option_src = edge.get("option_src")
            edges.append(
                {
                    "from": item["id"],
                    "to": target,
                    "kind": edge["kind"],
                    "option_src": option_src,
                    "option_zh": strings_map.get(option_src) if option_src else None,
                    "line": edge["line"],
                }
            )

    nodes.sort(key=lambda node: (node["chapter"], node["line"]))
    chapters: dict[str, dict] = {}
    for node in nodes:
        chapter = chapters.setdefault(
            node["chapter"],
            {
                "id": node["chapter"],
                "file": node["file"],
                "labels": 0,
                "say": 0,
                "zh": 0,
                "cache_zh": 0,
                "progress": 0,
                "_first_line": node["line"],
            },
        )
        chapter["labels"] += 1
        chapter["say"] += node["say"]
        chapter["zh"] += node["zh"]
        chapter["cache_zh"] += node["cache_zh"]
        chapter["progress"] += node["progress"]
        chapter["_first_line"] = min(chapter["_first_line"], node["line"])
    chapter_list = []
    for chapter in sorted(chapters.values(), key=lambda item: item["id"]):
        chapter.pop("_first_line", None)
        chapter_list.append(chapter)

    cache_lines = sum(node["cache_zh"] for node in nodes)
    stats = {
        "chapters": len(chapter_list),
        "labels": len(nodes),
        "say_lines": sum(node["say"] for node in nodes),
        "zh_lines": sum(node["zh"] for node in nodes),
        "cache_lines": cache_lines,
        "translated_labels": sum(1 for node in nodes if node["cache_zh"] > 0),
        "labels_with_image": sum(1 for node in nodes if node["image"]),
        "edges": len(edges),
        "menu_edges": sum(1 for edge in edges if edge["kind"] == "menu"),
        "jump_edges": sum(1 for edge in edges if edge["kind"] == "jump"),
        "placeholder_labels": sum(1 for node in nodes if node["placeholder"]),
        "progress_source": "cache" if from_cache else "tl",
    }
    return {"stats": stats, "chapters": chapter_list, "nodes": nodes, "edges": edges}


def read_label(
    game_dir: Path,
    chapter: str,
    label_id: str,
    translations: TranslationIndex | None = None,
) -> dict | None:
    """读一个 label 的逐行明细：行号、说话人、原文、缓存译文、状态。

    蓝图清单视图用它把「这段剧情到底哪句没翻」铺开；译文同样来自应用缓存，
    和校对台看到的是同一份数据。
    """
    game_dir = Path(game_dir)
    relative = f"{chapter}.rpy"
    path = game_dir / relative
    if not path.is_file():
        return None
    parsed = _parse_labels(path, game_dir)
    item = next((entry for entry in parsed if entry["id"] == label_id), None)
    if item is None:
        return None

    translations = translations or TranslationIndex.empty()
    from_cache = len(translations) > 0
    body, body_start = item["body"], item["body_start"]
    # 画面口径必须和 scan() 完全一致：scene 优先、show 只算 label 结束时仍可见的
    # 那些（scene 清屏、hide 收走）。两处各写一套的话会出现「画布上有图、点开详情
    # 没图」这种更让人困惑的不一致。
    _, _, scenes, shows = _label_says_and_scenes(body)
    lines: list[dict] = []
    says: list[str] = []
    for offset, raw in enumerate(body):
        text = _say_text(raw)
        if text is None:
            continue
        dst = translations.take(item["file"], text)
        says.append(text)
        lines.append(
            {
                "line": body_start + offset + 1,
                "speaker": _say_speaker(raw),
                "src": text,
                "dst": dst,
                "status": "done" if dst else "empty",
            }
        )

    index = get_index(game_dir)
    image, show_count = _resolve_label_image(index, scenes, shows)
    cache_zh = sum(1 for line in lines if line["dst"])
    effective = cache_zh if from_cache else 0
    title_src, title_zh = _pick_title(says, [line["dst"] for line in lines], {})
    return {
        "id": item["id"],
        "chapter": item["chapter"],
        "file": item["file"],
        "line": item["line"],
        "end_line": item["end_line"],
        "title_src": title_src,
        "title_zh": title_zh,
        "say": len(lines),
        "cache_zh": cache_zh,
        "image": image,
        "show_image_count": show_count,
        "status": _status(effective, len(lines)),
        "lines": lines,
    }
