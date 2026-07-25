from types import SimpleNamespace

import pytest

from base.Base import Base
from frontend.Proofreading.ProofreadingPage import ProofreadingPage
from module.Engine.Quality import QualityTaskCoordinator
from module.Engine.Quality import QualityTaskProgress
from module.Engine.Quality import QualityTaskState
from module.Engine.Quality import QualityTaskType
from module.Localizer.Localizer import Localizer


class _ItemStub:
    def __init__(self, status: Base.TranslationStatus) -> None:
        self.status = status

    def get_status(self) -> Base.TranslationStatus:
        return self.status


class _SignalStub:
    def __init__(self) -> None:
        self.values: list[object] = []

    def emit(self, value: object) -> None:
        self.values.append(value)


class _ButtonStub:
    def __init__(self) -> None:
        self.enabled: bool | None = None

    def setEnabled(self, enabled: bool) -> None:
        self.enabled = enabled


def _install_localizer(monkeypatch) -> SimpleNamespace:
    strings = SimpleNamespace(
        proofreading_page_ai_polish = "润色",
        proofreading_page_ai_proofread = "校对",
        proofreading_page_quality_cancelled = "质量任务已取消",
        proofreading_page_quality_cancelling = "正在取消质量任务",
        proofreading_page_quality_confirm_polish = "确认润色 {COUNT} 项",
        proofreading_page_quality_confirm_proofread = "确认校对 {COUNT} 项",
        proofreading_page_quality_done = (
            "{TASK}完成：更新 {UPDATED}，失败 {FAILED}，跳过 {SKIPPED}"
        ),
        proofreading_page_quality_no_polishable = "没有可润色项",
        proofreading_page_quality_no_proofreadable = "没有可校对项",
        proofreading_page_quality_progress = (
            "{TASK}进度 {PROCESSED}/{TOTAL}，更新 {UPDATED}，失败 {FAILED}"
        ),
        proofreading_page_quality_start_failed = "质量任务启动失败",
    )
    monkeypatch.setattr(Localizer, "get", classmethod(lambda cls: strings))
    return strings


class _SelectionPageStub:
    def __init__(self, selected_items: list[_ItemStub]) -> None:
        self.table_widget = SimpleNamespace(
            get_selected_items = lambda: selected_items,
        )
        self.confirmations: list[tuple[str, int]] = []
        self.starts: list[tuple[QualityTaskType, list[_ItemStub]]] = []
        self.warnings: list[str] = []

    def _confirm_quality_task(self, template: str, count: int) -> bool:
        self.confirmations.append((template, count))
        return True

    def _start_quality_task(
        self,
        task_type: QualityTaskType,
        selected_items: list[_ItemStub],
    ) -> None:
        self.starts.append((task_type, selected_items))

    def _show_quality_warning(self, message: str) -> None:
        self.warnings.append(message)


@pytest.mark.parametrize(
    ("handler", "task_type", "confirm_template", "expected_statuses"),
    (
        (
            ProofreadingPage._on_ai_polish_clicked,
            QualityTaskType.POLISHER,
            "确认润色 {COUNT} 项",
            [Base.TranslationStatus.TRANSLATED],
        ),
        (
            ProofreadingPage._on_ai_proofread_clicked,
            QualityTaskType.PROOFREADER,
            "确认校对 {COUNT} 项",
            [
                Base.TranslationStatus.TRANSLATED,
                Base.TranslationStatus.POLISHED,
            ],
        ),
    ),
)
def test_quality_actions_only_start_with_eligible_selected_items(
    monkeypatch,
    handler,
    task_type: QualityTaskType,
    confirm_template: str,
    expected_statuses: list[Base.TranslationStatus],
) -> None:
    _install_localizer(monkeypatch)
    selected_items = [
        _ItemStub(Base.TranslationStatus.UNTRANSLATED),
        _ItemStub(Base.TranslationStatus.TRANSLATED),
        _ItemStub(Base.TranslationStatus.POLISHED),
        _ItemStub(Base.TranslationStatus.TRANSLATED_IN_PAST),
        _ItemStub(Base.TranslationStatus.EXCLUDED),
    ]
    page = _SelectionPageStub(selected_items)

    handler(page)

    expected_items = [
        item for item in selected_items if item.get_status() in expected_statuses
    ]
    assert page.confirmations == [(confirm_template, len(expected_items))]
    assert page.starts == [(task_type, expected_items)]
    assert page.warnings == []


def test_quality_action_warns_without_eligible_selected_items(monkeypatch) -> None:
    strings = _install_localizer(monkeypatch)
    page = _SelectionPageStub([
        _ItemStub(Base.TranslationStatus.UNTRANSLATED),
        _ItemStub(Base.TranslationStatus.EXCLUDED),
    ])

    ProofreadingPage._on_ai_proofread_clicked(page)

    assert page.warnings == [strings.proofreading_page_quality_no_proofreadable]
    assert page.confirmations == []
    assert page.starts == []


class _CoordinatorStub:
    def __init__(self, progress: QualityTaskProgress) -> None:
        self.progress = progress
        self.calls: list[dict] = []

    def start_polishing(
        self,
        config,
        items,
        selected_items,
        *,
        on_progress,
        on_done,
    ) -> bool:
        self.calls.append({
            "task_type": QualityTaskType.POLISHER,
            "config": config,
            "items": items,
            "selected_items": selected_items,
            "on_progress": on_progress,
            "on_done": on_done,
        })
        return True

    def start_proofreading(
        self,
        config,
        items,
        selected_items,
        *,
        warning_map,
        on_progress,
        on_done,
    ) -> bool:
        self.calls.append({
            "task_type": QualityTaskType.PROOFREADER,
            "config": config,
            "items": items,
            "selected_items": selected_items,
            "warning_map": warning_map,
            "on_progress": on_progress,
            "on_done": on_done,
        })
        return True

    def get_progress(self) -> QualityTaskProgress:
        return self.progress


class _StartPageStub:
    def __init__(self) -> None:
        self.is_readonly = False
        self.config = object()
        self.items = [object(), object(), object()]
        self.warning_map = {id(self.items[0]): ["warning"]}
        self._quality_target_ids: set[int] = set()
        self.quality_progress_updated = _SignalStub()
        self.quality_done = _SignalStub()
        self.progress_messages: list[str] = []
        self.status_check_count = 0
        self.events: list[tuple[object, dict]] = []
        self.errors: list[tuple[str, Exception]] = []

    def _format_quality_progress(self, progress: QualityTaskProgress) -> str:
        return f"进度：{progress.completed_count}/{progress.total_count}"

    def indeterminate_show(self, message: str) -> None:
        self.progress_messages.append(message)

    def _check_engine_status(self) -> None:
        self.status_check_count += 1

    def emit(self, event, payload: dict) -> None:
        self.events.append((event, payload))

    def error(self, message: str, error: Exception) -> None:
        self.errors.append((message, error))


@pytest.mark.parametrize(
    "task_type",
    (QualityTaskType.POLISHER, QualityTaskType.PROOFREADER),
)
def test_start_quality_task_passes_context_and_routes_callbacks(
    monkeypatch,
    task_type: QualityTaskType,
) -> None:
    initial_progress = QualityTaskProgress(
        task_type = task_type,
        total_count = 2,
    )
    coordinator = _CoordinatorStub(initial_progress)
    monkeypatch.setattr(
        QualityTaskCoordinator,
        "get",
        classmethod(lambda cls: coordinator),
    )
    page = _StartPageStub()
    selected_items = [page.items[0], page.items[2]]

    ProofreadingPage._start_quality_task(page, task_type, selected_items)

    assert len(coordinator.calls) == 1
    call = coordinator.calls[0]
    assert call["task_type"] == task_type
    assert call["config"] is page.config
    assert call["items"] is page.items
    assert call["selected_items"] is selected_items
    if task_type == QualityTaskType.PROOFREADER:
        assert call["warning_map"] is page.warning_map
    else:
        assert "warning_map" not in call
    assert page._quality_target_ids == {id(item) for item in selected_items}
    assert page.progress_messages == ["进度：0/2"]
    assert page.status_check_count == 1
    assert page.events == []

    running_progress = QualityTaskProgress(
        task_type = task_type,
        total_count = 2,
        completed_count = 1,
    )
    done_progress = QualityTaskProgress(
        task_type = task_type,
        state = QualityTaskState.COMPLETED,
        total_count = 2,
        completed_count = 2,
    )
    call["on_progress"](running_progress)
    call["on_done"](done_progress)

    assert page.quality_progress_updated.values == [running_progress]
    assert page.quality_done.values == [done_progress]


class _DonePageStub:
    def __init__(self) -> None:
        self.target_item = object()
        self.other_item = object()
        self.items = [self.target_item, self.other_item]
        self._quality_target_ids = {id(self.target_item)}
        self._translation_progress = {"total": 2}
        self.quality_report = None
        self.rechecked_items: list[object] = []
        self.filter_count = 0
        self.status_check_count = 0
        self.hide_count = 0
        self.events: list[tuple[object, dict]] = []

    def _recheck_item(self, item: object) -> None:
        self.rechecked_items.append(item)

    def _apply_filter(self) -> None:
        self.filter_count += 1

    def _check_engine_status(self) -> None:
        self.status_check_count += 1

    def indeterminate_hide(self) -> None:
        self.hide_count += 1

    def emit(self, event, payload: dict) -> None:
        self.events.append((event, payload))

    @staticmethod
    def _quality_task_label(task_type: QualityTaskType) -> str:
        return ProofreadingPage._quality_task_label(task_type)


@pytest.mark.parametrize(
    ("progress", "expected_type", "expected_message"),
    (
        (
            QualityTaskProgress(
                task_type = QualityTaskType.POLISHER,
                state = QualityTaskState.COMPLETED,
                total_count = 4,
                completed_count = 4,
                updated_count = 3,
                failed_count = 0,
                skipped_count = 1,
            ),
            Base.ToastType.SUCCESS,
            "润色完成：更新 3，失败 0，跳过 1",
        ),
        (
            QualityTaskProgress(
                task_type = QualityTaskType.PROOFREADER,
                state = QualityTaskState.CANCELLED,
            ),
            Base.ToastType.WARNING,
            "质量任务已取消",
        ),
        (
            QualityTaskProgress(
                task_type = QualityTaskType.PROOFREADER,
                state = QualityTaskState.FAILED,
                error_message = "上游服务失败",
            ),
            Base.ToastType.ERROR,
            "上游服务失败",
        ),
    ),
)
def test_quality_done_updates_page_and_shows_state_specific_toast(
    monkeypatch,
    progress: QualityTaskProgress,
    expected_type: Base.ToastType,
    expected_message: str,
) -> None:
    _install_localizer(monkeypatch)
    report = object()
    report_calls: list[tuple[list[object], dict]] = []

    def build_report(items, translation_progress):
        report_calls.append((items, translation_progress))
        return report

    monkeypatch.setattr(
        "frontend.Proofreading.ProofreadingPage.build_translation_quality_report",
        build_report,
    )
    page = _DonePageStub()

    ProofreadingPage._on_quality_done_ui(page, progress)

    assert page.rechecked_items == [page.target_item]
    assert page._quality_target_ids == set()
    assert report_calls == [(page.items, page._translation_progress)]
    assert page.quality_report is report
    assert page.filter_count == 1
    assert page.status_check_count == 1
    assert page.hide_count == 1
    assert page.events == [(
        Base.Event.APP_TOAST_SHOW,
        {"type": expected_type, "message": expected_message},
    )]


def test_quality_progress_text_includes_task_and_counts(monkeypatch) -> None:
    strings = _install_localizer(monkeypatch)
    page = SimpleNamespace(
        _quality_task_label = ProofreadingPage._quality_task_label,
    )
    progress = QualityTaskProgress(
        task_type = QualityTaskType.PROOFREADER,
        total_count = 8,
        completed_count = 5,
        updated_count = 3,
        failed_count = 1,
    )

    assert ProofreadingPage._format_quality_progress(page, progress) == (
        "校对进度 5/8，更新 3，失败 1"
    )
    assert ProofreadingPage._format_quality_progress(page, None) == (
        strings.proofreading_page_quality_start_failed
    )


def test_cancel_quality_task_disables_button_and_updates_progress(monkeypatch) -> None:
    strings = _install_localizer(monkeypatch)
    coordinator = SimpleNamespace(cancel = lambda: True)
    monkeypatch.setattr(
        QualityTaskCoordinator,
        "get",
        classmethod(lambda cls: coordinator),
    )
    page = SimpleNamespace(
        btn_quality_cancel = _ButtonStub(),
        progress_messages = [],
    )
    page.indeterminate_show = page.progress_messages.append

    ProofreadingPage._on_quality_cancel_clicked(page)

    assert page.btn_quality_cancel.enabled is False
    assert page.progress_messages == [
        strings.proofreading_page_quality_cancelling,
    ]
