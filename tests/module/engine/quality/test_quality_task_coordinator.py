from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable

import pytest

from base.Base import Base
from base.BaseLanguage import BaseLanguage
from module.Cache.CacheItem import CacheItem
from module.Cache.CacheManager import CacheLoadError, CacheManager
from module.Cache.CacheProject import CacheProject
from module.Config import Config
from module.Engine.Engine import Engine
from module.Engine.Quality.QualityTaskCoordinator import (
    QualityTaskCoordinator,
    QualityTaskState,
)
from module.Engine.Quality._common import QualityTaskResult
from module.Engine.TaskRequester import TaskRequester
from module.Engine.Translator.TranslationTaskContext import (
    ProjectAssets,
    TranslationTaskContext,
)
from module.Engine.Translator.Translator import Translator
from module.Workbench.AnalysisService import AnalysisServiceError, WorkbenchAnalysisService


class RecordingTask:
    def __init__(
        self,
        context: TranslationTaskContext,
        *,
        cancel: Callable[[], bool] | None = None,
        cancel_on_call: int = 1,
    ) -> None:
        self.context = context
        self.cancel = cancel
        self.cancel_on_call = cancel_on_call
        self.calls = 0

    def run(self, items: list[CacheItem], **kwargs) -> QualityTaskResult:
        del kwargs
        self.calls += 1
        for item in items:
            item.set_quality_result(
                f"润色：{item.get_dst()}",
                CacheItem.QualityOrigin.POLISHER,
            )
        if self.cancel is not None and self.calls == self.cancel_on_call:
            self.cancel()
        return QualityTaskResult(
            total_count = len(items),
            eligible_count = len(items),
            updated_count = len(items),
            input_tokens = 2,
            output_tokens = 3,
        )


class MutatingFailureTask:
    def __init__(self, context: TranslationTaskContext) -> None:
        del context

    def run(self, items: list[CacheItem], **kwargs) -> QualityTaskResult:
        del kwargs
        items[0].set_quality_result("不应保存", CacheItem.QualityOrigin.POLISHER)
        raise RuntimeError("模拟批次异常")


class BlockingCancellableTask:
    """模拟会等待请求级取消令牌的质量请求。"""

    started = threading.Event()

    def __init__(self, context: TranslationTaskContext) -> None:
        del context

    def run(self, items: list[CacheItem], **kwargs) -> QualityTaskResult:
        del kwargs
        self.started.set()
        deadline = time.monotonic() + 3
        while not TaskRequester.is_cancel_requested() and time.monotonic() < deadline:
            time.sleep(0.01)
        if not TaskRequester.is_cancel_requested():
            raise TimeoutError("没有收到质量任务取消令牌")
        items[0].set_quality_result("不应保存", CacheItem.QualityOrigin.POLISHER)
        return QualityTaskResult(
            total_count = len(items),
            eligible_count = len(items),
            updated_count = 1,
        )


def _prepare_cache(tmp_path, item_count: int = 3) -> tuple[Config, list[CacheItem]]:
    snapshot_config = Config(
        source_language = BaseLanguage.Enum.EN,
        target_language = BaseLanguage.Enum.ZH,
        output_folder = str(tmp_path),
        cache_use_sqlite = False,
        activate_platform = 7,
        platforms = [{
            "id": 7,
            "api_url": "https://snapshot.invalid/v1",
            "model": "snapshot-model",
            "api_key": ["stale-secret"],
        }],
    )
    context = TranslationTaskContext.from_config(
        snapshot_config,
        ProjectAssets(),
        created_at = "2026-07-25T00:00:00+00:00",
    )
    project = CacheProject(
        id = "quality-project",
        status = Base.TranslationStatus.TRANSLATED,
    )
    project.set_translation_snapshot(context)
    items = [
        CacheItem(
            src = f"source-{index}",
            dst = f"译文-{index}",
            status = Base.TranslationStatus.TRANSLATED,
        )
        for index in range(item_count)
    ]
    manager = CacheManager(service = False)
    manager.cache_use_sqlite = False
    manager.save_to_file(project, items, str(tmp_path))

    runtime_config = Config(
        source_language = BaseLanguage.Enum.EN,
        target_language = BaseLanguage.Enum.ZH,
        output_folder = str(tmp_path),
        cache_use_sqlite = False,
        activate_platform = 7,
        platforms = [{
            "id": 7,
            "api_url": "https://current.invalid/v2",
            "model": "current-model",
            "api_key": ["current-secret"],
        }],
    )
    return runtime_config, items


def test_coordinator_restores_snapshot_batches_and_saves_progress(tmp_path) -> None:
    config, items = _prepare_cache(tmp_path)
    engine = Engine()
    created_tasks: list[RecordingTask] = []

    def factory(context: TranslationTaskContext) -> RecordingTask:
        task = RecordingTask(context)
        created_tasks.append(task)
        return task

    coordinator = QualityTaskCoordinator(engine = engine, polisher_factory = factory)
    coordinator.emit = lambda *args, **kwargs: None
    done = threading.Event()
    callback_threads: list[str] = []
    final_results = []

    def on_progress(progress) -> None:
        del progress
        callback_threads.append(threading.current_thread().name)

    def on_done(progress) -> None:
        final_results.append(progress)
        callback_threads.append(threading.current_thread().name)
        done.set()

    assert coordinator.start_polishing(
        config,
        items,
        items,
        batch_size = 2,
        on_progress = on_progress,
        on_done = on_done,
    )
    assert done.wait(5)

    result = final_results[0]
    assert result.state == QualityTaskState.COMPLETED
    assert result.total_count == 3
    assert result.completed_count == 3
    assert result.updated_count == 3
    assert result.batch_count == 2
    assert result.total_batch_count == 2
    assert result.input_tokens == 4
    assert result.output_tokens == 6
    assert engine.get_status() == Engine.Status.IDLE
    assert all(name == f"{Engine.TASK_PREFIX}QUALITY" for name in callback_threads)

    provider = created_tasks[0].context.runtime_provider.to_dict()
    assert provider["model"] == "snapshot-model"
    assert provider["api_url"] == "https://snapshot.invalid/v1"
    assert provider["api_key"] == ["current-secret"]

    reloaded = CacheManager(service = False)
    reloaded.cache_use_sqlite = False
    reloaded.load_from_file(str(tmp_path), strict = True)
    assert reloaded.get_project().get_status() == Base.TranslationStatus.TRANSLATED
    saved_progress = reloaded.get_project().get_extras()["polishing_progress"]
    assert saved_progress["state"] == QualityTaskState.COMPLETED.value
    assert saved_progress["snapshot_id"] == result.snapshot_id
    assert saved_progress["batch_count"] == 2
    assert all(
        item.get_status() == Base.TranslationStatus.POLISHED
        for item in reloaded.get_items()
    )

    project_json = (tmp_path / "cache" / "project.json").read_text(encoding = "utf-8")
    assert "current-secret" not in project_json
    assert "stale-secret" not in project_json
    json.loads(project_json)


def test_cancel_only_stops_later_batches_and_keeps_saved_batch(tmp_path) -> None:
    config, items = _prepare_cache(tmp_path)
    engine = Engine()
    done = threading.Event()
    final_results = []
    coordinator: QualityTaskCoordinator

    def factory(context: TranslationTaskContext) -> RecordingTask:
        return RecordingTask(
            context,
            cancel = coordinator.cancel,
            cancel_on_call = 2,
        )

    coordinator = QualityTaskCoordinator(engine = engine, polisher_factory = factory)
    coordinator.emit = lambda *args, **kwargs: None

    assert coordinator.start_polishing(
        config,
        items,
        items,
        batch_size = 1,
        on_done = lambda progress: (final_results.append(progress), done.set()),
    )
    assert done.wait(5)

    result = final_results[0]
    assert result.state == QualityTaskState.CANCELLED
    assert result.cancel_requested is True
    assert result.completed_count == 1
    assert result.updated_count == 1
    assert result.batch_count == 1
    assert items[0].get_status() == Base.TranslationStatus.POLISHED
    assert items[1].get_status() == Base.TranslationStatus.TRANSLATED
    assert items[2].get_status() == Base.TranslationStatus.TRANSLATED

    reloaded = CacheManager(service = False)
    reloaded.cache_use_sqlite = False
    reloaded.load_from_file(str(tmp_path), strict = True)
    saved_items = reloaded.get_items()
    saved_progress = reloaded.get_project().get_extras()["polishing_progress"]
    assert saved_items[0].get_status() == Base.TranslationStatus.POLISHED
    assert saved_items[1].get_status() == Base.TranslationStatus.TRANSLATED
    assert saved_progress["state"] == QualityTaskState.CANCELLED.value
    assert saved_progress["completed_count"] == 1
    assert reloaded.get_project().get_status() == Base.TranslationStatus.TRANSLATED


def test_cancel_interrupts_current_quality_request_and_rolls_back_batch(
    tmp_path,
    monkeypatch,
) -> None:
    config, items = _prepare_cache(tmp_path, item_count = 1)
    original = items[0].asdict()
    engine = Engine()
    done = threading.Event()
    final_results = []
    close_calls = []
    BlockingCancellableTask.started.clear()
    monkeypatch.setattr(
        TaskRequester,
        "close_all_clients_async",
        lambda **kwargs: close_calls.append(kwargs),
    )
    coordinator = QualityTaskCoordinator(
        engine = engine,
        polisher_factory = BlockingCancellableTask,
    )
    coordinator.emit = lambda *args, **kwargs: None

    assert coordinator.start_polishing(
        config,
        items,
        items,
        on_done = lambda progress: (final_results.append(progress), done.set()),
    )
    assert BlockingCancellableTask.started.wait(2)
    assert coordinator.cancel() is True
    assert done.wait(2)

    result = final_results[0]
    assert result.state == QualityTaskState.CANCELLED
    assert result.completed_count == 0
    assert result.updated_count == 0
    assert items[0].asdict() == original
    assert close_calls == [{}]
    assert engine.get_status() == Engine.Status.IDLE

    # 工作线程退出时必须解除绑定，下一轮任务不能继承本轮取消状态。
    observed_cancel_state = []

    class NextTask(RecordingTask):
        def run(self, next_items: list[CacheItem], **kwargs) -> QualityTaskResult:
            observed_cancel_state.append(TaskRequester.is_cancel_requested())
            return super().run(next_items, **kwargs)

    coordinator.polisher_factory = NextTask
    second_done = threading.Event()
    assert coordinator.start_polishing(
        config,
        items,
        items,
        on_done = lambda progress: second_done.set(),
    )
    assert second_done.wait(2)
    assert observed_cancel_state == [False]


def test_coordinator_refuses_to_start_when_engine_is_owned(tmp_path) -> None:
    config, items = _prepare_cache(tmp_path, item_count = 1)
    engine = Engine()
    assert engine.try_set_status(Engine.Status.IDLE, Engine.Status.TESTING)
    coordinator = QualityTaskCoordinator(engine = engine)

    assert coordinator.start_polishing(config, items, items) is False
    assert coordinator.is_busy() is False
    assert engine.get_status() == Engine.Status.TESTING
    assert engine.release_status(Engine.Status.TESTING)


def test_workbench_can_validate_its_atomic_engine_reservation() -> None:
    engine = Engine.get()
    engine.set_status(Engine.Status.IDLE)
    config = Config(
        activate_platform = 1,
        platforms = [{
            "id": 1,
            "api_format": Base.APIFormat.OPENAI,
            "model": "analysis-model",
        }],
    )
    service = WorkbenchAnalysisService()

    try:
        assert engine.try_set_status(Engine.Status.IDLE, Engine.Status.TESTING)
        assert service.ensure_analysis_ready(config, engine_reserved = True)["id"] == 1
        with pytest.raises(AnalysisServiceError):
            service.ensure_analysis_ready(config)
    finally:
        engine.set_status(Engine.Status.IDLE)


def test_translation_stop_does_not_take_over_quality_task() -> None:
    engine = Engine.get()
    engine.set_status(Engine.Status.QUALITY)

    try:
        Translator.translation_stop(object(), Base.Event.TRANSLATION_STOP, {})
        assert engine.get_status() == Engine.Status.QUALITY
    finally:
        engine.set_status(Engine.Status.IDLE)


def test_single_retranslation_blocks_quality_status_until_finished() -> None:
    engine = Engine()

    assert engine.try_begin_single_task() is True
    assert engine.try_set_status(Engine.Status.IDLE, Engine.Status.QUALITY) is False

    engine.end_single_task()
    assert engine.try_set_status(Engine.Status.IDLE, Engine.Status.QUALITY) is True


def test_failed_batch_restores_partial_quality_mutation(tmp_path) -> None:
    config, items = _prepare_cache(tmp_path, item_count = 2)
    original = [item.asdict() for item in items]
    engine = Engine()
    coordinator = QualityTaskCoordinator(engine = engine, polisher_factory = MutatingFailureTask)
    coordinator.emit = lambda *args, **kwargs: None
    done = threading.Event()
    results = []

    assert coordinator.start_polishing(
        config,
        items,
        items,
        on_done = lambda progress: (results.append(progress), done.set()),
    )
    assert done.wait(5)
    assert results[0].state == QualityTaskState.FAILED
    assert [item.asdict() for item in items] == original


@pytest.mark.parametrize(
    ("starter_name", "partition"),
    (
        ("start_polishing", "polishing_progress"),
        ("start_proofreading", "proofreading_progress"),
    ),
)
def test_missing_snapshot_fails_without_mutating_items_or_leaking_credentials(
    tmp_path,
    starter_name: str,
    partition: str,
) -> None:
    config, items = _prepare_cache(tmp_path, item_count = 1)
    items[0].set_metadata({"trace_id": "kept"})
    original = items[0].asdict()

    manager = CacheManager(service = False)
    manager.cache_use_sqlite = False
    manager.load_project_from_file(str(tmp_path), strict = True)
    project = manager.get_project()
    project.clear_translation_snapshot()
    manager.save_to_file(project, items, str(tmp_path))

    engine = Engine()
    coordinator = QualityTaskCoordinator(engine = engine)
    coordinator.emit = lambda *args, **kwargs: None
    done = threading.Event()
    final_results = []
    starter = getattr(coordinator, starter_name)

    assert starter(
        config,
        items,
        items,
        on_done = lambda progress: (final_results.append(progress), done.set()),
    )
    assert done.wait(5)

    result = final_results[0]
    assert result.state == QualityTaskState.FAILED
    assert result.error_message == (
        "无法进行质量校对：当前缓存缺少翻译快照，请重新执行一键翻译"
    )
    assert items[0].asdict() == original
    assert engine.get_status() == Engine.Status.IDLE

    reloaded = CacheManager(service = False)
    reloaded.cache_use_sqlite = False
    reloaded.load_from_file(str(tmp_path), strict = True)
    assert reloaded.get_items()[0].asdict() == original
    saved_progress = reloaded.get_project().get_extras()[partition]
    assert saved_progress["state"] == QualityTaskState.FAILED.value
    assert saved_progress["snapshot_id"] == ""
    serialized = json.dumps(reloaded.get_project().asdict(), ensure_ascii = False)
    assert "current-secret" not in serialized
    assert "stale-secret" not in serialized


@pytest.mark.parametrize(
    ("error", "expected"),
    (
        (
            CacheLoadError("SQLite cache has no project record"),
            "无法载入翻译缓存，请确认项目路径和输出目录一致后重试",
        ),
        (
            ValueError("快照中的翻译接口已不存在，请恢复原接口后再进行校对"),
            "无法进行质量校对：原翻译接口不可用，请恢复平台配置后重试",
        ),
        (
            RuntimeError("第三方响应中不应显示的密钥"),
            "质量任务执行失败，请稍后重试；详细原因已写入日志",
        ),
    ),
)
def test_public_quality_error_message_is_safe(error, expected) -> None:
    message = QualityTaskCoordinator._public_error_message(error)
    assert message == expected
    assert "密钥" not in message
