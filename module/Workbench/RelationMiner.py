"""用「称谓词 × 同场景角色变量名」这条规则，从 .rpy 源码里挖有证据的人物关系。

规则本身很窄，但证据是可复核的：

    define mom = Character("{b}Airi{/b}")
    ...
    label after_school:
        airi "Did you see my mom today?"     ← 同一 label 里 mom 也开口过

于是得到 `Airi --母亲--> Airi`？不，得到的是「说话人 --母亲--> mom 这个变量指向的角色」。
两个条件必须**同时**成立才记一条证据：

1. 这台词的文本里出现了称谓词（`\\bmom\\b`）；
2. 同场景里正好有角色的 Character 变量名等于该称谓词。

只满足第一条是「台词里提到妈妈」，满足两条才是「这个角色就是他的妈妈」。
Ren'Py 里 `define mom = Character(...)` 这种写法非常常见，所以第 2 条能落地；
换成随意命名的工程，规则自然挖不出东西，也不会瞎猜——这是刻意的。

两个容易踩的点：

- Character 参数里的名字可能带 Ren'Py 标记（`{b}Airi{/b}`、`{color=#fff}…`），
  必须剥掉标记后才能和扫描结果里的显示名对上，否则一条边都挖不到；
- `define airi = mom` 这类别名变量在台词里也会当说话人出现，要先归一到
  真正持有 Character 定义的那个变量，否则「同场景有 mom」永远判定不成立。
"""

from __future__ import annotations

import bisect
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from base.Base import Base

# 称谓词 -> (中文关系词, 关系类别)。类别取值必须落在 WorkbenchData.RELATION_CATEGORIES 里。
RELATION_WORDS: dict[str, tuple[str, str]] = {
    "mom": ("母亲", "family"),
    "mother": ("母亲", "family"),
    "mum": ("母亲", "family"),
    "dad": ("父亲", "family"),
    "father": ("父亲", "family"),
    "sister": ("姐妹", "family"),
    "brother": ("兄弟", "family"),
    "daughter": ("女儿", "family"),
    "son": ("儿子", "family"),
    "wife": ("妻子", "romantic"),
    "husband": ("丈夫", "romantic"),
    "master": ("主人", "work"),
    "mistress": ("主母", "work"),
    "servant": ("仆从", "work"),
    "slave": ("奴隶", "work"),
    "teacher": ("老师", "work"),
    "student": ("学生", "work"),
    "doctor": ("医生", "work"),
    "nurse": ("护士", "work"),
    "boss": ("上司", "work"),
    "captain": ("长官", "work"),
    "princess": ("公主", "other"),
    "lady": ("女士", "other"),
    "granny": ("奶奶", "family"),
    "aunt": ("姑姨", "family"),
    "uncle": ("叔伯", "family"),
    "cousin": ("表亲", "family"),
    "friend": ("朋友", "friendly"),
    "lover": ("恋人", "romantic"),
    "darling": ("爱人", "romantic"),
}

# 每条边最多留几条原文证据、每条证据截断多少字。
RELATION_SAMPLE_LIMIT = 3
RELATION_SAMPLE_CHARS = 90
# 章节证据：一条边最多记多少个剧本文件、每个文件最多留几条原文。
# 上限是给时间线矩阵用的——列数太多图就没法看了，超出的按命中次数取最多的那些。
RELATION_CHAPTER_LIMIT = 32
RELATION_CHAPTER_SAMPLE_LIMIT = 2

# 扫描时跳过的运行时目录（和 CharacterScanner 保持一致）
EXCLUDED_DIRS = frozenset({"tl", "cache", "__pycache__"})

# 只保留含称谓词的台词：整份脚本里这样的行通常不到 3%，缓存体积和后续
# 正则次数都能压下来，跑完一个 37000 行的工程不需要逐行遍历全部文本。
RE_ANY_WORD = re.compile(r"\b(?:" + "|".join(RELATION_WORDS) + r")\b", re.IGNORECASE)


def _natural_key(name: str) -> tuple:
    """自然序键：把名字切成「文本/数字」交替的块，数字块按数值比较。

    events2 要排在 events10 前面——纯字典序会反过来，时间线就对不上剧情顺序了。
    """
    parts = re.split(r"(\d+)", (name or "").casefold())
    return tuple((1, int(part)) if part.isdigit() else (0, part) for part in parts if part != "")


@dataclass
class RelationEvidence:
    """一条有源码证据的人物关系。"""

    from_name: str
    to_name: str
    relation: str
    category: str
    count: int
    # 命中的台词原文，按出现顺序最多 RELATION_SAMPLE_LIMIT 条
    samples: list[str] = field(default_factory = list)
    # 按剧本文件切开的命中分布，给「关系时间线」用：
    # {"file": "events3.rpy", "line": 128, "count": 7, "samples": ["...", "..."]}
    # file 是相对 game/ 的 POSIX 路径；line 是该文件里第一次命中的行号（1 起）。
    chapters: list[dict] = field(default_factory = list)


@dataclass(frozen = True)
class _Scene:
    """一个场景（label 块）里与关系挖掘有关的信息。"""

    # 本场景开口过的角色变量名（按首次开口顺序）
    speakers: tuple[str, ...]
    # 本场景里含称谓词的台词：(变量名, 台词原文, 行号)
    hits: tuple[tuple[str, str, int], ...]


@dataclass(frozen = True)
class _ParsedFile:
    """单个 .rpy 的解析结果；缓存这一层，重扫时只做 stat。"""

    defines: tuple[tuple[str, str], ...]
    aliases: tuple[tuple[str, str], ...]
    scenes: tuple[_Scene, ...]


_EMPTY_FILE = _ParsedFile((), (), ())


class RelationMiner(Base):
    """按「称谓词 × 同场景变量名」规则挖掘人物关系。"""

    # define <var> = Character(     —— 只匹配到左括号，参数在下面按需截取
    RE_CHARACTER_DEFINE = re.compile(
        r"^[ \t]*define[ \t]+(?P<var>[A-Za-z_]\w*)[ \t]*=[ \t]*Character[ \t]*\(",
        re.MULTILINE,
    )
    # 左括号之后的第一个字符串字面量；兼容 Character(_("名字"), ...) 写法
    RE_FIRST_STRING = re.compile(
        r"""[ \t]*(?:_\([ \t]*)?(?:"(?P<double>(?:\\.|[^"\\\n])*)"|'(?P<single>(?:\\.|[^'\\\n])*)')"""
    )
    # define <var> = <target>：把已有 Character 变量换个名字引用
    RE_CHARACTER_ALIAS = re.compile(
        r"^[ \t]*define[ \t]+(?P<var>[A-Za-z_]\w*)[ \t]*=[ \t]*(?P<target>[A-Za-z_]\w*)[ \t]*(?:#.*)?$",
        re.MULTILINE,
    )
    RE_LABEL = re.compile(r"^label\s+([\w.]+)", re.MULTILINE)
    # 和 CharacterScanner 的台词正则保持一致，保证两边行数口径相同
    RE_DIALOGUE = re.compile(
        r"^[ \t]*(?P<var>[A-Za-z_]\w*)"
        r"(?:[ \t]+(?:@|[A-Za-z_]\w*|-[A-Za-z_]\w*))*[ \t]+"
        r"(?P<quote>\"(?:\\.|[^\"\n])*\"|'(?:\\.|[^'\n])*')",
        re.MULTILINE,
    )
    # Ren'Py 富文本标签：{b}Airi{/b} / {color=#fff}Airi{/color}
    RE_FORMAT_TAG = re.compile(r"\{[^{}]*\}")
    RE_SPACES = re.compile(r"\s+")

    # 称谓词边界匹配，预编译避免每行都重新编译
    _WORD_PATTERNS: dict[str, re.Pattern[str]] = {
        word: re.compile(r"\b" + word + r"\b", re.IGNORECASE) for word in RELATION_WORDS
    }

    # 文件级缓存：路径 -> ((mtime_ns, size), 解析结果)。指纹没变就不重新解析。
    _CACHE: dict[str, tuple[tuple[int, int], _ParsedFile]] = {}
    _CACHE_LIMIT = 4096

    def __init__(self) -> None:
        super().__init__()

    # ---------------------------------------------------------------- 解析
    @staticmethod
    def clean_name(value: str) -> str:
        """剥掉 Ren'Py 富文本标记，得到和扫描结果同口径的显示名。"""
        text = (value or "").replace('\\"', '"').replace("\\'", "'").replace("\\\\", "\\")
        return RelationMiner.RE_FORMAT_TAG.sub("", text).strip()

    @classmethod
    def _first_string_argument(cls, text: str, position: int) -> str:
        """取 Character( 之后第一个字符串参数；取不到就返回空串。"""
        match = cls.RE_FIRST_STRING.match(text, position)
        if match is None:
            return ""
        double = match.group("double")
        raw = double if double is not None else (match.group("single") or "")
        return cls.clean_name(raw)

    @classmethod
    def _line_text(cls, quoted: str) -> str:
        """去掉台词两侧引号并压掉多余空白。"""
        text = quoted[1:-1] if len(quoted) >= 2 else quoted
        return cls.RE_SPACES.sub(" ", text.replace("\\n", " ")).strip()

    @classmethod
    def _clean_sample(cls, line: str) -> str:
        """证据原文：压成一行，截断到 RELATION_SAMPLE_CHARS 字。"""
        text = cls.RE_SPACES.sub(" ", line).strip()
        return text[:RELATION_SAMPLE_CHARS]

    def _parse(self, path: Path) -> _ParsedFile:
        """解析单个 .rpy：Character 定义、别名定义、按 label 切好的场景。"""
        try:
            text = path.read_text(encoding = "utf-8-sig", errors = "ignore")
        except (OSError, ValueError):
            return _EMPTY_FILE
        if text == "":
            return _EMPTY_FILE

        defines: list[tuple[str, str]] = []
        for match in self.RE_CHARACTER_DEFINE.finditer(text):
            name = self._first_string_argument(text, match.end())
            if name != "":
                defines.append((match.group("var"), name))

        aliases: list[tuple[str, str]] = [
            (match.group("var"), match.group("target"))
            for match in self.RE_CHARACTER_ALIAS.finditer(text)
        ]

        # label 是 Ren'Py 的场景边界；没有 label 的文件退化成整文件一个场景。
        starts = [match.start() for match in self.RE_LABEL.finditer(text)]
        speakers: dict[int, list[str]] = defaultdict(list)
        hits: dict[int, list[tuple[str, str, int]]] = defaultdict(list)
        line_count = 0
        cursor = 0
        for match in self.RE_DIALOGUE.finditer(text):
            var = match.group("var")
            # 位于第一个 label 之前的台词归到 -1 号场景，不硬塞进下一个 label。
            scene = bisect.bisect_right(starts, match.start()) - 1 if starts else 0
            if var not in speakers[scene]:
                speakers[scene].append(var)
            line = self._line_text(match.group("quote"))
            if line != "" and RE_ANY_WORD.search(line):
                # 行号只算一次：match 是按位置递增的，从上次的位置往后数换行符，
                # 整份文件只扫一遍，不要每命中一行都 count("\n", 0, pos)。
                line_count += text.count("\n", cursor, match.start())
                cursor = match.start()
                hits[scene].append((var, line, line_count + 1))

        scenes = tuple(
            _Scene(tuple(speakers[scene]), tuple(hits.get(scene, ())))
            for scene in sorted(speakers)
        )
        return _ParsedFile(tuple(defines), tuple(aliases), scenes)

    def _load(self, path: Path) -> _ParsedFile:
        """带缓存的解析：按 mtime + size 指纹判断文件是否变化。"""
        try:
            stat = path.stat()
        except OSError:
            return _EMPTY_FILE
        fingerprint = (stat.st_mtime_ns, stat.st_size)
        key = str(path)
        cached = self._CACHE.get(key)
        if cached is not None and cached[0] == fingerprint:
            return cached[1]
        parsed = self._parse(path)
        self._CACHE[key] = (fingerprint, parsed)
        while len(self._CACHE) > self._CACHE_LIMIT:
            self._CACHE.pop(next(iter(self._CACHE)), None)
        return parsed

    @classmethod
    def _iter_source_files(cls, game_dir: Path) -> list[Path]:
        """遍历源码文件，跳过 tl / cache 等运行时目录。"""
        result: list[Path] = []
        for path in game_dir.rglob("*.rpy"):
            try:
                parts = {part.casefold() for part in path.relative_to(game_dir).parts[:-1]}
            except ValueError:
                continue
            if parts & EXCLUDED_DIRS:
                continue
            result.append(path)
        return sorted(result)

    # ---------------------------------------------------------------- 建模
    @staticmethod
    def _build_speakers(parsed: list[_ParsedFile], known_names: set[str]) -> dict[str, str]:
        """变量名 -> 角色名；只保留显示名能对上扫描结果的定义。"""
        speakers: dict[str, str] = {}
        for item in parsed:
            for var, name in item.defines:
                if name in known_names:
                    speakers.setdefault(var, name)
        return speakers

    @staticmethod
    def _canonical_vars(parsed: list[_ParsedFile], speakers: dict[str, str]) -> dict[str, str]:
        """别名变量 -> 真正持有 Character 定义的那个变量。

        `define airi = mom` 之后台词里的说话人是 airi，但「同场景有 mom 这个变量」
        才是关系规则的判定条件，所以要把 airi 归一到 mom。
        """
        aliases: dict[str, str] = {}
        for item in parsed:
            for var, target in item.aliases:
                aliases.setdefault(var, target)

        canonical: dict[str, str] = {}
        for var in aliases:
            if var in speakers:
                # 自己就有 Character 定义，按自己的身份出现
                continue
            current = var
            seen = {var}
            while current in aliases and current not in speakers:
                current = aliases[current]
                if current in seen:
                    break
                seen.add(current)
            if current in speakers:
                canonical[var] = current
        return canonical

    # ------------------------------------------------------------------ 挖掘
    def mine(self, game_dir: Path, known_names: set[str]) -> list[RelationEvidence]:
        """挖出所有有证据的关系边，按命中次数降序返回。"""
        root = self._normalize_game_dir(game_dir)
        if root is None or not known_names:
            return []

        files = self._iter_source_files(root)
        active = {str(path) for path in files}
        for key in [item for item in self._CACHE if item not in active]:
            self._CACHE.pop(key, None)

        # 带上路径：章节证据要知道每个命中来自哪个剧本文件。
        parsed = [(path, self._load(path)) for path in files]
        documents = [item for _path, item in parsed]
        speakers = self._build_speakers(documents, known_names)
        if len(speakers) < 2:
            self.debug(f"[RelationMiner] 可用的 Character 定义不足：{len(speakers)} 个")
            return []
        canonical = self._canonical_vars(documents, speakers)

        evidence: dict[tuple[str, str, str], RelationEvidence] = {}
        # (关系边, 文件名) -> 该文件里的命中分布；最后再按自然序挂回每条边。
        chapters: dict[tuple[tuple[str, str, str], str], dict] = {}
        for path, item in parsed:
            relative = self._relative_name(path, root)
            for scene in item.scenes:
                if len(scene.speakers) < 2 or not scene.hits:
                    continue
                # 本场景在场的变量名（小写）-> 角色名
                present: dict[str, str] = {}
                for var in scene.speakers:
                    root_var = canonical.get(var, var)
                    name = speakers.get(root_var, "")
                    if name != "":
                        present.setdefault(root_var.casefold(), name)
                if len(present) < 2:
                    continue
                # 只有「本场景真的在场的称谓变量」才值得逐行匹配
                words = [word for word in RELATION_WORDS if word in present]
                if not words:
                    continue

                for var, line, line_no in scene.hits:
                    speaker = speakers.get(canonical.get(var, var), "")
                    if speaker == "":
                        continue
                    speaker_key = canonical.get(var, var).casefold()
                    for word in words:
                        if word == speaker_key:
                            # 「mom 说：我妈妈……」不构成 mom 与自己的关系
                            continue
                        if not self._WORD_PATTERNS[word].search(line):
                            continue
                        target = present[word]
                        if target == speaker:
                            continue
                        relation, category = RELATION_WORDS[word]
                        key = (speaker, target, relation)
                        row = evidence.get(key)
                        if row is None:
                            row = RelationEvidence(speaker, target, relation, category, 0, [])
                            evidence[key] = row
                        row.count += 1
                        sample = self._clean_sample(line)
                        if len(row.samples) < RELATION_SAMPLE_LIMIT:
                            if sample != "" and sample not in row.samples:
                                row.samples.append(sample)
                        # 章节证据：同一个文件里的多次命中合成一条，行号留第一次出现的。
                        chapter = chapters.get((key, relative))
                        if chapter is None:
                            chapter = {"file": relative, "line": line_no, "count": 0, "samples": []}
                            chapters[(key, relative)] = chapter
                        chapter["count"] += 1
                        if (
                            sample != ""
                            and sample not in chapter["samples"]
                            and len(chapter["samples"]) < RELATION_CHAPTER_SAMPLE_LIMIT
                        ):
                            chapter["samples"].append(sample)

        for (key, _relative), chapter in chapters.items():
            evidence[key].chapters.append(chapter)
        for row in evidence.values():
            row.chapters = self._sort_chapters(row.chapters)

        rows = sorted(
            evidence.values(),
            key = lambda row: (-row.count, row.from_name.casefold(), row.to_name.casefold(), row.relation),
        )
        self.info(
            f"[RelationMiner] 挖掘完成：{len(files)} 个文件 / "
            f"{len(speakers)} 个角色变量 / {len(rows)} 条关系边"
        )
        return rows

    @staticmethod
    def _relative_name(path: Path, root: Path) -> str:
        """相对 game/ 的 POSIX 路径，保留 .rpy 后缀；算不出来就退回文件名。

        时间线把它当列标识用，Windows 上反斜杠会让同一份工程出现两套列名。
        """
        try:
            return path.relative_to(root).as_posix()
        except ValueError:
            return path.name

    @staticmethod
    def _sort_chapters(chapters: list[dict]) -> list[dict]:
        """章节按自然序排，超出上限时保留命中次数最多的那些。

        自然序（events2 在 events10 前）才能对上剧情顺序，纯字典序会把
        events10 排到 events2 前面，时间线就乱了。
        """
        if len(chapters) <= RELATION_CHAPTER_LIMIT:
            return sorted(chapters, key = lambda item: _natural_key(item.get("file", "")))
        busiest = sorted(chapters, key = lambda item: -int(item.get("count") or 0))[:RELATION_CHAPTER_LIMIT]
        return sorted(busiest, key = lambda item: _natural_key(item.get("file", "")))

    @staticmethod
    def _normalize_game_dir(game_dir: Path) -> Path | None:
        """允许传工程根目录或 game 目录。"""
        try:
            root = Path(game_dir)
        except (TypeError, ValueError):
            return None
        if root.name.lower() != "game" and (root / "game").is_dir():
            root = root / "game"
        return root if root.is_dir() else None


_INSTANCE = RelationMiner()


def mine(game_dir: Path, known_names: set[str]) -> list[RelationEvidence]:
    """模块级入口：复用同一个挖掘器，文件缓存才能生效。"""
    return _INSTANCE.mine(game_dir, known_names)
