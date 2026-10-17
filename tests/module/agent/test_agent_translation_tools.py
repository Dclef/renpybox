from pathlib import Path

from module.Agent.ToolDispatcher import ToolDispatcher
from module.Agent.tools import pipeline_tools
from module.Agent.tools.pipeline_tools import (
    apply_translation,
    start_translation,
    stop_translation,
    translation_apply_confirmation_context,
)
from module.Config import Config
from module.Localizer.Localizer import Localizer


def _config_for(root: Path) -> Config:
    config = Config()
    config.platforms = []
    config.renpy_project_path = str(root)
    config.renpy_game_folder = str(root / "game")
    config.renpy_tl_folder = str(root / "game" / "tl" / "chinese")
    config.input_folder = str(root / "game" / "tl" / "chinese")
    config.output_folder = str(root / "RenpyBox_Translation" / "chinese")
    config.target_language = "ZH"
    config.save = lambda: config
    return config


def _make_project(tmp_path: Path, *, with_output: bool = True) -> tuple[Path, Config, Path]:
    root = tmp_path / "MyGame"
    tl_dir = root / "game" / "tl" / "chinese"
    tl_dir.mkdir(parents=True)
    (tl_dir / "script.rpy").write_text(
        'translate chinese strings:\n    old "A"\n    new "甲"\n',
        encoding="utf-8",
    )
    out_dir = root / "RenpyBox_Translation" / "chinese"
    if with_output:
        out_dir.mkdir(parents=True)
        (out_dir / "script.rpy").write_text(
            'translate chinese strings:\n    old "A"\n    new "甲"\n',
            encoding="utf-8",
        )
    return root, _config_for(root), out_dir


def test_start_translation_requires_app_context() -> None:
    result = start_translation()

    assert result.success is False
    assert result.code == "AGENT_APP_CONTEXT_MISSING"
    assert result.message == Localizer.get().agent_app_context_missing


def test_start_translation_accepts_and_forwards_arguments() -> None:
    calls: list[dict] = []

    def callback(payload: dict) -> dict:
        calls.append(payload)
        return {
            "accepted": True,
            "request_id": "req-1",
            "reason": "STARTED",
            "stage": "translating",
        }

    result = start_translation(
        pipeline_callbacks={"start_translation": callback},
        status="untranslated",
        preflight_confirmed=True,
    )

    assert result.success is True
    assert result.message == Localizer.get().agent_start_translation_accepted
    assert result.data == {
        "request_id": "req-1",
        "reason": "STARTED",
        "stage": "translating",
    }
    assert calls == [{
        "status": "untranslated",
        "preflight_confirmed": True,
        "platform_source": "configured",
    }]


def test_start_translation_reports_rejection_reason() -> None:
    detail = "已有翻译启动正在处理，请稍候再试。"

    def callback(_payload: dict) -> dict:
        return {
            "accepted": False,
            "reason": "ENGINE_BUSY",
            "detail": detail,
            "status_code": 200,
        }

    result = start_translation(pipeline_callbacks={"start_translation": callback})

    assert result.success is False
    assert result.code == "ENGINE_BUSY"
    assert result.data["reason"] == "ENGINE_BUSY"
    assert result.data["detail"] == detail
    assert result.data["status_code"] == 200
    assert result.message == Localizer.get().agent_start_translation_rejected.format(
        reason = "ENGINE_BUSY",
        detail = detail,
    )


def test_stop_translation_reports_stopping_status() -> None:
    payloads: list[dict] = []

    def callback(payload: dict) -> dict:
        payloads.append(payload)
        return {"ok": True, "status": "STOPPING"}

    result = stop_translation(pipeline_callbacks={"stop_translation": callback})

    assert result.success is True
    assert result.message == Localizer.get().agent_translation_stopped
    assert result.data == {"status": "STOPPING"}
    assert payloads == [{}]


def test_stop_translation_requires_app_context() -> None:
    result = stop_translation()

    assert result.success is False
    assert result.code == "AGENT_APP_CONTEXT_MISSING"


def test_apply_translation_rejects_stale_confirmation(tmp_path: Path, monkeypatch) -> None:
    _, config, _ = _make_project(tmp_path)
    context = translation_apply_confirmation_context(config_loader = lambda: config)
    context["signature"] = "stale"
    calls: list[dict] = []

    def fake_apply(**kwargs):
        calls.append(kwargs)
        return True, "ok", {"count": 1}

    monkeypatch.setattr(pipeline_tools.flow, "apply_full_translation", fake_apply)

    result = apply_translation(
        config_loader = lambda: config,
        confirmed_context = context,
    )

    assert result.success is False
    assert result.code == "CONFIRMATION_STALE"
    assert calls == []


def test_apply_translation_requires_output_files(tmp_path: Path) -> None:
    _, config, out_dir = _make_project(tmp_path, with_output = False)
    context = translation_apply_confirmation_context(config_loader = lambda: config)

    result = apply_translation(
        config_loader = lambda: config,
        confirmed_context = context,
    )

    assert result.success is False
    assert result.code == "NO_OUTPUT_FILES"
    assert result.data["output_dir"] == str(out_dir)
    assert result.message == Localizer.get().agent_apply_no_output_files


def test_apply_translation_full_mode_calls_flow_and_reports_counts(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root, config, out_dir = _make_project(tmp_path)
    tl_dir = root / "game" / "tl" / "chinese"
    context = translation_apply_confirmation_context(config_loader = lambda: config)
    captured: dict = {}

    def fake_apply(**kwargs):
        captured.update(kwargs)
        return True, "已写回", {"count": 3}

    monkeypatch.setattr(pipeline_tools.flow, "apply_full_translation", fake_apply)

    result = apply_translation(
        config_loader = lambda: config,
        mode = "full",
        confirmed_context = context,
    )

    assert result.success is True
    assert result.data["mode"] == "full"
    assert result.data["applied_count"] == 3
    assert result.data["failed_count"] == 0
    assert result.data["output_dir"] == str(out_dir)
    assert result.data["target_dir"] == str(tl_dir)
    assert result.message == Localizer.get().agent_apply_translation_complete.format(
        count = 3,
        output_dir = tl_dir,
    )
    assert captured["config"] is config
    assert Path(captured["output_dir"]) == out_dir
    assert Path(captured["input_dir"]) == tl_dir
    assert [Path(path) for path in captured["output_files"]] == [out_dir / "script.rpy"]
    assert Path(captured["project_root"]).resolve() == root.resolve()
    assert captured["project_language"] == "chinese"


def test_apply_translation_failure_uses_apply_failed_code(tmp_path: Path, monkeypatch) -> None:
    _, config, _ = _make_project(tmp_path)
    context = translation_apply_confirmation_context(config_loader = lambda: config)

    def fake_apply(**_kwargs):
        return False, "写入失败", {"failed_count": 1}

    monkeypatch.setattr(pipeline_tools.flow, "apply_full_translation", fake_apply)

    result = apply_translation(
        config_loader = lambda: config,
        confirmed_context = context,
    )

    assert result.success is False
    assert result.code == "APPLY_FAILED"
    assert result.message == "写入失败"


def test_dispatcher_injects_pipeline_callbacks_only_when_available() -> None:
    calls: list[dict] = []

    def callback(payload: dict) -> dict:
        calls.append(payload)
        return {
            "accepted": True,
            "request_id": "req-9",
            "reason": "STARTED",
            "stage": "translating",
        }

    dispatcher = ToolDispatcher(pipeline_callbacks = {"start_translation": callback})
    result = dispatcher.execute("start_translation", {"status": "translated"}, confirmed = True)

    assert result.success is True
    assert calls == [{
        "status": "translated",
        "preflight_confirmed": False,
        "platform_source": "configured",
    }]
    assert result.data["request_id"] == "req-9"

    qt5 = ToolDispatcher()
    missing = qt5.execute("start_translation", {}, confirmed = True)
    assert missing.success is False
    assert missing.code == "AGENT_APP_CONTEXT_MISSING"
