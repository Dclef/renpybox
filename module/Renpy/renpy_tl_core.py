# -*- coding: utf-8 -*-
"""
Ren'Py TL 解析核心

说明：
- 提供 AST 数据结构、词法/语法解析、匹配与基础工具
- 命名风格与原实现区分，但保持对外行为一致
"""

from __future__ import annotations

import dataclasses
import hashlib
import os
import re
from enum import Enum
from typing import Literal, Sequence

from module.Cache.CacheItem import CacheItem

try:
    from enum import StrEnum  # Python 3.11+
except Exception:
    class StrEnum(str, Enum):
        """兼容 Python 3.10 的 StrEnum。"""
        pass


class TlBlockKind(StrEnum):
    """translate 块类型"""
    LABEL = "LABEL"
    STRINGS = "STRINGS"
    PYTHON = "PYTHON"
    OTHER = "OTHER"


def tl_block_kind_name(value) -> str:
    """返回跨 Python 版本稳定的翻译块类型名称。"""
    raw = getattr(value, "value", value)
    text = str(raw or "")
    return text.rsplit(".", 1)[-1]


def tl_statement_ordinal(block, line_no):
    """返回块中某个语句的布局无关序号。

    增量临时文件与合并后的主 TL 可能存在空行/注释布局差异（先后空行、
    META 位置注释等），因此身份不能依赖 ``line_no - header_line_no`` 这类
    原始行偏移。这里按 TEMPLATE/TARGET 语句的相对顺序计数，所有格式下
    都能得到相同结果。
    """
    if not isinstance(block, TlBlock) or not isinstance(line_no, int):
        return None
    ordinal = 0
    for stmt in block.statements:
        if stmt.line_no >= line_no:
            break
        if stmt.stmt_kind in (TlStmtKind.TEMPLATE, TlStmtKind.TARGET):
            ordinal += 1
    return ordinal


def tl_dir_signature(tl_dir) -> tuple:
    """返回 tl 目录下全部 .rpy 文件的变更签名。

    签名包含每个文件的相对路径、mtime(ns) 与大小，任何文件变化都会改变
    签名，因此可以安全用于结果缓存（不会产生遗漏）。
    """
    from pathlib import Path

    entries = []
    if tl_dir is not None and Path(tl_dir).is_dir():
        for path in sorted(Path(tl_dir).rglob("*.rpy")):
            try:
                stat = path.stat()
                entries.append(
                    (
                        path.relative_to(tl_dir).as_posix(),
                        stat.st_mtime_ns,
                        stat.st_size,
                    )
                )
            except OSError:
                entries.append((path.relative_to(tl_dir).as_posix(), 0, 0))
    return tuple(entries)


class TlStmtKind(StrEnum):
    """语句类型"""
    TEMPLATE = "TEMPLATE"  # 模板行（注释模板或 old 行）
    TARGET = "TARGET"      # 目标翻译行
    META = "META"          # 位置/元注释
    BLANK = "BLANK"
    OTHER = "OTHER"


class TlSlotRole(StrEnum):
    """抽取槽位类型"""
    DIALOGUE = "DIALOGUE"
    NAME = "NAME"
    STRING = "STRING"      # strings: old/new


@dataclasses.dataclass(frozen=True)
class TlStringLiteral:
    start_col: int
    end_col: int
    raw_inner: str
    value: str
    quote: Literal['"'] = '"'


@dataclasses.dataclass(frozen=True)
class TlSlot:
    role: TlSlotRole
    lit_index: int


@dataclasses.dataclass
class TlStatement:
    line_no: int
    raw_line: str
    indent: str
    code: str
    stmt_kind: TlStmtKind
    block_kind: TlBlockKind
    literals: list[TlStringLiteral]
    strict_key: str
    relaxed_key: str
    string_count: int


@dataclasses.dataclass
class TlBlock:
    header_line_no: int
    lang: str
    label: str
    kind: TlBlockKind
    statements: list[TlStatement]


@dataclasses.dataclass
class TlDocument:
    lines: list[str]
    blocks: list[TlBlock]


PLACEHOLDER = '"{}"'

RE_TRANSLATE_HEADER = re.compile(
    r"^translate\s+([A-Za-z0-9_]+)\s+([A-Za-z0-9_]+)\s*:\s*$"
)
RE_GAME_LOCATION = re.compile(r"^(?:game/)?[^:]+\.(?:rpy|rpyc):\d+\s*$")
RENPYBOX_REPLACE_ONLY_MARKER = "renpybox: replace-only"


def has_replace_only_marker(lines, old_index: int) -> bool:
    """只认紧邻条目的补充替换标记，允许中间有空行和源码位置注释。"""
    cursor = old_index - 1
    while cursor >= 0:
        stripped = lines[cursor].strip()
        if not stripped or (stripped.startswith("#") and RE_GAME_LOCATION.match(stripped[1:].strip()) is not None):
            cursor -= 1
            continue
        return stripped == f"# {RENPYBOX_REPLACE_ONLY_MARKER}"
    return False



# ==================== 词法工具 ====================

def split_indent(raw_line: str) -> tuple[str, str]:
    i = 0
    while i < len(raw_line) and raw_line[i] in {" ", "\t"}:
        i += 1
    return raw_line[:i], raw_line[i:]


def strip_comment_prefix(text: str) -> tuple[bool, str]:
    if not text.startswith("#"):
        return False, text
    content = text[1:]
    if content.startswith(" "):
        content = content[1:]
    return True, content


def sha1_hex(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8"), usedforsecurity=False).hexdigest()


def normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def unescape_tl_string(raw_inner: str) -> str:
    """还原写入翻译文件时使用的字符串转义。"""
    result: list[str] = []
    index = 0
    escape_map = {"n": "\n", "r": "\r", "t": "\t"}
    while index < len(raw_inner):
        char = raw_inner[index]
        if char != "\\" or index + 1 >= len(raw_inner):
            result.append(char)
            index += 1
            continue

        escaped = raw_inner[index + 1]
        if escaped in escape_map:
            result.append(escape_map[escaped])
        elif escaped in {"\\", '"', "'"}:
            result.append(escaped)
        else:
            result.extend(("\\", escaped))
        index += 2
    return "".join(result)


def escape_tl_string(text: str) -> str:
    """写回时转义引号与换行。"""
    return (
        text.replace("\\", "\\\\")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\n", "\\n")
        .replace('"', '\\"')
    )


def scan_quoted_literals(code: str) -> list[TlStringLiteral]:
    """扫描双引号字面量（仅支持双引号）。"""
    literals: list[TlStringLiteral] = []
    i = 0
    while i < len(code):
        if code[i] != '"':
            i += 1
            continue

        start = i
        i += 1
        buf: list[str] = []
        while i < len(code):
            ch = code[i]
            if ch == "\\" and i + 1 < len(code):
                buf.append(code[i])
                buf.append(code[i + 1])
                i += 2
                continue
            if ch == '"':
                end = i + 1
                raw_inner = "".join(buf)
                value = unescape_tl_string(raw_inner)
                literals.append(
                    TlStringLiteral(
                        start_col=start,
                        end_col=end,
                        raw_inner=raw_inner,
                        value=value,
                    )
                )
                i = end
                break
            buf.append(ch)
            i += 1
        else:
            # 未闭合引号：视为不可解析
            return []

    return literals


def build_line_skeleton(code: str, literals: list[TlStringLiteral]) -> str:
    if not literals:
        return normalize_ws(code)

    parts: list[str] = []
    pos = 0
    for lit in literals:
        parts.append(code[pos:lit.start_col])
        parts.append(PLACEHOLDER)
        pos = lit.end_col
    parts.append(code[pos:])
    return normalize_ws("".join(parts))


def normalize_speaker_token(code: str) -> str:
    stripped = code.lstrip()
    if stripped.startswith('"'):
        return code

    m = re.match(r"^(\s*)([A-Za-z_][A-Za-z0-9_]*)(\b.*)$", code)
    if m is None:
        return code
    return f"{m.group(1)}<SPEAKER>{m.group(3)}"


def is_resource_path(text: str) -> bool:
    s = text.strip()
    if s == "":
        return False

    base = os.path.basename(s)
    _, ext = os.path.splitext(base)
    if ext == "":
        return False

    ext_lower = ext.lower()
    resource_exts = {
        ".mp3", ".ogg", ".wav", ".flac", ".opus",
        ".mp4", ".webm", ".avi", ".mkv",
        ".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp",
        ".ttf", ".otf", ".woff", ".woff2",
    }
    return ext_lower in resource_exts


def strip_renpy_markup(text: str) -> str:
    result = text
    for rule in CacheItem.REGEX_RENPY:
        result = rule.sub("", result)
    return result


def is_tl_text(text: str) -> bool:
    s = text.strip()
    if s == "":
        return False

    # 纯 [var] 字符串通常是运行时占位符
    if re.fullmatch(r"\[[^\]]+\]", s) is not None:
        return False

    cleaned = strip_renpy_markup(text).strip()
    if cleaned != "":
        return True

    # 形如 {#language name and font} 需要翻译
    if "{#" in s:
        return True

    return False


# ==================== 语法解析 ====================

def parse_tl_header(line: str) -> tuple[str, str] | None:
    m = RE_TRANSLATE_HEADER.match(line.strip())
    if m is None:
        return None
    return m.group(1), m.group(2)


def get_block_kind(label: str) -> TlBlockKind:
    if label == "strings":
        return TlBlockKind.STRINGS
    if label == "python":
        return TlBlockKind.PYTHON
    return TlBlockKind.LABEL


def is_meta_comment(content: str) -> bool:
    stripped = content.strip()
    if stripped == RENPYBOX_REPLACE_ONLY_MARKER:
        return True
    if stripped.startswith("TODO:"):
        return True
    return RE_GAME_LOCATION.match(stripped) is not None


def parse_tl_statement(
    line_no: int,
    raw_line: str,
    block_kind: TlBlockKind,
) -> TlStatement:
    if raw_line.strip() == "":
        return TlStatement(
            line_no=line_no,
            raw_line=raw_line,
            indent="",
            code="",
            stmt_kind=TlStmtKind.BLANK,
            block_kind=block_kind,
            literals=[],
            strict_key="",
            relaxed_key="",
            string_count=0,
        )

    indent, rest = split_indent(raw_line)
    is_comment, content = strip_comment_prefix(rest)

    stmt_kind = TlStmtKind.OTHER
    code = rest

    if is_comment:
        code = content
        if is_meta_comment(content):
            stmt_kind = TlStmtKind.META
        else:
            stmt_kind = TlStmtKind.TEMPLATE
    else:
        if block_kind == TlBlockKind.STRINGS and rest.startswith("old "):
            stmt_kind = TlStmtKind.TEMPLATE
        elif block_kind == TlBlockKind.STRINGS and rest.startswith("new "):
            stmt_kind = TlStmtKind.TARGET
        else:
            stmt_kind = TlStmtKind.TARGET

    literals = scan_quoted_literals(code)
    strict_key = build_line_skeleton(code, literals)

    relaxed_key = strict_key
    if block_kind == TlBlockKind.LABEL:
        relaxed_key = normalize_ws(normalize_speaker_token(strict_key))

    return TlStatement(
        line_no=line_no,
        raw_line=raw_line,
        indent=indent,
        code=code,
        stmt_kind=stmt_kind,
        block_kind=block_kind,
        literals=literals,
        strict_key=strict_key,
        relaxed_key=relaxed_key,
        string_count=len(literals),
    )


def parse_tl_document(lines: list[str]) -> TlDocument:
    blocks: list[TlBlock] = []

    i = 0
    while i < len(lines):
        header = parse_tl_header(lines[i])
        if header is None:
            i += 1
            continue

        lang, label = header
        kind = get_block_kind(label)
        header_line_no = i + 1
        i += 1

        stmts: list[TlStatement] = []
        while i < len(lines):
            if parse_tl_header(lines[i]) is not None:
                break
            stmts.append(parse_tl_statement(i + 1, lines[i], kind))
            i += 1

        blocks.append(
            TlBlock(
                header_line_no=header_line_no,
                lang=lang,
                label=label,
                kind=kind,
                statements=stmts,
            )
        )

    return TlDocument(lines=lines, blocks=blocks)


class TlSyntaxError(ValueError):
    """TL 文本已无法安全解析，写入前必须拦下。"""


def validate_tl_document(text: str) -> TlDocument:
    """写入前的严格校验：解析新文本并与写入前的解析结果对照。

    ``parse_tl_document`` 对畸形输入是**故意**不抛异常的——它被用在增量抽取等
    热路径上，遇到半截文件也要继续往下走。但 ``atomic_write_text`` 的
    ``validator=`` 就是最后一道闸：一旦这里放过一份语法已坏的 TL，Ren'Py 启动时
    会直接报解析错误，而用户的原文已经在这一步被覆盖了。

    原来这里写的是 ``lambda value: parse_tl_document(value.splitlines())``，
    它对任何输入都返回一个文档对象，因此这个"校验器"从来不会失败，等于没写。
    """
    document = parse_tl_document(text.splitlines())
    _reject_unparseable_statements(document)
    return document


def _reject_unparseable_statements(document: TlDocument) -> None:
    """把解析器悄悄放过的问题变成异常。

    ``scan_quoted_literals`` 在遇到未闭合引号时直接 ``return []``
    （``scan_quoted_literals`` 里的 ``else: # 未闭合引号：视为不可解析``），
    而空列表和"这行本来就没有字符串"在调用方眼里长得一模一样——结果就是
    写坏的文件仍被当成"没有可翻译内容"接受，下一轮抽取会把它当成空文件删掉。
    这里补一个独立扫描来分辨这两种情况。
    """
    for block in document.blocks:
        for statement in block.statements:
            if statement.stmt_kind in (TlStmtKind.BLANK, TlStmtKind.META):
                continue
            if '"' not in statement.code:
                continue
            if statement.literals:
                continue
            if _has_unterminated_quote(statement.code):
                raise TlSyntaxError(
                    f"第 {statement.line_no} 行存在未闭合的双引号，"
                    f"无法安全解析：{statement.raw_line.strip()!r}"
                )


def _has_unterminated_quote(code: str) -> bool:
    """判断一行里是否有引号一直开到行尾都没闭合。

    这里必须逐字复刻 ``scan_quoted_literals`` 的转义规则，否则两边对"什么算
    转义"的判断不一致，校验器就会在解析器已经成功的那行上误报。也不能像
    ``scan_quoted_literals`` 那样遇到第一个坏引号就整体放弃——那样一行里
    "前面几个字面量正常、最后半个引号没闭合"会被漏掉。
    """
    index = 0
    length = len(code)
    while index < length:
        if code[index] != '"':
            index += 1
            continue
        index += 1
        closed = False
        while index < length:
            char = code[index]
            if char == "\\" and index + 1 < length:
                index += 2
                continue
            if char == '"':
                index += 1
                closed = True
                break
            index += 1
        if not closed:
            return True
    return False


# ==================== 匹配算法 ====================

def _drop_normalized_speaker(key: str) -> str:
    prefix = "<SPEAKER> "
    if key.startswith(prefix):
        return key.removeprefix(prefix)
    return key


def statements_equal(template: TlStatement, target: TlStatement) -> bool:
    if template.string_count != target.string_count:
        return False

    if template.strict_key == target.strict_key:
        return True

    if template.relaxed_key == target.relaxed_key:
        return True

    if template.strict_key == _drop_normalized_speaker(target.relaxed_key):
        return True

    if _drop_normalized_speaker(template.relaxed_key) == target.strict_key:
        return True

    return False


# 整表 LCS 的时间与内存都是 O(n*m)，超过该单元数就改用带宽受限 DP。
LCS_MAX_EXACT_CELLS = 1_000_000
# 带宽之外（块内漂移超过该值）的错位不参与对齐。
LCS_BAND = 64


def _backtrack_lcs(
    templates: list[TlStatement],
    targets: list[TlStatement],
    rows: Sequence[Sequence[int]],
    lows: Sequence[int],
    highs: Sequence[int],
) -> dict[int, int]:
    """用已算好的 DP 行回溯出模板行号→译文行号。"""
    mapping: dict[int, int] = {}
    i = 0
    j = 0
    while i < len(templates) and j < len(targets):
        if statements_equal(templates[i], targets[j]):
            mapping[templates[i].line_no] = targets[j].line_no
            i += 1
            j += 1
            continue

        if _banded_get(rows[i + 1], lows[i + 1], highs[i + 1], j) >= _banded_get(
            rows[i], lows[i], highs[i], j + 1
        ):
            i += 1
        else:
            j += 1

    return mapping


def match_tpl_to_target(block: TlBlock) -> dict[int, int]:
    templates = [
        s
        for s in block.statements
        if s.stmt_kind == TlStmtKind.TEMPLATE and s.strict_key != ""
    ]
    targets = [
        s
        for s in block.statements
        if s.stmt_kind == TlStmtKind.TARGET and s.strict_key != ""
    ]

    if not templates or not targets:
        return {}

    # 生成式 TL 的模板与译文严格交替、数量相等，按下标配对即可。结果与整表
    # DP 一致：回溯遇到相等位置必定取对角线，而对角线长度已达到 LCS 上界
    # min(n, m)，不存在更长的对齐方式。
    if len(templates) == len(targets) and all(
        statements_equal(template, target)
        for template, target in zip(templates, targets)
    ):
        return {
            template.line_no: target.line_no
            for template, target in zip(templates, targets)
        }

    if len(templates) * len(targets) <= LCS_MAX_EXACT_CELLS:
        return _exact_lcs_mapping(templates, targets)
    # 超大块：整表会同时打满 CPU 与内存，改为只在插值对角线附近对齐。
    return _banded_lcs_mapping(templates, targets)


def _banded_get(row: Sequence[int], low: int, high: int, column: int) -> int:
    """读取行内列值；带宽外视为不可达，返回 -1。"""
    if column < low or column > high:
        return -1
    return row[column - low]


def _exact_lcs_mapping(
    templates: list[TlStatement],
    targets: list[TlStatement],
) -> dict[int, int]:
    """整表 LCS 对齐，结果与原实现一致。"""
    dp: list[list[int]] = [[0] * (len(targets) + 1) for _ in range(len(templates) + 1)]
    for i in range(len(templates) - 1, -1, -1):
        for j in range(len(targets) - 1, -1, -1):
            if statements_equal(templates[i], targets[j]):
                dp[i][j] = dp[i + 1][j + 1] + 1
            else:
                dp[i][j] = max(dp[i + 1][j], dp[i][j + 1])

    return _backtrack_lcs(
        templates,
        targets,
        dp,
        [0] * (len(templates) + 1),
        [len(targets)] * (len(templates) + 1),
    )


def _banded_lcs_mapping(
    templates: list[TlStatement],
    targets: list[TlStatement],
) -> dict[int, int]:
    """只对齐插值对角线附近的 LCS，避免超大 translate 块卡死扫描。"""
    n = len(templates)
    m = len(targets)
    # 允许两类漂移：块内模板/译文总量差，以及额外的插入删除。
    band = LCS_BAND + abs(n - m)

    lows: list[int] = []
    highs: list[int] = []
    for i in range(n + 1):
        center = (i * m) // n
        lows.append(max(0, center - band))
        highs.append(min(m, ((i * m + n - 1) // n) + band))

    rows: list[Sequence[int]] = [()] * (n + 1)
    for i in range(n, -1, -1):
        low = lows[i]
        high = highs[i]
        row = [0] * (high - low + 1)
        for offset in range(high - low, -1, -1):
            j = low + offset
            if i == n or j == m:
                continue

            diagonal = _banded_get(rows[i + 1], lows[i + 1], highs[i + 1], j + 1)
            if statements_equal(templates[i], targets[j]):
                row[offset] = diagonal + 1 if diagonal >= 0 else 0
                continue

            row[offset] = max(
                diagonal,
                _banded_get(rows[i + 1], lows[i + 1], highs[i + 1], j),
                _banded_get(row, low, high, j + 1),
            )
        rows[i] = row

    return _backtrack_lcs(templates, targets, rows, lows, highs)


def pair_old_new_lines(block: TlBlock) -> dict[int, int]:
    pending_old: int | None = None
    mapping: dict[int, int] = {}

    for stmt in block.statements:
        code = stmt.code.strip()

        if stmt.stmt_kind == TlStmtKind.TEMPLATE and code.startswith("old "):
            pending_old = stmt.line_no
            continue

        if stmt.stmt_kind == TlStmtKind.TARGET and code.startswith("new "):
            if pending_old is None:
                continue
            mapping[pending_old] = stmt.line_no
            pending_old = None

    return mapping
