"""Translation import/export helpers using JSON payloads."""

from __future__ import annotations

import json
import os
import shutil
import stat
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional

from base.LogManager import LogManager
from module.File.AtomicWrite import atomic_write_text
from module.Tool.AssetSuiteOps import AssetSuiteError, resolve_under_root

logger = LogManager.get()

_REPARSE_POINT = 0x400


def resolve_tl_rpy_relative(tl_dir: Path, file_name: str) -> Path:
    """将 JSON 中的相对 .rpy 键解析到 tl 根目录内；拒绝绝对路径、.. 与越界符号链接。"""
    name = str(file_name or "").strip().replace("\\", "/")
    if not name or not name.lower().endswith(".rpy"):
        raise ValueError(f"仅允许 tl 下的相对 .rpy 路径：{file_name!r}")
    try:
        return resolve_under_root(tl_dir, name)
    except AssetSuiteError as exc:
        raise ValueError(str(exc)) from exc


def _norm_path_key(path: Path) -> str:
    return os.path.normcase(os.path.abspath(str(path.resolve(strict=False))))


def _is_linkish(path: Path) -> bool:
    try:
        info = path.lstat()
    except OSError:
        return False
    if stat.S_ISLNK(info.st_mode):
        return True
    attributes = getattr(info, "st_file_attributes", 0) or 0
    return bool(attributes & _REPARSE_POINT)


def _within_root(root: Path, path: Path) -> bool:
    try:
        root_key = _norm_path_key(root)
        real_key = _norm_path_key(path)
    except OSError:
        return False
    return real_key == root_key or real_key.startswith(root_key + os.sep)


def _assert_ancestor_chain_safe(root: Path, target: Path) -> None:
    """校验目标及其祖先在 tl 根内，且中间链接不越界。"""
    if not _within_root(root, target):
        raise ValueError(f"路径越出译文根目录：{target}")
    cursor = target
    while True:
        if _is_linkish(cursor):
            try:
                resolved = cursor.resolve(strict=False)
            except OSError as exc:
                raise ValueError(f"无法解析链接：{cursor}: {exc}") from exc
            if not _within_root(root, resolved):
                raise ValueError(f"符号链接/重解析点越出译文根目录：{cursor}")
        if cursor == root or cursor.parent == cursor:
            break
        try:
            if _norm_path_key(cursor) == _norm_path_key(root):
                break
        except OSError:
            break
        cursor = cursor.parent


def _validate_language_segment(language: str) -> str:
    name = str(language or "").strip() or "chinese"
    if name in {".", ".."} or any(ch in name for ch in '/\\<>:"|?*'):
        raise ValueError(f"语言名无效：{language!r}")
    return name


def resolve_contained_tl_dir(game_folder: Path, language: str) -> Path:
    """在任何 mkdir 前解析 game/tl/<lang>，拒绝 TL 根或其祖先链接越出 game。"""
    lang = _validate_language_segment(language)
    game_folder = Path(game_folder)
    tl_root = game_folder / "tl"

    # game/tl 若已是链接/重解析点，解析后必须仍落在 game 内
    if tl_root.exists() or _is_linkish(tl_root):
        try:
            resolved_tl_root = tl_root.resolve(strict=False)
        except OSError as exc:
            raise ValueError(f"无法解析 TL 根目录：{tl_root}: {exc}") from exc
        if not _within_root(game_folder, resolved_tl_root):
            raise ValueError(f"TL 根目录越界：{tl_root}")
        try:
            tl_dir = resolve_under_root(resolved_tl_root, lang)
        except AssetSuiteError as exc:
            raise ValueError(str(exc)) from exc
    else:
        try:
            tl_dir = resolve_under_root(tl_root, lang)
        except AssetSuiteError as exc:
            raise ValueError(str(exc)) from exc

    if not _within_root(game_folder, tl_dir):
        raise ValueError(f"TL 目录越界：{tl_dir}")
    _assert_ancestor_chain_safe(game_folder, tl_dir)
    return tl_dir


def plan_tl_write_targets(
    translations: Dict[str, List[Dict]],
    tl_dir: Path,
    *,
    backup: bool,
) -> dict[str, Path]:
    """写前全量规划：相对键、normcase 去重、备份目标/父树界限。未通过时不做 mkdir。"""
    if not isinstance(translations, dict) or not translations:
        raise ValueError("没有可应用的翻译条目")

    resolved_targets: dict[str, Path] = {}
    seen_norm: dict[str, str] = {}
    for file_name in translations:
        target = resolve_tl_rpy_relative(tl_dir, file_name)
        norm = _norm_path_key(target)
        previous = seen_norm.get(norm)
        if previous is not None:
            raise ValueError(f"重复目标路径：{previous!r} 与 {file_name!r}")
        seen_norm[norm] = str(file_name)
        _assert_ancestor_chain_safe(tl_dir, target)
        if backup:
            backup_path = target.with_suffix(target.suffix + ".bak")
            _assert_ancestor_chain_safe(tl_dir, backup_path)
            if _is_linkish(backup_path):
                # 已存在的 .bak 若是链接，copy2 可能跟随覆盖外部文件
                raise ValueError(f"备份目标是符号链接/重解析点，已拒绝：{backup_path}")
            if backup_path.exists():
                try:
                    resolved_bak = backup_path.resolve(strict=False)
                except OSError as exc:
                    raise ValueError(f"备份路径无效：{backup_path}: {exc}") from exc
                if not _within_root(tl_dir, resolved_bak):
                    raise ValueError(f"备份目标越出译文根目录：{backup_path}")
        resolved_targets[str(file_name)] = target
    return resolved_targets


def _build_metadata(translations: Dict[str, List[Dict]], extra: Optional[Dict] = None) -> Dict:
    total_files = len(translations)
    total_entries = sum(len(items) for items in translations.values())
    metadata: Dict = {
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "total_files": total_files,
        "total_entries": total_entries,
        "format": "renpybox-translations-json",
        "version": "1.0",
    }
    if extra:
        metadata.update(extra)
    return metadata


def _normalise_entry(entry: Dict) -> Dict:
    return {
        "line": entry.get("line", 0),
        "original": entry.get("original", ""),
        "translation": entry.get("translation", ""),
        "type": entry.get("type", "dialogue"),
        "status": entry.get("status", "pending"),
        "note": entry.get("note", ""),
        "identifier": entry.get("identifier", ""),
    }


def _escape_rpy_string(value: str) -> str:
    return (
        (value or "")
        .replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\n", "\\n")
    )


class JsonExporter:
    """Export translation entries into a structured JSON file."""

    def export(
        self,
        translations: Dict[str, List[Dict]],
        output_path: str,
        include_metadata: bool = True,
    ) -> bool:
        try:
            payload = {
                "translations": {file_path: [
                    _normalise_entry(item) for item in items
                ] for file_path, items in translations.items()}
            }
            if include_metadata:
                payload["meta"] = _build_metadata(translations)

            output = Path(output_path)
            output.parent.mkdir(parents=True, exist_ok=True)
            text = json.dumps(payload, ensure_ascii=False, indent=2)
            atomic_write_text(output, text, encoding="utf-8")

            logger.info(f"JSON 导出成功: {output}")
            return True
        except Exception as exc:
            logger.error(f"JSON 导出失败: {exc}", exc)
            return False


class JsonImporter:
    """Load translation entries from a JSON file."""

    def import_translations(self, json_path: str) -> Dict[str, List[Dict]]:
        try:
            path = Path(json_path)
            if not path.exists():
                raise FileNotFoundError(f"文件不存在: {json_path}")

            with path.open("r", encoding="utf-8") as reader:
                payload = json.load(reader)

            if isinstance(payload, dict) and "translations" in payload:
                raw = payload.get("translations", {})
            else:
                raw = payload

            if isinstance(raw, list):
                translations: Dict[str, List[Dict]] = {}
                for item in raw:
                    if not isinstance(item, dict):
                        continue
                    file_name = str(item.get("file") or item.get("name") or "")
                    entries = item.get("entries")
                    if not file_name or not isinstance(entries, list):
                        continue
                    translations[file_name] = [_normalise_entry(entry) for entry in entries if isinstance(entry, dict)]
            elif isinstance(raw, dict):
                translations = {
                    str(file_name): [_normalise_entry(entry) for entry in entries if isinstance(entry, dict)]
                    for file_name, entries in raw.items()
                    if isinstance(entries, list)
                }
            else:
                translations = {}

            logger.info(f"JSON 导入成功: {json_path}，共 {len(translations)} 个文件")
            return translations
        except Exception as exc:
            logger.error(f"JSON 导入失败: {exc}", exc)
            return {}

    def apply_translations(
        self,
        translations: Dict[str, List[Dict]],
        game_dir: str,
        target_language: str = "chinese",
        backup: bool = True,
        *,
        should_stop: Callable[[], bool] | None = None,
        result_meta: dict | None = None,
    ) -> bool:
        meta: dict = {
            "written_files": [],
            "backup_paths": [],
            "partial": False,
        }
        try:
            logger.info("开始应用 JSON 翻译到游戏文件")
            project_path = Path(game_dir)
            if not project_path.exists():
                raise FileNotFoundError(f"游戏目录不存在: {game_dir}")

            language = _validate_language_segment(target_language)
            game_folder = project_path / "game"
            if not game_folder.is_dir():
                raise FileNotFoundError(f"未找到 game 目录: {game_folder}")

            # TL 根 containment（含祖先链接）必须在 mkdir 前完成
            tl_dir = resolve_contained_tl_dir(game_folder, language)
            resolved_targets = plan_tl_write_targets(translations, tl_dir, backup=backup)

            # 预检通过后再创建目录树
            tl_dir.mkdir(parents=True, exist_ok=True)

            seen_global: set[str] = set()
            dup_count = 0

            for file_name, items in translations.items():
                if should_stop is not None and should_stop():
                    meta["partial"] = True
                    if result_meta is not None:
                        result_meta.update(meta)
                    raise RuntimeError("导入已取消")

                target = resolved_targets[str(file_name)]
                target.parent.mkdir(parents=True, exist_ok=True)

                if backup and target.exists():
                    backup_path = target.with_suffix(target.suffix + ".bak")
                    if _is_linkish(backup_path):
                        raise ValueError(f"拒绝写入越界或链接备份目标：{backup_path}")
                    # 复制到真实文件；若目标.bak为链接则上面已拒绝
                    shutil.copy2(target, backup_path, follow_symlinks=False)
                    meta["backup_paths"].append(str(backup_path))
                    logger.info(f"已备份: {backup_path}")

                content_lines = [
                    "# Generated by RenpyBox JSON import",
                    "# Source file: " + str(file_name),
                    "",
                    f"translate {language} strings:",
                    "",
                ]

                for item in items:
                    original_raw = item.get("original") or ""
                    if original_raw in seen_global:
                        dup_count += 1
                        continue
                    seen_global.add(original_raw)

                    original = _escape_rpy_string(original_raw)
                    translation = _escape_rpy_string(
                        item.get("translation") or item.get("original") or ""
                    )
                    line_number = item.get("line", "?")
                    content_lines.append(f"    # Line {line_number}")
                    content_lines.append(f"    old \"{original}\"")
                    content_lines.append(f"    new \"{translation}\"")
                    content_lines.append("")

                atomic_write_text(
                    target,
                    "\n".join(content_lines),
                    encoding="utf-8",
                    allowed_roots=[tl_dir],
                )
                meta["written_files"].append(str(target))
                logger.info(f"已应用翻译: {target}")

            if dup_count > 0:
                logger.warning(f"跳过 {dup_count} 条重复原文（跨文件只保留首次出现的 old），避免 Ren'Py 重复翻译报错")

            logger.info("JSON 翻译应用完成")
            if result_meta is not None:
                result_meta.update(meta)
            return True
        except ValueError:
            if result_meta is not None:
                result_meta.update(meta)
            raise
        except Exception as exc:
            logger.error(f"应用翻译失败: {exc}", exc)
            if result_meta is not None:
                result_meta.update(meta)
            return False


# Backward compatibility aliases -------------------------------------------------
ExcelExporter = JsonExporter
ExcelImporter = JsonImporter
