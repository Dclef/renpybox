"""Agent 项目翻译体检工具。"""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from module.Agent.types import ToolResult

from base.Base import Base
from base.LogManager import LogManager
from module.Cache.CacheItem import CacheItem
from module.Cache.CacheManager import CacheManager
from module.Cache.CacheProject import CacheProject
from module.Config import Config
from module.Engine.Quality import build_translation_quality_report
from module.Engine.Translator.TranslationPreflightService import (
    TranslationPreflightService,
)
from module.Engine.Translator.TranslationTaskContext import ProjectAssets
from module.Extract.ReplaceGenerator import collect_translated_old_new_pairs
from module.Localizer.Localizer import Localizer
from module.Renpy.renpy_tl_core import (
    TlBlockKind,
    pair_old_new_lines,
    parse_tl_document,
)
from module.Renpy.ProjectPaths import (
    RenpyProjectPaths,
    source_script_counts,
    translation_output_candidates,
)

from .project_tools import _config, _not_set, _resolve_paths


ConfigLoader = Callable[[], Config]
QUALITY_SAMPLE_LIMIT = 5
PROGRESS_KEYS = (
    "line",
    "total_line",
    "failed_line_count",
    "fallback_line_count",
    "line_count_mismatch_count",
)


def _file_summary(paths: RenpyProjectPaths) -> dict[str, Any]:
    rpa_count = sum(1 for _ in paths.game_dir.glob("*.rpa"))
    rpy_count, rpyc_count = source_script_counts(paths)
    tl_file_count = (
        sum(1 for _ in paths.tl_language_dir.rglob("*.rpy"))
        if paths.tl_language_dir.is_dir()
        else 0
    )

    unpack_required = rpa_count > 0 and rpy_count == 0 and rpyc_count == 0
    if unpack_required:
        status = "need_unpack"
    elif rpy_count == 0 and rpyc_count > 0:
        status = "need_decompile"
    elif rpy_count > 0 and rpyc_count > 0:
        status = "mixed"
    elif rpy_count > 0:
        status = "ready"
    else:
        status = "empty"

    return {
        "status": status,
        "rpa_state": (
            "required"
            if unpack_required
            else "scripts_present"
            if rpa_count > 0
            else "not_applicable"
        ),
        "unpack_required": unpack_required,
        "rpa_count": rpa_count,
        "rpy_count": rpy_count,
        "rpyc_count": rpyc_count,
        "tl_file_count": tl_file_count,
    }


def _path_key(path: Path) -> str:
    try:
        return str(path.resolve(strict=False)).replace("\\", "/").casefold()
    except (OSError, RuntimeError):
        return str(path).replace("\\", "/").casefold()


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(parent.resolve(strict=False))
        return True
    except (OSError, RuntimeError, ValueError):
        return False


def _is_current_language_output(
    output_path: Path,
    paths: RenpyProjectPaths,
) -> bool:
    allowed = (
        paths.translation_output_dir,
        paths.translation_output_dir.parent / f"{paths.language}_new",
        paths.application_target_dir,
    )
    if any(_path_key(output_path) == _path_key(candidate) for candidate in allowed):
        return True

    if _is_within(output_path, paths.tl_root):
        try:
            relative = output_path.resolve(strict=False).relative_to(
                paths.tl_root.resolve(strict=False)
            )
            return (
                bool(relative.parts)
                and relative.parts[0].casefold() == paths.language.casefold()
            )
        except (OSError, RuntimeError, ValueError):
            return False

    translation_root = paths.project_root / "RenpyBox_Translation"
    if _is_within(output_path, translation_root):
        try:
            relative = output_path.resolve(strict=False).relative_to(
                translation_root.resolve(strict=False)
            )
            if not relative.parts:
                return False
            first = relative.parts[0].casefold()
            return first in {
                paths.language.casefold(),
                f"{paths.language}_new".casefold(),
            }
        except (OSError, RuntimeError, ValueError):
            return False
    return (
        _is_within(output_path, paths.project_root)
        and _path_key(output_path) != _path_key(paths.project_root)
    )


def _cache_markers(output_path: Path) -> tuple[bool, bool]:
    cache_dir = output_path / "cache"
    database = cache_dir / CacheManager.CACHE_DB_NAME
    items = (cache_dir / "items.json").is_file()
    journal = (cache_dir / CacheManager.RESET_JOURNAL_NAME).is_file()
    database_has_translation = (
        _database_has_translation_state(database) if database.is_file() else False
    )
    return database_has_translation or items or journal, journal


def _translation_output(config: Config, paths: RenpyProjectPaths) -> Path:
    candidates = [
        candidate
        for candidate in translation_output_candidates(config)
        if _is_current_language_output(candidate, paths)
    ]
    for candidate in candidates:
        exists, _ = _cache_markers(candidate)
        if exists:
            return candidate
    return paths.translation_output_dir


def _read_json_cache(cache_dir: Path) -> tuple[CacheProject, list[CacheItem]]:
    items_path = cache_dir / "items.json"
    project_path = cache_dir / "project.json"
    if not items_path.is_file() or not project_path.is_file():
        raise RuntimeError("Translation cache is incomplete")
    items_payload = json.loads(items_path.read_text(encoding="utf-8-sig"))
    project_payload = json.loads(project_path.read_text(encoding="utf-8-sig"))
    if not isinstance(items_payload, list) or not isinstance(project_payload, dict):
        raise RuntimeError("Translation cache has an invalid schema")
    return (
        CacheProject.from_dict(project_payload),
        [CacheItem.from_dict(item) for item in items_payload],
    )


def _read_sqlite_cache(
    database: Path,
    *,
    include_items: bool,
) -> tuple[CacheProject, list[CacheItem], str | None]:
    """通过 SQLite 只读 URI 读取缓存，禁止建表、WAL 与恢复写入。"""
    wal_path = database.with_name(f"{database.name}-wal")
    if wal_path.is_file() and wal_path.stat().st_size > 0:
        raise RuntimeError("SQLite cache has an uncheckpointed WAL")
    uri = f"{database.resolve().as_uri()}?mode=ro&immutable=1"
    connection = sqlite3.connect(uri, uri=True)
    try:
        connection.execute("PRAGMA query_only=ON")
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        if "meta" not in tables:
            raise RuntimeError("SQLite cache has no meta table")
        row = connection.execute(
            "SELECT value FROM meta WHERE key = ?",
            ("project",),
        ).fetchone()
        if row is None:
            raise RuntimeError("SQLite cache has no project record")
        project = CacheProject.from_dict(json.loads(row[0]))

        items: list[CacheItem] = []
        if include_items:
            if "items" not in tables:
                raise RuntimeError("SQLite cache has no items table")
            rows = connection.execute("SELECT data FROM items ORDER BY id").fetchall()
            items = [CacheItem.from_dict(json.loads(item[0])) for item in rows]
        digest_row = connection.execute(
            "SELECT value FROM meta WHERE key = ?",
            ("items_digest",),
        ).fetchone()
        digest = str(digest_row[0]) if digest_row is not None else None
        return project, items, digest
    finally:
        connection.close()


def _database_has_translation_state(database: Path) -> bool:
    """区分仅保存项目资产的数据库与真正的翻译缓存。"""
    wal_path = database.with_name(f"{database.name}-wal")
    if wal_path.is_file() and wal_path.stat().st_size > 0:
        return True
    uri = f"{database.resolve().as_uri()}?mode=ro&immutable=1"
    try:
        with CacheManager.LOCK:
            connection = sqlite3.connect(uri, uri=True)
            try:
                connection.execute("PRAGMA query_only=ON")
                tables = {
                    str(row[0])
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    )
                }
                if "meta" not in tables or "items" not in tables:
                    return True
                project = connection.execute(
                    "SELECT 1 FROM meta WHERE key = ?",
                    ("project",),
                ).fetchone()
                if project is None:
                    return True
                digest = connection.execute(
                    "SELECT 1 FROM meta WHERE key = ?",
                    ("items_digest",),
                ).fetchone()
                if digest is not None:
                    return True
                return (
                    connection.execute("SELECT 1 FROM items LIMIT 1").fetchone()
                    is not None
                )
            finally:
                connection.close()
    except Exception:
        # 无法确认数据库只含资产时，将其作为损坏翻译缓存交给体检报告。
        return True


def _read_cache_pair(cache_dir: Path) -> tuple[CacheProject, list[CacheItem]]:
    database = cache_dir / CacheManager.CACHE_DB_NAME
    items_json_exists = (cache_dir / "items.json").is_file()
    project_json_exists = (cache_dir / "project.json").is_file()
    json_available = items_json_exists and project_json_exists
    if not database.is_file():
        return _read_json_cache(cache_dir)
    wal_path = database.with_name(f"{database.name}-wal")
    if wal_path.is_file() and wal_path.stat().st_size > 0:
        raise RuntimeError("SQLite cache has an uncheckpointed WAL")

    try:
        project, items, digest = _read_sqlite_cache(database, include_items=True)
    except Exception:
        if json_available:
            return _read_json_cache(cache_dir)
        raise

    # 仅含资产的数据库不能把半套旧版翻译缓存伪装成可读缓存。
    if not items and digest is None and items_json_exists != project_json_exists:
        raise RuntimeError("Translation cache is incomplete")
    if not items and digest is None and json_available:
        json_project, json_items = _read_json_cache(cache_dir)
        if json_items:
            return json_project, json_items
    return project, items


def _load_cache(
    output_path: Path,
) -> tuple[dict[str, Any], CacheProject | None, list[CacheItem]]:
    exists, has_journal = _cache_markers(output_path)
    data: dict[str, Any] = {
        "exists": exists,
        "readable": False,
        "output_path": str(output_path),
        "project_status": "",
        "item_count": 0,
        "completed_count": 0,
        "untranslated_count": 0,
        "status_counts": {},
        "progress": {},
    }
    if not exists:
        return data, None, []
    if has_journal:
        data["error_code"] = "CACHE_RECOVERY_REQUIRED"
        return data, None, []

    try:
        with CacheManager.LOCK:
            project, items = _read_cache_pair(output_path / "cache")
    except Exception as exc:
        LogManager.get().warning(f"Agent 项目体检读取翻译缓存失败: {exc}")
        data["error_code"] = "CACHE_UNREADABLE"
        return data, None, []

    status_counts = Counter(item.get_status().value for item in items)
    completed_count = sum(
        1 for item in items if Base.is_item_completed(item.get_status())
    )
    untranslated_count = sum(
        1
        for item in items
        if item.get_status() == Base.TranslationStatus.UNTRANSLATED
    )
    raw_progress = project.get_progress()
    progress = {
        key: raw_progress[key]
        for key in PROGRESS_KEYS
        if key in raw_progress
        and isinstance(raw_progress[key], int)
        and not isinstance(raw_progress[key], bool)
        and raw_progress[key] >= 0
    }
    data.update(
        {
            "readable": True,
            "project_status": project.get_status().value,
            "item_count": len(items),
            "completed_count": completed_count,
            "untranslated_count": untranslated_count,
            "status_counts": dict(sorted(status_counts.items())),
            "progress": progress,
        }
    )
    return data, project, items


def _load_asset_project(
    output_path: Path,
) -> tuple[bool, bool, CacheProject | None]:
    """只读主输出中的项目元数据，不触发旧配置迁移。"""
    cache_dir = output_path / "cache"
    database = cache_dir / CacheManager.CACHE_DB_NAME
    project_json = cache_dir / "project.json"
    journal = cache_dir / CacheManager.RESET_JOURNAL_NAME
    exists = database.is_file() or project_json.is_file() or journal.is_file()
    if not exists:
        return False, True, None
    if journal.is_file():
        return True, False, None

    if database.is_file():
        wal_path = database.with_name(f"{database.name}-wal")
        if wal_path.is_file() and wal_path.stat().st_size > 0:
            return True, False, None
        try:
            with CacheManager.LOCK:
                project, _, _ = _read_sqlite_cache(
                    database,
                    include_items=False,
                )
            return True, True, project
        except Exception as exc:
            LogManager.get().warning(f"Agent 项目体检读取项目资产数据库失败: {exc}")

    if not project_json.is_file():
        return True, False, None
    try:
        with CacheManager.LOCK:
            payload = json.loads(project_json.read_text(encoding="utf-8-sig"))
        return True, True, CacheProject.from_dict(payload)
    except Exception as exc:
        LogManager.get().warning(f"Agent 项目体检读取项目资产文件失败: {exc}")
        return True, False, None


def _has_content(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, dict):
        return any(_has_content(item) for item in value.values())
    if isinstance(value, (list, tuple, set, frozenset)):
        return any(_has_content(item) for item in value)
    return bool(value)


def _asset_summary(project: CacheProject | None) -> dict[str, Any]:
    if project is None:
        assets = ProjectAssets()
        candidates: dict[str, Any] = {}
    else:
        assets = ProjectAssets.from_dict(project.get_project_assets())
        candidates = project.get_analysis_candidates()

    preflight = TranslationPreflightService.check(assets)
    worldbook_draft = candidates.get("worldbook_draft", {})
    character_drafts = candidates.get("character_drafts", [])
    worldbook_has_draft = _has_content(worldbook_draft)
    character_draft_count = (
        sum(1 for item in character_drafts if _has_content(item))
        if isinstance(character_drafts, list)
        else 0
    )
    return {
        "has_effective_assets": preflight.has_effective_assets,
        "effective_sections": list(preflight.effective_sections),
        "has_drafts": worldbook_has_draft or character_draft_count > 0,
        "worldbook_draft": worldbook_has_draft,
        "character_draft_count": character_draft_count,
    }


def _quality_summary(
    items: list[CacheItem],
    progress: dict[str, Any],
) -> dict[str, Any]:
    report = build_translation_quality_report(items, progress)
    return {
        "failed_count": report.failed_count,
        "fallback_count": report.fallback_count,
        "line_mismatch_count": report.line_mismatch_count,
        "error_type_counts": dict(report.error_type_counts),
        "samples": [
            reference.as_dict()
            for reference in report.item_references[:QUALITY_SAMPLE_LIMIT]
        ],
    }


def _translated_pairs_in_file(path: Path) -> dict[str, str]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    document = parse_tl_document(lines)
    pairs: dict[str, str] = {}
    for block in document.blocks:
        if block.kind != TlBlockKind.STRINGS:
            continue
        statements = {statement.line_no: statement for statement in block.statements}
        for old_line, new_line in pair_old_new_lines(block).items():
            old_statement = statements.get(old_line)
            new_statement = statements.get(new_line)
            if (
                old_statement is None
                or new_statement is None
                or not old_statement.literals
                or not new_statement.literals
            ):
                continue
            original = old_statement.literals[0].value
            translation = new_statement.literals[0].value
            if original and translation and original != translation:
                pairs[original] = translation
    return pairs


def _old_new_summary(paths: RenpyProjectPaths) -> dict[str, Any]:
    try:
        old_new_pairs, conflict_count = collect_translated_old_new_pairs(
            paths.tl_language_dir
        )
        old_new_sources = {source for source, _ in old_new_pairs}
        supplement_pairs: dict[str, str] = {}
        miss_candidates = (
            paths.tl_language_dir / "miss" / "miss_ready_replace.rpy",
            paths.tl_language_dir / "miss_ready_replace.rpy",
            paths.tl_language_dir / "miss" / "miss_ready_replace.txt",
            paths.tl_language_dir / "miss_ready_replace.txt",
        )
        for candidate in miss_candidates:
            if candidate.is_file():
                supplement_pairs = _translated_pairs_in_file(candidate)
                break
    except Exception as exc:
        LogManager.get().warning(f"Agent 项目体检读取 old/new 状态失败: {exc}")
        return {
            "effective_count": 0,
            "supplement_count": 0,
            "conflict_count": 0,
            "hook_exists": False,
            "readable": False,
        }
    return {
        "effective_count": len(old_new_pairs),
        "supplement_count": sum(
            1 for source in supplement_pairs if source not in old_new_sources
        ),
        "conflict_count": conflict_count,
        "hook_exists": (paths.tl_language_dir / "replace_text_auto.rpy").is_file(),
        "readable": True,
    }


def _next_action(
    files: dict[str, Any],
    cache: dict[str, Any],
    assets: dict[str, Any],
    quality: dict[str, Any],
    old_new: dict[str, Any],
) -> str:
    if cache["exists"] and not cache["readable"]:
        return "REPAIR_CACHE"
    if assets["storage_exists"] and not assets["readable"]:
        return "REPAIR_CACHE"
    if cache["item_count"] > 0:
        if cache["untranslated_count"] > 0:
            if (
                cache["project_status"] == Base.TranslationStatus.TRANSLATING.value
                or cache["progress"].get("line", 0) > 0
            ):
                return "CONTINUE_TRANSLATION"
            return "START_TRANSLATION"
        if (
            quality["failed_count"] > 0
            or quality["fallback_count"] > 0
            or quality["line_mismatch_count"] > 0
            or bool(quality["error_type_counts"])
        ):
            return "REVIEW_QUALITY"
        return "REVIEW_TRANSLATION"
    if files["unpack_required"]:
        return "UNPACK_RPA"
    if files["status"] == "need_decompile":
        return "DECOMPILE_SCRIPTS"
    if old_new["effective_count"] > 0:
        return "REVIEW_TRANSLATION"
    if files["status"] == "empty":
        return "CHECK_PROJECT_FILES"
    if not assets["has_effective_assets"] and assets["has_drafts"]:
        return "REVIEW_WORKBENCH"
    return "START_TRANSLATION"


def inspect_translation_project(
    *,
    config: Config | None = None,
    config_loader: ConfigLoader | None = None,
) -> "ToolResult":
    """汇总当前项目的翻译阶段并建议下一步，不修改任何文件。"""
    from module.Agent.types import ToolResult

    current = _config(config, config_loader)
    paths = _resolve_paths(current)
    if paths is None:
        return _not_set()

    files = _file_summary(paths)
    output_path = _translation_output(current, paths)
    cache, cache_project, items = _load_cache(output_path)
    asset_exists, asset_readable, asset_project = _load_asset_project(
        paths.translation_output_dir
    )
    asset_source = "main_output"
    if not asset_exists and cache_project is not None:
        asset_project = cache_project
        asset_source = "translation_cache"
    assets = _asset_summary(asset_project)
    assets.update(
        {
            "storage_exists": asset_exists,
            "readable": asset_readable,
            "source": asset_source if asset_project is not None else "none",
        }
    )
    if asset_exists and not asset_readable:
        assets["error_code"] = "ASSET_CACHE_UNREADABLE"
    quality = _quality_summary(items, cache["progress"])
    old_new = _old_new_summary(paths)
    action_code = _next_action(files, cache, assets, quality, old_new)
    localizer = Localizer.get()
    action = getattr(
        localizer,
        f"agent_inspection_action_{action_code.casefold()}",
    )
    data = {
        "next_action_code": action_code,
        "next_action": action,
        "project": {
            "project_root": str(paths.project_root),
            "game_dir": str(paths.game_dir),
            "language": paths.language,
        },
        "files": files,
        "cache": cache,
        "assets": assets,
        "quality": quality,
        "old_new": old_new,
    }
    message = localizer.agent_project_inspection_complete.format(
        rpy_count=files["rpy_count"],
        rpyc_count=files["rpyc_count"],
        rpa_count=files["rpa_count"],
        item_count=cache["item_count"],
        untranslated_count=cache["untranslated_count"],
        next_action=action,
    )
    return ToolResult(True, message, data=data)
