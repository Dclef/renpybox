"""Generate missing-translation patch files for Ren'Py projects."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Optional, Set, Tuple

from base.LogManager import LogManager
from module.Extract.SimpleRpyExtractor import SimpleRpyExtractor
from module.Text.SkipRules import should_skip_text
from module.Translate.RenpySourceTranslator import RenpySourceTranslator, TranslationEntry


def _normalize_text(text: str | None) -> str:
    return (text or "").strip()


def _load_runtime_json(runtime_json: Path) -> Set[str]:
    if not runtime_json.exists():
        return set()
    try:
        data = json.loads(runtime_json.read_text(encoding="utf-8"))
        collected: Set[str] = set()
        for entries in data.values():
            for entry in entries:
                if not isinstance(entry, (list, tuple)) or len(entry) < 3:
                    continue
                _, _, what = entry[:3]
                text = _normalize_text(str(what) if what is not None else "")
                if should_skip_text(text):
                    continue
                collected.add(text)
        return collected
    except Exception:
        return set()


def _collect_tl_entries(extractor: SimpleRpyExtractor, project_dir: Path, tl_name: str) -> Set[str]:
    """收集已存在的翻译条目"""
    tl_dir = SimpleRpyExtractor.find_tl_directory(project_dir, tl_name)
    if tl_dir is None:
        return set()
    
    entries = extractor.extract_from_directory(tl_dir, tl_name, filter_garbage=False)
    result: Set[str] = set()
    for entry in entries:
        text = _normalize_text(entry.get("original", ""))
        if should_skip_text(text):
            continue
        result.add(text)
    return result


def _collect_source_entries(game_dir: Path) -> Iterable[Tuple[Path, TranslationEntry]]:
    parser = RenpySourceTranslator()
    for file_path, entries in parser.scan_directory(game_dir).items():
        for entry in entries:
            text = _normalize_text(entry.text)
            if should_skip_text(text):
                continue
            yield file_path, entry


def generate_patch(
    target_path: str | Path,
    tl_name: str,
    runtime_json: str | Path | None = None,
    output_path: str | Path | None = None,
) -> Tuple[Optional[Path], int]:
    """
    生成缺失翻译补丁文件 patch_missing.rpy（非侵入式，写入 tl 目录）。

    Returns:
        (补丁路径或 None, 缺失条目数量)
    """
    logger = LogManager.get()
    extractor = SimpleRpyExtractor()
    _, project = SimpleRpyExtractor.resolve_game_path(target_path)
    game_dir = project / "game"

    # 收集已存在的翻译条目
    existing_set = _collect_tl_entries(extractor, project, tl_name)
    
    runtime_set: Set[str] = set()
    if runtime_json:
        runtime_set = _load_runtime_json(Path(runtime_json))
    else:
        candidate = project / "extraction_hooked.json"
        if candidate.exists():
            runtime_set = _load_runtime_json(candidate)

    tl_dir = game_dir / "tl" / tl_name
    tl_dir.mkdir(parents=True, exist_ok=True)
    patch_path = Path(output_path) if output_path else tl_dir / "patch_missing.rpy"

    seen: Set[str] = set()
    missing_items: list[Tuple[Path, TranslationEntry]] = []
    for file_path, entry in _collect_source_entries(game_dir):
        text = _normalize_text(entry.text)
        if text in seen:
            continue
        if text in existing_set or text in runtime_set:
            continue
        seen.add(text)
        missing_items.append((file_path, entry))

    if not missing_items:
        logger.info("未发现缺失条目，不生成补丁文件")
        return None, 0

    lines: list[str] = [
        "# Auto-generated patch for missing translations",
        f"# Game: {project.name}",
        "",
        f"translate {tl_name} strings:",
        "",
    ]

    for file_path, entry in missing_items:
        rel = file_path.relative_to(game_dir)
        text = _normalize_text(entry.text)
        escaped = text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        lines.append(f"    # {rel}:{entry.line_number}")
        lines.append(f'    old "{escaped}"')
        lines.append('    new ""')
        lines.append("")

    patch_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info(f"缺失补丁已生成: {patch_path} ({len(missing_items)} 条)")
    return patch_path, len(missing_items)
