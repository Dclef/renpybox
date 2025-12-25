from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


@dataclass
class RenpyStringEntry:
    """Parsed Ren'Py string with its position and optional tag context."""

    source: str
    translation: str
    line_no: int
    tag: Optional[str] = None
    format_type: str = ""


class RenpyStringReader:
    """Lightweight Ren'Py reader (adapted from AiNiee) that keeps line mapping."""

    COMMENT_TRANSLATION_START_PATTERN = re.compile(r"^\s*#\s*")

    def __init__(self, encoding: str = "utf-8") -> None:
        self.encoding = encoding

    def read(self, file_path: Path) -> List[RenpyStringEntry]:
        lines = file_path.read_text(encoding=self.encoding, errors="replace").splitlines()
        entries: List[RenpyStringEntry] = []
        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()

            # --- 格式 1: old / new ---
            if stripped.startswith("old "):
                parts = self._get_dialogue_parts(stripped)
                if parts:
                    source = parts[1]
                    for j in range(i + 1, len(lines)):
                        next_line = lines[j]
                        next_stripped = next_line.strip()
                        if next_stripped.startswith("new "):
                            new_parts = self._get_dialogue_parts(next_stripped)
                            if new_parts:
                                translation = new_parts[1]
                                entries.append(
                                    RenpyStringEntry(
                                        source=source,
                                        translation=translation,
                                        line_no=j,
                                        format_type="old_new",
                                    )
                                )
                                i = j
                                break
                        elif next_stripped.startswith("old ") or self.COMMENT_TRANSLATION_START_PATTERN.match(
                            next_stripped
                        ):
                            break
                i += 1
                continue

            # --- 格式 2~6: 注释行后跟代码行 (支持跳过 voice) ---
            if self.COMMENT_TRANSLATION_START_PATTERN.match(stripped):
                potential_source_line = line.split("#", 1)[-1].lstrip()
                comment_parts = self._get_dialogue_parts(potential_source_line)

                is_meta_comment = potential_source_line.startswith("game/") or potential_source_line.startswith("renpy/")
                if comment_parts and not is_meta_comment:
                    comment_tag, comment_source = comment_parts

                    if comment_tag == "voice":
                        i += 1
                        continue

                    search_index = i + 1
                    while search_index < len(lines):
                        next_line_info = self._find_next_relevant_line(lines, search_index)
                        if not next_line_info:
                            break

                        code_line_num, code_line = next_line_info
                        code_parts = self._get_dialogue_parts(code_line.strip())
                        if code_parts:
                            code_tag, code_text = code_parts

                            if code_tag == "voice":
                                search_index = code_line_num + 1
                                continue

                            if comment_tag == code_tag:
                                entries.append(
                                    RenpyStringEntry(
                                        source=comment_source,
                                        translation=code_text,
                                        line_no=code_line_num,
                                        tag=code_tag,
                                        format_type="comment_dialogue",
                                    )
                                )
                                i = code_line_num + 1
                            break
                        break

                    i += 1
                    continue

            i += 1

        return entries

    def _is_escaped_quote(self, text: str, pos: int) -> bool:
        if pos == 0:
            return False

        backslash_count = 0
        check_pos = pos - 1
        while check_pos >= 0 and text[check_pos] == "\\":
            backslash_count += 1
            check_pos -= 1

        return backslash_count % 2 == 1

    def _find_last_unescaped_quote(self, text: str, end: int = -1) -> int:
        if end == -1:
            end = len(text)

        pos = end - 1
        while pos >= 0:
            if text[pos] == '"' and not self._is_escaped_quote(text, pos):
                return pos
            pos -= 1

        return -1

    def _find_first_unescaped_quote(self, text: str, start: int = 0) -> int:
        pos = start
        while pos < len(text):
            if text[pos] == '"' and not self._is_escaped_quote(text, pos):
                return pos
            pos += 1

        return -1

    def _get_dialogue_parts(self, line: str) -> Optional[tuple[str, str]]:
        last_quote_index = self._find_last_unescaped_quote(line)
        if last_quote_index == -1:
            return None

        first_quote_index = self._find_last_unescaped_quote(line, last_quote_index)
        if first_quote_index == -1:
            if line.strip().startswith('"'):
                first_quote_index = self._find_first_unescaped_quote(line)
                if first_quote_index >= last_quote_index:
                    return None
            else:
                return None

        tag = line[:first_quote_index].strip()
        text = line[first_quote_index + 1 : last_quote_index]
        return tag, text

    def _find_next_relevant_line(self, lines: List[str], start_index: int) -> Optional[tuple[int, str]]:
        for i in range(start_index, len(lines)):
            line = lines[i]
            stripped = line.strip()

            if stripped.startswith("translate "):
                return None

            if self._get_dialogue_parts(stripped) is not None:
                return i, line

        return None


class RenpyStringWriter:
    """Line-aware writer that applies translations back to .rpy files."""

    def __init__(self, encoding: str = "utf-8") -> None:
        self.encoding = encoding

    def write(
        self,
        translation_file_path: Path,
        entries: List[RenpyStringEntry],
        source_file_path: Optional[Path] = None,
    ) -> None:
        source_path = source_file_path or translation_file_path
        if not source_path.exists():
            return

        lines = source_path.read_text(encoding=self.encoding, errors="replace").splitlines(True)
        for entry in sorted(entries, key=lambda e: e.line_no, reverse=True):
            if not entry.translation:
                continue

            line_num = entry.line_no
            if line_num < 0 or line_num >= len(lines):
                continue

            original_line = lines[line_num]
            new_trans = self._escape_quotes_for_renpy(entry.translation)
            search_start_index = 0
            if entry.tag:
                tag_start_index = original_line.find(entry.tag)
                if tag_start_index != -1:
                    search_start_index = tag_start_index + len(entry.tag)

            first_quote_index = self._find_first_unescaped_quote(original_line, search_start_index)
            last_quote_index = self._find_last_unescaped_quote(original_line)

            if first_quote_index != -1 and last_quote_index > first_quote_index:
                prefix = original_line[: first_quote_index + 1]
                suffix = original_line[last_quote_index:]
                lines[line_num] = f"{prefix}{new_trans}{suffix}"

        translation_file_path.parent.mkdir(parents=True, exist_ok=True)
        translation_file_path.write_text("".join(lines), encoding=self.encoding)

    def _is_escaped_quote(self, text: str, pos: int) -> bool:
        if pos == 0:
            return False

        backslash_count = 0
        check_pos = pos - 1
        while check_pos >= 0 and text[check_pos] == "\\":
            backslash_count += 1
            check_pos -= 1

        return backslash_count % 2 == 1

    def _find_first_unescaped_quote(self, text: str, start: int = 0) -> int:
        pos = start
        while pos < len(text):
            if text[pos] == '"' and not self._is_escaped_quote(text, pos):
                return pos
            pos += 1
        return -1

    def _find_last_unescaped_quote(self, text: str) -> int:
        pos = len(text) - 1
        while pos >= 0:
            if text[pos] == '"' and not self._is_escaped_quote(text, pos):
                return pos
            pos -= 1
        return -1

    def _escape_quotes_for_renpy(self, text: str) -> str:
        pattern = r'\\"|""|" "|\"'

        def replacer(match: re.Match[str]) -> str:
            matched_text = match.group(0)
            if matched_text in ('\\"', '""', '" "'):
                return matched_text
            if matched_text == '"':
                return '\\"'
            return matched_text

        return re.sub(pattern, replacer, text)
