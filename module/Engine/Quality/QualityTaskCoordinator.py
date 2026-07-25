from __future__ import annotations

import copy
import dataclasses
import json
import math
import threading
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

from base.Base import Base
from base.compat import Self, StrEnum
from module.Cache.CacheItem import CacheItem
from module.Cache.CacheManager import CacheLoadError, CacheManager
from module.Cache.CacheProject import CacheProject
from module.Config import Config
from module.Engine.Engine import Engine
from module.Engine.Translator.TranslationTaskContext import (
    TranslationTaskContext,
    merge_provider_credentials,
)

from .PolisherTask import PolisherTask
from .ProofreadTask import ProofreadTask
from ._common import QualityTaskFailure, QualityTaskResult


class QualityTaskType(StrEnum):
    """质量任务类型。"""

    POLISHER = "POLISHER"
    PROOFREADER = "PROOFREADER"


class QualityTaskState(StrEnum):
    """质量任务运行状态。"""

    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


@dataclasses.dataclass(frozen = True)
class QualityTaskProgress:
    """可直接持久化并发送给 UI 的质量任务进度。"""

    schema_version: int = 1
    task_type: QualityTaskType = QualityTaskType.POLISHER
    state: QualityTaskState = QualityTaskState.RUNNING
    snapshot_id: str = ""
    total_count: int = 0
    completed_count: int = 0
    updated_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    batch_count: int = 0
    total_batch_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    failures: tuple[QualityTaskFailure, ...] = ()
    error_type_counts: tuple[tuple[str, int], ...] = ()
    cancel_requested: bool = False
    error_message: str = ""
    started_at: str = ""
    updated_at: str = ""
    completed_at: str = ""

    @property
    def is_finished(self) -> bool:
        return self.state in {
            QualityTaskState.COMPLETED,
            QualityTaskState.CANCELLED,
            QualityTaskState.FAILED,
        }

    @property
    def processed_count(self) -> int:
        """返回与进度协议同义的已处理条目数。"""
        return self.completed_count

    def as_dict(self) -> dict[str, Any]:
        """转换为不含运行凭据的 JSON 兼容结构。"""
        return {
            "schema_version": self.schema_version,
            "task_type": self.task_type.value,
            "state": self.state.value,
            "snapshot_id": self.snapshot_id,
            "total_count": self.total_count,
            "completed_count": self.completed_count,
            "updated_count": self.updated_count,
            "failed_count": self.failed_count,
            "skipped_count": self.skipped_count,
            "batch_count": self.batch_count,
            "total_batch_count": self.total_batch_count,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "failures": [
                {
                    "item_index": failure.item_index,
                    "reason": failure.reason,
                    "attempts": failure.attempts,
                }
                for failure in self.failures
            ],
            "error_type_counts": dict(self.error_type_counts),
            "cancel_requested": self.cancel_requested,
            "error_message": self.error_message,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
            "completed_at": self.completed_at,
        }

    def to_dict(self) -> dict[str, Any]:
        """返回持久化用字典，作为 ``as_dict`` 的兼容别名。"""
        return self.as_dict()


ProgressCallback = Callable[[QualityTaskProgress], None]
DoneCallback = Callable[[QualityTaskProgress], None]
CacheManagerFactory = Callable[[], CacheManager]
QualityTaskFactory = Callable[[TranslationTaskContext], Any]


class QualityTaskCoordinator(Base):
    """
    协调独立润色/校对任务，并在每个已完成批次后保存缓存。

    ``on_progress`` 和 ``on_done`` 都在质量任务工作线程调用；Qt 调用方应通过
    ``pyqtSignal`` 切回 UI 线程。取消只会阻止尚未开始的后续批次，当前批次会
    正常完成、保存，然后进入 ``CANCELLED``。
    """

    PROGRESS_SCHEMA_VERSION = 1
    DEFAULT_POLISHING_BATCH_SIZE = 8
    # 校对默认按小批次保存，避免每条都重写整个缓存。
    DEFAULT_PROOFREADING_BATCH_SIZE = 8

    @staticmethod
    def _public_error_message(exc: BaseException) -> str:
        """把内部异常转换成安全、可操作的用户提示。

        不直接展示第三方异常文本：其中可能包含请求地址、认证信息或服务端
        返回体。分类只依据异常类型和少量固定关键词，详细信息仍写入日志。
        """
        if isinstance(exc, CacheLoadError):
            return "无法载入翻译缓存，请确认项目路径和输出目录一致后重试"

        if isinstance(exc, (FileNotFoundError, PermissionError, OSError)):
            return "无法访问翻译缓存，请检查目录权限、磁盘空间后重试"

        if isinstance(exc, json.JSONDecodeError):
            return "翻译缓存格式损坏，请重新执行翻译后再进行校对"

        if isinstance(exc, ValueError):
            # 这些异常由 _restore_context/_resolve_runtime_provider 主动抛出，
            # 只用固定关键词分类，不把原始文本写入持久化进度。
            reason = str(exc).casefold()
            if "provider" in reason or "翻译接口" in reason or "平台配置" in reason:
                return "无法进行质量校对：原翻译接口不可用，请恢复平台配置后重试"
            if "translation_snapshot" in reason or "快照" in reason:
                return "无法进行质量校对：当前缓存缺少翻译快照，请重新执行一键翻译"
            if "缓存" in reason or "cache" in reason:
                return "无法载入翻译缓存，请确认项目路径和输出目录一致后重试"
            return "质量任务配置无效，请检查输出目录和选中条目"

        if isinstance(exc, TypeError):
            return "质量任务配置无效，请检查当前项目设置"

        return "质量任务执行失败，请稍后重试；详细原因已写入日志"

    def __init__(
        self,
        *,
        engine: Engine | None = None,
        cache_manager_factory: CacheManagerFactory | None = None,
        polisher_factory: QualityTaskFactory | None = None,
        proofreader_factory: QualityTaskFactory | None = None,
    ) -> None:
        super().__init__()
        self.engine = engine or Engine.get()
        self.cache_manager_factory = cache_manager_factory or (
            lambda: CacheManager(service = False)
        )
        self.polisher_factory = polisher_factory or PolisherTask
        self.proofreader_factory = proofreader_factory or ProofreadTask

        self._lock = threading.RLock()
        self._cancel_event = threading.Event()
        self._busy = False
        self._progress: QualityTaskProgress | None = None
        self._on_progress: ProgressCallback | None = None
        self._on_done: DoneCallback | None = None

    @classmethod
    def get(cls) -> Self:
        if not hasattr(cls, "__instance__"):
            cls.__instance__ = cls()
        return cls.__instance__

    def is_busy(self) -> bool:
        with self._lock:
            return self._busy

    def get_progress(self) -> QualityTaskProgress | None:
        with self._lock:
            return self._progress

    def cancel(self) -> bool:
        """请求在当前批次保存后停止，不中断正在进行的网络请求。"""
        with self._lock:
            if not self._busy:
                return False
            self._cancel_event.set()
            if self._progress is not None:
                self._progress = dataclasses.replace(
                    self._progress,
                    cancel_requested = True,
                    updated_at = self._now(),
                )
            return True

    def start_polishing(
        self,
        config: Config,
        all_items: Sequence[CacheItem],
        selected_items: Sequence[CacheItem],
        *,
        batch_size: int | None = None,
        on_progress: ProgressCallback | None = None,
        on_done: DoneCallback | None = None,
    ) -> bool:
        """异步启动 AI 润色；仅 ``TRANSLATED`` 条目会被核心任务消费。"""
        return self._start(
            QualityTaskType.POLISHER,
            config,
            all_items,
            selected_items,
            warning_map = None,
            batch_size = batch_size,
            on_progress = on_progress,
            on_done = on_done,
        )

    def start_proofreading(
        self,
        config: Config,
        all_items: Sequence[CacheItem],
        selected_items: Sequence[CacheItem],
        *,
        warning_map: Mapping[int, Sequence[Any]] | None = None,
        batch_size: int | None = None,
        on_progress: ProgressCallback | None = None,
        on_done: DoneCallback | None = None,
    ) -> bool:
        """异步启动 AI 校对；错误类型通过 ``warning_map`` 传给核心任务。"""
        return self._start(
            QualityTaskType.PROOFREADER,
            config,
            all_items,
            selected_items,
            warning_map = warning_map,
            batch_size = batch_size,
            on_progress = on_progress,
            on_done = on_done,
        )

    def _start(
        self,
        task_type: QualityTaskType,
        config: Config,
        all_items: Sequence[CacheItem],
        selected_items: Sequence[CacheItem],
        *,
        warning_map: Mapping[int, Sequence[Any]] | None,
        batch_size: int | None,
        on_progress: ProgressCallback | None,
        on_done: DoneCallback | None,
    ) -> bool:
        if not isinstance(config, Config):
            raise TypeError("质量任务需要当前 Config 以读取输出目录和运行凭据")
        if str(config.output_folder or "").strip() == "":
            raise ValueError("质量任务需要有效的缓存输出目录")

        cached_items = list(all_items)
        targets = list(selected_items)
        if not targets:
            raise ValueError("质量任务至少需要一个选中条目")
        cached_ids = {id(item) for item in cached_items}
        if any(id(item) not in cached_ids for item in targets):
            raise ValueError("选中条目必须来自当前缓存条目列表")

        resolved_batch_size = self._normalize_batch_size(task_type, batch_size)
        total_batch_count = math.ceil(len(targets) / resolved_batch_size)
        now = self._now()
        initial_progress = QualityTaskProgress(
            schema_version = self.PROGRESS_SCHEMA_VERSION,
            task_type = task_type,
            total_count = len(targets),
            total_batch_count = total_batch_count,
            started_at = now,
            updated_at = now,
        )

        with self._lock:
            if self._busy:
                return False
            if not self.engine.try_set_status(Engine.Status.IDLE, Engine.Status.QUALITY):
                return False

            self._busy = True
            self._cancel_event.clear()
            self._progress = initial_progress
            self._on_progress = on_progress
            self._on_done = on_done
            runtime_config = copy.deepcopy(config)
            copied_warning_map = dict(warning_map or {})
            thread = threading.Thread(
                target = self._run_worker,
                args = (
                    task_type,
                    runtime_config,
                    cached_items,
                    targets,
                    copied_warning_map,
                    resolved_batch_size,
                    initial_progress,
                ),
                name = f"{Engine.TASK_PREFIX}QUALITY",
                daemon = True,
            )
        try:
            thread.start()
        except Exception:
            with self._lock:
                self._busy = False
                self._on_progress = None
                self._on_done = None
            self.engine.release_status(Engine.Status.QUALITY)
            raise
        return True

    def _run_worker(
        self,
        task_type: QualityTaskType,
        config: Config,
        all_items: list[CacheItem],
        targets: list[CacheItem],
        warning_map: Mapping[int, Sequence[Any]],
        batch_size: int,
        progress: QualityTaskProgress,
    ) -> None:
        final_progress = progress
        cache_manager: CacheManager | None = None
        project: CacheProject | None = None
        try:
            cache_manager = self.cache_manager_factory()
            cache_manager.cache_use_sqlite = bool(config.cache_use_sqlite)
            # 使用完整严格载入，复用 SQLite 损坏时的 JSON 回退逻辑；随后
            # 仍以当前页面条目覆盖内存列表，保证质量任务和校对页选中集一致。
            cache_manager.load_from_file(config.output_folder, strict = True)
            cache_manager.set_items(all_items)
            project = cache_manager.get_project()

            context = self._restore_context(project, config)
            progress = dataclasses.replace(
                progress,
                snapshot_id = context.snapshot_id,
                cancel_requested = self._cancel_event.is_set(),
                updated_at = self._now(),
            )
            self._publish_progress(progress)
            self._save_progress(cache_manager, project, all_items, config.output_folder, progress)

            task = (
                self.polisher_factory(context)
                if task_type == QualityTaskType.POLISHER
                else self.proofreader_factory(context)
            )
            all_item_indices = {id(item): index for index, item in enumerate(all_items)}
            failures: list[QualityTaskFailure] = []
            error_counts: Counter[str] = Counter()

            for batch_start in range(0, len(targets), batch_size):
                if self._cancel_event.is_set():
                    break

                batch = targets[batch_start:batch_start + batch_size]
                batch_states = {
                    id(item): item.get_translation_state()
                    for item in batch
                }
                try:
                    if task_type == QualityTaskType.POLISHER:
                        result = task.run(batch)
                    else:
                        result = task.run(batch, warning_map = warning_map)
                    if not isinstance(result, QualityTaskResult):
                        raise TypeError("质量任务返回了无效结果")
                except Exception:
                    # 核心任务若在写入部分条目后抛出异常，恢复整个当前批次，
                    # 保证失败边界不会把半成品当作成功译文保存。
                    self._restore_batch_states(batch, batch_states)
                    raise

                batch_failures = self._map_failures(
                    result.failures,
                    batch,
                    all_item_indices,
                )
                failures.extend(batch_failures)
                for failure in batch_failures:
                    error_counts.update(self._failure_codes(failure.reason))

                progress = dataclasses.replace(
                    progress,
                    completed_count = progress.completed_count + len(batch),
                    updated_count = progress.updated_count + result.updated_count,
                    failed_count = progress.failed_count + result.failed_count,
                    skipped_count = progress.skipped_count + result.skipped_count,
                    batch_count = progress.batch_count + 1,
                    input_tokens = progress.input_tokens + result.input_tokens,
                    output_tokens = progress.output_tokens + result.output_tokens,
                    failures = tuple(failures),
                    error_type_counts = tuple(sorted(error_counts.items())),
                    cancel_requested = self._cancel_event.is_set(),
                    updated_at = self._now(),
                )
                self._save_progress(
                    cache_manager,
                    project,
                    all_items,
                    config.output_folder,
                    progress,
                )
                self._publish_progress(progress)

            completed_at = self._now()
            cancelled = self._cancel_event.is_set() and progress.completed_count < progress.total_count
            final_progress = dataclasses.replace(
                progress,
                state = (
                    QualityTaskState.CANCELLED
                    if cancelled
                    else QualityTaskState.COMPLETED
                ),
                cancel_requested = self._cancel_event.is_set(),
                updated_at = completed_at,
                completed_at = completed_at,
            )
            self._save_progress(
                cache_manager,
                project,
                all_items,
                config.output_folder,
                final_progress,
            )
        except Exception as exc:
            # 异常文本可能来自第三方客户端，不写入缓存或日志，避免其中夹带运行凭据。
            public_error = __class__._public_error_message(exc)
            self.error(f"质量任务协调器运行失败: {type(exc).__name__}")
            completed_at = self._now()
            final_progress = dataclasses.replace(
                progress,
                state = QualityTaskState.FAILED,
                cancel_requested = self._cancel_event.is_set(),
                error_message = public_error,
                updated_at = completed_at,
                completed_at = completed_at,
            )
            if cache_manager is not None and project is not None:
                try:
                    self._save_progress(
                        cache_manager,
                        project,
                        all_items,
                        config.output_folder,
                        final_progress,
                    )
                except Exception as save_exc:
                    self.error(f"质量任务失败状态保存失败: {type(save_exc).__name__}")
        finally:
            self.engine.release_status(Engine.Status.QUALITY)
            self._finish(final_progress)

    def _finish(self, progress: QualityTaskProgress) -> None:
        with self._lock:
            self._progress = progress
            self._busy = False
            on_progress = self._on_progress
            on_done = self._on_done
            self._on_progress = None
            self._on_done = None

        self._emit_runtime_update(progress)
        self._invoke_callback(on_progress, progress)
        self._invoke_callback(on_done, progress)

    def _publish_progress(self, progress: QualityTaskProgress) -> None:
        with self._lock:
            self._progress = progress
            callback = self._on_progress
        self._emit_runtime_update(progress)
        self._invoke_callback(callback, progress)

    def _emit_runtime_update(self, progress: QualityTaskProgress) -> None:
        self.emit(Base.Event.TRANSLATION_UPDATE, {
            "quality_task": progress.as_dict(),
        })

    def _invoke_callback(
        self,
        callback: ProgressCallback | DoneCallback | None,
        progress: QualityTaskProgress,
    ) -> None:
        if not callable(callback):
            return
        try:
            callback(progress)
        except Exception as exc:
            self.warning(f"质量任务回调执行失败: {type(exc).__name__}")

    def _restore_context(
        self,
        project: CacheProject,
        config: Config,
    ) -> TranslationTaskContext:
        snapshot = project.get_translation_snapshot()
        if not snapshot:
            raise ValueError("当前缓存没有 translation_snapshot，无法恢复质量任务语义")
        runtime_provider = self._resolve_runtime_provider(snapshot, config)
        return TranslationTaskContext.from_snapshot(
            snapshot,
            runtime_provider = runtime_provider,
        )

    @staticmethod
    def _resolve_runtime_provider(snapshot: Mapping[str, Any], config: Config) -> dict[str, Any]:
        request_policy = snapshot.get("request_policy", {})
        persisted = (
            request_policy.get("provider", {})
            if isinstance(request_policy, Mapping)
            else {}
        )
        persisted = dict(persisted) if isinstance(persisted, Mapping) else {}

        current: dict[str, Any] = {}
        persisted_id = persisted.get("id")
        if isinstance(config.platforms, list):
            for platform in config.platforms:
                if isinstance(platform, dict) and platform.get("id") == persisted_id:
                    current = copy.deepcopy(platform)
                    break
        if persisted and not current:
            raise ValueError("快照中的翻译接口已不存在，请恢复原接口后再进行校对")
        if not current:
            active = config.get_platform(config.activate_platform)
            if isinstance(active, dict):
                current = copy.deepcopy(active)
        if not current:
            raise ValueError("当前没有可用于质量任务的接口配置")
        if not persisted:
            return current
        return merge_provider_credentials(persisted, current)

    @classmethod
    def _save_progress(
        cls,
        cache_manager: CacheManager,
        project: CacheProject,
        all_items: list[CacheItem],
        output_folder: str,
        progress: QualityTaskProgress,
    ) -> None:
        extras = project.get_extras()
        extras[cls._progress_partition(progress.task_type)] = progress.as_dict()
        project.set_extras(extras)
        cache_manager.save_to_file(
            project = project,
            items = all_items,
            output_folder = output_folder,
            strict = True,
        )

    @staticmethod
    def _progress_partition(task_type: QualityTaskType) -> str:
        if task_type == QualityTaskType.POLISHER:
            return "polishing_progress"
        return "proofreading_progress"

    @classmethod
    def _normalize_batch_size(
        cls,
        task_type: QualityTaskType,
        batch_size: int | None,
    ) -> int:
        default = (
            cls.DEFAULT_POLISHING_BATCH_SIZE
            if task_type == QualityTaskType.POLISHER
            else cls.DEFAULT_PROOFREADING_BATCH_SIZE
        )
        if batch_size is None:
            return default
        try:
            return max(1, int(batch_size))
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _map_failures(
        failures: Sequence[QualityTaskFailure],
        batch: Sequence[CacheItem],
        all_item_indices: Mapping[int, int],
    ) -> list[QualityTaskFailure]:
        mapped: list[QualityTaskFailure] = []
        for failure in failures:
            item_index = failure.item_index
            if 0 <= item_index < len(batch):
                item_index = all_item_indices.get(id(batch[item_index]), item_index)
            mapped.append(QualityTaskFailure(
                item_index = item_index,
                reason = failure.reason,
                attempts = failure.attempts,
            ))
        return mapped

    @staticmethod
    def _restore_batch_states(
        batch: Sequence[CacheItem],
        states: Mapping[int, Mapping[str, Any]],
    ) -> None:
        """恢复异常批次的译文状态与质量元数据。"""
        for item in batch:
            state = states.get(id(item))
            if not isinstance(state, Mapping):
                continue
            item.set_dst(state.get("dst", ""))
            item.set_name_dst(copy.deepcopy(state.get("name_dst")))
            item.set_status(state.get("status", Base.TranslationStatus.UNTRANSLATED))
            item.set_retry_count(state.get("retry_count", 0))
            item.set_metadata(copy.deepcopy(state.get("metadata", {})))

    @staticmethod
    def _failure_codes(reason: str) -> tuple[str, ...]:
        text = str(reason or "UNKNOWN").strip() or "UNKNOWN"
        if text.startswith("VALIDATION_FAILED:"):
            details = text.split(":", 1)[1]
            codes = [value.split(":", 1)[0].strip() for value in details.split(",")]
            return tuple(value for value in codes if value) or ("VALIDATION_FAILED",)
        return (text.split(":", 1)[0],)

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()


__all__ = [
    "QualityTaskCoordinator",
    "QualityTaskProgress",
    "QualityTaskState",
    "QualityTaskType",
]
