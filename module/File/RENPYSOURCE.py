from __future__ import annotations

import json
from pathlib import Path
from typing import List, Set

from base.Base import Base
from module.Cache.CacheItem import CacheItem
from module.Config import Config
from module.Engine.Engine import Engine
from module.File import WritebackVerdict
from module.Translate.RenpySourceTranslator import RenpySourceTranslator
from module.File.AtomicWrite import atomic_write_text, validate_write_path

# 只有"已翻译"类状态才值得人工复核：写回后仍落进 stale/unapplied 时进 needs_review，
# 避免把从未翻译或已排除的条目也当成异常上报。
REVIEW_STATUSES = frozenset({
    Base.TranslationStatus.TRANSLATED,
    Base.TranslationStatus.POLISHED,
    Base.TranslationStatus.TRANSLATED_IN_PAST,
})


class RENPYSOURCE(Base):
    """Ren'Py 源码翻译读写器"""

    def __init__(self, config: Config) -> None:
        super().__init__()
        self.config = config
        self.input_path = Path(config.input_folder)
        self.output_path = Path(config.output_folder)

    def _build_text_preserve_set(self) -> Set[str]:
        """构建禁翻表集合"""
        preserves: Set[str] = set()
        if not getattr(self.config, "text_preserve_enable", False):
            return preserves
        for item in getattr(self.config, "text_preserve_data", []) or []:
            src = item.get("src", "") if isinstance(item, dict) else str(item)
            if src:
                preserves.add(src.strip())
        return preserves

    def _relative_to_input(self, path: Path) -> str:
        try:
            if self.input_path.is_file():
                rel = path.name
            else:
                rel = path.relative_to(self.input_path)
        except ValueError:
            rel = path.name
        return str(rel).replace("\\", "/")

    def _is_in_tl_dir(self, path: Path) -> bool:
        """跳过 tl 目录，避免翻译已存在的翻译文件"""
        parts = [p.lower() for p in path.parts]
        return "tl" in parts

    def _resolve_source_path(self, rel_path: str) -> Path:
        target_path = self.output_path / rel_path
        if target_path.exists():
            return target_path
        if self.input_path.is_file():
            return self.input_path
        return self.input_path / rel_path

    def _resolve_reference_path(self, rel_path: str) -> Path:
        """返回原始输入源码路径，用于写回时恢复代码骨架。"""
        if self.input_path.is_file():
            return self.input_path
        return self.input_path / rel_path

    @staticmethod
    def _literal_slot(line: str, text: str, occurrence: int = 0) -> int | None:
        """Return the quoted-literal slot containing a parser entry."""
        matches = list(RenpySourceTranslator.RE_SINGLE_LINE_STRING_LITERAL.finditer(line))
        matching_slots = [
            index for index, match in enumerate(matches) if match.group("text") == text
        ]
        if 0 <= occurrence < len(matching_slots):
            return matching_slots[occurrence]
        return None

    @staticmethod
    def _literal_slot_has_destination(
        translator: RenpySourceTranslator,
        line: str,
        slot: int,
        destination: str,
    ) -> bool:
        matches = list(translator.RE_SINGLE_LINE_STRING_LITERAL.finditer(line))
        if slot < 0 or slot >= len(matches):
            return False
        literal = matches[slot]
        current = literal.group(0)
        expected = translator._replace_text_in_line(
            current, literal.group("text"), destination
        )
        return current == expected

    @staticmethod
    def _recorded_literal_slot(item: CacheItem) -> int | None:
        extra = item.get_extra_field()
        if not isinstance(extra, dict):
            return None
        source_meta = extra.get("renpy_source")
        if not isinstance(source_meta, dict):
            return None
        candidate = source_meta.get("literal_slot")
        return candidate if isinstance(candidate, int) else None

    @staticmethod
    def _replace_literal_at_slot(
        translator: RenpySourceTranslator,
        line: str,
        slot: int,
        source: str,
        destination: str,
    ) -> str:
        matches = list(translator.RE_SINGLE_LINE_STRING_LITERAL.finditer(line))
        if slot < 0 or slot >= len(matches):
            return line
        literal = matches[slot]
        if literal.group("text") != source:
            return line
        current = literal.group(0)
        replacement = translator._replace_text_in_line(
            current, source, destination
        )
        if replacement == current:
            return line
        return line[:literal.start()] + replacement + line[literal.end():]

    @classmethod
    def _line_has_only_destination(
        cls,
        translator: RenpySourceTranslator,
        line: str,
        destination: str,
    ) -> bool:
        """行内只有一个字符串字面量，且该字面量已经是目标译文。"""
        matches = list(translator.RE_SINGLE_LINE_STRING_LITERAL.finditer(line))
        if len(matches) != 1:
            return False
        return cls._literal_slot_has_destination(translator, line, 0, destination)

    @staticmethod
    def _matches_expected_rewrite(
        translator: RenpySourceTranslator,
        reference_line: str | None,
        current_line: str,
        source: str,
        destination: str,
    ) -> bool:
        """输出行是否正好等于「原始行替换后应得的结果」。"""
        if reference_line is None or source not in reference_line:
            # 参考行里没有原文时替换是空操作，未翻译行会和自己相等，必须先排除。
            return False
        expected = translator._replace_text_in_line(reference_line, source, destination)
        expected = translator._restore_non_literal_structure(reference_line, expected)
        return expected == current_line

    def read_from_path(self, abs_paths: List[str]) -> List[CacheItem]:
        """读取 .rpy 源码并生成 CacheItem"""
        items: List[CacheItem] = []
        parser = RenpySourceTranslator()

        preserves = self._build_text_preserve_set()
        if preserves and hasattr(parser, "set_text_preserve"):
            parser.set_text_preserve(preserves)

        from module.Extract.RpyExtractionSettings import selection_for_path, scan_source
        root, mode, profile = selection_for_path(self.input_path, 'source')
        custom = {}
        base = root / 'game' if (root / 'game').is_dir() else (self.input_path.parent if self.input_path.is_file() else self.input_path)
        if mode != 'builtin':
            scan = scan_source(root, profile, lambda: Engine.get().get_status() == Engine.Status.STOPPING, base=base, paths=abs_paths)
            for candidate in scan.candidates:
                custom.setdefault((base / candidate.path).resolve(), []).append(candidate)

        total_files = len(abs_paths)
        for index, abs_path in enumerate(abs_paths, start = 1):
            if Engine.get().get_status() == Engine.Status.STOPPING:
                self.info("源码扫描已停止")
                break

            if index == 1 or index % 5 == 0 or index == total_files:
                self.emit(Base.Event.TRANSLATION_UPDATE, {
                    "phase": "preparing",
                    "message": f"正在扫描源码文件… {index}/{total_files}",
                })

            path = Path(abs_path)
            if not path.is_file():
                continue
            if self._is_in_tl_dir(path):
                continue

            rel_path = self._relative_to_input(path)
            entries = parser.scan_file(path) if mode != 'custom' else []

            selected_slots = set()
            entry_occurrences: dict[tuple[int, str], int] = {}
            for entry in entries:
                text = (entry.text or "").strip()
                if not entry.needs_translation or text == "":
                    continue
                occurrence_key = (entry.line_number, entry.text)
                occurrence = entry_occurrences.get(occurrence_key, 0)
                literal_slot = self._literal_slot(
                    entry.original_line, entry.text, occurrence
                )
                entry_occurrences[occurrence_key] = occurrence + 1
                selected_slots.add((entry.line_number, literal_slot))
                items.append(
                    CacheItem.from_dict(
                        {
                            "src": entry.text,
                            "dst": entry.text,
                            "row": entry.line_number,
                            "file_type": CacheItem.FileType.RENPYSOURCE,
                            "file_path": rel_path,
                            "text_type": CacheItem.TextType.RENPY,
                            "status": Base.TranslationStatus.UNTRANSLATED,
                            "extra_field": {
                                "renpy_source": {
                                    "line": entry.line_number,
                                    "line_type": getattr(entry.line_type, "name", str(entry.line_type)),
                                    "literal_slot": literal_slot,
                                }
                            },
                        }
                    )
                )

            if custom.get(path.resolve()):
                fallback_lines = None
                for candidate in custom[path.resolve()]:
                    # 规则扫描已经保留了命中行，避免为定位槽位再次读取整个文件。
                    line = candidate.line_text
                    if not line:
                        if fallback_lines is None:
                            fallback_lines = path.read_text(encoding='utf-8-sig').splitlines()
                        if candidate.line <= 0 or candidate.line > len(fallback_lines):
                            continue
                        line = fallback_lines[candidate.line - 1]
                    literals = list(parser.RE_SINGLE_LINE_STRING_LITERAL.finditer(line))
                    slot = next((i for i, m in enumerate(literals) if m.span() == (candidate.start, candidate.end)), None)
                    if slot is None or (candidate.line, slot) in selected_slots or candidate.text.strip() in preserves:
                        continue
                    selected_slots.add((candidate.line, slot))
                    items.append(CacheItem.from_dict({
                        'src': candidate.raw_text, 'dst': candidate.raw_text, 'row': candidate.line,
                        'file_type': CacheItem.FileType.RENPYSOURCE, 'file_path': rel_path,
                        'text_type': CacheItem.TextType.RENPY, 'status': Base.TranslationStatus.UNTRANSLATED,
                        'extra_field': {'renpy_source': {'line': candidate.line, 'line_type': 'CUSTOM', 'literal_slot': slot}},
                    }))

        items.sort(key=lambda item: (item.get_file_path(), item.get_row()))
        return items

    def write_to_path(self, items: List[CacheItem]) -> None:
        """将翻译结果写回源码文件"""
        target = [
            item for item in items
            if item.get_file_type() == CacheItem.FileType.RENPYSOURCE
        ]
        if not target:
            return

        grouped: dict[str, list[CacheItem]] = {}
        for item in target:
            grouped.setdefault(item.get_file_path(), []).append(item)

        translator = RenpySourceTranslator()
        report: list[dict] = []
        errors: list[str] = []

        for rel_path, group_items in grouped.items():
            target_path = self.output_path / rel_path
            try:
                validate_write_path(target_path, [self.output_path])
            except Exception as exc:
                self.error(f"写入 Ren'Py 源码失败: {target_path}", exc)
                errors.append(f"写入失败 {target_path}: {exc}")
                continue

            source_path = self._resolve_source_path(rel_path)
            if not source_path.exists():
                self.warning(f"RENPY 源码不存在: {source_path}")
                errors.append(f"源文件不存在: {source_path}")
                continue

            reference_path = self._resolve_reference_path(rel_path)

            try:
                text = source_path.read_text(encoding="utf-8", errors="replace")
            except Exception as exc:
                self.error(f"读取 Ren'Py 源码失败: {source_path}", exc)
                errors.append(f"读取失败 {source_path}: {exc}")
                continue

            reference_lines: list[str] | None = None
            if reference_path.exists():
                try:
                    reference_text = reference_path.read_text(encoding="utf-8", errors="replace")
                    reference_lines = reference_text.split("\n")
                except Exception:
                    reference_lines = None

            lines = text.split("\n")
            # 本组条目开始前的输出行快照：用于识别同一行多条被前序条目消费的情况。
            baseline_lines = list(lines)
            applied = 0
            already_applied = 0
            skipped = 0
            translated_items = 0
            no_translation = 0
            untranslatable = 0
            # 残留条目先记完整对象，写盘后还能回头取证改判（见下方结果取证层）。
            stale_items: list[dict] = []
            unapplied_entries: list[dict] = []
            benign_samples: list[dict] = []

            def record_benign(kind: str, row: int, src: str) -> None:
                """留前几条良性残留样例，方便用户核对报告。"""
                if len(benign_samples) >= 5:
                    return
                benign_samples.append(
                    {
                        "kind": kind,
                        "row": row,
                        "src": WritebackVerdict.truncate_sample(src),
                    }
                )

            def record_stale(item: CacheItem, row: int, src: str, dst: str) -> None:
                stale_items.append({"item": item, "row": row, "src": src, "dst": dst})
                record_benign("stale", row, src)

            group_items.sort(key=lambda item: item.get_row())
            for item in group_items:
                src = item.get_src()
                dst = item.get_dst()
                row = item.get_row()
                if not isinstance(src, str) or src.strip() == "":
                    skipped += 1
                    continue
                if not isinstance(dst, str) or dst.strip() == "":
                    skipped += 1
                    continue

                if dst == src:
                    # 缓存里本来就没有译文：无字符文本单独计数，不和真实失败混在一起。
                    if WritebackVerdict.is_untranslatable_markup(src):
                        untranslatable += 1
                        record_benign("untranslatable", row, src)
                    else:
                        no_translation += 1
                        record_benign("no_translation", row, src)
                    skipped += 1
                    continue

                translated_items += 1

                if row <= 0 or row > len(lines):
                    record_stale(item, row, src, dst)
                    skipped += 1
                    continue

                current_line = lines[row - 1]
                baseline_line = baseline_lines[row - 1]
                reference_line = (
                    reference_lines[row - 1]
                    if reference_lines is not None and row <= len(reference_lines)
                    else None
                )

                literal_slot = self._recorded_literal_slot(item)
                if literal_slot is None and reference_line is not None:
                    matching_slots = [
                        index
                        for index, match in enumerate(
                            translator.RE_SINGLE_LINE_STRING_LITERAL.finditer(
                                reference_line
                            )
                        )
                        if match.group("text") == src
                    ]
                    if len(matching_slots) == 1:
                        literal_slot = matching_slots[0]

                # 判定 1：译文已经在位。有槽位时只看本槽位，避免把同一行其他
                # 槽位里的译文误判成本条已生效。
                if literal_slot is not None and self._literal_slot_has_destination(
                    translator, current_line, literal_slot, dst
                ):
                    already_applied += 1
                    continue
                # 未翻译行（与原始行完全相同）不可能是"已经生效"的终点，先跳过判定省开销。
                if (
                    reference_line is None or current_line != reference_line
                ) and (
                    self._line_has_only_destination(translator, current_line, dst)
                    or self._matches_expected_rewrite(
                        translator, reference_line, current_line, src, dst
                    )
                ):
                    # 无槽位条目：单字面量行已是译文，或输出行正好等于原始行替换结果。
                    already_applied += 1
                    continue

                if literal_slot is not None:
                    new_line = self._replace_literal_at_slot(
                        translator,
                        current_line,
                        literal_slot,
                        src,
                        dst,
                    )
                else:
                    new_line = translator._replace_text_in_line(
                        current_line, src, dst
                    )
                if reference_line is not None:
                    # 用原始源码恢复非字符串代码结构，避免 screen action 等表达式被污染。
                    new_line = translator._restore_non_literal_structure(
                        reference_line, new_line
                    )

                if new_line == current_line and literal_slot is not None:
                    # 记录的槽位可能已随行内容变动失效，退回全文替换再试一次。
                    new_line = translator._replace_text_in_line(
                        current_line, src, dst
                    )
                    if reference_line is not None:
                        new_line = translator._restore_non_literal_structure(
                            reference_line, new_line
                        )

                if new_line != current_line:
                    lines[row - 1] = new_line
                    applied += 1
                    continue

                # 判定 2：本行没有变化，按证据区分良性残留与真实失败。
                if (
                    current_line != baseline_line
                    and src in baseline_line
                    and src not in current_line
                ):
                    # 同一行有多条条目，本条的 src 已被前序条目消费掉。
                    already_applied += 1
                    continue
                if src not in current_line and not (
                    reference_line is not None and src in reference_line
                ):
                    # 当前输出行与原始源码里都没有该原文：陈旧缓存，不算失败。
                    record_stale(item, row, src, dst)
                    skipped += 1
                    continue

                # 判定 3：原文确实存在但替换没有落地，属于真实未生效。
                unapplied_entries.append(
                    {"item": item, "row": row, "src": src, "dst": dst}
                )

            # 写回前备份（仅本地 .bak）
            if self.config.renpy_backup_original:
                bak_path = target_path.with_suffix(target_path.suffix + ".bak")
                if target_path.exists() and not bak_path.exists():
                    try:
                        atomic_write_text(
                            bak_path,
                            target_path.read_text(encoding="utf-8", errors="replace"),
                            allowed_roots=[self.output_path],
                        )
                    except Exception:
                        pass

            try:
                atomic_write_text(
                    target_path,
                    "\n".join(lines),
                    allowed_roots=[self.output_path],
                )
            except Exception as exc:
                self.error(f"写入 Ren'Py 源码失败: {target_path}", exc)
                errors.append(f"写入失败 {target_path}: {exc}")
                continue

            # ===== 结果取证层 =====
            # 行漂（上游 .rpy 插删行导致缓存行号/文本对不上）时，译文往往已经在
            # 文件里了，只是不在缓存指认的那一行。此时把它们当失败会误报，用户
            # 还会看到"已翻译 100%"却在导出文件里读到英文。这里对刚写好的内容做
            # 一次字面量取证：dst 在文件里真实存在，就改判 already_applied。
            if stale_items:
                literal_texts: Set[str] = set()
                for probe_line in lines:
                    for match in RenpySourceTranslator.RE_SINGLE_LINE_STRING_LITERAL.finditer(
                        probe_line
                    ):
                        literal_texts.add(
                            WritebackVerdict.normalize_compare_value(match.group("text"))
                        )

                if literal_texts:
                    def exists_in_file(dst: str) -> bool:
                        normalized = WritebackVerdict.normalize_compare_value(dst)
                        return normalized != "" and normalized in literal_texts

                    kept_stale: list[dict] = []
                    reclassified = 0
                    for entry_file in stale_items:
                        if exists_in_file(entry_file["dst"]):
                            already_applied += 1
                            reclassified += 1
                            record_benign("already_in_file", entry_file["row"], entry_file["src"])
                        else:
                            kept_stale.append(entry_file)
                    stale_items = kept_stale
                    # 注意：unapplied 不做取证改判。unapplied 意味着原文还留在文件里
                    # （或参考行里仍有原文却没替换成功），译文出现在同一行别的槽位
                    # 属于巧合，不能当成"已生效"，否则会放过真实失败。
                    # stale 条目先前计过 skipped，改判为已生效后要把这笔账退回去。
                    skipped = max(skipped - reclassified, 0)

            stale = len(stale_items)
            unapplied_items: list[dict] = [
                {
                    "row": entry["row"],
                    "src": WritebackVerdict.truncate_sample(entry["src"]),
                    "dst": WritebackVerdict.truncate_sample(entry["dst"]),
                }
                for entry in unapplied_entries
            ]
            # 状态标着"已翻译"却没能落地的条目，单独列出来供人工复核；
            # 这里只读状态、绝不改状态。
            review_sources = [(entry, "stale") for entry in stale_items] + [
                (entry, "unapplied") for entry in unapplied_entries
            ]
            needs_review: list[dict] = [
                {
                    "row": entry["row"],
                    "src": WritebackVerdict.truncate_sample(entry["src"]),
                    "dst": WritebackVerdict.truncate_sample(entry["dst"]),
                    "status": str(entry["item"].get_status()),
                    "reason": reason,
                }
                for entry, reason in review_sources
                if entry["item"].get_status() in REVIEW_STATUSES
            ]

            if unapplied_items:
                samples = "、".join(
                    f"{entry['row']}:{entry['src']}->{entry['dst']}"
                    for entry in unapplied_items[:3]
                )
                errors.append(
                    f"译文未生效 {rel_path} (translated={translated_items}, "
                    f"applied={applied}, already_applied={already_applied}, "
                    f"unapplied={len(unapplied_items)}, skipped={skipped})"
                    + (f"；样例 {samples}" if samples else "")
                )

            if stale > 0 or untranslatable > 0:
                # 这些是良性残留，不抛错，但必须让用户在 console 上看见。
                # no_translation 不触发告警：部分翻译的项目每次导出都会有大量
                # 未翻译条目，按它告警等于制造噪音。
                self.warning(
                    f"RENPYSOURCE 写回跳过 {stale + untranslatable + no_translation} 条良性残留: {rel_path} "
                    f"(stale={stale}, untranslatable={untranslatable}, no_translation={no_translation})"
                )

            report.append(
                {
                    "file": rel_path,
                    "source": str(source_path),
                    "target": str(target_path),
                    "items": len(group_items),
                    "translated_items": translated_items,
                    "applied": applied,
                    "already_applied": already_applied,
                    "skipped": skipped,
                    "no_translation": no_translation,
                    "untranslatable": untranslatable,
                    "stale": stale,
                    "unapplied": len(unapplied_items),
                    "unapplied_items": unapplied_items,
                    "benign_samples": benign_samples,
                    "needs_review": needs_review,
                }
            )

        if report:
            report_path = self.output_path / "writeback_report_renpy_source.json"
            try:
                atomic_write_text(
                    report_path,
                    json.dumps(report, ensure_ascii=False, indent=2),
                    allowed_roots=[self.output_path],
                )
            except Exception:
                pass
        if errors:
            raise RuntimeError("Ren'Py 源码写回未完整完成：" + "；".join(errors))
