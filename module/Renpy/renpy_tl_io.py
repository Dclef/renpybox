# -*- coding: utf-8 -*-
"""
Ren'Py TL 读写与条目抽取
"""

from __future__ import annotations

from base.Base import Base
from module.Cache.CacheItem import CacheItem
from module.Renpy.renpy_tl_core import (
    TlBlock,
    TlBlockKind,
    TlDocument,
    TlSlot,
    TlSlotRole,
    TlStatement,
    escape_tl_string,
    is_resource_path,
    is_tl_text,
    match_tpl_to_target,
    pair_old_new_lines,
    scan_quoted_literals,
    sha1_hex,
    build_line_skeleton,
    split_indent,
    strip_comment_prefix,
)


class RenpyTlItemExtractor(Base):
    """从 TL AST 中抽取 CacheItem。"""

    def extract(self, doc: TlDocument, rel_path: str) -> list[CacheItem]:
        items: list[CacheItem] = []

        for block in doc.blocks:
            if block.kind in {TlBlockKind.PYTHON, TlBlockKind.OTHER}:
                continue

            if block.kind == TlBlockKind.STRINGS:
                mapping = pair_old_new_lines(block)
            else:
                mapping = match_tpl_to_target(block)

            if not mapping:
                continue

            stmt_by_line = {s.line_no: s for s in block.statements}
            for template_line, target_line in mapping.items():
                template_stmt = stmt_by_line.get(template_line)
                target_stmt = stmt_by_line.get(target_line)
                if template_stmt is None or target_stmt is None:
                    continue

                item = self._build_cache_item(block, template_stmt, target_stmt, rel_path)
                if item is not None:
                    items.append(item)

        # 保持稳定排序
        items.sort(key=lambda x: (x.get_file_path(), x.get_row()))
        return items

    def _build_cache_item(
        self,
        block: TlBlock,
        template_stmt: TlStatement,
        target_stmt: TlStatement,
        rel_path: str,
    ) -> CacheItem | None:
        slots = self._select_slots(block, template_stmt)
        if not slots:
            return None

        name_slot = next((s for s in slots if s.role == TlSlotRole.NAME), None)
        dialogue_slot = next(
            (s for s in slots if s.role in {TlSlotRole.DIALOGUE, TlSlotRole.STRING}),
            None,
        )

        if dialogue_slot is None:
            return None

        src = self._get_literal_value(template_stmt, dialogue_slot.lit_index)
        dst = self._get_literal_value(target_stmt, dialogue_slot.lit_index)

        name_src: str | None = None
        name_dst: str | None = None
        if name_slot is not None:
            name_src = self._get_literal_value(template_stmt, name_slot.lit_index)
            name_dst = self._get_literal_value(target_stmt, name_slot.lit_index)

        if src == "":
            return None

        status = self._get_status(src, dst)
        if status == Base.TranslationStatus.UNTRANSLATED and dst == "":
            dst = src

        extra_field = self._build_extra_field(
            block,
            template_stmt,
            target_stmt,
            slots,
        )

        return CacheItem.from_dict(
            {
                "src": src,
                "dst": dst if dst != "" else src,
                "name_src": name_src,
                "name_dst": name_dst,
                "extra_field": extra_field,
                "row": template_stmt.line_no,
                "file_type": CacheItem.FileType.RENPY,
                "file_path": rel_path,
                "text_type": CacheItem.TextType.RENPY,
                "status": status,
            }
        )

    def _get_status(self, src: str, dst: str) -> Base.TranslationStatus:
        if src == "":
            return Base.TranslationStatus.EXCLUDED
        if dst != "" and src != dst:
            return Base.TranslationStatus.TRANSLATED_IN_PAST
        return Base.TranslationStatus.UNTRANSLATED

    def _build_extra_field(
        self,
        block: TlBlock,
        template_stmt: TlStatement,
        target_stmt: TlStatement,
        slots: list[TlSlot],
    ) -> dict:
        return {
            "renpy": {
                "v": 1,
                "block": {
                    "lang": block.lang,
                    "label": block.label,
                    "kind": block.kind,
                    "header_line": block.header_line_no,
                },
                "pair": {
                    "template_line": template_stmt.line_no,
                    "target_line": target_stmt.line_no,
                },
                "slots": [{"role": s.role, "lit_index": s.lit_index} for s in slots],
                "digest": {
                    "template_raw_sha1": sha1_hex(template_stmt.raw_line),
                    "template_raw_rstrip_sha1": sha1_hex(
                        template_stmt.raw_line.rstrip()
                    ),
                    "target_skeleton_sha1": sha1_hex(target_stmt.strict_key),
                    "target_string_count": target_stmt.string_count,
                },
            }
        }

    def _get_literal_value(self, stmt: TlStatement, lit_index: int) -> str:
        if lit_index < 0 or lit_index >= len(stmt.literals):
            return ""
        return stmt.literals[lit_index].value

    def _select_slots(self, block: TlBlock, template_stmt: TlStatement) -> list[TlSlot]:
        if block.kind == TlBlockKind.STRINGS:
            return self._select_slots_strings(template_stmt)
        if block.kind == TlBlockKind.LABEL:
            return self._select_slots_label(template_stmt)
        return []

    def _select_slots_strings(self, stmt: TlStatement) -> list[TlSlot]:
        code = stmt.code.strip()
        if not code.startswith("old "):
            return []

        if not stmt.literals:
            return []

        value = stmt.literals[0].value
        if is_resource_path(value):
            return []
        if not is_tl_text(value):
            return []
        return [TlSlot(role=TlSlotRole.STRING, lit_index=0)]

    def _select_slots_label(self, stmt: TlStatement) -> list[TlSlot]:
        if not stmt.literals:
            return []

        name_index = self._find_character_name_lit_index(stmt)
        tail_group = self._find_tail_string_group(stmt)
        if not tail_group:
            return []

        dialogue_index = tail_group[-1]
        tail_name_index: int | None = None
        if len(tail_group) >= 2:
            tail_name_index = tail_group[-2]

        dialogue_value = stmt.literals[dialogue_index].value
        if is_resource_path(dialogue_value):
            return []
        if not is_tl_text(dialogue_value):
            return []

        slots: list[TlSlot] = []
        if name_index is None and tail_name_index is not None:
            name_index = tail_name_index

        if name_index is not None:
            name_value = stmt.literals[name_index].value
            if (not is_resource_path(name_value)) and is_tl_text(name_value):
                slots.append(TlSlot(role=TlSlotRole.NAME, lit_index=name_index))

        slots.append(TlSlot(role=TlSlotRole.DIALOGUE, lit_index=dialogue_index))
        return slots

    def _find_tail_string_group(self, stmt: TlStatement) -> list[int]:
        if not stmt.literals:
            return []

        indices = [len(stmt.literals) - 1]
        for idx in range(len(stmt.literals) - 2, -1, -1):
            prev_lit = stmt.literals[idx]
            next_lit = stmt.literals[idx + 1]
            between = stmt.code[prev_lit.end_col: next_lit.start_col]
            if between.strip() == "":
                indices.append(idx)
                continue
            break

        indices.reverse()
        return indices

    def _find_character_name_lit_index(self, stmt: TlStatement) -> int | None:
        code = stmt.code.lstrip()
        if not code.startswith("Character("):
            return None

        open_pos = stmt.code.find("(")
        if open_pos < 0:
            return None

        close_pos = self._find_matching_paren(stmt, open_pos)
        if close_pos is None:
            return None

        for i, lit in enumerate(stmt.literals):
            if open_pos < lit.start_col < close_pos:
                return i

        return None

    def _find_matching_paren(self, stmt: TlStatement, open_pos: int) -> int | None:
        ranges = [(lit.start_col, lit.end_col) for lit in stmt.literals]
        range_index = 0
        depth = 0
        i = open_pos
        while i < len(stmt.code):
            if range_index < len(ranges) and i == ranges[range_index][0]:
                i = ranges[range_index][1]
                range_index += 1
                continue

            ch = stmt.code[i]
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    return i
            i += 1

        return None


class RenpyTlLineUpdater(Base):
    """将 CacheItem 应用回 tl 文件行。"""

    def __init__(self) -> None:
        super().__init__()
        self._debug_skip_limit = 200
        self._debug_skip_count = 0

    def _reset_debug_skip(self) -> None:
        self._debug_skip_count = 0

    def _short_hash(self, value: str | None) -> str:
        if not isinstance(value, str):
            return ""
        return value[:8]

    def _debug_skip(self, item: CacheItem | None, reason: str, **details) -> bool:
        if self._debug_skip_count >= self._debug_skip_limit:
            if self._debug_skip_count == self._debug_skip_limit:
                self.debug(
                    "[WRITEBACK_DEBUG] skip log limit reached, suppressing further entries",
                    console=False,
                )
            self._debug_skip_count += 1
            return False

        self._debug_skip_count += 1
        parts: list[str] = [f"reason={reason}"]
        if item is not None:
            file_path = item.get_file_path()
            row = item.get_row()
            if file_path:
                parts.append(f"file={file_path}")
            if row:
                parts.append(f"row={row}")

        for key, value in details.items():
            if value is None:
                continue
            parts.append(f"{key}={value}")

        self.debug("[WRITEBACK_DEBUG] skip " + " ".join(parts), console=False)
        return False

    def apply_items_to_lines(
        self, lines: list[str], items: list[CacheItem]
    ) -> tuple[int, int]:
        self._reset_debug_skip()
        applied = 0
        skipped = 0

        for item in items:
            ok = self.apply_item(lines, item)
            if ok:
                applied += 1
            else:
                skipped += 1

        return applied, skipped

    def apply_item(self, lines: list[str], item: CacheItem) -> bool:
        extra_raw = item.get_extra_field()
        extra: dict = extra_raw if isinstance(extra_raw, dict) else {}
        renpy: dict = extra.get("renpy", {})
        if not isinstance(renpy, dict):
            return self._debug_skip(
                item,
                "no_renpy_extra",
                mode="strict",
                extra_type=type(extra_raw).__name__,
                renpy_type=type(renpy).__name__,
            )

        pair = renpy.get("pair", {})
        digest = renpy.get("digest", {})
        slots = renpy.get("slots", [])
        block = renpy.get("block", {})
        if not isinstance(pair, dict) or not isinstance(digest, dict):
            return self._debug_skip(
                item,
                "invalid_pair_or_digest",
                mode="strict",
                pair_type=type(pair).__name__,
                digest_type=type(digest).__name__,
            )
        if not isinstance(slots, list) or not isinstance(block, dict):
            return self._debug_skip(
                item,
                "invalid_slots_or_block",
                mode="strict",
                slots_type=type(slots).__name__,
                block_type=type(block).__name__,
            )

        template_line = pair.get("template_line")
        target_line = pair.get("target_line")
        if not isinstance(template_line, int) or not isinstance(target_line, int):
            return self._debug_skip(
                item,
                "invalid_line_number_type",
                mode="strict",
                template_line=template_line,
                target_line=target_line,
            )
        if template_line <= 0 or target_line <= 0:
            return self._debug_skip(
                item,
                "line_number_non_positive",
                mode="strict",
                template_line=template_line,
                target_line=target_line,
            )
        if template_line > len(lines) or target_line > len(lines):
            return self._debug_skip(
                item,
                "line_out_of_range",
                mode="strict",
                template_line=template_line,
                target_line=target_line,
                total_lines=len(lines),
            )

        template_raw_sha1 = digest.get("template_raw_sha1")
        target_skeleton_sha1 = digest.get("target_skeleton_sha1")
        target_string_count = digest.get("target_string_count")
        if not isinstance(template_raw_sha1, str) or not isinstance(
            target_skeleton_sha1, str
        ):
            return self._debug_skip(
                item,
                "digest_missing",
                mode="strict",
                template_raw_sha1_type=type(template_raw_sha1).__name__,
                target_skeleton_sha1_type=type(target_skeleton_sha1).__name__,
            )
        if not isinstance(target_string_count, int):
            return self._debug_skip(
                item,
                "invalid_target_string_count",
                mode="strict",
                target_string_count=target_string_count,
            )

        template_raw = lines[template_line - 1]
        template_raw_sha1_now = sha1_hex(template_raw)
        if template_raw_sha1_now != template_raw_sha1:
            return self._debug_skip(
                item,
                "template_raw_sha1_mismatch",
                mode="strict",
                template_line=template_line,
                expected=self._short_hash(template_raw_sha1),
                actual=self._short_hash(template_raw_sha1_now),
            )

        target_raw = lines[target_line - 1]
        target_indent, target_rest = split_indent(target_raw)
        target_literals = scan_quoted_literals(target_rest)
        target_skeleton = build_line_skeleton(target_rest, target_literals)
        target_skeleton_sha1_now = sha1_hex(target_skeleton)
        if target_skeleton_sha1_now != target_skeleton_sha1:
            return self._debug_skip(
                item,
                "target_skeleton_sha1_mismatch",
                mode="strict",
                target_line=target_line,
                expected=self._short_hash(target_skeleton_sha1),
                actual=self._short_hash(target_skeleton_sha1_now),
            )
        if len(target_literals) != target_string_count:
            return self._debug_skip(
                item,
                "target_string_count_mismatch",
                mode="strict",
                target_line=target_line,
                expected=target_string_count,
                actual=len(target_literals),
            )

        kind = block.get("kind")
        kind_str = str(kind) if kind is not None else ""

        replacement_by_index = self._build_replacements(item, slots)
        if not replacement_by_index:
            return self._debug_skip(
                item,
                "no_replacements",
                mode="strict",
                slots_count=len(slots),
            )

        if kind_str == "STRINGS":
            base_code = target_rest
        else:
            _, template_rest = split_indent(template_raw)
            is_comment, template_code = strip_comment_prefix(template_rest)
            if not is_comment:
                return self._debug_skip(
                    item,
                    "template_not_comment",
                    mode="strict",
                    template_line=template_line,
                    target_line=target_line,
                )
            base_code = template_code

        new_code = self._replace_literals_by_index(base_code, replacement_by_index)
        lines[target_line - 1] = f"{target_indent}{new_code}"
        return True

    def apply_items_to_lines_loose(
        self, lines: list[str], items: list[CacheItem]
    ) -> tuple[int, int]:
        """宽松写回：不校验哈希，仅基于行号与字面量结构写回。"""
        self._reset_debug_skip()
        applied = 0
        skipped = 0

        for item in items:
            ok = self.apply_item_loose(lines, item)
            if ok:
                applied += 1
            else:
                skipped += 1

        return applied, skipped

    def apply_item_loose(self, lines: list[str], item: CacheItem) -> bool:
        extra_raw = item.get_extra_field()
        extra: dict = extra_raw if isinstance(extra_raw, dict) else {}
        renpy: dict = extra.get("renpy", {})
        if not isinstance(renpy, dict):
            return self._debug_skip(
                item,
                "no_renpy_extra",
                mode="loose",
                extra_type=type(extra_raw).__name__,
                renpy_type=type(renpy).__name__,
            )

        pair = renpy.get("pair", {})
        slots = renpy.get("slots", [])
        block = renpy.get("block", {})
        if not isinstance(pair, dict) or not isinstance(slots, list) or not isinstance(block, dict):
            return self._debug_skip(
                item,
                "invalid_pair_slots_or_block",
                mode="loose",
                pair_type=type(pair).__name__,
                slots_type=type(slots).__name__,
                block_type=type(block).__name__,
            )

        template_line = pair.get("template_line")
        target_line = pair.get("target_line")
        if not isinstance(template_line, int) or not isinstance(target_line, int):
            return self._debug_skip(
                item,
                "invalid_line_number_type",
                mode="loose",
                template_line=template_line,
                target_line=target_line,
            )
        if template_line <= 0 or target_line <= 0:
            return self._debug_skip(
                item,
                "line_number_non_positive",
                mode="loose",
                template_line=template_line,
                target_line=target_line,
            )
        if template_line > len(lines) or target_line > len(lines):
            return self._debug_skip(
                item,
                "line_out_of_range",
                mode="loose",
                template_line=template_line,
                target_line=target_line,
                total_lines=len(lines),
            )

        replacement_by_index = self._build_replacements(item, slots)
        if not replacement_by_index:
            return self._debug_skip(
                item,
                "no_replacements",
                mode="loose",
                slots_count=len(slots),
            )

        target_raw = lines[target_line - 1]
        target_indent, target_rest = split_indent(target_raw)

        kind = block.get("kind")
        kind_str = str(kind) if kind is not None else ""

        if kind_str == "STRINGS":
            base_code = target_rest
        else:
            template_raw = lines[template_line - 1]
            _, template_rest = split_indent(template_raw)
            is_comment, template_code = strip_comment_prefix(template_rest)
            base_code = template_code if is_comment else target_rest

        new_code = self._replace_literals_by_index(base_code, replacement_by_index)
        lines[target_line - 1] = f"{target_indent}{new_code}"
        return True

    def _build_replacements(self, item: CacheItem, slots: list) -> dict[int, str]:
        result: dict[int, str] = {}
        for s in slots:
            if not isinstance(s, dict):
                continue
            role = s.get("role")
            idx = s.get("lit_index")
            if not isinstance(idx, int):
                continue

            role_str = ""
            if role is not None:
                if hasattr(role, "value"):
                    role_str = str(role.value)
                else:
                    role_str = str(role)
            if role_str.startswith("TlSlotRole."):
                role_str = role_str.split(".", 1)[1]
            if role_str == "NAME":
                name_dst_raw = item.get_name_dst()
                if isinstance(name_dst_raw, str) and name_dst_raw != "":
                    result[idx] = name_dst_raw
            elif role_str in {"DIALOGUE", "STRING"}:
                result[idx] = item.get_dst()

        return result

    def _replace_literals_by_index(self, code: str, replacements: dict[int, str]) -> str:
        literals = scan_quoted_literals(code)
        if not literals:
            return code

        parts: list[str] = []
        pos = 0
        for i, lit in enumerate(literals):
            parts.append(code[pos:lit.start_col])
            if i in replacements:
                inner = escape_tl_string(replacements[i])
                parts.append(f'"{inner}"')
            else:
                parts.append(code[lit.start_col:lit.end_col])
            pos = lit.end_col
        parts.append(code[pos:])

        return "".join(parts)
