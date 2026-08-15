# -*- coding: utf-8 -*-
"""一键翻译第 4 步“翻译已完成”状态回归测试。"""

from types import SimpleNamespace

from base.Base import Base
import frontend.RenpyToolbox.OneKeyTranslatePage as page_module
from frontend.RenpyToolbox.OneKeyTranslatePage import YiJianFanyiPage
from module.Engine.Engine import Engine


def test_step4_refresh_shows_completed_state():
    status_texts = []
    start_texts = []
    skip_texts = []
    start_enabled = []
    page = SimpleNamespace(
        _onekey_translation_completed=True,
        _translation_output_completed=lambda: False,
        step4_status=SimpleNamespace(
            setText=status_texts.append,
            setStyleSheet=lambda value: None,
        ),
        start_trans_btn=SimpleNamespace(
            setText=start_texts.append,
            setEnabled=start_enabled.append,
        ),
        skip_trans_btn=SimpleNamespace(setText=skip_texts.append),
    )

    YiJianFanyiPage._refresh_step4_state(page)

    assert "翻译已完成" in status_texts[-1]
    assert start_texts[-1] == "重新翻译"
    assert skip_texts[-1] == "进入后续处理 →"
    assert start_enabled[-1] is True


def test_step4_refresh_falls_back_to_ready_check_when_not_completed():
    status_texts = []
    start_texts = []
    skip_texts = []
    ready_calls = []
    page = SimpleNamespace(
        _onekey_translation_completed=False,
        _translation_output_completed=lambda: False,
        step4_status=SimpleNamespace(
            setText=status_texts.append,
            setStyleSheet=lambda value: None,
        ),
        start_trans_btn=SimpleNamespace(
            setText=start_texts.append,
            setEnabled=lambda value: None,
        ),
        skip_trans_btn=SimpleNamespace(setText=skip_texts.append),
        _refresh_step4_ready=lambda: ready_calls.append(True) or True,
    )

    YiJianFanyiPage._refresh_step4_state(page)

    assert ready_calls == [True]
    assert start_texts[-1] == "🚀 开始翻译"
    assert skip_texts[-1] == "跳过翻译 →"


def test_agent_entry_prefills_project_and_starts_extraction(monkeypatch):
    class Edit:
        def __init__(self, value=""):
            self.value = value

        def setText(self, value):
            self.value = value

        def text(self):
            return self.value

        def blockSignals(self, blocked):
            return False

    extracted = []
    validated = []
    page = SimpleNamespace(
        extraction_worker=None,
        tl_folder_edit=Edit(),
        game_path_edit=Edit(),
        step1_next_btn=SimpleNamespace(isEnabled=lambda: True),
        _on_path_text_changed=validated.append,
        _go_step2=lambda: extracted.append(True),
    )
    monkeypatch.setattr(
        page_module.Engine,
        "get",
        lambda: SimpleNamespace(
            get_status=lambda: Engine.Status.IDLE,
            has_stop_barrier=lambda: False,
            has_single_tasks=lambda: False,
        ),
    )

    started = YiJianFanyiPage.start_current_project(
        page,
        "E:/Games/Test",
        "chinese",
    )

    assert started is True
    assert page.tl_folder_edit.text() == "chinese"
    assert page.game_path_edit.text() == "E:/Games/Test"
    assert validated == ["E:/Games/Test"]
    assert extracted == [True]
    assert page._start_translation_after_extraction is True
    assert page._agent_direct_start is True
    assert page._onekey_translation_completed is False


def test_agent_entry_rejects_busy_engine_without_mutating_fields(monkeypatch):
    writes = []
    page = SimpleNamespace(
        extraction_worker=None,
        tl_folder_edit=SimpleNamespace(setText=lambda value: writes.append(("language", value))),
        game_path_edit=SimpleNamespace(setText=lambda value: writes.append(("project", value))),
    )
    monkeypatch.setattr(
        page_module.Engine,
        "get",
        lambda: SimpleNamespace(
            get_status=lambda: Engine.Status.TRANSLATING,
            has_stop_barrier=lambda: False,
            has_single_tasks=lambda: False,
        ),
    )

    started = YiJianFanyiPage.start_current_project(
        page,
        "E:/Games/Test",
        "chinese",
    )

    assert started is False
    assert writes == []


def test_agent_entry_rejects_pending_start_request(monkeypatch):
    writes = []
    page = SimpleNamespace(
        extraction_worker=None,
        _preprocess_worker=None,
        _onekey_request_id="request-pending",
        tl_folder_edit=SimpleNamespace(setText=lambda value: writes.append(("language", value))),
        game_path_edit=SimpleNamespace(setText=lambda value: writes.append(("project", value))),
    )
    monkeypatch.setattr(
        page_module.Engine,
        "get",
        lambda: SimpleNamespace(
            get_status=lambda: Engine.Status.IDLE,
            has_stop_barrier=lambda: False,
            has_single_tasks=lambda: False,
        ),
    )

    started = YiJianFanyiPage.start_current_project(
        page,
        "E:/Games/Test",
        "chinese",
    )

    assert started is False
    assert writes == []


def test_agent_extraction_success_continues_to_translation_confirmation(
    monkeypatch,
):
    calls = []
    page = SimpleNamespace(
        _start_translation_after_extraction=True,
        _go_step4=lambda: calls.append("step4"),
        _on_start_translate_clicked=lambda: calls.append("confirm"),
    )
    monkeypatch.setattr(
        page_module.QTimer,
        "singleShot",
        lambda _delay, callback: callback(),
    )

    YiJianFanyiPage._continue_agent_start_after_extraction(page)

    assert calls == ["step4", "confirm"]
    assert page._start_translation_after_extraction is False


def test_agent_direct_start_emits_translation_start_after_navigation():
    requests = []
    navigated = []
    translation_page = SimpleNamespace(
        _request_translation_start=lambda status, window, request_id="": requests.append(
            (status, window, request_id)
        )
        or True
    )
    window = SimpleNamespace(
        translation_page=translation_page,
        navigate_to_page=navigated.append,
    )
    page = SimpleNamespace(
        window=window,
        _reset_auto_hook_state=lambda: None,
    )

    YiJianFanyiPage._open_legacy_translation_page(
        page,
        start_immediately=True,
    )

    assert navigated == [translation_page]
    assert len(requests) == 1
    assert requests[0][:2] == (Base.TranslationStatus.UNTRANSLATED, window)
    assert requests[0][2]
    assert page._onekey_request_id == requests[0][2]
    assert page._onekey_run_id is None


def test_agent_translation_start_result_only_accepts_matching_request():
    page = SimpleNamespace(
        _onekey_request_id="request-current",
        _onekey_run_id=None,
        _onekey_translation_started=False,
    )

    YiJianFanyiPage._on_translation_start_result(
        page,
        Base.Event.TRANSLATION_START_RESULT,
        {"accepted": True, "request_id": "request-old", "run_id": 3},
    )
    assert page._onekey_request_id == "request-current"
    assert page._onekey_translation_started is False

    YiJianFanyiPage._on_translation_start_result(
        page,
        Base.Event.TRANSLATION_START_RESULT,
        {"accepted": True, "request_id": "request-current", "run_id": 4},
    )
    assert page._onekey_request_id == ""
    assert page._onekey_run_id == 4
    assert page._onekey_translation_started is True


def test_agent_translation_done_can_arrive_before_start_result():
    refreshed = []
    page = SimpleNamespace(
        _auto_hook_running=False,
        _auto_hook_pending=False,
        _onekey_request_id="request-current",
        _onekey_run_id=None,
        _onekey_translation_started=False,
        _onekey_translation_completed=False,
        _hook_restore_paths=None,
        _last_onekey_output_dir=None,
        _refresh_step4_state=lambda: refreshed.append(True),
    )
    page._reset_auto_hook_state = lambda: YiJianFanyiPage._reset_auto_hook_state(page)

    YiJianFanyiPage._on_translation_done(
        page,
        Base.Event.TRANSLATION_DONE,
        {
            "success": True,
            "request_id": "request-old",
            "run_id": 7,
        },
    )
    assert page._onekey_request_id == "request-current"
    assert refreshed == []

    YiJianFanyiPage._on_translation_done(
        page,
        Base.Event.TRANSLATION_DONE,
        {
            "success": True,
            "request_id": "request-current",
            "run_id": 8,
        },
    )
    assert page._onekey_translation_completed is True
    assert page._onekey_translation_started is False
    assert refreshed == [True]


def test_auto_hook_ignores_unrelated_translation_done():
    restored = []
    reset = []
    page = SimpleNamespace(
        _auto_hook_running=True,
        _onekey_request_id="hook-current",
        _onekey_run_id=None,
        _restore_paths_after_auto_hook=lambda: restored.append(True),
        _reset_auto_hook_state=lambda: reset.append(True),
    )

    YiJianFanyiPage._on_translation_done(
        page,
        Base.Event.TRANSLATION_DONE,
        {
            "success": True,
            "request_id": "other-request",
            "run_id": 10,
        },
    )

    assert restored == []
    assert reset == []
    assert page._onekey_request_id == "hook-current"


def test_auto_hook_matching_done_restores_paths_and_resets(monkeypatch):
    calls = []
    page = SimpleNamespace(
        _auto_hook_running=True,
        _onekey_request_id="hook-current",
        _onekey_run_id=None,
        _restore_paths_after_auto_hook=lambda: calls.append("restore"),
        _reset_auto_hook_state=lambda: calls.append("reset"),
    )
    monkeypatch.setattr(
        page_module,
        "InfoBar",
        SimpleNamespace(success=lambda *args, **kwargs: calls.append("success")),
    )

    YiJianFanyiPage._on_translation_done(
        page,
        Base.Event.TRANSLATION_DONE,
        {
            "success": True,
            "request_id": "hook-current",
            "run_id": 11,
        },
    )

    assert calls == ["restore", "reset", "success"]


def test_auto_hook_start_emits_correlated_request(monkeypatch, tmp_path):
    root = tmp_path / "Project"
    tl_dir = root / "game" / "tl" / "chinese"
    tl_dir.mkdir(parents=True)
    paths = page_module.RenpyProjectPaths.from_path(root, "chinese")
    assert paths is not None
    events = []
    config = SimpleNamespace(
        source_language="english",
        target_language="chinese",
        save=lambda: None,
    )
    page = SimpleNamespace(
        game_dir=str(root),
        _last_onekey_output_dir=paths.translation_output_dir,
        _hook_restore_paths=None,
        _auto_hook_running=False,
        _onekey_request_id="",
        _onekey_run_id=None,
        _sync_game_dir_to_config=lambda _root: None,
        emit=lambda event, payload: events.append((event, payload)),
        _reset_auto_hook_state=lambda: None,
        _restore_paths_after_auto_hook=lambda: None,
        logger=SimpleNamespace(error=lambda *args: None),
    )
    monkeypatch.setattr(page_module.Config, "load", lambda self: config)
    monkeypatch.setattr(
        page_module.RenpyProjectPaths,
        "from_config",
        lambda _config: paths,
    )
    monkeypatch.setattr(page_module, "_remember_translation_run", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        page_module,
        "InfoBar",
        SimpleNamespace(warning=lambda *args, **kwargs: None),
    )

    YiJianFanyiPage._start_auto_hook_supplement(page, paths)

    assert page._auto_hook_running is True
    assert page._onekey_request_id
    assert events[0][0] == Base.Event.TRANSLATION_START
    assert events[0][1]["request_id"] == page._onekey_request_id


def test_auto_hook_rejection_restores_paths_before_reset(monkeypatch):
    calls = []
    page = SimpleNamespace(
        _onekey_request_id="hook-current",
        _onekey_translation_completed=False,
        _auto_hook_running=True,
        _restore_paths_after_auto_hook=lambda: calls.append("restore"),
        _reset_auto_hook_state=lambda: calls.append("reset"),
    )
    monkeypatch.setattr(
        page_module,
        "InfoBar",
        SimpleNamespace(warning=lambda *args, **kwargs: calls.append("warning")),
    )

    YiJianFanyiPage._on_translation_start_result(
        page,
        Base.Event.TRANSLATION_START_RESULT,
        {
            "accepted": False,
            "request_id": "hook-current",
            "reason": "ENGINE_BUSY",
        },
    )

    assert calls == ["restore", "reset", "warning"]


def test_apply_completion_schedules_hook_with_project_snapshot(monkeypatch):
    scheduled = []
    received_paths = []
    project_paths = object()
    page = SimpleNamespace(
        _apply_card=None,
        _apply_parent=None,
        _apply_project_paths=project_paths,
        _apply_progress_dialog=None,
        _apply_running=True,
        _apply_worker=object(),
        _onekey_translation_started=True,
        _auto_hook_pending=True,
        _last_onekey_output_dir=None,
        _incremental_dir=None,
        _incremental_output_dir=None,
        _apply_target_dir=None,
        _start_auto_hook_supplement=received_paths.append,
    )
    monkeypatch.setattr(
        page_module,
        "InfoBar",
        SimpleNamespace(success=lambda *args, **kwargs: None),
    )
    monkeypatch.setattr(
        page_module.QTimer,
        "singleShot",
        lambda _delay, callback: scheduled.append(callback),
    )

    YiJianFanyiPage._on_apply_finished(page, True, "应用完成", {})
    scheduled[0]()

    assert received_paths == [project_paths]
    assert page._auto_hook_pending is False


def test_stale_extraction_restores_retry_ui(monkeypatch):
    ring_visibility = []
    status_texts = []
    description_texts = []
    retry_visibility = []
    retry_enabled = []
    page = SimpleNamespace(
        _extraction_generation=1,
        game_dir="E:/Games/A",
        tl_folder_edit=SimpleNamespace(text=lambda: "chinese"),
        _start_translation_after_extraction=True,
        _agent_direct_start=True,
        extraction_worker=object(),
        step2_page=SimpleNamespace(
            progress_ring=SimpleNamespace(setVisible=ring_visibility.append),
        ),
        step2_status=SimpleNamespace(setText=status_texts.append),
        step2_desc=SimpleNamespace(setText=description_texts.append),
        step2_retry_btn=SimpleNamespace(
            setVisible=retry_visibility.append,
            setEnabled=retry_enabled.append,
        ),
    )
    monkeypatch.setattr(
        page_module.Config,
        "load",
        lambda self: SimpleNamespace(),
    )
    monkeypatch.setattr(
        page_module.RenpyProjectPaths,
        "from_config",
        lambda _config: None,
    )
    monkeypatch.setattr(
        page_module.RenpyProjectPaths,
        "from_path",
        lambda _path, _language: None,
    )

    YiJianFanyiPage._on_extract_finished(
        page,
        True,
        "旧任务完成",
        generation=1,
        context={"project_key": "project-a"},
    )

    assert page._start_translation_after_extraction is False
    assert page._agent_direct_start is False
    assert page.extraction_worker is None
    assert ring_visibility == [False]
    assert "项目已切换" in status_texts[-1]
    assert description_texts[-1] == status_texts[-1]
    assert retry_visibility == [True]
    assert retry_enabled == [True]


def test_stale_extraction_generation_is_ignored():
    page = SimpleNamespace(_extraction_generation=2)

    YiJianFanyiPage._on_extract_finished(
        page,
        True,
        "旧任务完成",
        generation=1,
    )
