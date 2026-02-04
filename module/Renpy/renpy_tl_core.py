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
from typing import Literal

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
RE_GAME_LOCATION = re.compile(r"^game/.+?:\d+\s*$")


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
    """仅做最小反转义，避免行为偏离。"""
    return raw_inner.replace("\\n", "\n").replace('\\"', '"')


def escape_tl_string(text: str) -> str:
    """写回时转义引号与换行。"""
    return text.replace("\n", "\\n").replace('\\"', '"').replace('"', '\\"')


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

    dp: list[list[int]] = [[0] * (len(targets) + 1) for _ in range(len(templates) + 1)]
    for i in range(len(templates) - 1, -1, -1):
        for j in range(len(targets) - 1, -1, -1):
            if statements_equal(templates[i], targets[j]):
                dp[i][j] = dp[i + 1][j + 1] + 1
            else:
                dp[i][j] = max(dp[i + 1][j], dp[i][j + 1])

    mapping: dict[int, int] = {}
    i = 0
    j = 0
    while i < len(templates) and j < len(targets):
        if statements_equal(templates[i], targets[j]):
            mapping[templates[i].line_no] = targets[j].line_no
            i += 1
            j += 1
            continue

        if dp[i + 1][j] >= dp[i][j + 1]:
            i += 1
        else:
            j += 1

    return mapping


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
