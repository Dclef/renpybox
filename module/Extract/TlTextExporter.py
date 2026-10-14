# -*- coding: utf-8 -*-
"""
TL 待翻译文本导出/回填（工作流模块）。

供工具箱“网页/AI 翻译向导”使用：
- extract_pending_from_tl: 扫描 game/tl/<lang>，挑出官方抽取产生、
  new 为空（或与 old 相同）的条目，写成带行号清单 + 纯文本 TXT。
- apply_translations_to_tl: 读取翻译完成的 TXT（每行一条，与导出的清单一一对应），
  按行号把译文写回对应文件的 new 字段，生成新 TL 目录（不覆盖原目录）。

只处理官方抽取结果：带 `renpybox: replace-only` 标记的补充抽取条目
（依赖运行时 replace_text 兜底，不应进入 TL 翻译工作流）一律跳过。

写入边界：
- manifest 保存可信 tl_root；兼容旧 list 清单（需安全推导或显式 source_tl_dir）
- 任何 copy/rmtree/写前全量校验 seq/index/file containment/槽位原文
- 输出暂存在 game 外，全部成功后原子替换；失败保留原输出
- 源 TL 不改；只删除输出侧配对 RPYC
- 原文含真实换行时拒绝（一条一行 TXT 契约），不打乱序号
"""

from __future__ import annotations

import json
import os
import re
import shutil
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional, Sequence, Tuple

from base.LogManager import LogManager
from module.Renpy.renpy_tl_core import RENPYBOX_REPLACE_ONLY_MARKER

logger = LogManager.get()

_OLD_RE = re.compile(r'^(?P<indent>\s*)old\s+(?P<quote>["\'])(?P<text>(?:\\.|(?!\2).)*?)(?P=quote)\s*$')
_NEW_RE = re.compile(r'^(?P<indent>\s*)new\s+(?P<quote>["\'])(?P<text>(?:\\.|(?!\2).)*?)(?P=quote)\s*$')
_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
_MANIFEST_VERSION = 1


@dataclass
class PendingEntry:
    """一条待翻译条目。"""

    seq: int
    file_path: Path
    new_line_index: int
    old_text: str


class TlTextExporterError(ValueError):
    """TL 导出/回填业务错误。"""


def _decode_literal(quote: str, text: str) -> str:
    """解码 rpy 字符串字面量内容。"""
    import ast

    try:
        return ast.literal_eval(f"{quote}{text}{quote}")
    except Exception:
        return text.replace('\\"', '"').replace("\\'", "'").replace("\\n", "\n")


def _escape_literal(text: str) -> str:
    """把真实文本转义为可写入 rpy 双引号字面量的内容。"""
    return (
        text.replace("\\", "\\\\")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\n", "\\n")
        .replace('"', '\\"')
    )


def _is_replace_only(lines: List[str], old_idx: int) -> bool:
    """判断 old 行是否属于补充抽取（replace-only）条目。"""
    cursor = old_idx - 1
    while cursor >= 0:
        stripped = lines[cursor].strip()
        if not stripped or stripped.startswith("# game/"):
            cursor -= 1
            continue
        return stripped == f"# {RENPYBOX_REPLACE_ONLY_MARKER}"
    return False


def _path_key(path: Path) -> str:
    return os.path.normcase(os.path.abspath(str(path))).rstrip("\\/")


def _is_link(path: Path) -> bool:
    try:
        if path.is_symlink():
            return True
    except OSError:
        return True
    try:
        return bool(path.lstat().st_file_attributes & _REPARSE_POINT)  # type: ignore[attr-defined]
    except (AttributeError, OSError):
        return False


def _within(root: Path, child: Path) -> bool:
    try:
        child.resolve().relative_to(root.resolve())
        return True
    except (ValueError, OSError):
        return False


def _paths_overlap(a: Path, b: Path) -> bool:
    """相同或祖孙重叠。"""
    ka, kb = _path_key(a), _path_key(b)
    if ka == kb:
        return True
    sep = os.sep
    return ka.startswith(kb + sep) or kb.startswith(ka + sep)


def _is_dangerous_output(path: Path) -> bool:
    """拒绝磁盘根、名为 game 的目录本身等危险输出目标。"""
    resolved = path.expanduser()
    try:
        resolved = resolved.resolve(strict=False)
    except OSError as exc:
        raise TlTextExporterError(f"输出路径无效: {path}") from exc
    text = str(resolved)
    if not text or text.rstrip("\\/") in {resolved.anchor.rstrip("\\/"), ""}:
        return True
    if resolved.name.lower() == "game":
        return True
    return False


def resolve_tl_lang_dir(path: Path) -> Path:
    """从 TL 内任意文件/目录上溯到 tl/<lang>。"""
    current = path if path.is_dir() else path.parent
    while current != current.parent:
        if current.parent.name.lower() == "tl":
            return current
        current = current.parent
    raise TlTextExporterError(f"无法从路径推导 tl/<语言> 根: {path}")


def default_translated_output(source_tl: Path) -> Path:
    """原 TL 同级 <lang>_translated。"""
    lang_dir = resolve_tl_lang_dir(source_tl)
    return lang_dir.parent / f"{lang_dir.name}_translated"


def resolve_apply_output_dir(
    manifest_path: str | Path,
    output_tl_dir: str | Path | None = None,
) -> Path:
    """解析回填输出目录；空值时推导同级 <lang>_translated，再回退 translated_tl。"""
    manifest_path = Path(manifest_path)
    text = str(output_tl_dir or "").strip()
    if text:
        return Path(text).expanduser()
    try:
        embedded, entries = _load_manifest_document(manifest_path)
        if embedded is not None:
            return default_translated_output(embedded)
        if entries:
            return default_translated_output(Path(str(entries[0]["file"])))
    except Exception:
        pass
    return manifest_path.parent / "translated_tl"


def _staging_base(source_tl: Path, output_tl: Path) -> Path:
    """暂存/备份放在 game 外，避免 Ren'Py 加载中间脚本。"""
    for candidate in (source_tl, output_tl, *source_tl.parents, *output_tl.parents):
        if candidate.name.lower() == "game":
            return candidate.parent
    return Path(tempfile.gettempdir())


def _load_manifest_document(manifest_path: Path) -> tuple[Path | None, list[dict[str, Any]]]:
    """读取清单：新格式 {tl_root, entries} 或旧 list。"""
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    if isinstance(raw, list):
        return None, raw
    if isinstance(raw, dict):
        entries = raw.get("entries")
        if not isinstance(entries, list):
            raise TlTextExporterError("清单格式无效：缺少 entries 列表")
        tl_root_raw = raw.get("tl_root")
        tl_root = Path(str(tl_root_raw)) if tl_root_raw else None
        return tl_root, entries
    raise TlTextExporterError("清单格式无效")


def _derive_tl_root(
    entries: Sequence[dict[str, Any]],
    *,
    source_tl_dir: str | Path | None,
    embedded_root: Path | None,
) -> Path:
    """绑定可信 TL 根：优先显式参数，其次清单内嵌，最后安全上溯。"""
    if source_tl_dir is not None and str(source_tl_dir).strip():
        root = Path(source_tl_dir).expanduser().resolve(strict=False)
        if not root.is_dir():
            raise TlTextExporterError(f"源 TL 目录不存在: {root}")
        return root
    if embedded_root is not None and str(embedded_root).strip():
        root = Path(embedded_root).expanduser().resolve(strict=False)
        if not root.is_dir():
            raise TlTextExporterError(f"清单中的 TL 根不存在: {root}")
        return root
    if not entries:
        raise TlTextExporterError("清单为空")
    try:
        first = Path(str(entries[0]["file"]))
    except (KeyError, TypeError) as exc:
        raise TlTextExporterError("清单条目缺少 file") from exc
    return resolve_tl_lang_dir(first)


def _find_old_for_new(lines: Sequence[str], new_idx: int) -> str | None:
    """从 new 行向上找最近的 old 原文。"""
    cursor = new_idx - 1
    while cursor >= 0:
        match = _OLD_RE.match(lines[cursor])
        if match:
            return _decode_literal(match.group("quote"), match.group("text"))
        stripped = lines[cursor].strip()
        if stripped and not stripped.startswith("#"):
            # 中间夹了其它非注释语句，停止
            if _NEW_RE.match(lines[cursor]):
                cursor -= 1
                continue
            break
        cursor -= 1
    return None


def _validate_entries(
    entries: Sequence[dict[str, Any]],
    tl_root: Path,
) -> list[dict[str, Any]]:
    """写前全量校验清单项与源槽位身份；seq 必须为整数且恰好覆盖 0..n-1。"""
    if _is_link(tl_root) and not tl_root.is_dir():
        raise TlTextExporterError(f"源 TL 根无效或为断开链接: {tl_root}")
    if not tl_root.is_dir():
        raise TlTextExporterError(f"源 TL 目录不存在: {tl_root}")

    root_key = _path_key(tl_root)
    normalized: list[dict[str, Any]] = []
    file_cache: dict[str, list[str]] = {}
    seen_seq: set[int] = set()

    for item in entries:
        if not isinstance(item, dict):
            raise TlTextExporterError("清单条目必须是对象")
        try:
            seq_raw = item["seq"]
            idx_raw = item["new_line_index"]
            # 拒绝 bool（bool 是 int 子类）与字符串/浮点等宽松转换
            if isinstance(seq_raw, bool) or type(seq_raw) is not int:
                raise TypeError("seq 必须是整数")
            if isinstance(idx_raw, bool) or type(idx_raw) is not int:
                raise TypeError("new_line_index 必须是整数")
            seq = seq_raw
            new_line_index = idx_raw
            file_text = str(item["file"])
            old_text = str(item["old"])
        except (KeyError, TypeError, ValueError) as exc:
            raise TlTextExporterError("清单条目缺少或含有无效的 seq/file/new_line_index/old") from exc
        if seq < 0 or new_line_index < 0:
            raise TlTextExporterError(f"清单序号或行号不能为负: seq={seq}, new_line_index={new_line_index}")
        if seq in seen_seq:
            raise TlTextExporterError(f"清单序号重复: seq={seq}")
        seen_seq.add(seq)
        if "\n" in old_text or "\r" in old_text:
            raise TlTextExporterError(
                f"清单第 {seq} 条原文含真实换行，与一条一行 TXT 契约冲突，已拒绝"
            )

        src_file = Path(file_text)
        if not src_file.is_file():
            raise TlTextExporterError(f"清单文件不存在: {src_file}")
        if _is_link(src_file):
            # 允许指向 root 内的常规文件链接；越界拒绝
            if not _within(tl_root, src_file):
                raise TlTextExporterError(f"清单文件通过链接越出源 TL: {src_file}")
        if not _within(tl_root, src_file):
            raise TlTextExporterError(f"清单文件不在源 TL 根下: {src_file}")
        if src_file.suffix.lower() != ".rpy":
            raise TlTextExporterError(f"清单文件必须是 .rpy: {src_file}")

        key = _path_key(src_file)
        if key not in file_cache:
            try:
                file_cache[key] = src_file.read_text(encoding="utf-8", errors="replace").splitlines()
            except (OSError, UnicodeError) as exc:
                raise TlTextExporterError(f"读取源 TL 文件失败: {src_file}") from exc
        lines = file_cache[key]
        if new_line_index >= len(lines):
            raise TlTextExporterError(
                f"清单第 {seq} 条 new_line_index={new_line_index} 超出文件行数"
            )
        if not _NEW_RE.match(lines[new_line_index]):
            raise TlTextExporterError(
                f"清单第 {seq} 条指向的行已不是 new 槽位（文件可能已变更）"
            )
        actual_old = _find_old_for_new(lines, new_line_index)
        if actual_old is None or actual_old != old_text:
            raise TlTextExporterError(
                f"清单第 {seq} 条原文与源文件槽位不匹配（陈旧清单）"
            )

        normalized.append(
            {
                "seq": seq,
                "file": str(src_file.resolve()),
                "new_line_index": new_line_index,
                "old": old_text,
                "_root_key": root_key,
            }
        )

    expected = set(range(len(normalized)))
    if seen_seq != expected:
        missing = sorted(expected - seen_seq)
        extra = sorted(seen_seq - expected)
        detail_parts: list[str] = []
        if missing:
            detail_parts.append(f"缺号 {missing}")
        if extra:
            detail_parts.append(f"越界 {extra}")
        raise TlTextExporterError(
            "清单序号必须从 0 连续到 "
            f"{len(normalized) - 1}（{'; '.join(detail_parts) or '乱序/不连续'}）"
        )

    # 按 seq 排序后再应用，保证与译文 TXT 行序一致（输入可乱序）
    normalized.sort(key=lambda item: item["seq"])
    # 排序后仍要求逻辑连续；乱序输入已在集合校验通过后被重排
    for index, item in enumerate(normalized):
        if item["seq"] != index:
            raise TlTextExporterError(
                f"清单序号乱序或不连续: 期望 seq={index}，实际 seq={item['seq']}"
            )
    return normalized


def extract_pending_from_tl(
    tl_dir: str | Path,
    txt_output: str | Path,
    manifest_output: str | Path | None = None,
) -> Tuple[int, Path]:
    """扫描 TL 目录，把待翻译原文写入 TXT，并生成行号清单 JSON。

    Returns:
        (条目数, manifest 路径)
    """
    tl_dir = Path(tl_dir).expanduser()
    txt_output = Path(txt_output).expanduser()
    if manifest_output is None:
        manifest_output = txt_output.with_suffix(".manifest.json")
    manifest_output = Path(manifest_output).expanduser()

    if not tl_dir.is_dir():
        raise FileNotFoundError(f"TL 目录不存在: {tl_dir}")
    tl_root = tl_dir.resolve()

    entries: List[PendingEntry] = []
    seq = 0
    for rpy_file in sorted(tl_dir.rglob("*.rpy"), key=lambda p: p.as_posix()):
        if _is_link(rpy_file) and not _within(tl_root, rpy_file):
            continue
        try:
            lines = rpy_file.read_text(encoding="utf-8", errors="replace").splitlines()
        except (OSError, UnicodeError) as exc:
            logger.warning(f"读取 TL 文件失败 {rpy_file}: {exc}")
            continue

        idx = 0
        while idx < len(lines):
            old_match = _OLD_RE.match(lines[idx])
            if not old_match:
                idx += 1
                continue

            new_idx = None
            probe = idx + 1
            while probe < len(lines):
                stripped = lines[probe].strip()
                if not stripped or stripped.startswith("#"):
                    probe += 1
                    continue
                if _NEW_RE.match(lines[probe]):
                    new_idx = probe
                break

            if new_idx is None:
                idx += 1
                continue

            new_match = _NEW_RE.match(lines[new_idx])
            old_text = _decode_literal(old_match.group("quote"), old_match.group("text"))
            new_text = _decode_literal(new_match.group("quote"), new_match.group("text"))

            is_pending = (not new_text.strip()) or (new_text == old_text)
            if is_pending and not _is_replace_only(lines, idx):
                if "\n" in old_text or "\r" in old_text:
                    raise TlTextExporterError(
                        f"条目含真实换行，无法按一条一行 TXT 导出（文件 {rpy_file}）"
                    )
                entries.append(
                    PendingEntry(
                        seq=seq,
                        file_path=rpy_file.resolve(),
                        new_line_index=new_idx,
                        old_text=old_text,
                    )
                )
                seq += 1

            idx = new_idx + 1

    txt_output.parent.mkdir(parents=True, exist_ok=True)
    with open(txt_output, "w", encoding="utf-8", newline="\n") as writer:
        writer.write("\n".join(entry.old_text for entry in entries))

    manifest_doc = {
        "version": _MANIFEST_VERSION,
        "tl_root": str(tl_root),
        "entries": [
            {
                "seq": entry.seq,
                "file": str(entry.file_path),
                "new_line_index": entry.new_line_index,
                "old": entry.old_text,
            }
            for entry in entries
        ],
    }
    manifest_output.parent.mkdir(parents=True, exist_ok=True)
    manifest_output.write_text(
        json.dumps(manifest_doc, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    logger.info(f"已导出 {len(entries)} 条待翻译文本到 {txt_output}")
    return len(entries), manifest_output


def apply_translations_to_tl(
    manifest_path: str | Path,
    translated_txt: str | Path,
    output_tl_dir: str | Path,
    *,
    source_tl_dir: str | Path | None = None,
    confirm_overwrite: bool = False,
) -> Tuple[int, Path]:
    """按行号清单把译文 TXT 回填到 new 字段，生成新 TL 目录。

    Args:
        source_tl_dir: 可信原 TL 根；新清单可省略，旧 list 清单建议显式传入
        confirm_overwrite: 输出目录已存在时必须为 True

    Returns:
        (回填条目数, 输出目录)
    """
    manifest_path = Path(manifest_path).expanduser()
    translated_txt = Path(translated_txt).expanduser()
    output_tl_dir = Path(output_tl_dir).expanduser()

    if not manifest_path.is_file():
        raise FileNotFoundError(f"清单不存在: {manifest_path}")
    embedded_root, raw_entries = _load_manifest_document(manifest_path)
    if not raw_entries:
        raise TlTextExporterError("清单为空")

    tl_root = _derive_tl_root(
        raw_entries,
        source_tl_dir=source_tl_dir,
        embedded_root=embedded_root,
    )
    entries = _validate_entries(raw_entries, tl_root)

    if not translated_txt.is_file():
        # 缺少译文文件等同于零行，沿用行数契约返回可读的少于错误。
        raise TlTextExporterError(
            f"译文行数（0）少于待翻译条目数（{len(entries)}），译文 TXT 不存在: {translated_txt}"
        )
    with open(translated_txt, "r", encoding="utf-8") as reader:
        translated_lines = [line.rstrip("\n").rstrip("\r") for line in reader]

    # 译文行数必须严格等于条目数；空 TXT 仅在清单为空时允许
    if len(translated_lines) != len(entries):
        if len(translated_lines) < len(entries):
            raise TlTextExporterError(
                f"译文行数（{len(translated_lines)}）少于待翻译条目数（{len(entries)}），"
                "请确认 TXT 每行一条译文且与导出顺序一致。"
            )
        raise TlTextExporterError(
            f"译文行数（{len(translated_lines)}）多于待翻译条目数（{len(entries)}），"
            "多余行已拒绝，请确认 TXT 与清单一一对应。"
        )

    if _is_dangerous_output(output_tl_dir):
        raise TlTextExporterError(f"拒绝危险输出目录: {output_tl_dir}")
    if _paths_overlap(tl_root, output_tl_dir):
        raise TlTextExporterError("输出目录不能与源 TL 相同或形成祖孙重叠")
    # 也拒绝清掉 game / 项目根一类祖先
    for ancestor in tl_root.parents:
        if _path_key(ancestor) == _path_key(output_tl_dir):
            raise TlTextExporterError("输出目录不能是源 TL 的祖先目录")

    if output_tl_dir.exists():
        if not confirm_overwrite:
            raise TlTextExporterError(
                f"输出目录已存在，需确认覆盖: {output_tl_dir}"
            )
        if _is_link(output_tl_dir):
            raise TlTextExporterError(f"拒绝覆盖链接输出目录: {output_tl_dir}")

    staging_parent = _staging_base(tl_root, output_tl_dir)
    staging_parent.mkdir(parents=True, exist_ok=True)
    work_dir = Path(
        tempfile.mkdtemp(prefix=".renpybox-tl-apply-", dir=str(staging_parent))
    )
    stage_dir = work_dir / "stage"
    backup_dir = work_dir / "backup"
    filled = 0
    try:
        shutil.copytree(str(tl_root), str(stage_dir))

        by_file: dict[str, list[dict]] = {}
        for item in entries:
            by_file.setdefault(item["file"], []).append(item)

        for src_file_str, items in by_file.items():
            src_file = Path(src_file_str)
            rel = src_file.relative_to(tl_root)
            dst_file = stage_dir / rel
            try:
                lines = dst_file.read_text(encoding="utf-8", errors="replace").splitlines()
            except (OSError, UnicodeError) as exc:
                raise TlTextExporterError(f"读取暂存 TL 文件失败: {dst_file}") from exc

            changed = False
            for item in items:
                seq = item["seq"]
                new_line_index = item["new_line_index"]
                old_text = item["old"]
                if seq >= len(translated_lines):
                    continue
                translation = translated_lines[seq].strip()
                if not translation or translation == old_text:
                    continue
                if new_line_index >= len(lines):
                    raise TlTextExporterError(
                        f"回填时第 {seq} 条行号失效（暂存副本异常）"
                    )
                new_match = _NEW_RE.match(lines[new_line_index])
                if not new_match:
                    raise TlTextExporterError(
                        f"回填时第 {seq} 条已不是 new 槽位"
                    )
                indent = new_match.group("indent")
                lines[new_line_index] = f'{indent}new "{_escape_literal(translation)}"'
                changed = True
                filled += 1

            if changed:
                dst_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
                dst_file.with_suffix(".rpyc").unlink(missing_ok=True)

        # 全部暂存成功后再替换输出；失败保留原输出
        had_output = output_tl_dir.exists() or output_tl_dir.is_symlink()
        if had_output:
            try:
                output_tl_dir.replace(backup_dir)
            except OSError:
                shutil.copytree(str(output_tl_dir), str(backup_dir), symlinks=False)
                shutil.rmtree(str(output_tl_dir))

        try:
            try:
                stage_dir.replace(output_tl_dir)
            except OSError:
                shutil.copytree(str(stage_dir), str(output_tl_dir))
        except Exception:
            if output_tl_dir.exists() or output_tl_dir.is_symlink():
                shutil.rmtree(str(output_tl_dir), ignore_errors=True)
            if backup_dir.exists():
                try:
                    backup_dir.replace(output_tl_dir)
                except OSError:
                    shutil.copytree(str(backup_dir), str(output_tl_dir))
            raise

        logger.info(f"已回填 {filled} 条译文到 {output_tl_dir}")
        return filled, output_tl_dir.resolve()
    finally:
        shutil.rmtree(str(work_dir), ignore_errors=True)


__all__ = [
    "PendingEntry",
    "TlTextExporterError",
    "apply_translations_to_tl",
    "default_translated_output",
    "extract_pending_from_tl",
    "resolve_apply_output_dir",
    "resolve_tl_lang_dir",
]
