import dataclasses
import copy
import threading
from typing import Any
from base.compat import Self

from base.Base import Base

@dataclasses.dataclass
class CacheProject():

    EXTRAS_SCHEMA_VERSION = 2
    PROJECT_ASSETS_SCHEMA_VERSION = 1
    ANALYSIS_CANDIDATES_SCHEMA_VERSION = 1

    LEGACY_PROGRESS_KEYS = frozenset({
        "failed_line_count",
        "fallback_line_count",
        "line",
        "line_count_mismatch_count",
        "requested_line_count",
        "start_time",
        "time",
        "total_input_tokens",
        "total_line",
        "total_output_tokens",
        "total_tokens",
    })
    RUN_SCOPED_PARTITIONS = frozenset({
        "polishing_progress",
        "proofreading_progress",
        "quality_progress",
        "translation_snapshot",
    })

    id: str = ""                                                                        # 项目 ID
    status: Base.TranslationStatus = Base.TranslationStatus.UNTRANSLATED                # 翻译状态
    extras: dict = dataclasses.field(default_factory = dict)                            # 额外数据

    # 线程锁
    lock: threading.Lock = dataclasses.field(init = False, repr = False, compare = False, default_factory = threading.Lock)

    def __post_init__(self) -> None:
        status = Base.normalize_translation_status(self.status)
        if not Base.is_project_status(status):
            raise ValueError(f"Invalid cache project status: {status.value}")
        self.status = status
        self.extras = self.migrate_extras(self.extras)

    @classmethod
    def _empty_analysis_candidates(cls) -> dict[str, Any]:
        return {
            "schema_version": cls.ANALYSIS_CANDIDATES_SCHEMA_VERSION,
            "items": [],
        }

    @staticmethod
    def _normalize_snapshot(snapshot: Any) -> dict[str, Any]:
        if hasattr(snapshot, "to_snapshot") and callable(snapshot.to_snapshot):
            snapshot = snapshot.to_snapshot()
        if not isinstance(snapshot, dict):
            return {}
        if not snapshot:
            return {}

        # Keep the persistence boundary defensive even when a caller supplies a
        # raw dict instead of a TranslationTaskContext.
        from module.Engine.Translator.TranslationTaskContext import sanitize_translation_snapshot

        return sanitize_translation_snapshot(snapshot)

    @classmethod
    def _normalize_project_assets(cls, assets: Any) -> dict[str, Any]:
        from module.Engine.Translator.TranslationTaskContext import ProjectAssets

        return ProjectAssets.from_dict(assets).to_dict()

    @classmethod
    def _normalize_analysis_candidates(cls, candidates: Any) -> dict[str, Any]:
        if not isinstance(candidates, dict):
            return cls._empty_analysis_candidates()
        result = copy.deepcopy(candidates)
        try:
            version = int(result.get("schema_version", cls.ANALYSIS_CANDIDATES_SCHEMA_VERSION))
        except (TypeError, ValueError):
            version = 0
        if version != cls.ANALYSIS_CANDIDATES_SCHEMA_VERSION:
            raise ValueError(f"Unsupported analysis candidates schema: {version}")
        result["schema_version"] = cls.ANALYSIS_CANDIDATES_SCHEMA_VERSION
        result.setdefault("items", [])
        return result

    @classmethod
    def migrate_extras(cls, extras: Any) -> dict[str, Any]:
        """Normalize legacy flat extras into the versioned partition layout."""
        source = copy.deepcopy(extras) if isinstance(extras, dict) else {}
        try:
            source_version = int(source.get("schema_version", 0))
        except (TypeError, ValueError):
            source_version = -1
        if source_version not in (0, 1, cls.EXTRAS_SCHEMA_VERSION):
            raise ValueError(f"Unsupported cache extras schema: {source_version}")
        result: dict[str, Any] = {}

        progress = source.get("progress", {})
        if not isinstance(progress, dict):
            progress = {}
        else:
            progress = copy.deepcopy(progress)

        for key in cls.LEGACY_PROGRESS_KEYS:
            if key in source:
                progress.setdefault(key, copy.deepcopy(source[key]))

        reserved = {
            "schema_version",
            "progress",
            "project_assets",
            "analysis_candidates",
            "translation_snapshot",
        } | cls.LEGACY_PROGRESS_KEYS
        for key, value in source.items():
            if key not in reserved:
                result[key] = copy.deepcopy(value)

        project_assets = source.get("project_assets")
        project_assets = cls._normalize_project_assets(project_assets)

        analysis_candidates = source.get("analysis_candidates")
        analysis_candidates = cls._normalize_analysis_candidates(analysis_candidates)

        translation_snapshot = source.get("translation_snapshot")
        translation_snapshot = cls._normalize_snapshot(translation_snapshot)

        result.update({
            "schema_version": cls.EXTRAS_SCHEMA_VERSION,
            "progress": progress,
            "project_assets": copy.deepcopy(project_assets),
            "analysis_candidates": copy.deepcopy(analysis_candidates),
            "translation_snapshot": copy.deepcopy(translation_snapshot),
        })
        return result

    @classmethod
    def from_dict(cls, data: dict) -> Self:
        class_fields = {f.name for f in dataclasses.fields(cls)}
        filtered_data = {k: v for k, v in data.items() if k in class_fields}
        return cls(**filtered_data)

    # 获取项目 ID
    def get_id(self) -> str:
        with self.lock:
            return self.id

    # 设置项目 ID
    def set_id(self, id: str) -> None:
        with self.lock:
            self.id = id

    # 获取翻译状态
    def get_status(self) -> Base.TranslationStatus:
        with self.lock:
            return self.status

    # 设置翻译状态
    def set_status(self, status: Base.TranslationStatus) -> None:
        normalized = Base.normalize_translation_status(status)
        if not Base.is_project_status(normalized):
            raise ValueError(f"Invalid cache project status: {normalized.value}")
        with self.lock:
            self.status = normalized

    # 获取额外数据
    def get_extras(self) -> dict:
        with self.lock:
            return copy.deepcopy(self.extras)

    # 设置额外数据
    def set_extras(self, extras: dict) -> None:
        with self.lock:
            is_legacy_progress = (
                isinstance(extras, dict)
                and "schema_version" not in extras
                and "progress" not in extras
                and "project_assets" not in extras
                and "analysis_candidates" not in extras
                and "translation_snapshot" not in extras
            )
            if is_legacy_progress:
                merged = copy.deepcopy(self.extras)
                merged["progress"] = {
                    key: copy.deepcopy(value)
                    for key, value in extras.items()
                    if key in self.LEGACY_PROGRESS_KEYS
                }
                for key, value in extras.items():
                    if key not in self.LEGACY_PROGRESS_KEYS:
                        merged[key] = copy.deepcopy(value)
                self.extras = self.migrate_extras(merged)
            else:
                self.extras = self.migrate_extras(extras)

    def get_progress(self) -> dict[str, Any]:
        with self.lock:
            return copy.deepcopy(self.extras["progress"])

    def set_progress(self, progress: dict[str, Any] | None) -> None:
        with self.lock:
            self.extras["progress"] = copy.deepcopy(progress) if isinstance(progress, dict) else {}

    def get_project_assets(self) -> dict[str, Any]:
        with self.lock:
            return copy.deepcopy(self.extras["project_assets"])

    def set_project_assets(self, assets: Any) -> None:
        assets = self._normalize_project_assets(assets)
        with self.lock:
            self.extras["project_assets"] = copy.deepcopy(assets)

    def get_analysis_candidates(self) -> dict[str, Any]:
        with self.lock:
            return copy.deepcopy(self.extras["analysis_candidates"])

    def set_analysis_candidates(self, candidates: dict[str, Any] | None) -> None:
        candidates = self._normalize_analysis_candidates(candidates)
        with self.lock:
            self.extras["analysis_candidates"] = copy.deepcopy(candidates)

    def get_translation_snapshot(self) -> dict[str, Any] | None:
        with self.lock:
            snapshot = self.extras["translation_snapshot"]
            return copy.deepcopy(snapshot) if snapshot else None

    def set_translation_snapshot(self, snapshot: Any) -> None:
        snapshot = self._normalize_snapshot(snapshot)
        with self.lock:
            self.extras["translation_snapshot"] = copy.deepcopy(snapshot)

    def clear_translation_snapshot(self) -> None:
        with self.lock:
            self.extras["translation_snapshot"] = {}

    def reset_translation_run(
        self,
        snapshot: Any = None,
        progress: dict[str, Any] | None = None,
    ) -> None:
        """Clear one translation run while preserving project-level data."""
        snapshot = self._normalize_snapshot(snapshot)
        with self.lock:
            self.extras["progress"] = (
                copy.deepcopy(progress) if isinstance(progress, dict) else {}
            )
            for key in self.RUN_SCOPED_PARTITIONS:
                if key == "translation_snapshot":
                    self.extras[key] = copy.deepcopy(snapshot)
                else:
                    self.extras.pop(key, None)
            self.status = Base.TranslationStatus.UNTRANSLATED

    def asdict(self) -> dict[str, Any]:
        with self.lock:
            return {
                v.name: copy.deepcopy(getattr(self, v.name))
                for v in dataclasses.fields(self)
                if v.init != False
            }
