from __future__ import annotations

import copy
import json
import os
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from module.Cache.CacheDB import CacheDB
from module.Cache.CacheManager import CacheManager
from module.Cache.CacheProject import CacheProject
from module.Engine.Translator.TranslationTaskContext import ProjectAssets, TermAsset
from module.Renpy.ProjectPaths import RenpyProjectPaths


@dataclass(frozen = True)
class ProjectAssetsState:
    assets: ProjectAssets
    analysis_candidates: dict[str, Any]


class ProjectAssetsRepository:
    """Project-scoped persistence boundary for translation assets and drafts."""

    CANDIDATE_SCHEMA_VERSION = 1

    def __init__(
        self,
        output_folder: str,
        *,
        cache_use_sqlite: bool = True,
    ) -> None:
        self.output_folder = str(output_folder or "").strip()
        self.cache_use_sqlite = bool(cache_use_sqlite)
        # 当前仓库实例发现 SQLite 不可用后，后续读写统一回退 JSON，
        # 避免反复访问损坏或不可写的数据库。
        self._sqlite_unavailable = False

    @property
    def has_storage(self) -> bool:
        """是否有可写的项目资产目录。"""
        return self.output_folder != ""

    @classmethod
    def from_config(cls, config: Any) -> ProjectAssetsRepository:
        # Ren'Py 的项目资产必须绑定主输出目录，而不是当前运行的
        # ``<lang>_new`` 增量目录；否则应用翻译后工作台会看起来像丢失数据。
        renpy_paths = RenpyProjectPaths.from_config(config)
        output_folder = (
            str(renpy_paths.translation_output_dir)
            if renpy_paths is not None
            else getattr(config, "output_folder", "")
        )
        return cls(
            output_folder,
            cache_use_sqlite = bool(getattr(config, "cache_use_sqlite", True)),
        )

    def load(self, legacy_config: Any = None) -> ProjectAssetsState:
        """Load current project data and perform the one-time legacy bootstrap."""
        with CacheManager.LOCK:
            if not self.has_storage:
                # 空配置只能返回内存态，不能把项目资产误写到当前工作目录
                # 下的 ``./cache``。
                assets = ProjectAssets.from_config(legacy_config)
                candidates = self._migrate_legacy_candidates(
                    {
                        "schema_version": self.CANDIDATE_SCHEMA_VERSION,
                        "items": [],
                    },
                    legacy_config,
                )
                return ProjectAssetsState(
                    assets = self._stamp_assets(assets, minimum_revision = 1),
                    analysis_candidates = self.normalize_analysis_candidates(candidates),
                )
            recovered = self._recover_json_transaction_unlocked()
            active_project = self._resolve_active_project()
            project = (
                (active_project if recovered is False else None)
                or self._read_project_unlocked()
            )
            assets = ProjectAssets.from_dict(project.get_project_assets())
            candidates = self.normalize_analysis_candidates(project.get_analysis_candidates())
            changed = False

            if self._has_project_state(assets) is False:
                legacy_assets = ProjectAssets.from_config(legacy_config)
                assets = self._stamp_assets(legacy_assets, minimum_revision = 1)
                project.set_project_assets(assets)
                changed = True
            elif assets.revision <= 0:
                assets = self._stamp_assets(assets, minimum_revision = 1)
                project.set_project_assets(assets)
                changed = True

            if candidates.get("legacy_config_migrated") is not True:
                candidates = self._migrate_legacy_candidates(candidates, legacy_config)
                project.set_analysis_candidates(candidates)
                changed = True

            if changed:
                self._write_project_unlocked(project)

            return ProjectAssetsState(
                assets = ProjectAssets.from_dict(project.get_project_assets()),
                analysis_candidates = self.normalize_analysis_candidates(
                    project.get_analysis_candidates()
                ),
            )

    def save_assets(self, assets: ProjectAssets | Mapping[str, Any]) -> ProjectAssets:
        incoming = ProjectAssets.from_dict(assets)

        def update(project: CacheProject) -> None:
            current = ProjectAssets.from_dict(project.get_project_assets())
            revision = max(current.revision, incoming.revision, 0) + 1
            project.set_project_assets(self._stamp_assets(incoming, minimum_revision = revision))

        project = self._update_project(update)
        return ProjectAssets.from_dict(project.get_project_assets())

    def save_analysis_candidates(self, candidates: Mapping[str, Any]) -> dict[str, Any]:
        normalized = self.normalize_analysis_candidates(candidates)

        def update(project: CacheProject) -> None:
            project.set_analysis_candidates(normalized)

        project = self._update_project(update)
        return self.normalize_analysis_candidates(project.get_analysis_candidates())

    def save_workbench_view(self, config: Any) -> ProjectAssetsState:
        """Persist only the workbench-owned asset and candidate sections."""
        worldbook = getattr(config, "renpy_workbench_worldbook_data", {})
        cards = getattr(config, "renpy_workbench_character_cards", [])
        worldbook_draft = getattr(config, "renpy_workbench_generated_worldbook_draft", {})
        character_drafts = getattr(config, "renpy_workbench_generated_character_drafts", [])
        scope = str(getattr(config, "renpy_workbench_last_analysis_scope", "current") or "current")

        def update(project: CacheProject) -> None:
            assets_data = project.get_project_assets()
            current = ProjectAssets.from_dict(assets_data)
            assets_data["worldbook"] = {
                "enabled": bool(getattr(config, "renpy_workbench_worldbook_enable", False)),
                "data": copy.deepcopy(worldbook),
            }
            assets_data["character_cards"] = {
                "enabled": bool(getattr(config, "renpy_workbench_character_cards_enable", False)),
                "items": copy.deepcopy(cards),
            }
            assets_data["revision"] = max(current.revision, 0) + 1
            assets_data["updated_at"] = self._now()
            project.set_project_assets(assets_data)

            candidates = self.normalize_analysis_candidates(project.get_analysis_candidates())
            candidates["worldbook_draft"] = copy.deepcopy(worldbook_draft)
            candidates["character_drafts"] = copy.deepcopy(character_drafts)
            candidates["last_analysis_scope"] = scope
            candidates["legacy_config_migrated"] = True
            project.set_analysis_candidates(candidates)

        project = self._update_project(update)
        return ProjectAssetsState(
            assets = ProjectAssets.from_dict(project.get_project_assets()),
            analysis_candidates = self.normalize_analysis_candidates(
                project.get_analysis_candidates()
            ),
        )

    def load_into_config(self, config: Any) -> ProjectAssetsState:
        """Overlay project-owned values on a transient Config view."""
        state = self.load(config)
        assets = state.assets
        candidates = state.analysis_candidates

        config.renpy_workbench_worldbook_enable = assets.worldbook_enabled
        config.renpy_workbench_worldbook_data = assets.worldbook.to_dict()
        config.renpy_workbench_character_cards_enable = assets.character_cards_enabled
        config.renpy_workbench_character_cards = [card.to_dict() for card in assets.character_cards]
        config.glossary_enable = assets.glossary_enabled
        config.glossary_data = [self._term_to_legacy(item) for item in assets.glossary]
        config.do_not_translate_enable = assets.do_not_translate_enabled
        config.do_not_translate_data = [self._term_to_legacy(item) for item in assets.do_not_translate]
        config.renpy_workbench_generated_worldbook_draft = copy.deepcopy(
            candidates.get("worldbook_draft", {})
        )
        config.renpy_workbench_generated_character_drafts = copy.deepcopy(
            candidates.get("character_drafts", [])
        )
        config.renpy_workbench_last_analysis_scope = str(
            candidates.get("last_analysis_scope", "current") or "current"
        )
        return state

    def replace_glossary(
        self,
        entries: Iterable[Mapping[str, Any]],
        *,
        enabled: bool,
        consumed_candidate_ids: Iterable[str] = (),
    ) -> ProjectAssetsState:
        """Replace formal rows while keeping unconfirmed analysis rows as candidates."""
        rows = [dict(entry) for entry in entries if isinstance(entry, Mapping)]
        consumed = {str(value).strip() for value in consumed_candidate_ids if str(value).strip()}

        def update(project: CacheProject) -> None:
            assets_data = project.get_project_assets()
            current_assets = ProjectAssets.from_dict(assets_data)
            formal: list[dict[str, Any]] = []
            incomplete: list[dict[str, Any]] = []
            metadata: dict[str, dict[str, Any]] = {}

            for row in rows:
                source = str(row.get("source", row.get("src", "")) or "").strip()
                target = str(row.get("target", row.get("dst", "")) or "").strip()
                if source == "":
                    continue
                note = str(row.get("note", row.get("comment", row.get("info", ""))) or "").strip()
                regex = bool(row.get("regex", False))
                is_candidate = bool(row.get("candidate", False))
                candidate_confirmed = bool(row.get("candidate_confirmed", False))
                if target and (is_candidate is False or candidate_confirmed):
                    term = TermAsset.from_value(
                        {
                            "record_id": TermAsset.build_record_id("LOCAL", source, regex),
                            "origin": "LOCAL",
                            "source": source,
                            "target": target,
                            "enabled": row.get("enabled", True),
                            "regex": regex,
                            "note": note,
                        },
                        default_origin = "LOCAL",
                        require_target = True,
                    )
                    if term is not None:
                        formal.append(term.to_dict())
                        metadata[term.record_id] = {
                            "type": self._normalize_candidate_type(row.get("type", "")),
                            "case_sensitive": bool(row.get("case_sensitive", False)),
                        }
                else:
                    candidate_record_id = TermAsset.build_record_id(
                        "ANALYSIS",
                        source,
                        regex,
                    )
                    incomplete.append({
                        "record_id": row.get("record_id", ""),
                        "origin": "ANALYSIS",
                        "source": source,
                        "target": target,
                        "enabled": row.get("enabled", True),
                        "regex": regex,
                        "note": note,
                    })
                    metadata[candidate_record_id] = {
                        "type": self._normalize_candidate_type(row.get("type", "")),
                        "case_sensitive": bool(row.get("case_sensitive", False)),
                    }

            assets_data["glossary"] = {
                "enabled": bool(enabled),
                "items": formal,
            }
            assets_data["revision"] = max(current_assets.revision, 0) + 1
            assets_data["updated_at"] = self._now()
            project.set_project_assets(assets_data)

            candidates = self.normalize_analysis_candidates(project.get_analysis_candidates())
            remaining = [
                item
                for item in candidates.get("items", [])
                if str(item.get("record_id", "")) not in consumed
            ]
            candidates["items"] = self._merge_candidate_items(remaining, incomplete)
            old_metadata = candidates.get("glossary_metadata", {})
            if not isinstance(old_metadata, Mapping):
                old_metadata = {}
            candidates["glossary_metadata"] = {
                **{
                    str(key): copy.deepcopy(value)
                    for key, value in old_metadata.items()
                    if str(key) not in consumed
                },
                **metadata,
            }
            candidates["legacy_config_migrated"] = True
            project.set_analysis_candidates(candidates)

        project = self._update_project(update)
        return ProjectAssetsState(
            assets = ProjectAssets.from_dict(project.get_project_assets()),
            analysis_candidates = self.normalize_analysis_candidates(
                project.get_analysis_candidates()
            ),
        )

    def replace_do_not_translate(
        self,
        entries: Iterable[Mapping[str, Any]],
        *,
        enabled: bool,
    ) -> ProjectAssets:
        rows = [dict(entry) for entry in entries if isinstance(entry, Mapping)]

        def update(project: CacheProject) -> None:
            assets_data = project.get_project_assets()
            current = ProjectAssets.from_dict(assets_data)
            normalized: list[dict[str, Any]] = []
            for row in rows:
                source = row.get("source", row.get("src", ""))
                regex = bool(row.get("regex", False))
                term = TermAsset.from_value(
                    {
                        "record_id": TermAsset.build_record_id("LOCAL", source, regex),
                        "origin": "LOCAL",
                        "source": source,
                        "target": "",
                        "enabled": row.get("enabled", True),
                        "regex": regex,
                        "note": row.get("note", row.get("comment", row.get("info", ""))),
                    },
                    default_origin = "LOCAL",
                    require_target = False,
                )
                if term is not None:
                    normalized.append(term.to_dict())
            assets_data["do_not_translate"] = {
                "enabled": bool(enabled),
                "items": normalized,
            }
            assets_data["revision"] = max(current.revision, 0) + 1
            assets_data["updated_at"] = self._now()
            project.set_project_assets(assets_data)

        project = self._update_project(update)
        return ProjectAssets.from_dict(project.get_project_assets())

    def merge_analysis_terms(
        self,
        entries: Iterable[Mapping[str, Any]],
    ) -> dict[str, Any]:
        incoming = [dict(entry) for entry in entries if isinstance(entry, Mapping)]

        def update(project: CacheProject) -> None:
            candidates = self.normalize_analysis_candidates(project.get_analysis_candidates())
            candidates["items"] = self._merge_candidate_items(
                candidates.get("items", []),
                incoming,
            )
            metadata = candidates.get("glossary_metadata", {})
            if not isinstance(metadata, Mapping):
                metadata = {}
            metadata = copy.deepcopy(dict(metadata))
            for item in incoming:
                term = TermAsset.from_value(
                    item,
                    default_origin = "ANALYSIS",
                    require_target = False,
                )
                if term is None:
                    continue
                record_id = TermAsset.build_record_id("ANALYSIS", term.source, term.regex)
                metadata[record_id] = {
                    "type": self._normalize_candidate_type(
                        item.get("type", item.get("category", ""))
                    ),
                    "case_sensitive": bool(item.get("case_sensitive", False)),
                }
            candidates["glossary_metadata"] = metadata
            project.set_analysis_candidates(candidates)

        project = self._update_project(update)
        return self.normalize_analysis_candidates(project.get_analysis_candidates())

    def replace_analysis_terms(
        self,
        entries: Iterable[Mapping[str, Any]],
        *,
        removed_record_ids: Iterable[str] = (),
    ) -> dict[str, Any]:
        """Atomically remove known candidates and merge their replacements."""
        incoming = [dict(entry) for entry in entries if isinstance(entry, Mapping)]
        removed = {
            str(record_id).strip()
            for record_id in removed_record_ids
            if str(record_id).strip()
        }

        def update(project: CacheProject) -> None:
            candidates = self.normalize_analysis_candidates(project.get_analysis_candidates())
            remaining = [
                item
                for item in candidates.get("items", [])
                if str(item.get("record_id", "")) not in removed
            ]
            candidates["items"] = self._merge_candidate_items(remaining, incoming)
            metadata = candidates.get("glossary_metadata", {})
            if not isinstance(metadata, Mapping):
                metadata = {}
            metadata = {
                str(key): copy.deepcopy(value)
                for key, value in metadata.items()
                if str(key) not in removed
            }
            for item in incoming:
                term = TermAsset.from_value(
                    item,
                    default_origin = "ANALYSIS",
                    require_target = False,
                )
                if term is None:
                    continue
                record_id = TermAsset.build_record_id("ANALYSIS", term.source, term.regex)
                metadata[record_id] = {
                    "type": self._normalize_candidate_type(
                        item.get("type", item.get("category", ""))
                    ),
                    "case_sensitive": bool(item.get("case_sensitive", False)),
                }
            candidates["glossary_metadata"] = metadata
            project.set_analysis_candidates(candidates)

        project = self._update_project(update)
        return self.normalize_analysis_candidates(project.get_analysis_candidates())

    @classmethod
    def normalize_analysis_candidates(cls, value: Any) -> dict[str, Any]:
        source = copy.deepcopy(dict(value)) if isinstance(value, Mapping) else {}
        try:
            version = int(source.get("schema_version", cls.CANDIDATE_SCHEMA_VERSION))
        except (TypeError, ValueError):
            version = 0
        if version != cls.CANDIDATE_SCHEMA_VERSION:
            raise ValueError(f"Unsupported analysis candidates schema: {version}")
        source["schema_version"] = cls.CANDIDATE_SCHEMA_VERSION
        source["items"] = cls._merge_candidate_items([], source.get("items", []))
        return source

    @classmethod
    def _merge_candidate_items(cls, current: Any, incoming: Any) -> list[dict[str, Any]]:
        merged: dict[str, dict[str, Any]] = {}
        order: list[str] = []
        values: list[Any] = []
        if isinstance(current, (list, tuple)):
            values.extend(current)
        if isinstance(incoming, (list, tuple)):
            values.extend(incoming)

        for value in values:
            term = TermAsset.from_value(
                value,
                default_origin = "ANALYSIS",
                require_target = False,
            )
            if term is None:
                continue
            data = term.to_dict()
            data["origin"] = "ANALYSIS"
            data["record_id"] = TermAsset.build_record_id(
                "ANALYSIS",
                data["source"],
                bool(data.get("regex", False)),
            )
            key = cls.normalize_source(data["source"])
            if key == "":
                continue
            if key not in merged:
                merged[key] = data
                order.append(key)
                continue
            previous = merged[key]
            if data.get("target"):
                previous["target"] = data["target"]
            if data.get("note"):
                previous["note"] = data["note"]
            previous["enabled"] = bool(previous.get("enabled", True) or data.get("enabled", True))
            previous["regex"] = bool(previous.get("regex", False) or data.get("regex", False))
            previous["record_id"] = TermAsset.build_record_id(
                "ANALYSIS",
                previous["source"],
                previous["regex"],
            )

        return [merged[key] for key in order]

    @staticmethod
    def normalize_source(value: Any) -> str:
        text = unicodedata.normalize("NFKC", str(value or ""))
        return re.sub(r"\s+", " ", text).strip().casefold()

    @staticmethod
    def _normalize_candidate_type(value: Any) -> str:
        text = str(value or "").strip()
        if text == "候选":
            return ""
        if text.startswith("候选 / "):
            return text[len("候选 / "):].strip()
        return text

    def _migrate_legacy_candidates(
        self,
        candidates: dict[str, Any],
        config: Any,
    ) -> dict[str, Any]:
        result = self.normalize_analysis_candidates(candidates)
        if config is not None:
            if "worldbook_draft" not in result:
                result["worldbook_draft"] = copy.deepcopy(
                    getattr(config, "renpy_workbench_generated_worldbook_draft", {})
                )
            if "character_drafts" not in result:
                result["character_drafts"] = copy.deepcopy(
                    getattr(config, "renpy_workbench_generated_character_drafts", [])
                )
            result.setdefault(
                "last_analysis_scope",
                str(getattr(config, "renpy_workbench_last_analysis_scope", "current") or "current"),
            )

            legacy_incomplete: list[dict[str, Any]] = []
            metadata = result.get("glossary_metadata", {})
            if not isinstance(metadata, Mapping):
                metadata = {}
            metadata = copy.deepcopy(dict(metadata))
            for item in getattr(config, "glossary_data", []) or []:
                if not isinstance(item, Mapping):
                    continue
                source = str(item.get("source", item.get("src", "")) or "").strip()
                target = str(item.get("target", item.get("dst", "")) or "").strip()
                if source:
                    origin = "LOCAL" if target else "ANALYSIS"
                    record_id = TermAsset.build_record_id(
                        origin,
                        source,
                        bool(item.get("regex", False)),
                    )
                    metadata[record_id] = {
                        "type": str(item.get("type", item.get("category", "")) or "").strip(),
                        "case_sensitive": bool(item.get("case_sensitive", False)),
                    }
                if source and not target:
                    legacy_incomplete.append(dict(item))
            result["items"] = self._merge_candidate_items(
                result.get("items", []),
                legacy_incomplete,
            )
            result["glossary_metadata"] = metadata

        result["legacy_config_migrated"] = True
        return result

    def _update_project(self, updater) -> CacheProject:
        with CacheManager.LOCK:
            if not self.has_storage:
                project = CacheProject()
                updater(project)
                return project
            recovered = self._recover_json_transaction_unlocked()
            active_project = self._resolve_active_project()
            project = (
                (active_project if recovered is False else None)
                or self._read_project_unlocked()
            )
            updater(project)
            self._write_project_unlocked(project)
            return project

    def _read_project_unlocked(self) -> CacheProject:
        if not self.has_storage:
            return CacheProject()
        db_path = self._db_path()
        use_sqlite = (
            self._sqlite_unavailable is False
            and (os.path.isfile(db_path) or self.cache_use_sqlite)
        )
        sqlite_error: Exception | None = None
        sqlite_missing_project = False
        if use_sqlite:
            try:
                project = CacheDB(db_path).get_project()
            except Exception as error:
                self._sqlite_unavailable = True
                sqlite_error = error
            else:
                if project is not None:
                    return project
                sqlite_missing_project = os.path.isfile(db_path)

        json_path = self._project_json_path()
        if os.path.isfile(json_path):
            with open(json_path, "r", encoding = "utf-8-sig") as reader:
                project = CacheProject.from_dict(json.load(reader))
            # 不能只把 project 记录迁移到 SQLite：翻译条目仍在
            # items.json 时，CacheManager 会优先读到“只有项目、没有条目”
            # 的半成品数据库，进而遮蔽完整 JSON。当前读取 JSON 后保持
            # JSON 为本实例的权威后端，待完整翻译缓存另行建立 SQLite。
            if use_sqlite:
                self._sqlite_unavailable = True
            return project
        if sqlite_error is not None:
            # 没有 JSON 备份时保留原始数据库异常，避免返回空项目后覆盖数据。
            raise sqlite_error
        if sqlite_missing_project:
            # 已存在的 SQLite 缺少 project 元数据，通常表示事务只写入了
            # items 或数据库已损坏；不能把它当作全新目录写入空项目，
            # 否则会静默遮蔽已有条目。
            raise RuntimeError("SQLite cache has no project record")
        return CacheProject()

    def _write_project_unlocked(self, project: CacheProject) -> None:
        if not self.has_storage:
            return
        db_path = self._db_path()
        items_path = str(Path(self.output_folder) / "cache" / "items.json")
        # 没有条目 JSON 时允许首次资产引导创建 SQLite（兼容旧缓存与
        # 现有 SQLite 用户）；若同目录已有完整 JSON，则不能创建只有
        # project 记录的数据库去遮蔽它，改用 JSON 保存资产。
        if not os.path.isfile(db_path) and os.path.isfile(items_path):
            self._sqlite_unavailable = True
        if (
            self._sqlite_unavailable is False
            and (os.path.isfile(db_path) or self.cache_use_sqlite)
        ):
            try:
                CacheDB(db_path).set_project(project)
            except Exception:
                self._sqlite_unavailable = True
            else:
                return

        self._write_project_json_unlocked(project)

    def _write_project_json_unlocked(self, project: CacheProject) -> None:
        path = self._project_json_path()
        os.makedirs(os.path.dirname(path), exist_ok = True)
        temp_path = f"{path}.assets.tmp"
        try:
            with open(temp_path, "w", encoding = "utf-8") as writer:
                json.dump(project.asdict(), writer, ensure_ascii = False, separators = (",", ":"))
                writer.flush()
                os.fsync(writer.fileno())
            os.replace(temp_path, path)
        finally:
            if os.path.isfile(temp_path):
                os.remove(temp_path)

    def _recover_json_transaction_unlocked(self) -> bool:
        if not self.has_storage:
            return False
        journal_path = Path(self.output_folder) / "cache" / CacheManager.RESET_JOURNAL_NAME
        if journal_path.is_file() is False:
            return False
        db_path = Path(self._db_path())
        if db_path.is_file():
            # SQLite 可读且包含完整条目时，journal 可能只是旧 JSON 后端
            # 留下的残片；此时以 SQLite 为准，避免被无关坏日志阻断工作台。
            try:
                store = CacheDB(str(db_path))
                project = store.get_project()
                items = store.get_items()
                complete = project is not None
                if complete and not items:
                    items_path = Path(self.output_folder) / "cache" / "items.json"
                    if items_path.is_file():
                        payload = json.loads(items_path.read_text(encoding = "utf-8-sig"))
                        complete = not (isinstance(payload, list) and len(payload) > 0)
                if complete:
                    return False
            except Exception:
                # 数据库损坏/半成品时必须继续走 JSON journal 恢复。
                pass
        # reset.journal.json 是跨文件替换的写前日志。SQLite 不完整时，
        # 直接跳过会让工作台继续读取旧 project.json。
        manager = CacheManager(service = False)
        manager.cache_use_sqlite = False
        manager._recover_json_transaction(self.output_folder)
        return True

    def _resolve_active_project(self) -> CacheProject | None:
        try:
            from module.Engine.Engine import Engine

            translator = getattr(Engine.get(), "translator", None)
            runtime_output = str(
                getattr(translator, "_active_cache_output_folder", "") or ""
            ).strip()
            manager = getattr(translator, "cache_manager", None)
            if manager is None or runtime_output == "":
                return None
            if self._same_path(runtime_output, self.output_folder):
                return manager.get_project()
        except Exception:
            return None
        return None

    @staticmethod
    def _same_path(left: str, right: str) -> bool:
        try:
            return os.path.normcase(os.path.abspath(left)) == os.path.normcase(os.path.abspath(right))
        except Exception:
            return False

    @staticmethod
    def _has_project_state(assets: ProjectAssets) -> bool:
        return bool(
            assets.revision > 0
            or assets.updated_at
            or assets.worldbook_enabled
            or assets.character_cards_enabled
            or assets.glossary_enabled
            or assets.do_not_translate_enabled
            or len(assets.worldbook) > 0
            or len(assets.character_cards) > 0
            or len(assets.glossary) > 0
            or len(assets.do_not_translate) > 0
        )

    def _stamp_assets(self, assets: ProjectAssets, *, minimum_revision: int) -> ProjectAssets:
        data = assets.to_dict()
        data["revision"] = max(int(data.get("revision", 0) or 0), int(minimum_revision))
        data["updated_at"] = self._now()
        return ProjectAssets.from_dict(data)

    @staticmethod
    def _term_to_legacy(item: TermAsset) -> dict[str, Any]:
        return {
            "record_id": item.record_id,
            "src": item.source,
            "dst": item.target,
            "info": item.note,
            "enabled": item.enabled,
            "regex": item.regex,
            "origin": item.origin,
        }

    def _db_path(self) -> str:
        return str(Path(self.output_folder) / "cache" / CacheManager.CACHE_DB_NAME)

    def _project_json_path(self) -> str:
        return str(Path(self.output_folder) / "cache" / "project.json")

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()
