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
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from base.LogManager import LogManager
from module.Renpy.renpy_tl_core import RENPYBOX_REPLACE_ONLY_MARKER

logger = LogManager.get()

# 与 UnifiedExtractor 保持一致的 old/new 行解析（转义感知）
import re
_OLD_RE = re.compile(r'^(?P<indent>\s*)old\s+(?P<quote>["\'])(?P<text>(?:\\.|(?!\2).)*?)(?P=quote)\s*$')
_NEW_RE = re.compile(r'^(?P<indent>\s*)new\s+(?P<quote>["\'])(?P<text>(?:\\.|(?!\2).)*?)(?P=quote)\s*$')


@dataclass
class PendingEntry:
    """一条待翻译条目。"""
    seq: int            # 导出序号（0 起，与 TXT 行号一致）
    file_path: Path     # 所在 TL 文件
    new_line_index: int # new 行在文件 lines 中的下标
    old_text: str       # 原文


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


def extract_pending_from_tl(
    tl_dir: str | Path,
    txt_output: str | Path,
    manifest_output: str | Path | None = None,
) -> Tuple[int, Path]:
    """扫描 TL 目录，把待翻译原文写入 TXT，并生成行号清单 JSON。

    Args:
        tl_dir: game/tl/<lang> 目录
        txt_output: 输出的纯文本 TXT（每行一条原文）
        manifest_output: 行号清单 JSON 路径；默认与 TXT 同目录同名 .manifest.json

    Returns:
        (条目数, manifest 路径)
    """
    tl_dir = Path(tl_dir)
    txt_output = Path(txt_output)
    if manifest_output is None:
        manifest_output = txt_output.with_suffix(".manifest.json")
    manifest_output = Path(manifest_output)

    if not tl_dir.is_dir():
        raise FileNotFoundError(f"TL 目录不存在: {tl_dir}")

    entries: List[PendingEntry] = []
    seq = 0
    for rpy_file in sorted(tl_dir.rglob("*.rpy"), key=lambda p: p.as_posix()):
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

            # 找紧邻的 new 行
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

            # 只收官方抽取的空位（new 为空或与 old 相同），跳过补充抽取标记
            is_pending = (not new_text.strip()) or (new_text == old_text)
            if is_pending and not _is_replace_only(lines, idx):
                entries.append(PendingEntry(
                    seq=seq,
                    file_path=rpy_file,
                    new_line_index=new_idx,
                    old_text=old_text,
                ))
                seq += 1

            idx = new_idx + 1

    # 写 TXT：每行一条原文
    txt_output.parent.mkdir(parents=True, exist_ok=True)
    with open(txt_output, "w", encoding="utf-8") as writer:
        writer.write("\n".join(entry.old_text for entry in entries))

    # 写行号清单
    manifest = [
        {
            "seq": entry.seq,
            "file": str(entry.file_path),
            "new_line_index": entry.new_line_index,
            "old": entry.old_text,
        }
        for entry in entries
    ]
    manifest_output.parent.mkdir(parents=True, exist_ok=True)
    manifest_output.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    logger.info(f"已导出 {len(entries)} 条待翻译文本到 {txt_output}")
    return len(entries), manifest_output


def apply_translations_to_tl(
    manifest_path: str | Path,
    translated_txt: str | Path,
    output_tl_dir: str | Path,
) -> Tuple[int, Path]:
    """按行号清单把译文 TXT 回填到 new 字段，生成新 TL 目录。

    Args:
        manifest_path: extract_pending_from_tl 生成的 .manifest.json
        translated_txt: 翻译完成的 TXT（每行一条译文，与导出顺序一致）
        output_tl_dir: 输出目录（原 TL 会被整体复制到这里再回填，不动原目录）

    Returns:
        (回填条目数, 输出目录)
    """
    manifest_path = Path(manifest_path)
    translated_txt = Path(translated_txt)
    output_tl_dir = Path(output_tl_dir)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, list):
        raise ValueError("清单格式无效")

    with open(translated_txt, "r", encoding="utf-8") as reader:
        translated_lines = [line.rstrip("\n").rstrip("\r") for line in reader]

    if len(translated_lines) < len(manifest):
        raise ValueError(
            f"译文行数（{len(translated_lines)}）少于待翻译条目数（{len(manifest)}），"
            "请确认 TXT 每行一条译文且与导出顺序一致。"
        )

    # 计算原 TL 根目录（manifest 里 file 字段的公共祖先）
    file_paths = [Path(item["file"]) for item in manifest]
    if not file_paths:
        raise ValueError("清单为空")
    tl_root = file_paths[0].parent
    # TL 根目录是 tl/<lang>，file 在其子目录；上溯到 <lang> 这一级
    # manifest 的 file 可能是 tl/<lang>/xxx.rpy 或 tl/<lang>/sub/xxx.rpy
    # 公共前缀即 tl/<lang>
    import os
    common = Path(os.path.commonpath([str(p) for p in file_paths]))
    # common 可能是文件本身（单文件时），取目录
    tl_root = common if common.is_dir() else common.parent

    # 整体复制原 TL 到输出目录
    if output_tl_dir.exists():
        shutil.rmtree(str(output_tl_dir))
    shutil.copytree(str(tl_root), str(output_tl_dir))

    # 按文件分组回填
    by_file: dict[str, list[dict]] = {}
    for item in manifest:
        by_file.setdefault(item["file"], []).append(item)

    filled = 0
    for src_file_str, items in by_file.items():
        src_file = Path(src_file_str)
        rel = src_file.relative_to(tl_root)
        dst_file = output_tl_dir / rel

        try:
            lines = dst_file.read_text(encoding="utf-8", errors="replace").splitlines()
        except (OSError, UnicodeError) as exc:
            logger.warning(f"读取输出 TL 文件失败 {dst_file}: {exc}")
            continue

        changed = False
        for item in items:
            seq = item["seq"]
            new_line_index = item["new_line_index"]
            old_text = item["old"]
            if seq >= len(translated_lines):
                continue
            translation = translated_lines[seq].strip()
            # 空译文或与原文相同则跳过（保持空位，不污染 TL）
            if not translation or translation == old_text:
                continue
            if new_line_index >= len(lines):
                continue
            new_match = _NEW_RE.match(lines[new_line_index])
            if not new_match:
                continue
            indent = new_match.group("indent")
            lines[new_line_index] = f'{indent}new "{_escape_literal(translation)}"'
            changed = True
            filled += 1

        if changed:
            dst_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
            # 删除同名 .rpyc，让 Ren'Py 重新编译
            dst_file.with_suffix(".rpyc").unlink(missing_ok=True)

    logger.info(f"已回填 {filled} 条译文到 {output_tl_dir}")
    return filled, output_tl_dir
