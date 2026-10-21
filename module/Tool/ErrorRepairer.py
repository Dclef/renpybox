"""
Ren'Py 错误修复工具
检查并修复常见语法错误，支持深度 Lint 检查
"""

import contextlib
import dataclasses
import hashlib
import io
import json
import os
import re
import secrets
import shutil
import subprocess
import tempfile
import time
import zipfile
from collections import Counter
from typing import Callable, Iterator, List, Dict, Tuple, Optional
from pathlib import Path

from base.LogManager import LogManager
from module.File.AtomicWrite import atomic_write_text
from module.Localizer.Localizer import Localizer
from module.Renpy.renpy_tl_core import (
    TlBlockKind,
    TlDocument,
    TlStmtKind,
    match_tpl_to_target,
    pair_old_new_lines,
    parse_tl_document,
)
from utils.call_game_python import get_python_path_from_game_path, get_py_path


# Ren'Py lint 里已知「跟译文好不好无关」的提示：游戏把角色名存进运行时变量
# （`$ x = "名字"` 后 `x "台词"`）时 lint 求不出 who，但 Ren'Py 的 say 明确
# 支持字符串 who（见 renpy/exports.py 的 say 文档），运行时是好的。这类条目
# 不计入译文问题，避免几百条噪音把真问题淹掉。
IGNORED_LINT_HINT_TYPES = frozenset({
    "who_unresolved",
})

# 扫描问题的分类。auto：无参数即可安全批量修复；conditional：用户勾选后才修；
# manual：只能人工处理（或仅提示）。UI/API 的默认修复范围只取 auto。
AUTO_FIX_TYPES = frozenset({
    "indent",
    "empty_block",
    "duplicate_old_new",
    "unescaped_dialogue_quotes",
})
CONDITIONAL_FIX_TYPES = frozenset({
    "indentation_level",
    "quotes",
})
MANUAL_TYPES = frozenset({
    "syntax",
    "placeholder_missing",
    "placeholder_extra",
    "placeholder_rewritten",
    "linebreak_mismatch",
    "extra_empty_string",
})
# 环境级问题（不属于文件内错误，单独收集，不参与文件修复）。
INCREMENTAL_LEFTOVER = "incremental_leftover"


def classify_issue_type(type_name: str) -> str:
    """把扫描出的问题类型归为 ``auto`` / ``conditional`` / ``manual``。

    未知类型一律按 ``manual`` 处理：宁可不自动写盘，也不能误改。
    """
    name = str(type_name or "").strip()
    if name in AUTO_FIX_TYPES:
        return "auto"
    if name in CONDITIONAL_FIX_TYPES:
        return "conditional"
    return "manual"


@dataclasses.dataclass
class FolderScanResult:
    """文件夹扫描结果：错误表加本次预算执行情况。

    ``total_files`` 仅在 ``total_files_known`` 为真时表示完整枚举的文件数。
    枚举完成前取消或超时会返回 0 和 False，不继续遍历以补齐总数。
    ``scanned_files`` 和 ``errors`` 只包含已完成检查的文件；
    ``budget_exhausted`` 表示取消或预算中断，不能将其视为目录无错误。
    """

    errors: Dict[str, List[Dict]]
    scanned_files: int
    total_files: int
    scanned_bytes: int
    budget_exhausted: bool
    # Enumeration can be cancelled before it returns a list. In that case the
    # legacy integer total remains 0, but it must not mean an empty directory.
    total_files_known: bool = True
    # 按类型统计的问题数，以及按分类聚合的可修复（auto）/需人工（manual）数量。
    # conditional 两类都不计入：它们必须由用户显式勾选才会被修复。
    issues_by_type: Dict[str, int] = dataclasses.field(default_factory=dict)
    environment_issues: List[Dict] = dataclasses.field(default_factory=list)
    fixable_count: int = 0
    manual_count: int = 0


class _ScanStopped(BaseException):
    """Unwind a scan without being swallowed by per-file error handling."""


class ErrorRepairer:
    """错误修复器"""

    # 模块级分类常量在类上再暴露一份：调用方既可 ``from ... import AUTO_FIX_TYPES``
    # 也可 ``ErrorRepairer.AUTO_FIX_TYPES``。
    AUTO_FIX_TYPES = AUTO_FIX_TYPES
    CONDITIONAL_FIX_TYPES = CONDITIONAL_FIX_TYPES
    MANUAL_TYPES = MANUAL_TYPES
    INCREMENTAL_LEFTOVER = INCREMENTAL_LEFTOVER
    classify_issue_type = staticmethod(classify_issue_type)

    # 真正的 label 语句尾部只允许「标识符」或「标识符(参数)」，
    # 其余形态是 screen 里的 label displayable（不是 label 语句）。
    RE_LABEL_STATEMENT_TAIL = re.compile(r"^\.?[A-Za-z_]\w*(?:\s*\([^)]*\))?$")

    # ``screen name(...):`` 以及 ``init -501 screen name(...):`` 都会开启 screen 块。
    RE_SCREEN_HEADER = re.compile(r"^(?:init\s+[-+]?[0-9.]+\s+)?screen(?:\s|$)")

    # ``python:`` / ``python early:`` / ``init python:`` 块内是 Python，
    # 缩进由 Python 语法决定，不能按 Ren'Py 块层级判断。
    RE_PYTHON_HEADER = re.compile(
        r"^(?:(?:init\s+(?:[-+]?[0-9.]+\s+)?)|(?:translate\s+\S+\s+))?python(?:\s|:|$)"
    )

    # 仅匹配单行、双引号定界的翻译或简单 say 语句。suffix 被限制为
    # 空白/注释，避免跨过 menu 条件、screen action 和同一行的其他代码。
    RE_RENPY_STRING_LINE = re.compile(
        r'^(?P<indent>[ \t]*)(?:(?P<prefix>old|new|[A-Za-z_]\w*)(?P<separator>[ \t]+))?'
        r'"(?P<body>.*?)"(?P<suffix>[ \t]*(?:#.*)?)$'
    )
    RE_CURLY_DOUBLE_STRING_LINE = re.compile(
        r'^(?P<indent>[ \t]*)(?:(?P<prefix>old|new|[A-Za-z_]\w*)(?P<separator>[ \t]+))?'
        r'“(?P<body>.*?)”(?P<suffix>[ \t]*(?:#.*)?)$'
    )
    RE_CURLY_SINGLE_STRING_LINE = re.compile(
        r'^(?P<indent>[ \t]*)(?:(?P<prefix>old|new|[A-Za-z_]\w*)(?P<separator>[ \t]+))?'
        r'‘(?P<body>.*?)’(?P<suffix>[ \t]*(?:#.*)?)$'
    )
    NON_DIALOGUE_PREFIXES = {
        "add", "bar", "button", "call", "camera", "default", "define",
        "drag", "else", "elif", "fixed", "for", "frame", "grid", "hide",
        "hbox", "if", "image", "imagebutton", "init", "jump", "key",
        "layeredimage", "menu", "on", "pass", "pause", "play", "python",
        "queue", "return", "scene", "screen", "show", "stop", "style",
        "text", "textbutton", "timer", "transform", "use", "vbar", "vbox",
        "viewport", "voice", "while", "window", "with",
    }
    SAFE_LINT_FIX_TYPES = frozenset({
        "parse_error",
        "syntax_error",
        "empty_block",
        "indentation_mismatch",
        "indentation_level",
    })
    SCREEN_BLOCK_PREFIXES = (
        "textbutton",
        "imagebutton",
        "text",
        "frame",
        "hbox",
        "vbox",
        "grid",
        "fixed",
        "window",
        "viewport",
        "use",
        "button",
        "image",
        "add",
    )

    # 大型项目首次 lint 要加载全部脚本与图片，实测常见数分钟；
    # 旧版固定 120 秒会把正常项目误判成「执行失败」，这里放宽到 30 分钟，可随时取消。
    LINT_TIMEOUT = 1800.0

    def __init__(self):
        self.logger = LogManager.get()
        self.errors_found = []
        # 最近一次 lint 失败原因（超时 / 找不到运行时 / 退出码），供上层拼提示。
        self.last_lint_error = ""
        # Ren'Py lint 的退出码：脚本有语法错误时 Ren'Py 会以 1 退出，但输出里
        # 仍然有能直接定位问题的条目，调用方据此决定提示口径。
        self.last_lint_exit_code = 0

    @staticmethod
    def resolve_translation_folder(folder_path: str | Path) -> Path:
        """将项目目录或 game 目录解析为翻译文件目录。"""
        path = Path(folder_path).expanduser()
        if path.name.casefold() == "game":
            return path / "tl"
        project_tl = path / "game" / "tl"
        if project_tl.is_dir():
            return project_tl
        return path

    @staticmethod
    def get_rpy_files(folder_path: str | Path, *, checkpoint: Optional[Callable[[], None]] = None) -> list[Path]:
        """返回目录下的 Ren'Py 脚本；不跟随 symlink/junction（lexical 边界）。"""
        from module.Tool.LexicalFs import iter_rpy_files_lexical

        return iter_rpy_files_lexical(folder_path, checkpoint=checkpoint)

    def _split_line_ending(self, line: str) -> tuple[str, str]:
        """拆分行内容和换行符，修复后保持原始换行风格。"""
        if line.endswith("\r\n"):
            return line[:-2], "\r\n"
        if line.endswith("\n"):
            return line[:-1], "\n"
        if line.endswith("\r"):
            return line[:-1], "\r"
        return line, ""

    @staticmethod
    def _scan_code_structure(line: str) -> tuple[str, int]:
        """返回（去掉字符串外注释并 rstrip 的代码, 括号净深度）。

        用于「语句是否有冒号」「条件是否跨行」这类结构判断：注释里的冒号、
        字符串里的括号都不能参与判断。转义字符按 Ren'Py 字符串语义跳过。
        """
        pieces: list[str] = []
        depth = 0
        quote = ""
        escaped = False
        for char in line:
            if escaped:
                pieces.append(char)
                escaped = False
                continue
            if char == "\\":
                pieces.append(char)
                escaped = True
                continue
            if quote:
                pieces.append(char)
                if char == quote:
                    quote = ""
                continue
            if char in ("'", '"'):
                quote = char
                pieces.append(char)
                continue
            if char == "#":
                break
            if char in "([{":
                depth += 1
            elif char in ")]}":
                depth -= 1
            pieces.append(char)
        return "".join(pieces).rstrip(), depth

    def _looks_like_label_statement_tail(self, remainder: str) -> bool:
        """判断 ``label`` 后面剩下的内容是否像真正的 label 语句。

        ``label foo`` / ``label foo(a)`` / 空（裸 ``label``）视为真语句；
        ``label "名字" xalign 0.5``、``label char_name text_bold True`` 这类
        带属性的写法是 screen displayable，不是 label 语句。
        """
        tail = str(remainder or "").strip()
        if not tail:
            return True
        return self.RE_LABEL_STATEMENT_TAIL.match(tail) is not None

    def _has_unescaped_quote(self, text: str, quote_char: str) -> bool:
        return bool(self._unescaped_quote_offsets(text, quote_char))

    def _unescaped_quote_offsets(self, text: str, quote_char: str) -> list[int]:
        offsets: list[int] = []
        escaped = False
        for offset, ch in enumerate(text):
            if escaped:
                escaped = False
                continue
            if ch == "\\":
                escaped = True
                continue
            if ch == quote_char:
                offsets.append(offset)
        return offsets

    def _escape_unescaped_quotes(self, text: str, quote_char: str) -> tuple[str, bool]:
        result: list[str] = []
        escaped = False
        changed = False

        for ch in text:
            if escaped:
                result.append(ch)
                escaped = False
                continue

            if ch == "\\":
                result.append(ch)
                escaped = True
                continue

            if ch == quote_char:
                result.append("\\")
                result.append(ch)
                changed = True
                continue

            result.append(ch)

        return "".join(result), changed

    def _looks_like_renpy_string_statement(self, prefix: Optional[str]) -> bool:
        """仅对类似对话/翻译语句的行执行未转义引号修复。"""
        stripped = (prefix or "").strip()
        if stripped == "":
            return True
        return stripped in {"old", "new"} or stripped not in self.NON_DIALOGUE_PREFIXES

    def _can_repair_unescaped_quotes(self, body: str) -> bool:
        """只接受成对的正文内双引号，并拒绝明显的多个字符串参数。"""
        offsets = self._unescaped_quote_offsets(body, '"')
        if len(offsets) < 2 or len(offsets) % 2 != 0:
            return False

        for opening, closing in zip(offsets[::2], offsets[1::2]):
            between = body[opening + 1:closing].strip()
            if not between:
                return False
            if re.fullmatch(r'(?:[,;+*/%|&]|==?|!=|<=?|>=?|\+|-)+', between):
                return False
        return True

    def repair_unescaped_dialogue_quotes(self, line: str) -> tuple[str, bool]:
        """保守修复 Ren'Py 对话/old/new 行中成对的未转义双引号。"""
        content, line_ending = self._split_line_ending(line)
        if content.strip() == "" or content.lstrip().startswith("#") or '"""' in content:
            return line, False

        match = self.RE_RENPY_STRING_LINE.match(content)
        if not match:
            return line, False

        indent = match.group("indent") or ""
        prefix = match.group("prefix")
        body = match.group("body")
        suffix = match.group("suffix") or ""

        if not self._looks_like_renpy_string_statement(prefix):
            return line, False
        if not self._can_repair_unescaped_quotes(body):
            return line, False

        escaped_body, changed = self._escape_unescaped_quotes(body, '"')
        if not changed:
            return line, False

        statement_prefix = f"{prefix}{match.group('separator')}" if prefix else ""
        repaired = f'{indent}{statement_prefix}"{escaped_body}"{suffix}{line_ending}'
        return repaired, True

    def repair_curly_string_delimiters(self, line: str) -> tuple[str, bool]:
        """仅规范化明确用作字符串外层定界符的中文弯引号。"""
        content, line_ending = self._split_line_ending(line)
        if content.strip() == "" or content.lstrip().startswith("#"):
            return line, False

        for pattern, target_quote in (
            (self.RE_CURLY_DOUBLE_STRING_LINE, '"'),
            (self.RE_CURLY_SINGLE_STRING_LINE, "'"),
        ):
            match = pattern.match(content)
            if not match or not self._looks_like_renpy_string_statement(match.group("prefix")):
                continue

            body = match.group("body")
            # 变更外层定界符后，正文中的同类直引号会改变解析边界；无法
            # 无歧义判断其意图时保持原样。
            if self._has_unescaped_quote(body, target_quote):
                return line, False

            indent = match.group("indent") or ""
            prefix = match.group("prefix")
            statement_prefix = f"{prefix}{match.group('separator')}" if prefix else ""
            suffix = match.group("suffix") or ""
            repaired = (
                f"{indent}{statement_prefix}{target_quote}{body}{target_quote}"
                f"{suffix}{line_ending}"
            )
            return repaired, True

        return line, False

    def _detect_quote_issue(self, line: str) -> Optional[str]:
        """返回可高置信识别的引号问题；不对整行单双引号做奇偶计数。"""
        content, _ = self._split_line_ending(line)
        if content.strip() == "" or content.lstrip().startswith("#"):
            return None
        if '"""' in content or "'''" in content:
            return None

        for pattern in (self.RE_CURLY_DOUBLE_STRING_LINE, self.RE_CURLY_SINGLE_STRING_LINE):
            match = pattern.match(content)
            if match and self._looks_like_renpy_string_statement(match.group("prefix")):
                return "字符串使用了中文弯引号作为外层定界符"

        match = self.RE_RENPY_STRING_LINE.match(content)
        if match and self._looks_like_renpy_string_statement(match.group("prefix")):
            if self._can_repair_unescaped_quotes(match.group("body")):
                return "Ren'Py 字符串正文存在成对的未转义双引号"
            return None

        candidate = re.match(
            r'^[ \t]*(?:(?P<prefix>old|new|[A-Za-z_]\w*)[ \t]+)?"',
            content,
        )
        if candidate and self._looks_like_renpy_string_statement(candidate.group("prefix")):
            if len(self._unescaped_quote_offsets(content, '"')) % 2 != 0:
                return "双引号不匹配"
        return None

    @staticmethod
    def _decode_renpy_literal(raw_inner: str) -> str:
        """按扫描规则解码少量可靠的 Ren'Py 字符串转义。"""
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
            elif escaped in {'"', "'", "\\"}:
                result.append(escaped)
            else:
                # 未知转义保持原样，扫描器不能擅自改变其语义。
                result.extend(("\\", escaped))
            index += 2

        return "".join(result)

    @staticmethod
    def _scan_string_literals(code: str) -> list[dict]:
        """扫描一行代码中的单双引号字面量，忽略字符串外的注释。"""
        if '"""' in code or "'''" in code:
            return []

        literals: list[dict] = []
        index = 0
        while index < len(code):
            char = code[index]
            if char == "#":
                break
            if char not in {'"', "'"}:
                index += 1
                continue

            quote = char
            start = index
            index += 1
            raw: list[str] = []
            while index < len(code):
                char = code[index]
                if char == "\\" and index + 1 < len(code):
                    raw.extend((char, code[index + 1]))
                    index += 2
                    continue
                if char == quote:
                    raw_inner = "".join(raw)
                    literals.append({
                        "start": start,
                        "end": index + 1,
                        "raw": raw_inner,
                        "value": ErrorRepairer._decode_renpy_literal(raw_inner),
                    })
                    index += 1
                    break
                raw.append(char)
                index += 1
            else:
                break

        return literals

    @staticmethod
    def _extract_placeholders(text: str) -> Counter:
        """提取方括号插值与花括号文本标签，并忽略转义的双括号。"""
        placeholders: Counter = Counter()
        index = 0

        while index < len(text):
            opening = text[index]
            if opening not in {"[", "{"}:
                index += 1
                continue

            closing = "]" if opening == "[" else "}"
            doubled_open = opening * 2
            doubled_close = closing * 2
            if text.startswith(doubled_open, index):
                escaped_end = text.find(doubled_close, index + 2)
                index = escaped_end + 2 if escaped_end >= 0 else index + 2
                continue

            end = text.find(closing, index + 1)
            if end < 0:
                break

            body = text[index + 1:end]
            if body.strip() and opening not in body:
                placeholders[f"{opening}{body}{closing}"] += 1
            index = end + 1

        return placeholders

    @staticmethod
    def _classify_placeholder_diff(
        source: Counter,
        target: Counter,
    ) -> tuple[Counter, Counter, list[dict]]:
        """把 Counter 差异拆成缺失、额外和同类括号内的疑似改写。"""
        missing = source - target
        extra = target - source
        rewrite_counts: Counter = Counter()

        for opening in ("[", "{"):
            missing_tokens = sorted(
                token
                for token, count in missing.items()
                for _ in range(count)
                if token.startswith(opening)
            )
            extra_tokens = sorted(
                token
                for token, count in extra.items()
                for _ in range(count)
                if token.startswith(opening)
            )
            for source_token, target_token in zip(missing_tokens, extra_tokens):
                missing[source_token] -= 1
                extra[target_token] -= 1
                rewrite_counts[(source_token, target_token)] += 1

        missing += Counter()
        extra += Counter()
        rewrites = [
            {"source": source_token, "target": target_token, "count": count}
            for (source_token, target_token), count in sorted(rewrite_counts.items())
        ]
        return missing, extra, rewrites

    @staticmethod
    def _counter_details(counter: Counter) -> Dict[str, int]:
        return {token: counter[token] for token in sorted(counter)}

    def _iter_translation_pairs(
        self,
        lines: List[str],
        document: Optional[TlDocument] = None,
        *,
        checkpoint: Optional[Callable[[], None]] = None,
    ) -> Iterator[dict]:
        """返回 tl 文档中可可靠配对的模板/译文语句。"""
        if document is None:
            content_lines = [self._split_line_ending(line)[0] for line in lines]
            document = parse_tl_document(content_lines, checkpoint=checkpoint)

        for block in document.blocks:
            if checkpoint is not None:
                checkpoint()
            if block.kind == TlBlockKind.STRINGS:
                mapping = pair_old_new_lines(block, checkpoint=checkpoint)
            elif block.kind == TlBlockKind.LABEL:
                mapping = match_tpl_to_target(block, checkpoint=checkpoint, max_alignment_cells=4_000_000)
            else:
                continue

            statements = {}
            for index, statement in enumerate(block.statements):
                if checkpoint is not None and index % 256 == 0:
                    checkpoint()
                statements[statement.line_no] = statement
            for index, (source_line, target_line) in enumerate(mapping.items()):
                if checkpoint is not None and index % 256 == 0:
                    checkpoint()
                source = statements.get(source_line)
                target = statements.get(target_line)
                if source is None or target is None:
                    continue

                source_literals = self._scan_string_literals(source.code)
                target_literals = self._scan_string_literals(target.code)
                if not source_literals:
                    continue

                yield {
                    "language": block.lang,
                    "is_old_new": block.kind == TlBlockKind.STRINGS,
                    "source": source,
                    "target": target,
                    "source_values": [
                        literal["value"]
                        for literal in source_literals
                    ],
                    "target_values": [
                        literal["value"]
                        for literal in target_literals
                    ],
                }

    def _duplicate_old_new_error(
        self,
        pair: dict,
        first_path: str,
        first_line: int,
    ) -> Dict:
        source = pair["source"]
        original = pair["source_values"]
        return {
            "line": source.line_no,
            "type": "duplicate_old_new",
            "message": "检测到重复 old/new 条目",
            "content": source.raw_line.strip(),
            "original": original[0] if len(original) == 1 else original,
            "first_file": first_path,
            "first_line": first_line,
        }

    def _scan_extra_empty_strings(
        self,
        lines: List[str],
        document: Optional[TlDocument] = None,
        *,
        checkpoint: Optional[Callable[[], None]] = None,
    ) -> List[Dict]:
        """报告简单翻译语句中与其他字面量相邻的多余空字符串。"""
        if document is None:
            content_lines = [self._split_line_ending(line)[0] for line in lines]
            document = parse_tl_document(content_lines, checkpoint=checkpoint)

        errors: list[Dict] = []

        for block in document.blocks:
            if block.kind == TlBlockKind.PYTHON:
                continue
            for index, statement in enumerate(block.statements):
                if checkpoint is not None and index % 256 == 0:
                    checkpoint()
                if statement.stmt_kind != TlStmtKind.TARGET:
                    continue

                literals = self._scan_string_literals(statement.code)
                if len(literals) < 2:
                    continue

                prefix = statement.code[:literals[0]["start"]].strip()
                if prefix and (
                    re.fullmatch(r"[A-Za-z_]\w*", prefix) is None
                    or not self._looks_like_renpy_string_statement(prefix)
                ):
                    continue

                components: list[list[dict]] = []
                component = [literals[0]]
                for previous, current in zip(literals, literals[1:]):
                    between = statement.code[previous["end"]:current["start"]]
                    if between.strip() == "":
                        component.append(current)
                    else:
                        components.append(component)
                        component = [current]
                components.append(component)

                extra_count = 0
                for component in components:
                    if len(component) < 2:
                        continue
                    empty_count = sum(literal["value"] == "" for literal in component)
                    if empty_count == 0:
                        continue
                    has_non_empty = empty_count < len(component)
                    extra_count += empty_count if has_non_empty else empty_count - 1
                if extra_count <= 0:
                    continue

                errors.append({
                    "line": statement.line_no,
                    "type": "extra_empty_string",
                    "message": f"翻译语句包含 {extra_count} 个多余空字符串",
                    "content": statement.raw_line.strip(),
                    "count": extra_count,
                })

        return errors

    def _scan_empty_translate_blocks(self, lines: List[str], *, checkpoint: Optional[Callable[[], None]] = None) -> List[Dict]:
        """报告没有任何可执行语句的 ``translate ... strings`` 块。"""
        errors: list[Dict] = []
        header_re = re.compile(
            r"^(?P<indent>[ \t]*)translate\s+(?P<language>[A-Za-z0-9_]+)"
            r"\s+strings\s*:\s*$"
        )
        index = 0
        while index < len(lines):
            if checkpoint is not None and index % 256 == 0:
                checkpoint()
            content, _ = self._split_line_ending(lines[index])
            match = header_re.match(content)
            if not match:
                index += 1
                continue

            base_indent = len(match.group("indent"))
            end = index + 1
            has_content = False
            while end < len(lines):
                if checkpoint is not None and end % 256 == 0:
                    checkpoint()
                candidate, _ = self._split_line_ending(lines[end])
                if not candidate.strip():
                    end += 1
                    continue
                candidate_indent = len(candidate) - len(candidate.lstrip(" \t"))
                if candidate_indent > base_indent:
                    has_content = has_content or not candidate.lstrip().startswith("#")
                    end += 1
                    continue
                break

            if not has_content:
                errors.append({
                    "line": index + 1,
                    "type": "empty_block",
                    "message": "translate strings 语句缺少非空内容块",
                    "content": content.strip(),
                    "language": match.group("language"),
                })
            index = end

        return errors

    def _remove_empty_translate_blocks(self, lines: List[str], *, checkpoint=None) -> tuple[List[str], int]:
        """删除空的 ``translate <lang> strings:`` 块并返回删除数量。"""
        header_re = re.compile(
            r"^(?P<indent>[ \t]*)translate\s+(?P<language>[A-Za-z0-9_]+)"
            r"\s+strings\s*:\s*$"
        )
        output: list[str] = []
        removed = 0
        index = 0
        while index < len(lines):
            if checkpoint is not None and index % 256 == 0:
                checkpoint()
            content, _ = self._split_line_ending(lines[index])
            match = header_re.match(content)
            if not match:
                output.append(lines[index])
                index += 1
                continue

            base_indent = len(match.group("indent"))
            end = index + 1
            has_content = False
            while end < len(lines):
                if checkpoint is not None and end % 256 == 0:
                    checkpoint()
                candidate, _ = self._split_line_ending(lines[end])
                if not candidate.strip():
                    end += 1
                    continue
                candidate_indent = len(candidate) - len(candidate.lstrip(" \t"))
                if candidate_indent > base_indent:
                    has_content = has_content or not candidate.lstrip().startswith("#")
                    end += 1
                    continue
                break

            if has_content:
                output.extend(lines[index:end])
            else:
                # 只去掉空块头。注释可能保存着重复项的另一份译文，必须留在脚本里。
                body = lines[index + 1:end]
                if any(line.lstrip().startswith("#") for line in body):
                    output.extend(body)
                removed += 1
            index = end

        return output, removed

    def _scan_translation_issues(
        self,
        lines: List[str],
        file_path: str,
        document: Optional[TlDocument] = None,
        *,
        seen_old: Optional[dict] = None,
        checkpoint: Optional[Callable[[], None]] = None,
    ) -> List[Dict]:
        """纯读取扫描占位符、换行、空字符串和同文件重复条目。"""
        if document is None:
            content_lines = [self._split_line_ending(line)[0] for line in lines]
            document = parse_tl_document(content_lines, checkpoint=checkpoint)

        errors: list[Dict] = []
        if seen_old is None:
            seen_old = {}

        for pair in self._iter_translation_pairs(lines, document, checkpoint=checkpoint):
            source = pair["source"]
            target = pair["target"]
            source_values = pair["source_values"]
            target_values = pair["target_values"]

            if pair["is_old_new"]:
                duplicate_key = (pair["language"], tuple(source_values))
                first = seen_old.get(duplicate_key)
                if first is None:
                    seen_old[duplicate_key] = (file_path, source.line_no)
                else:
                    errors.append(self._duplicate_old_new_error(pair, first[0], first[1]))

            source_placeholders: Counter = Counter()
            target_placeholders: Counter = Counter()
            source_linebreaks = 0
            target_linebreaks = 0
            compared = False
            for source_value, target_value in zip(source_values, target_values):
                # 空 new 是合法的未翻译占位，不属于翻译损坏。
                if target_value == "":
                    continue
                compared = True
                source_placeholders.update(self._extract_placeholders(source_value))
                target_placeholders.update(self._extract_placeholders(target_value))
                source_linebreaks += source_value.count("\n")
                target_linebreaks += target_value.count("\n")

            if not compared:
                continue

            missing, extra, rewrites = self._classify_placeholder_diff(
                source_placeholders,
                target_placeholders,
            )
            common = {
                "line": target.line_no,
                "content": target.raw_line.strip(),
                "source_line": source.line_no,
                "source_content": source.raw_line.strip(),
            }
            if rewrites:
                errors.append({
                    **common,
                    "type": "placeholder_rewritten",
                    "message": "译文中的占位符疑似被改写",
                    "rewrites": rewrites,
                })
            if missing:
                errors.append({
                    **common,
                    "type": "placeholder_missing",
                    "message": "译文缺少原文占位符",
                    "placeholders": self._counter_details(missing),
                })
            if extra:
                errors.append({
                    **common,
                    "type": "placeholder_extra",
                    "message": "译文包含原文没有的占位符",
                    "placeholders": self._counter_details(extra),
                })
            if source_linebreaks != target_linebreaks:
                errors.append({
                    **common,
                    "type": "linebreak_mismatch",
                    "message": "译文与原文的换行数量不一致",
                    "source_count": source_linebreaks,
                    "target_count": target_linebreaks,
                })

        errors.extend(self._scan_extra_empty_strings(lines, document, checkpoint=checkpoint))
        return errors

    def _get_indent_width(self, line: str) -> int:
        expanded = line.expandtabs(4)
        return len(expanded) - len(expanded.lstrip(" "))

    def _is_blank_or_comment(self, line: str) -> bool:
        stripped = line.strip()
        return stripped == "" or stripped.startswith("#")

    def _find_previous_non_empty_index(self, lines: List[str], idx: int, checkpoint=None) -> Optional[int]:
        for current in range(idx - 1, -1, -1):
            if checkpoint is not None and current % 256 == 0:
                checkpoint()
            if not self._is_blank_or_comment(lines[current]):
                return current
        return None

    def _find_previous_block_indent_less_than(self, lines: List[str], idx: int, indent_limit: int, checkpoint=None) -> Optional[int]:
        for current in range(idx - 1, -1, -1):
            if checkpoint is not None and current % 256 == 0:
                checkpoint()
            line = lines[current]
            if self._is_blank_or_comment(line):
                continue
            content, _ = self._split_line_ending(line)
            stripped = content.lstrip(" \t")
            indent = self._get_indent_width(content)
            if indent < indent_limit and stripped.endswith(":"):
                return indent
        return None

    def _looks_like_screen_block_line(self, stripped: str) -> bool:
        token = stripped.split(maxsplit = 1)[0] if stripped else ""
        return token in self.SCREEN_BLOCK_PREFIXES or stripped.startswith(("if ", "elif ", "else:", "for ", "while "))

    def repair_indentation_level(self, lines: List[str], idx: int, *, checkpoint=None) -> tuple[str, bool]:
        """尝试修复明显错位的块级缩进。"""
        if idx < 0 or idx >= len(lines):
            return lines[idx], False

        original_line = lines[idx]
        content, line_ending = self._split_line_ending(original_line)
        if self._is_blank_or_comment(content):
            return original_line, False

        stripped = content.lstrip(" \t")
        current_indent = self._get_indent_width(content)
        prev_idx = self._find_previous_non_empty_index(lines, idx, checkpoint)
        if prev_idx is None:
            return original_line, False

        prev_content, _ = self._split_line_ending(lines[prev_idx])
        prev_stripped = prev_content.lstrip(" \t")
        prev_indent = self._get_indent_width(prev_content)

        # 情况 1：上一行是块起始，当前行应作为其子块，统一为 +4 空格。
        if prev_stripped.endswith(":") and not re.match(r"^(elif|else|except|finally)\b", stripped):
            expected_indent = prev_indent + 4
            if current_indent != expected_indent:
                return (" " * expected_indent) + stripped + line_ending, True

        # 情况 2：当前行自身是块起始，但前一段刚从深层子块退出。
        # 这时按最近父块缩进回退一层，适合修复 screen 里 displayable / textbutton 错位。
        if stripped.endswith(":") and self._looks_like_screen_block_line(stripped) and prev_indent >= current_indent + 8:
            parent_indent = self._find_previous_block_indent_less_than(lines, idx, current_indent, checkpoint)
            if parent_indent is not None and parent_indent != current_indent:
                return (" " * parent_indent) + stripped + line_ending, True

        return original_line, False

    def check_file(
        self,
        file_path: str,
        check_syntax: bool = True,
        check_indent: bool = True,
        check_indent_level: bool = True,
        check_quotes: bool = True,
        check_dialogue_quotes: bool = True,
        encoding: str = "utf-8",
        check_translation_issues: bool = True,
        *,
        document: Optional[TlDocument] = None,
    ) -> List[Dict[str, any]]:
        """
        检查单个文件

        Args:
            file_path: 文件路径
            check_syntax: 是否检查语法
            check_indent: 是否检查缩进
            check_quotes: 是否检查引号匹配
            encoding: 文件编码
            check_translation_issues: 是否扫描译文占位符、换行、空字符串和重复项
            document: 调用方已解析好的 TL AST，传入后不再重复解析

        Returns:
            错误列表 [{"line": 行号, "type": 错误类型, "message": 错误信息}, ...]
        """
        try:
            with open(file_path, "r", encoding=encoding, errors="ignore") as f:
                lines = f.readlines()
        except Exception as e:
            self.logger.error(f"检查文件失败 {file_path}: {e}")
            return []

        if document is None:
            document = parse_tl_document(
                [self._split_line_ending(line)[0] for line in lines]
            )

        return self._check_lines(
            lines,
            file_path,
            document,
            check_syntax=check_syntax,
            check_indent=check_indent,
            check_indent_level=check_indent_level,
            check_quotes=check_quotes,
            check_dialogue_quotes=check_dialogue_quotes,
            check_translation_issues=check_translation_issues,
        )

    def _check_lines(
        self,
        lines: List[str],
        file_path: str,
        document: TlDocument,
        *,
        check_syntax: bool,
        check_indent: bool,
        check_indent_level: bool,
        check_quotes: bool,
        check_dialogue_quotes: bool,
        check_translation_issues: bool,
        seen_old: Optional[dict] = None,
        checkpoint: Optional[Callable[[], None]] = None,
        on_line: Optional[Callable[[int], None]] = None,
    ) -> List[Dict[str, any]]:
        """对已读入的行执行检查；``document`` 由调用方复用，不再重复解析。"""
        errors = []
        # 只在含 translate 块的译文文件里检查缩进层级：源脚本的 screen 与
        # Python 缩进写法与 tl 文件不同，在源文件上几乎全是误报。
        has_translate_blocks = bool(document.blocks) if document is not None else False
        # 跨行括号条件的挂起深度：>0 表示正在等待条件表达式闭合。
        pending_bracket_depth = 0
        # ``screen`` 块内 ``label`` 是 displayable，不是 label 语句；记录块缩进，
        # 遇到缩进不大于它的有效行即视为离开该 screen 块。
        screen_indent: Optional[int] = None
        # python 块内缩进属于 Python 语法，不参与块级缩进层级判断。
        python_indent: Optional[int] = None
        inside_python = False

        try:
            for line_num, line in enumerate(lines, 1):
                if line_num % 256 == 1:
                    if on_line is not None:
                        on_line(line_num)
                    if checkpoint is not None:
                        checkpoint()
                # 语法检查
                if check_syntax:
                    code, bracket_depth = self._scan_code_structure(line)
                    stripped_code = code.strip()
                    stripped_line = line.strip()
                    line_indent: Optional[int] = None
                    if stripped_code:
                        line_indent = self._get_indent_width(code)
                        if screen_indent is not None and line_indent <= screen_indent:
                            screen_indent = None
                        if python_indent is not None and line_indent <= python_indent:
                            python_indent = None
                        if self.RE_SCREEN_HEADER.match(stripped_code) and \
                           stripped_code.endswith(":"):
                            screen_indent = line_indent
                        elif self.RE_PYTHON_HEADER.match(stripped_code) and \
                                stripped_code.endswith(":"):
                            python_indent = line_indent
                        inside_python = (
                            python_indent is not None
                            and line_indent > python_indent
                        )
                    inside_screen = (
                        screen_indent is not None
                        and line_indent is not None
                        and line_indent > screen_indent
                    )
                    if pending_bracket_depth > 0:
                        # 上一条控制流语句的条件还没闭合，本行是续行：
                        # 只在括号回到 0 的闭合行判断是否有冒号。
                        pending_bracket_depth += bracket_depth
                        if pending_bracket_depth <= 0:
                            pending_bracket_depth = 0
                            if not stripped_code.endswith(":") and \
                               not stripped_code.endswith("\\"):
                                errors.append({
                                    "line": line_num,
                                    "type": "syntax",
                                    "message": "控制流语句缺少冒号",
                                    "content": stripped_line
                                })
                    else:
                        # screen 里的 ``label "名字" xalign 0.5`` 是 displayable，
                        # 不是 label 语句；只有屏幕外、且尾部像真语句时才按缺冒号处理。
                        if re.match(r"^label(?:\s|$)", stripped_code) and \
                           not stripped_code.endswith(":"):
                            remainder = stripped_code[len("label"):]
                            if not inside_screen and self._looks_like_label_statement_tail(remainder):
                                errors.append({
                                    "line": line_num,
                                    "type": "syntax",
                                    "message": "label 语句缺少冒号",
                                    "content": stripped_line
                                })

                        # 检查翻译块头和控制流语句后是否有冒号。
                        if re.match(r"^translate\s+\S+", stripped_code) and \
                           not stripped_code.endswith(":"):
                            errors.append({
                                "line": line_num,
                                "type": "syntax",
                                "message": "translate 语句缺少冒号",
                                "content": stripped_code or stripped_line,
                            })

                        if re.match(r'^\s*(if|elif|else|menu|while|for)(?:\s|$)', line) and \
                           not stripped_code.endswith(":"):
                            if bracket_depth > 0:
                                # 条件表达式跨行：等括号闭合后由闭合行判断。
                                pending_bracket_depth = bracket_depth
                            elif not stripped_code.endswith("\\"):
                                errors.append({
                                    "line": line_num,
                                    "type": "syntax",
                                    "message": "控制流语句缺少冒号",
                                    "content": stripped_line
                                })

                # 缩进检查
                if check_indent:
                    # 检查是否使用 Tab
                    leading = line[: len(line) - len(line.lstrip(" \t"))]
                    if "\t" in leading:
                        errors.append({
                            "line": line_num,
                            "type": "indent",
                            "message": "使用了 Tab 而非空格缩进",
                            "content": line.strip()
                        })

                if check_indent_level and has_translate_blocks and not inside_python:
                    _, changed = self.repair_indentation_level(lines, line_num - 1, checkpoint=checkpoint)
                    if changed:
                        errors.append({
                            "line": line_num,
                            "type": "indentation_level",
                            "message": "疑似块级缩进层级错误",
                            "content": line.strip()
                        })

                quote_issue_found = False
                if check_quotes:
                    quote_message = self._detect_quote_issue(line)
                    if quote_message:
                        errors.append({
                            "line": line_num,
                            "type": "quotes",
                            "message": quote_message,
                            "content": line.strip()
                        })
                        quote_issue_found = True

                if check_dialogue_quotes and not quote_issue_found:
                    _, changed = self.repair_unescaped_dialogue_quotes(line)
                    if changed:
                        errors.append({
                            "line": line_num,
                            "type": "unescaped_dialogue_quotes",
                            "message": "Ren'Py 对话行存在未转义引号",
                            "content": line.strip()
                        })

            if check_syntax:
                errors.extend(self._scan_empty_translate_blocks(lines, checkpoint=checkpoint))

            if check_translation_issues:
                errors.extend(self._scan_translation_issues(
                    lines, file_path, document, seen_old=seen_old, checkpoint=checkpoint,
                ))

        except Exception as e:
            self.logger.error(f"检查文件失败 {file_path}: {e}")
            raise

        return errors

    def check_folder(
        self,
        folder_path: str,
        check_syntax: bool = True,
        check_indent: bool = True,
        check_indent_level: bool = True,
        check_quotes: bool = True,
        check_dialogue_quotes: bool = True,
        encoding: str = "utf-8",
        check_translation_issues: bool = True,
        *,
        max_files: Optional[int] = None,
        max_bytes: Optional[int] = None,
        deadline: Optional[float] = None,
        should_cancel: Optional[Callable[[], bool]] = None,
        on_progress: Optional[Callable[[dict], None]] = None,
    ) -> Dict[str, List[Dict]]:
        """
        批量检查文件夹

        Args:
            folder_path: 文件夹路径
            check_syntax: 是否检查语法
            check_indent: 是否检查缩进
            check_quotes: 是否检查引号匹配
            encoding: 文件编码
            check_translation_issues: 是否扫描译文占位符、换行、空字符串和重复项
            max_files: 最多扫描多少个 .rpy 文件，超出即停止
            max_bytes: 最多累计读取多少字节，超出即停止
            deadline: ``time.monotonic`` 绝对值，到点即停止
            should_cancel: 收集文件及文件内处理期间定期调用，返回 True 即停止
            on_progress: 接收阶段、文件和已完成数量；回调在工作线程中至多每 0.2 秒一次

        Returns:
            {文件路径: 错误列表}
        """
        return self.scan_folder(
            folder_path,
            check_syntax=check_syntax,
            check_indent=check_indent,
            check_indent_level=check_indent_level,
            check_quotes=check_quotes,
            check_dialogue_quotes=check_dialogue_quotes,
            encoding=encoding,
            check_translation_issues=check_translation_issues,
            max_files=max_files,
            max_bytes=max_bytes,
            deadline=deadline,
            should_cancel=should_cancel,
            on_progress=on_progress,
        ).errors

    def scan_folder(
        self,
        folder_path: str,
        check_syntax: bool = True,
        check_indent: bool = True,
        check_indent_level: bool = True,
        check_quotes: bool = True,
        check_dialogue_quotes: bool = True,
        encoding: str = "utf-8",
        check_translation_issues: bool = True,
        *,
        detect_environment: bool = True,
        max_files: Optional[int] = None,
        max_bytes: Optional[int] = None,
        deadline: Optional[float] = None,
        should_cancel: Optional[Callable[[], bool]] = None,
        on_progress: Optional[Callable[[dict], None]] = None,
    ) -> FolderScanResult:
        """同 :meth:`check_folder`，另外返回本次扫描覆盖了多少文件与字节。"""
        all_errors: Dict[str, List[Dict]] = {}
        rpy_files: list[Path] = []
        total_files_known = False
        scanned_bytes = 0
        scanned_files = 0
        budget_exhausted = False
        seen_old: dict[tuple, tuple[str, int]] = {}
        # Throttle in the worker, before enqueueing anything on the API event loop.
        started = time.monotonic()
        last_push = float("-inf")
        state = {"phase": "enumerate", "file": "", "fraction": 0.0, "line": 0}

        def checkpoint() -> None:
            nonlocal last_push
            if should_cancel is not None and should_cancel():
                raise _ScanStopped()
            now = time.monotonic()
            if deadline is not None and now >= deadline:
                raise _ScanStopped()
            if on_progress is not None and now - last_push >= 0.2:
                last_push = now
                on_progress({
                    **state, "scanned_files": scanned_files, "total_files": len(rpy_files),
                    "total_files_known": total_files_known,
                    "elapsed": now - started,
                })

        def phase(name: str, fraction: float) -> None:
            state.update(phase=name, fraction=fraction, line=0)
            checkpoint()

        try:
            checkpoint()
            rpy_files = self.get_rpy_files(folder_path, checkpoint=checkpoint)
            total_files_known = True
            for file_path in rpy_files:
                checkpoint()
                if max_files is not None and scanned_files >= max_files:
                    raise _ScanStopped()
                state["file"] = str(file_path)
                phase("read", 0.0)
                size = file_path.stat().st_size
                if max_bytes is not None and scanned_bytes + size > max_bytes:
                    raise _ScanStopped()
                scanned_bytes += size

                with open(file_path, "r", encoding=encoding, errors="ignore") as source_file:
                    lines = []
                    for index, line in enumerate(source_file):
                        if index % 256 == 0:
                            state["line"] = index + 1
                            checkpoint()
                        lines.append(line.rstrip("\r\n"))
                phase("parse", 0.1)
                document = parse_tl_document(lines, checkpoint=checkpoint)
                phase("check", 0.4)

                def on_line(line_no: int) -> None:
                    state.update(line=line_no, fraction=0.4 + 0.3 * line_no / max(len(lines), 1))

                errors = self._check_lines(
                    lines, str(file_path), document,
                    check_syntax=check_syntax,
                    check_indent=check_indent,
                    check_indent_level=check_indent_level,
                    check_quotes=check_quotes,
                    check_dialogue_quotes=check_dialogue_quotes,
                    check_translation_issues=False,
                    checkpoint=checkpoint, on_line=on_line,
                )
                if check_translation_issues:
                    phase("translation", 0.75)
                    # One pairing pass handles both local and cross-file duplicates.
                    errors.extend(self._scan_translation_issues(
                        lines, str(file_path), document, seen_old=seen_old, checkpoint=checkpoint,
                    ))
                if errors:
                    all_errors[str(file_path)] = errors
                # Release the previous file's AST before loading the next large file.
                del document, lines, errors
                scanned_files += 1
                phase("file_done", 0.0)
        except _ScanStopped:
            budget_exhausted = True
        except Exception as exc:
            raise RuntimeError(f"扫描未完成 {state['file'] or folder_path}: {exc}") from exc

        if budget_exhausted:
            total_label = str(len(rpy_files)) if total_files_known else "未知（文件枚举未完成）"
            self.logger.warning(
                f"检查中断: 已取消或达到预算上限，只扫描了 {scanned_files}/{total_label} 个文件"
            )
        else:
            self.logger.info(f"检查完成: 发现 {sum(map(len, all_errors.values()))} 个错误")

        # 分类统计只反映「已扫描完」的结果；中断的扫描不能声称目录无问题。
        issues_by_type: Dict[str, int] = {}
        fixable_count = 0
        manual_count = 0
        environment_issues: List[Dict] = []
        if not budget_exhausted:
            type_counter: Counter = Counter()
            for file_errors in all_errors.values():
                for error in file_errors:
                    type_name = str(error.get("type") or "").strip()
                    if type_name:
                        type_counter[type_name] += 1
            issues_by_type = {
                type_name: count for type_name, count in sorted(type_counter.items())
            }
            for type_name, count in issues_by_type.items():
                category = classify_issue_type(type_name)
                if category == "auto":
                    fixable_count += count
                elif category == "manual":
                    manual_count += count
            if detect_environment:
                try:
                    environment_issues = self.detect_environment_issues(folder_path)
                except Exception as exc:
                    # 环境检查是附加信息，不能因为探测失败让整次扫描失败。
                    self.logger.warning(f"环境问题检测失败 {folder_path}: {exc}")
                    environment_issues = []

        return FolderScanResult(
            errors=all_errors,
            scanned_files=scanned_files,
            total_files=len(rpy_files),
            scanned_bytes=scanned_bytes,
            budget_exhausted=budget_exhausted,
            total_files_known=total_files_known,
            issues_by_type=issues_by_type,
            environment_issues=environment_issues,
            fixable_count=fixable_count,
            manual_count=manual_count,
        )

    def _rewrite_with_backup(
        self,
        file_path: str | Path,
        original_lines: List[str],
        new_lines: List[str],
        encoding: str,
        *,
        checkpoint: Optional[Callable[[], None]] = None,
        before_replace: Optional[Callable[[], None]] = None,
    ) -> None:
        """与 :meth:`auto_fix_file` 相同的安全写回：原文校验 + .bak + 原子替换。

        ``original_lines`` 是修复前读到的内容；写之前重新读一遍字节做比对，
        发现文件已被其他程序改动就直接放弃，避免覆盖别人的修改。
        """
        if checkpoint is not None:
            checkpoint()
        target = Path(file_path)
        original = target.read_bytes()
        if original.decode(encoding) != "".join(original_lines):
            raise RuntimeError("文件已被其他程序修改，已停止修复")
        backup = target.with_name(f"{target.name}.{secrets.token_hex(8)}.bak")
        with open(backup, "xb") as writer:
            writer.write(original)
            writer.flush()
            os.fsync(writer.fileno())
        if checkpoint is not None:
            checkpoint()
        if before_replace is not None:
            before_replace()
        atomic_write_text(target, "".join(new_lines), encoding=encoding, newline="")

    def _comment_out_line(self, line: str) -> tuple[str, bool]:
        """保留缩进与换行，把整行注释掉；空行或已注释行原样返回。"""
        content, line_ending = self._split_line_ending(line)
        stripped = content.lstrip(" \t")
        if not stripped or stripped.startswith("#"):
            return line, False
        indent = content[: len(content) - len(stripped)]
        return f"{indent}# {stripped}{line_ending}", True

    def _comment_out_duplicate_pairs(
        self,
        lines: List[str],
        positions: List[Tuple[int, int]],
    ) -> int:
        """就地把重复的 old/new 两行注释掉，返回实际处理的条目数。"""
        fixed_pairs = 0
        for old_index, new_index in positions:
            changed = False
            for index in (old_index, new_index):
                if not 0 <= index < len(lines):
                    continue
                commented, line_changed = self._comment_out_line(lines[index])
                if line_changed:
                    lines[index] = commented
                    changed = True
            if changed:
                fixed_pairs += 1
        return fixed_pairs

    def _collect_duplicate_old_new_positions(
        self,
        lines: List[str],
        seen_old: Dict[tuple, tuple[str, int]],
        *,
        file_path: str = "",
        checkpoint: Optional[Callable[[], None]] = None,
    ) -> List[Tuple[int, int]]:
        """返回需要注释掉的（old 行, new 行）0 基行号。

        重复口径与 :meth:`_scan_translation_issues` 一致：``(language, tuple(old 原文))``
        在 ``translate <lang> strings:`` 块内出现多次。``seen_old`` 里已登记的 key
        全部视为重复；其余 key 在本文件内优先保留有效译文（见
        :meth:`_choose_duplicate_keepers`），并登记进 ``seen_old``。
        """
        entries = self._collect_old_new_entries(lines, checkpoint=checkpoint)
        path_text = str(file_path)
        keepers = self._choose_duplicate_keepers(
            [(path_text, [entry for entry in entries if entry[0] not in seen_old])]
        )
        for key, keeper in keepers.items():
            seen_old.setdefault(key, keeper)
        return self._duplicate_loser_positions(path_text, entries, seen_old)

    @staticmethod
    def _is_informative_translation(pair: dict) -> bool:
        """``new ""`` 或与 old 完全相同的 new 只是未翻译占位，不算有效译文。"""
        targets = pair["target_values"]
        return any(value != "" for value in targets) and targets != pair["source_values"]

    def _collect_old_new_entries(
        self,
        lines: List[str],
        *,
        checkpoint: Optional[Callable[[], None]] = None,
    ) -> List[Tuple[tuple, int, int, bool]]:
        """返回 strings 块内每条 old/new：(key, old 行号, new 行号, 是否有效译文)，行号 1 基。"""
        content_lines = [self._split_line_ending(line)[0] for line in lines]
        document = parse_tl_document(content_lines, checkpoint=checkpoint)
        entries: List[Tuple[tuple, int, int, bool]] = []
        for pair in self._iter_translation_pairs(lines, document, checkpoint=checkpoint):
            if not pair["is_old_new"]:
                continue
            entries.append((
                (pair["language"], tuple(pair["source_values"])),
                pair["source"].line_no,
                pair["target"].line_no,
                self._is_informative_translation(pair),
            ))
        return entries

    @staticmethod
    def _choose_duplicate_keepers(
        entries_by_file: List[Tuple[str, List[Tuple[tuple, int, int, bool]]]],
    ) -> Dict[tuple, Tuple[str, int]]:
        """每个 key 保留按顺序第一条有效译文；全是占位时保留第一条。"""
        keepers: Dict[tuple, Tuple[str, int]] = {}
        informative: set = set()
        for file_path, entries in entries_by_file:
            for key, old_line, _new_line, useful in entries:
                if key not in keepers or (useful and key not in informative):
                    keepers[key] = (file_path, old_line)
                    if useful:
                        informative.add(key)
        return keepers

    @staticmethod
    def _duplicate_loser_positions(
        file_path: str,
        entries: List[Tuple[tuple, int, int, bool]],
        keepers: Dict[tuple, Tuple[str, int]],
    ) -> List[Tuple[int, int]]:
        return [
            (old_line - 1, new_line - 1)
            for key, old_line, new_line, _useful in entries
            if keepers.get(key) != (file_path, old_line)
        ]

    def auto_fix_file(
        self,
        file_path: str,
        fix_indent: bool = True,
        fix_indent_level: bool = False,
        fix_quotes: bool = False,
        fix_dialogue_quotes: bool = False,
        encoding: str = "utf-8",
        *,
        fix_empty_blocks: bool = True,
        fix_trailing_spaces: bool = False,
        fix_duplicates: bool = False,
        checkpoint: Optional[Callable[[], None]] = None,
    ) -> Tuple[bool, int]:
        """
        自动修复文件

        Args:
            file_path: 文件路径
            fix_indent: 是否修复缩进
            fix_quotes: 是否尝试修复引号 (危险操作)
            encoding: 文件编码
            fix_trailing_spaces: 是否删除行尾多余空格
            fix_duplicates: 是否注释掉本文件内重复的 old/new 条目

        Returns:
            (是否成功, 修复数量)
        """
        try:
            with open(file_path, "r", encoding=encoding, newline="") as f:
                lines = []
                for index, line in enumerate(f):
                    if checkpoint is not None and index % 256 == 0:
                        checkpoint()
                    lines.append(line)

            new_lines = []
            fix_count = 0
            temp_lines = list(lines) if fix_indent_level else None

            for idx, line in enumerate(lines):
                if checkpoint is not None and idx % 256 == 0:
                    checkpoint()
                new_line = line

                # 修复缩进: Tab 转空格
                leading = line[: len(line) - len(line.lstrip(" \t"))]
                if fix_indent and "\t" in leading:
                    new_line = leading.replace("\t", "    ") + line[len(leading):]
                    fix_count += 1

                if fix_dialogue_quotes:
                    repaired_line, changed = self.repair_unescaped_dialogue_quotes(new_line)
                    if changed:
                        new_line = repaired_line
                        fix_count += 1

                # 中文弯引号只有在明确充当整条字符串的外层定界符时才转换。
                # 字符串正文中的正常中文引号必须原样保留。
                if fix_quotes:
                    repaired_line, changed = self.repair_curly_string_delimiters(new_line)
                    if changed:
                        new_line = repaired_line
                        fix_count += 1

                if fix_indent_level:
                    if idx:
                        temp_lines[idx - 1] = lines[idx - 1]
                    temp_lines[idx] = new_line
                    repaired_line, changed = self.repair_indentation_level(temp_lines, idx, checkpoint=checkpoint)
                    if changed:
                        new_line = repaired_line
                        fix_count += 1

                # 行尾空白放在其它修复之后：引号修复会把 suffix 原样带回。
                if fix_trailing_spaces:
                    content, line_ending = self._split_line_ending(new_line)
                    trimmed = content.rstrip(" \t")
                    if trimmed != content:
                        new_line = f"{trimmed}{line_ending}"
                        fix_count += 1

                new_lines.append(new_line)

            if fix_duplicates:
                positions = self._collect_duplicate_old_new_positions(
                    new_lines, {}, file_path=str(file_path), checkpoint=checkpoint,
                )
                if positions:
                    fix_count += self._comment_out_duplicate_pairs(new_lines, positions)
                    # 整块条目都被注释后必须连块头一起删掉，否则 Ren'Py 会报空翻译块。
                    new_lines, removed_blocks = self._remove_empty_translate_blocks(
                        new_lines, checkpoint=checkpoint,
                    )
                    fix_count += removed_blocks

            if fix_empty_blocks:
                new_lines, removed_blocks = self._remove_empty_translate_blocks(new_lines, checkpoint=checkpoint)
                fix_count += removed_blocks

            # 写回文件
            if fix_count > 0:
                self._rewrite_with_backup(
                    file_path, lines, new_lines, encoding, checkpoint=checkpoint,
                )
                self.logger.info(f"修复完成: {file_path} ({fix_count} 处)")

            return True, fix_count

        except Exception as e:
            self.logger.error(f"修复失败 {file_path}: {e}")
            return False, 0

    def fix_duplicate_strings(
        self,
        folder: str | Path,
        *,
        checkpoint: Optional[Callable[[], None]] = None,
        before_write: Optional[Callable[[], None]] = None,
        on_file: Optional[Callable[[str, int], None]] = None,
    ) -> tuple[int, list[str]]:
        """跨文件注释掉重复的 ``translate <lang> strings`` 条目。

        每个 (language, old) 保留第一条有效译文（``new ""`` 与 new==old 视为占位），
        都是占位时保留第一条；其余 old/new 两行注释掉。

        Args:
            before_write: 每次写盘前调用（如项目归属校验），抛异常即停止后续写入。
            on_file: 每写完一个文件回调 ``(路径, 本文件条目数)``；中途取消或
                抛异常时调用方据此保留已写入的增量。

        Returns:
            (修复条目数, 实际改写的文件路径列表)
        """
        fixed_count = 0
        changed_files: list[str] = []
        try:
            files = self.get_rpy_files(folder, checkpoint=checkpoint)
        except OSError as exc:
            self.logger.error(f"枚举待去重文件失败 {folder}: {exc}")
            return 0, []

        def read_lines(file_path: Path) -> List[str]:
            with open(file_path, "r", encoding="utf-8", newline="") as f:
                return list(f)

        # 第一遍只读：看完所有文件才知道每个 key 该保留哪一条。
        scanned: list[tuple[Path, str, List[Tuple[tuple, int, int, bool]]]] = []
        for file_path in sorted(files, key=lambda path: path.as_posix().casefold()):
            if checkpoint is not None:
                checkpoint()
            try:
                lines = read_lines(file_path)
            except OSError as exc:
                self.logger.warning(f"跳过无法读取的文件 {file_path}: {exc}")
                continue
            try:
                entries = self._collect_old_new_entries(lines, checkpoint=checkpoint)
            except Exception as exc:
                self.logger.warning(f"解析 {file_path} 失败，已跳过去重: {exc}")
                continue
            if entries:
                digest = hashlib.sha256("".join(lines).encode("utf-8")).hexdigest()
                scanned.append((file_path, digest, entries))

        keepers = self._choose_duplicate_keepers(
            [(str(file_path), entries) for file_path, _digest, entries in scanned]
        )

        for file_path, digest, entries in scanned:
            positions = self._duplicate_loser_positions(str(file_path), entries, keepers)
            if not positions:
                continue
            if checkpoint is not None:
                checkpoint()
            try:
                lines = read_lines(file_path)
            except OSError as exc:
                self.logger.warning(f"跳过无法读取的文件 {file_path}: {exc}")
                continue
            if hashlib.sha256("".join(lines).encode("utf-8")).hexdigest() != digest:
                # 两遍之间文件被改过，行号已不可信。
                self.logger.error(f"去重期间文件被其他程序修改，已跳过 {file_path}")
                continue

            new_lines = list(lines)
            fixed_here = self._comment_out_duplicate_pairs(new_lines, positions)
            if not fixed_here:
                continue
            # 条目全被注释掉的块必须连块头一起删除，否则 Ren'Py 报空翻译块。
            new_lines, _ = self._remove_empty_translate_blocks(new_lines, checkpoint=checkpoint)
            if before_write is not None:
                before_write()
            self._rewrite_with_backup(
                file_path,
                lines,
                new_lines,
                "utf-8",
                checkpoint=checkpoint,
                before_replace=before_write,
            )
            fixed_count += fixed_here
            changed_files.append(str(file_path))
            self.logger.info(f"去重完成: {file_path} ({fixed_here} 条)")
            if on_file is not None:
                on_file(str(file_path), fixed_here)

        return fixed_count, changed_files

    @staticmethod
    def _find_tl_dir(folder: str | Path, *, max_levels: int = 3) -> Optional[Path]:
        """定位 ``tl`` 目录：先看 ``folder`` 自身与其 ``tl`` / ``game/tl`` 子目录，
        再向上找最近的名为 ``tl`` 的祖先（最多 ``max_levels`` 层）。"""
        try:
            path = Path(os.path.abspath(str(Path(folder).expanduser())))
        except (OSError, ValueError):
            return None
        for direct in (path, path / "tl", path / "game" / "tl"):
            if direct.name.casefold() == "tl" and direct.is_dir():
                return direct
        candidates = [path, *path.parents][: max_levels + 1]
        for candidate in candidates:
            if candidate.name.casefold() == "tl" and candidate.is_dir():
                return candidate
        return None

    def _collect_strings_old_values(self, folder: str | Path) -> List[Tuple[str, str]]:
        """轻量收集 ``translate <lang> strings:`` 块里的 old 原文。

        环境检测只需要重复计数，用正则扫一遍即可，不构建完整文档，
        避免影响扫描主流程的解析次数与进度回调。
        """
        values: List[Tuple[str, str]] = []
        try:
            files = self.get_rpy_files(folder)
        except OSError:
            return values

        header_re = re.compile(r"^[ \t]*translate\s+([A-Za-z0-9_]+)\s+strings\s*:\s*$")
        other_header_re = re.compile(r"^[ \t]*translate\s+\S+")
        old_re = re.compile(r'^[ \t]*old\s+(["\'])(?P<text>.*)\1[ \t]*$')
        new_re = re.compile(r'^[ \t]*new\s+(["\'])')
        for path in files:
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as source:
                    lines = source.read().splitlines()
            except OSError:
                continue
            language = ""
            pending_old: Optional[str] = None
            for line in lines:
                header = header_re.match(line)
                if header:
                    language = header.group(1)
                    pending_old = None
                    continue
                if other_header_re.match(line):
                    language = ""
                    pending_old = None
                    continue
                if not language:
                    continue
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                old_match = old_re.match(line)
                if old_match:
                    pending_old = self._decode_renpy_literal(old_match.group("text"))
                    continue
                if pending_old is not None and new_re.match(line):
                    values.append((language, pending_old))
                pending_old = None
        return values

    def _count_duplicate_strings(self, main_dir: Path, leftover_dir: Path) -> int:
        """估算残留增量目录里与主翻译目录重复的 strings 条目数。"""
        seen: set[tuple[str, str]] = set()
        if main_dir.is_dir():
            seen.update(self._collect_strings_old_values(main_dir))
        duplicates = 0
        for key in self._collect_strings_old_values(leftover_dir):
            if key in seen:
                duplicates += 1
            else:
                seen.add(key)
        return duplicates

    def detect_environment_issues(self, folder: str | Path) -> List[Dict]:
        """识别 ``game/tl/<lang>_new`` 这类未合并的增量抽取残留目录。

        这类目录里的 ``translate ... strings:`` 会和主目录重复，Ren'Py 启动
        直接报 "A translation ... already exists"；它不属于文件内错误，
        所以要单独作为环境问题上报，由用户决定合并或移出。
        """
        issues: List[Dict] = []
        try:
            resolved = Path(os.path.abspath(str(Path(folder).expanduser())))
        except (OSError, ValueError):
            return issues
        if not resolved.is_dir():
            return issues
        tl_dir = self._find_tl_dir(resolved)
        if tl_dir is None:
            return issues

        try:
            children = sorted(
                (child for child in tl_dir.iterdir() if child.is_dir()),
                key=lambda path: path.name.casefold(),
            )
        except OSError as exc:
            self.logger.warning(f"读取翻译目录失败 {tl_dir}: {exc}")
            return issues

        name_suffix = "_new"
        for child in children:
            name = child.name
            if len(name) <= len(name_suffix) or not name.casefold().endswith(name_suffix):
                continue
            language = name[: -len(name_suffix)]
            if not language:
                continue
            try:
                if not self.get_rpy_files(child):
                    # 没有 .rpy 的残留目录不会产生重复翻译，不值得打扰用户。
                    continue
            except OSError:
                continue
            try:
                issue_count = self._count_duplicate_strings(tl_dir / language, child)
            except Exception as exc:
                self.logger.warning(f"统计重复译文失败 {child}: {exc}")
                issue_count = 0
            issues.append({
                "kind": INCREMENTAL_LEFTOVER,
                "type": INCREMENTAL_LEFTOVER,
                "path": str(child),
                "language": language,
                "message": Localizer.get().error_repair_env_leftover.format(
                    name=name, count=issue_count,
                ),
                "issue_count": issue_count,
                "actions": ["merge", "move"],
            })
        return issues

    @staticmethod
    def _resolve_project_root(tl_dir: Path) -> Path:
        """由 ``tl`` 目录反推项目根：``<proj>/game/tl`` 与 ``<proj>/tl`` 都支持。"""
        parents = tl_dir.parents
        if len(parents) >= 2 and (parents[1] / "game").is_dir():
            return parents[1]
        if len(parents) >= 1:
            return parents[0]
        return tl_dir

    @staticmethod
    def _unique_move_target(project_root: Path, name: str, extension: str = "") -> Path:
        """``_renpybox_backup/<name>_<时间戳><extension>``，同一秒冲突时追加序号，绝不覆盖。"""
        backup_root = project_root / "_renpybox_backup"
        base = f"{name}_{time.strftime('%Y%m%d_%H%M%S')}"
        target = backup_root / f"{base}{extension}"
        suffix = 2
        while target.exists():
            target = backup_root / f"{base}_{suffix}{extension}"
            suffix += 1
        return target

    @staticmethod
    def _archive_dirs(archive: Path, sources: List[Path]) -> None:
        """把若干目录完整打进一个新 zip（顶层为各目录名）；任何失败都删掉半成品并抛出。

        用 zip 而不是复制目录：备份可能落在游戏目录内，散落的 .rpy 会被 Ren'Py 加载。
        """
        archive.parent.mkdir(parents=True, exist_ok=True)
        expected = 0
        try:
            with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED) as bundle:
                for source in sources:
                    bundle.writestr(f"{source.name}/", b"")
                    for root, dirs, names in os.walk(source):
                        root_path = Path(root)
                        dirs[:] = sorted(
                            name for name in dirs
                            if not (root_path / name).is_symlink()
                            and not getattr(os.path, "isjunction", lambda _p: False)(root_path / name)
                        )
                        for name in sorted(names):
                            path = root_path / name
                            if path.is_symlink():
                                continue
                            bundle.write(path, path.relative_to(source.parent).as_posix())
                            expected += 1
            with zipfile.ZipFile(archive) as bundle:
                broken = bundle.testzip()
                stored = sum(1 for info in bundle.infolist() if not info.is_dir())
            if broken is not None or stored != expected:
                raise OSError(f"备份校验失败：{archive}")
        except BaseException:
            with contextlib.suppress(OSError):
                archive.unlink(missing_ok=True)
            raise

    def fix_environment_issue(self, issue: Dict, action: str = "merge") -> Dict:
        """合并或移出一条环境问题；任何异常都转成 ``ok: False``，绝不抛出。"""
        payload = {"path": "", "action": "", "ok": False, "message": ""}
        issue = issue if isinstance(issue, dict) else {}
        leftover = Path(str(issue.get("path") or ""))
        name = leftover.name or str(issue.get("path") or "")
        language = str(issue.get("language") or "").strip()
        if not language and name.casefold().endswith("_new"):
            language = name[: -len("_new")]
        action_name = str(action or "merge").strip() or "merge"
        payload.update(path=str(leftover), action=action_name)

        localizer = Localizer.get()
        if action_name not in {"merge", "move"}:
            payload["message"] = localizer.error_repair_env_failed.format(
                name=name, error=f"未知操作 {action_name}",
            )
            return payload
        if not language:
            payload["message"] = localizer.error_repair_env_failed.format(
                name=name, error="无法判定语言目录",
            )
            return payload

        try:
            if not leftover.is_dir():
                raise FileNotFoundError(f"目录不存在：{leftover}")
            tl_dir = leftover.parent
            project_root = self._resolve_project_root(tl_dir)

            if action_name == "move":
                target = self._unique_move_target(project_root, f"{language}_new")
                target.parent.mkdir(parents=True, exist_ok=True)
                # 只移动，绝不删除：残留目录里可能还有用户未合并的译文。
                shutil.move(str(leftover), str(target))
                payload.update(
                    ok=True,
                    message=localizer.error_repair_env_moved.format(
                        name=name, target=str(target),
                    ),
                )
                return payload

            # 合并会改写主目录并删除增量目录，先把两者完整打包；备份失败则不合并。
            main_dir = tl_dir / language
            archive = self._unique_move_target(project_root, f"merge_{language}", ".zip")
            try:
                self._archive_dirs(
                    archive, [path for path in (main_dir, leftover) if path.is_dir()],
                )
            except Exception as exc:
                raise RuntimeError(f"合并前备份失败，未执行合并：{exc}") from exc
            payload["backup"] = str(archive)
            backup_note = localizer.error_repair_env_backup.format(target=str(archive))

            # 延迟导入：避免 ErrorRepairer 在导入期就拉起整条提取器依赖链。
            from module.Extract.UnifiedExtractor import UnifiedExtractor

            merge_result = UnifiedExtractor().merge_incremental_folder(
                project_root,
                language,
                leftover,
                clean_duplicates=True,
                target_tl_dir=main_dir,
            )
            success = bool(getattr(merge_result, "success", False))
            detail = str(getattr(merge_result, "message", "") or "").strip()
            if success:
                payload.update(
                    ok=True,
                    message=localizer.error_repair_env_merged.format(
                        name=name, tl=language,
                    ) + backup_note,
                )
            else:
                payload["message"] = localizer.error_repair_env_failed.format(
                    name=name, error=detail or "合并失败",
                ) + backup_note
            return payload
        except Exception as exc:
            self.logger.error(f"处理环境问题失败 {leftover}: {exc}")
            payload["ok"] = False
            payload["message"] = localizer.error_repair_env_failed.format(
                name=name, error=str(exc),
            )
            if payload.get("backup"):
                payload["message"] += localizer.error_repair_env_backup.format(target=payload["backup"])
            return payload

    def export_error_report(self, errors: Dict[str, List[Dict]], output_path: str) -> bool:
        """
        导出错误报告为 Excel。

        成功写入后返回 True；失败返回 False（不因旧目标已存在而假成功）。
        使用临时文件写完再原子替换，避免半截 XLSX。
        """
        # 与 Qt 一致：缺 .xlsx 后缀时追加（含 .txt 等也会变成 *.txt.xlsx）
        output_text = str(output_path)
        if not output_text.lower().endswith(".xlsx"):
            output_text += ".xlsx"
        target = Path(output_text)
        temp_path: Path | None = None
        try:
            from openpyxl import Workbook

            wb = Workbook()
            ws = wb.active
            ws.title = "Error Report"

            headers = ["文件", "行号", "错误类型", "错误信息", "内容", "详情"]
            ws.append(headers)

            for file_path, file_errors in errors.items():
                for error in file_errors:
                    details = {
                        key: value
                        for key, value in error.items()
                        if key not in {"line", "type", "message", "content"}
                    }
                    ws.append([
                        file_path,
                        error.get("line", 0),
                        error.get("type", ""),
                        error.get("message", ""),
                        error.get("content", ""),
                        json.dumps(details, ensure_ascii=False, sort_keys=True),
                    ])

            target.parent.mkdir(parents=True, exist_ok=True)
            for _attempt in range(100):
                candidate = target.parent / f".{target.name}.{secrets.token_hex(8)}.tmp.xlsx"
                if not candidate.exists():
                    temp_path = candidate
                    break
            if temp_path is None:
                raise FileExistsError(f"无法创建临时导出文件: {target}")

            wb.save(str(temp_path))
            os.replace(str(temp_path), str(target))
            temp_path = None
            self.logger.info(f"错误报告已导出: {target}")
            return True

        except Exception as e:
            self.logger.error(f"导出错误报告失败: {e}")
            return False
        finally:
            if temp_path is not None:
                with contextlib.suppress(OSError):
                    temp_path.unlink(missing_ok=True)

    # ========== 深度 Lint 检查 (调用 Ren'Py 内置 lint) ==========
    
    def exec_renpy_lint(
        self, game_path: str, *, checkpoint: Optional[Callable[[], None]] = None,
        timeout: float = LINT_TIMEOUT,
        on_tick: Optional[Callable[[float], None]] = None,
    ) -> Optional[str]:
        """
        执行 Ren'Py 内置 lint 命令
        
        Args:
            game_path: 游戏可执行文件路径 (.exe)
            checkpoint: 取消探针，抛 CancelledError 即中止并杀进程
            timeout: 最长等待秒数（默认 LINT_TIMEOUT=30 分钟，旧版只有 120 秒）
            on_tick: 每秒回调一次已运行秒数，用于刷新进度文案，避免看起来像卡死
            
        Returns:
            None 表示执行失败，空字符串表示执行成功且无输出，非空字符串
            表示执行成功并获得 Lint 输出。
        """
        self.last_lint_error = ""
        self.last_lint_exit_code = 0
        report_path = ""
        try:
            python_path = get_python_path_from_game_path(game_path)
            py_path = get_py_path(game_path)
            game_dir = os.path.dirname(game_path)
            
            if not python_path or not os.path.isfile(python_path):
                self.last_lint_error = f"找不到游戏自带的 Python 运行时：{python_path or '（空）'}"
                self.logger.error(f"找不到游戏 Python: {python_path}")
                return None
                
            if not os.path.isfile(py_path):
                self.last_lint_error = f"找不到游戏入口脚本：{py_path}"
                self.logger.error(f"找不到游戏 .py 文件: {py_path}")
                return None
            
            # 错误输出文件
            error_output = os.path.join(game_dir, "lint_errors.txt")

            # 让 Ren'Py 把报告写成 UTF-8 文件：管道输出在中文 Windows 上按本地代码页
            # 编码，按 UTF-8 解码时中文路径会被整段吃掉，过滤后一条都不剩。
            try:
                handle, report_path = tempfile.mkstemp(prefix="renpybox-lint-", suffix=".txt")
                os.close(handle)
            except OSError:
                report_path = ""
            
            # 使用参数列表执行，避免 shell 对游戏路径做二次解释。
            command = [python_path, "-O", py_path, game_dir, "lint"]
            if report_path:
                command.append(report_path)
            
            self.logger.info(f"执行 Lint 命令: {command}")
            
            # 执行命令
            options = dict(
                shell=False, text=True, encoding='utf-8', errors='ignore',
                # 关掉标准输入：lint 若真要读键盘也不至于把进程挂在控制台上。
                stdin=subprocess.DEVNULL,
                creationflags=0x08000000 if os.name == 'nt' else 0,
                cwd=game_dir,
            )
            if checkpoint is None:
                result = subprocess.run(command, capture_output=True, timeout=timeout, **options)
            else:
                checkpoint()
                started = time.monotonic()
                deadline = started + timeout
                next_tick = 0.0
                with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **options) as process:
                    try:
                        while True:
                            checkpoint()
                            now = time.monotonic()
                            elapsed = now - started
                            # 每秒报一次心跳：前端状态文案会跟着走，用户不会以为程序挂了。
                            if on_tick is not None and elapsed >= next_tick:
                                next_tick = elapsed + 1.0
                                with contextlib.suppress(Exception):
                                    on_tick(elapsed)
                            remaining = deadline - now
                            if remaining <= 0:
                                raise subprocess.TimeoutExpired(command, timeout)
                            try:
                                stdout, stderr = process.communicate(timeout=min(0.2, remaining))
                                result = subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
                                break
                            except subprocess.TimeoutExpired:
                                continue
                    finally:
                        if process.poll() is None:
                            process.kill()
                            process.wait()
                checkpoint()
            
            self.last_lint_exit_code = int(result.returncode or 0)
            # 优先读报告文件（UTF-8、完整）；解析阶段报错时文件不会生成，退回管道输出。
            output = ""
            if report_path and os.path.isfile(report_path):
                with contextlib.suppress(OSError):
                    with open(report_path, "r", encoding="utf-8-sig", errors="replace") as handle:
                        output = handle.read()
            if not output.strip():
                output = (result.stdout or "") + (result.stderr or "")

            if result.returncode != 0:
                self.last_lint_error = f"Ren'Py 以退出码 {result.returncode} 结束"
                self.logger.error(f"Lint 执行失败，退出码: {result.returncode}")
                if output.strip():
                    self.logger.error(output.strip())
                # 只有输出里真的带「文件 + 行号」时才交回去：脚本解析错误时 Ren'Py
                # 以 1 退出，但输出正是能直接定位问题的条目，丢掉等于什么都没查。
                if not any(item.get("file") for item in self.parse_lint_errors(output)):
                    return None
            
            if output.strip():
                # 保存到文件
                with open(error_output, "w", encoding="utf-8") as f:
                    f.write(output)
                self.logger.info(f"Lint 结果已保存到: {error_output}")
                return output
            else:
                self.logger.info("Lint 检查完成，未发现错误")
                return ""

        except subprocess.TimeoutExpired:
            # 超时不是「跑不起来」：多数是项目太大，如实说明上限，提示可以调长。
            self.last_lint_error = (
                f"超过 {timeout:.0f} 秒上限仍未结束，已中止（大型项目首次 lint 常需数分钟）"
            )
            self.logger.error(f"执行 Lint 超时: {self.last_lint_error}")
            return None
        except Exception as e:
            self.last_lint_error = f"{type(e).__name__}: {e}"
            self.logger.error(f"执行 Lint 失败: {e}")
            return None
        finally:
            if report_path:
                with contextlib.suppress(OSError):
                    os.unlink(report_path)
    
    def parse_lint_errors(self, lint_output: str) -> List[Dict]:
        """
        解析 Lint 输出内容
        
        Args:
            lint_output: lint 命令的输出
            
        Returns:
            错误列表
        """
        errors = []
        
        if not lint_output:
            return errors

        # Ren'Py lint 报告的第一行带 BOM，先去掉，否则首条会被当成正文。
        lint_output = lint_output.lstrip("\ufeff")

        for line in lint_output.split('\n'):
            line = line.strip()
            if not line:
                continue
                
            error_info = {"raw": line}
            
            # Ren'Py lint 的真实格式（7.x / 8.x 一致），四种都要认：
            #   File "game/x.rpy", line 12: 解析阶段错误
            #   game/tl/chinese/x.rpy:12 具体问题      ← lint 报告主体
            #   game/tl/chinese/x.rpy : 整文件问题     ← 孤儿译文等，没有行号
            #   tl/chinese/x.rpy 文件名不是 ASCII      ← 无冒号，没有行号
            # 只看 `, line N:` 是旧实现的错：真实报告一条都匹配不上，永远显示 0 条。
            location_match = re.match(
                r'^(?:File\s+)?["\']?(?P<file>.+?\.rpyc?)["\']?,\s*'
                r'line\s+(?P<line>\d+):\s*(?P<message>.*)$',
                line,
                re.IGNORECASE,
            )
            if location_match:
                error_info["file"] = location_match.group("file")
                error_info["line"] = int(location_match.group("line"))
                error_info["message"] = location_match.group("message").strip()

            # 解析翻译重复错误
            elif line.startswith('Exception: A translation for '):
                error_info["type"] = "duplicate_translation"
                if 'already exists at ' in line:
                    idx = line.rindex('already exists at ')
                    location = line[idx + len('already exists at '):].rstrip('.')
                    if ':' in location:
                        file_part, line_part = location.rsplit(':', 1)
                        error_info["file"] = file_part.strip()
                        try:
                            error_info["line"] = int(line_part.strip())
                        except ValueError:
                            pass
                error_info["message"] = line

            else:
                located = re.match(
                    r'^(?P<file>[^\s].*?\.rpyc?)\s*:\s*(?P<line>\d+)\s*:?\s*(?P<message>.*)$',
                    line,
                    re.IGNORECASE,
                )
                whole_file = located is None and re.match(
                    r'^(?P<file>[^\s].*?\.rpyc?)\s*:\s*(?P<message>\S.*)$',
                    line,
                    re.IGNORECASE,
                )
                bare_file = located is None and whole_file is None and re.match(
                    r'^(?P<file>[^\s].*?\.rpyc?)\s+(?P<message>\S.*)$',
                    line,
                    re.IGNORECASE,
                )
                matched = located or whole_file or bare_file
                if matched is not None:
                    error_info["file"] = matched.group("file")
                    error_info["message"] = matched.group("message").strip()
                    error_info["line"] = int(matched.group("line")) if located else 0
            
            # 标记错误类型
            if 'is not terminated with a newline' in line:
                error_info["type"] = "unterminated_string"
            elif 'end of line expected' in line:
                error_info["type"] = "syntax_error"
            elif 'expects a non-empty block' in line:
                error_info["type"] = "empty_block"
            elif 'unknown statement' in line:
                error_info["type"] = "unknown_statement"
            elif 'expected statement' in line:
                error_info["type"] = "expected_statement"
            elif 'Could not parse string' in line:
                error_info["type"] = "parse_error"
            elif 'Indentation mismatch' in line:
                error_info["type"] = "indentation_mismatch"
            elif 'is not an image' in line:
                error_info["type"] = "missing_image"
            elif 'orphan translation' in line:
                error_info["type"] = "orphan_translation"
            elif 'non-ASCII characters' in line:
                error_info["type"] = "non_ascii_filename"
            elif 'who part of a say statement' in line:
                # 游戏把角色名存进变量（`$ x = "名字"` 后 `x "台词"`）时 lint 求值不到；
                # Ren'Py 的 say 明确支持字符串 who，这是 lint 的常见误报。
                error_info["type"] = "who_unresolved"
                 
            errors.append(error_info)
            
        return errors

    @staticmethod
    def _lint_path_variants(folder_path: str | Path) -> list[list[str]]:
        """翻译目录在 lint 报告里的几种写法（绝对路径 / game 起 / tl 起）。"""
        root_parts = [
            part.casefold()
            for part in Path(folder_path).expanduser().resolve().as_posix().split("/")
            if part
        ]
        if not root_parts:
            return []
        variants = [root_parts]
        for marker in ("game", "tl"):
            try:
                marker_index = len(root_parts) - 1 - root_parts[::-1].index(marker)
            except ValueError:
                continue
            variants.append(root_parts[marker_index:])
        return variants

    @staticmethod
    def _lint_error_file(error: Dict) -> str:
        return str(error.get("file") or "").strip().strip("\"'")

    @classmethod
    def split_lint_errors(
        cls,
        errors: List[Dict],
        folder_path: str | Path,
    ) -> Tuple[List[Dict], List[Dict]]:
        """按「译文」与「源码」分成两组。

        译者关心的是自己生成的那批 TL 文件；游戏本体的报错多半与翻译无关，
        混在一起看不出重点，所以分开给界面展示（源码组仍要保留：它解释了
        为什么 lint 可能整体跑不起来）。

        已知误报（who_unresolved，见 parse_lint_errors）不进译文组：游戏把
        角色名存进运行时变量时 lint 求值不到，但 Ren'Py 的 say 支持字符串
        who，这跟译文对错无关；源码侧已经报过同一句话时，译文那份直接丢掉。
        """
        variants = cls._lint_path_variants(folder_path)
        if not variants:
            return [], []
        tl_raw: List[Dict] = []
        source_raw: List[Dict] = []
        for error in errors:
            file_value = cls._lint_error_file(error)
            # lint 会把已编译脚本报成 .rpyc，只认 .rpy 会把这类条目全丢掉。
            if not file_value or not file_value.casefold().endswith((".rpy", ".rpyc")):
                continue
            file_parts = [
                part.casefold()
                for part in file_value.replace("\\", "/").split("/")
                if part
            ]
            under_tl = any(
                len(file_parts) >= len(variant) and file_parts[:len(variant)] == variant
                for variant in variants
            )
            (tl_raw if under_tl else source_raw).append(error)

        def hint(item: Dict) -> bool:
            return str(item.get("type") or "") in IGNORED_LINT_HINT_TYPES

        def message_of(item: Dict) -> str:
            return str(item.get("message") or item.get("raw") or "")

        source_messages = {message_of(item) for item in source_raw}
        tl_errors = [item for item in tl_raw if not hint(item)]
        # 译文里的同类提示：源码侧已有就当重复丢掉，没有才挪进源码组。
        moved = [
            item for item in tl_raw
            if hint(item) and message_of(item) not in source_messages
        ]
        return tl_errors, source_raw + moved

    @staticmethod
    def filter_lint_errors(
        errors: List[Dict],
        folder_path: str | Path,
    ) -> List[Dict]:
        """只保留目标翻译目录下的 Lint 文件错误。"""
        return ErrorRepairer.split_lint_errors(errors, folder_path)[0]
    
    def fix_by_lint(self, game_path: str, max_iterations: int = 16) -> Tuple[bool, int]:
        """
        通过 Lint 检查自动修复错误（递归修复）
        
        Args:
            game_path: 游戏可执行文件路径
            max_iterations: 最大迭代次数
            
        Returns:
            (是否已由 Lint 验证无错误, 安全修复的数量)
        """
        if max_iterations <= 0:
            return False, 0

        total_fixed = 0
        game_dir = os.path.dirname(game_path)
        game_root = Path(game_dir).resolve()

        for iteration in range(max_iterations):
            self.logger.info(f"开始第 {iteration + 1}/{max_iterations} 轮 Lint 检查...")

            # 执行 lint
            lint_output = self.exec_renpy_lint(game_path)

            if lint_output is None:
                self.logger.error("Lint 执行失败，停止自动修复")
                return False, total_fixed
            if lint_output == "":
                self.logger.info("没有更多错误，修复完成!")
                return True, total_fixed

            # 解析错误
            errors = self.parse_lint_errors(lint_output)

            if not errors:
                self.logger.warning("Lint 有输出，但没有可解析的错误；未修改文件")
                return False, total_fixed

            # 每轮最多改一处，然后重新执行 lint，避免继续使用已经失效的行号。
            fixed_in_round = False
            processed_locations: set[tuple[str, int]] = set()
            for error in errors:
                file_path = error.get("file")
                line_num = error.get("line")
                error_type = error.get("type", "")

                if error_type not in self.SAFE_LINT_FIX_TYPES:
                    continue
                if not file_path or not isinstance(line_num, int) or line_num < 1:
                    continue

                # 构建完整路径
                candidate = Path(file_path)
                if not candidate.is_absolute():
                    candidate = game_root / candidate
                try:
                    candidate = candidate.resolve()
                    candidate.relative_to(game_root)
                except (OSError, ValueError):
                    self.logger.warning(f"忽略游戏目录外的 Lint 路径: {file_path}")
                    continue

                if not candidate.is_file():
                    self.logger.warning(f"文件不存在: {candidate}")
                    continue

                location = (str(candidate), line_num)
                if location in processed_locations:
                    continue
                processed_locations.add(location)

                if self._fix_single_lint_error(str(candidate), line_num, error_type):
                    fixed_in_round = True
                    total_fixed += 1
                    break

            if not fixed_in_round:
                self.logger.warning("没有可安全自动修复的 Lint 错误；未继续修改文件")
                return False, total_fixed

            self.logger.info(f"第 {iteration + 1} 轮安全修复了 1 个错误")

        self.logger.warning("达到 Lint 自动修复轮次上限，结果尚未验证为无错误")
        return False, total_fixed
    
    def _fix_single_lint_error(self, file_path: str, line_num: int, error_type: str) -> bool:
        """
        修复单个 Lint 错误
        
        Args:
            file_path: 文件路径
            line_num: 错误行号 (1-based)
            error_type: 错误类型
            
        Returns:
            是否修复成功
        """
        if error_type not in self.SAFE_LINT_FIX_TYPES:
            return False

        try:
            with io.open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            if line_num < 1 or line_num > len(lines):
                return False
                
            idx = line_num - 1  # 转为 0-based
            self.logger.info(f"修复 {file_path} 第 {line_num} 行: {lines[idx].strip()[:50]}...")

            changed = False
            if error_type in {"parse_error", "syntax_error"}:
                candidate_indices = [idx]
                if error_type == "syntax_error" and idx > 0:
                    candidate_indices.append(idx - 1)
                for candidate_idx in candidate_indices:
                    repaired_line, repaired = self.repair_unescaped_dialogue_quotes(
                        lines[candidate_idx]
                    )
                    if repaired:
                        lines[candidate_idx] = repaired_line
                        changed = True
                        break
            elif error_type == "empty_block":
                # Removing all empty strings blocks in one pass avoids the
                # Lint line-number drift that would otherwise require one
                # iteration per block.
                lines, removed_blocks = self._remove_empty_translate_blocks(lines)
                changed = removed_blocks > 0
            elif error_type in {"indentation_mismatch", "indentation_level"}:
                candidate_indices = [idx] + ([idx - 1] if idx > 0 else [])
                for candidate_idx in candidate_indices:
                    repaired_line, repaired = self.repair_indentation_level(
                        lines,
                        candidate_idx,
                    )
                    if repaired:
                        lines[candidate_idx] = repaired_line
                        changed = True
                        break

            if not changed:
                return False

            # 保持行数不变，避免本轮错误位置整体漂移。
            with io.open(file_path, 'w', encoding='utf-8') as f:
                f.writelines(lines)

            return True

        except Exception as e:
            self.logger.error(f"修复错误失败 {file_path}:{line_num} - {e}")
            return False
    
    def _remove_consecutive_empty_lines(self, lines: List[str]) -> List[str]:
        """移除连续的空行，最多保留一个"""
        result = []
        prev_empty = False
        
        for line in lines:
            is_empty = not line.strip()
            if is_empty and prev_empty:
                continue
            result.append(line)
            prev_empty = is_empty
            
        return result
