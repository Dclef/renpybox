"""一条龙编排：成功、取消、未译完、拒绝、引擎忙、确认过期。"""

from pathlib import Path

from base.Base import Base
from module.Agent.AgentService import AgentService
from module.Agent.ToolDispatcher import ToolDispatcher
from module.Agent.tools.pipeline_tools import pipeline_identity, run_onekey_pipeline
from module.Agent.tools.stage_tools import set_stage
from module.Agent.types import AgentRequestResult, AgentToolCall, ToolDef, ToolResult
from module.Config import Config
from module.Engine.Engine import Engine
from module.Engine.TaskRequester import TaskRequester
from module.OneKey.pipeline import run_pipeline
from api.agent import AgentSession


class _Engine:
    def __init__(self, status=Engine.Status.IDLE, barrier: bool = False) -> None:
        self.status = status
        self.barrier = barrier

    def get_status(self):
        return self.status

    def has_stop_barrier(self) -> bool:
        return self.barrier

    def has_translation_reservation(self) -> bool:
        return False


def _config(root: Path) -> Config:
    config = Config()
    config.platforms = []
    game = root / "game"
    tl = game / "tl" / "chinese"
    tl.mkdir(parents=True)
    (game / "script.rpy").write_text("label start:\n    return\n", encoding="utf-8")
    output = root / "out"
    output.mkdir()
    config.renpy_project_path = str(root)
    config.renpy_game_folder = str(root)
    config.renpy_tl_folder = str(tl)
    config.input_folder = str(tl)
    config.output_folder = str(output)
    config.target_language = "ZH"
    config.save = lambda: config
    return config


def _install_engine(monkeypatch, engine: _Engine) -> None:
    # 只替换流水线自己的 sleep 注入点；直接打补丁 time.sleep 会连累同进程的
    # 事件总线 drain 线程。
    monkeypatch.setattr(Engine, "get", lambda: engine)
    monkeypatch.setattr("module.OneKey.pipeline._sleep", lambda _seconds: None)


def test_pipeline_runs_extract_translate_apply_fallback_in_order(tmp_path, monkeypatch) -> None:
    config = _config(tmp_path / "Game")
    engine = _Engine()
    _install_engine(monkeypatch, engine)
    order: list[str] = []
    reads = {"n": 0}

    def translation_state():
        reads["n"] += 1
        if reads["n"] == 1:
            return {"untranslated_count": 2, "progress": {"line": 0, "total_line": 2}}
        engine.status = Engine.Status.IDLE
        return {
            "untranslated_count": 0,
            "cache_ready": True,
            "progress": {"line": 2, "total_line": 2, "percent": 100},
        }

    def apply(mode):
        order.append(f"apply:{mode}")
        return ToolResult(True, "applied", {"applied_count": 4})

    callbacks = type("Callbacks", (), {})()
    callbacks.unpack = lambda cancel: order.append("unpack")
    callbacks.decompile = lambda cancel: order.append("decompile")
    callbacks.extract = lambda incremental, cancel, progress: (
        order.append(f"extract:{incremental}") or ToolResult(True, "extracted")
    )
    def start(params):
        order.append(params)
        engine.status = Engine.Status.TRANSLATING
        return {"accepted": True}

    callbacks.start_translation = start
    callbacks.stop_translation = lambda: order.append("stop") or {"ok": True}
    callbacks.translation_state = translation_state
    callbacks.apply = apply
    callbacks.fallback = lambda: order.append("fallback") or ToolResult(True, "fallback", {"pair_count": 3})
    progress_log: list[tuple] = []

    outcome = run_pipeline(
        config,
        callbacks=callbacks,
        progress=lambda stage, percent, detail: progress_log.append((stage, percent, detail)),
        auto_apply=True,
        auto_fallback=True,
        use_agent_model=True,
    )

    assert outcome.success is True
    assert outcome.code == "OK"
    assert [item for item in order if not isinstance(item, dict)] == [
        "extract:False",
        "apply:full",
        "fallback",
    ]
    assert order[1]["platform_source"] == "agent"
    assert order[1]["status"] == "untranslated"
    assert outcome.data["applied_files"] == 4
    assert outcome.data["fallback_count"] == 3
    assert outcome.data["translated_count"] == 2
    assert any(item[0] == "translate" for item in progress_log)
    assert progress_log[-1][0] == "done"


def test_pipeline_cancel_stops_translation_and_skips_apply(tmp_path, monkeypatch) -> None:
    config = _config(tmp_path / "Game")
    engine = _Engine()
    _install_engine(monkeypatch, engine)
    stopped: list[bool] = []

    def start(_params):
        engine.status = Engine.Status.TRANSLATING
        return {"accepted": True}

    def stop():
        stopped.append(True)
        engine.status = Engine.Status.IDLE
        return {"ok": True}

    callbacks = type("Callbacks", (), {})()
    callbacks.unpack = lambda cancel: ToolResult(True, "unpack")
    callbacks.decompile = lambda cancel: ToolResult(True, "decompile")
    callbacks.extract = lambda incremental, cancel, progress: ToolResult(True, "extract")
    callbacks.start_translation = start
    callbacks.stop_translation = stop
    callbacks.translation_state = lambda: {"untranslated_count": 5, "progress": {"line": 1, "total_line": 5}}
    callbacks.apply = lambda mode: (_ for _ in ()).throw(AssertionError("取消后不能回填"))
    callbacks.fallback = lambda: (_ for _ in ()).throw(AssertionError("取消后不能兜底"))

    outcome = run_pipeline(
        config,
        callbacks=callbacks,
        cancel_check=lambda: engine.status == Engine.Status.TRANSLATING,
    )

    assert outcome.code == "CANCELLED"
    assert outcome.success is False
    assert stopped == [True]


def test_pipeline_incomplete_translation_does_not_apply(tmp_path, monkeypatch) -> None:
    config = _config(tmp_path / "Game")
    engine = _Engine()
    _install_engine(monkeypatch, engine)
    reads = {"n": 0}

    def translation_state():
        reads["n"] += 1
        if reads["n"] > 1:
            engine.status = Engine.Status.IDLE
        return {
            "untranslated_count": 7,
            "cache_ready": True,
            "progress": {"line": 1, "total_line": 8, "percent": 12},
        }

    callbacks = type("Callbacks", (), {})()
    callbacks.unpack = lambda cancel: ToolResult(True, "unpack")
    callbacks.decompile = lambda cancel: ToolResult(True, "decompile")
    callbacks.extract = lambda incremental, cancel, progress: ToolResult(True, "extract")
    callbacks.start_translation = lambda params: (
        setattr(engine, "status", Engine.Status.TRANSLATING) or {"accepted": True}
    )
    callbacks.stop_translation = lambda: {"ok": True}
    callbacks.translation_state = translation_state
    callbacks.apply = lambda mode: (_ for _ in ()).throw(AssertionError("未译完不能回填"))
    callbacks.fallback = lambda: ToolResult(True, "fallback")

    outcome = run_pipeline(config, callbacks=callbacks)

    assert outcome.code == "TRANSLATION_INCOMPLETE"
    assert outcome.data["untranslated_count"] == 7
    assert outcome.data["progress"]["percent"] == 12


def test_pipeline_rejected_translation(tmp_path, monkeypatch) -> None:
    config = _config(tmp_path / "Game")
    _install_engine(monkeypatch, _Engine())
    callbacks = type("Callbacks", (), {})()
    callbacks.unpack = lambda cancel: ToolResult(True, "unpack")
    callbacks.decompile = lambda cancel: ToolResult(True, "decompile")
    callbacks.extract = lambda incremental, cancel, progress: ToolResult(True, "extract")
    callbacks.start_translation = lambda params: {
        "accepted": False,
        "reason": "NO_QUOTA",
        "detail": "额度不足",
    }
    callbacks.stop_translation = lambda: {"ok": True}
    callbacks.translation_state = lambda: {"untranslated_count": 1, "progress": {}}
    callbacks.apply = lambda mode: (_ for _ in ()).throw(AssertionError("拒绝后不能回填"))
    callbacks.fallback = lambda: ToolResult(True, "fallback")

    outcome = run_pipeline(config, callbacks=callbacks)

    assert outcome.code == "TRANSLATION_REJECTED"
    assert outcome.data["reason"] == "NO_QUOTA"
    assert outcome.data["detail"] == "额度不足"


def test_pipeline_refuses_busy_engine(tmp_path, monkeypatch) -> None:
    config = _config(tmp_path / "Game")
    _install_engine(monkeypatch, _Engine(status=Engine.Status.TRANSLATING))
    callbacks = type("Callbacks", (), {})()
    callbacks.unpack = lambda cancel: (_ for _ in ()).throw(AssertionError("不应解包"))
    callbacks.decompile = lambda cancel: ToolResult(True, "decompile")
    callbacks.extract = lambda incremental, cancel, progress: ToolResult(True, "extract")
    callbacks.start_translation = lambda params: {"accepted": True}
    callbacks.stop_translation = lambda: {"ok": True}
    callbacks.translation_state = lambda: {"untranslated_count": 1, "progress": {}}
    callbacks.apply = lambda mode: ToolResult(True, "apply")
    callbacks.fallback = lambda: ToolResult(True, "fallback")

    outcome = run_pipeline(config, callbacks=callbacks)

    assert outcome.code == "ENGINE_BUSY"


def test_pipeline_project_changed_skips_apply(tmp_path, monkeypatch) -> None:
    config = _config(tmp_path / "Game")
    _install_engine(monkeypatch, _Engine())
    output = tmp_path / "Game" / "out"
    (output / "script.rpy").write_text("translate chinese strings:\n", encoding="utf-8")

    def translation_state():
        config.renpy_project_path = ""
        config.renpy_game_folder = ""
        config.renpy_tl_folder = ""
        config.input_folder = ""
        return {"untranslated_count": 0, "cache_ready": True, "progress": {}}

    callbacks = type("Callbacks", (), {})()
    callbacks.unpack = lambda cancel: ToolResult(True, "unpack")
    callbacks.decompile = lambda cancel: ToolResult(True, "decompile")
    callbacks.extract = lambda incremental, cancel, progress: ToolResult(True, "extract")
    callbacks.start_translation = lambda params: {"accepted": True}
    callbacks.stop_translation = lambda: {"ok": True}
    callbacks.translation_state = translation_state
    callbacks.apply = lambda mode: (_ for _ in ()).throw(AssertionError("项目变了不能回填"))
    callbacks.fallback = lambda: ToolResult(True, "fallback")

    outcome = run_pipeline(config, callbacks=callbacks, auto_apply=True)

    assert outcome.code == "PROJECT_CHANGED"


def test_run_onekey_pipeline_rejects_stale_confirmation(tmp_path) -> None:
    config = _config(tmp_path / "Game")
    result = run_onekey_pipeline(
        config_loader=lambda: config,
        confirmed_context={"project_root": "other", "game_dir": "other", "tl_dir": "other", "language": "other"},
    )

    assert result.success is False
    assert result.code == "CONFIRMATION_STALE"
    assert result.continues is False


def test_set_stage_accepts_known_stages_only() -> None:
    ok = set_stage(stage="translate")
    assert ok.success is True
    assert ok.data["stage"] == "translate"
    assert set_stage(stage="").data["stage"] == ""
    invalid = set_stage(stage="nope")
    assert invalid.success is False
    assert invalid.code == "INVALID_STAGE"


def test_dispatcher_registers_pipeline_and_stage_tools() -> None:
    dispatcher = ToolDispatcher()
    pipeline = dispatcher.tools["run_onekey_pipeline"]
    stage = dispatcher.tools["set_stage"]
    assert pipeline.requires_confirmation is True
    assert pipeline.requires_idle_engine is False
    assert stage.requires_confirmation is False
    assert stage.requires_idle_engine is False
    assert pipeline_identity(Config()) == {}


def test_session_records_tool_progress_without_changing_reply_text() -> None:
    service = AgentService(config_loader=lambda: Config(), max_iterations=1)
    session = AgentSession(service, lambda _payload: None)
    message = {
        "content": "保持原文",
        "tools": [{"name": "run_onekey_pipeline", "status": "running"}],
    }
    session._event(message, "tool_progress", {"stage": "translate", "percent": 40, "detail": "1/2"})
    session._event(message, "stage", {"stage": "apply"})

    assert message["content"] == "保持原文"
    assert message["tools"][-1]["progress"] == {"stage": "translate", "percent": 40, "detail": "1/2"}
    assert session.snapshot()["stage"] == "apply"
    assert service.snapshot()["stage"] == ""


def test_set_stage_tool_updates_service_stage(monkeypatch) -> None:
    events: list[tuple[str, dict]] = []

    class _Dispatcher:
        def __init__(self) -> None:
            self.tools = {
                "set_stage": ToolDef(
                    "set_stage",
                    "阶段",
                    {
                        "type": "object",
                        "properties": {"stage": {"type": "string"}},
                        "required": ["stage"],
                        "additionalProperties": False,
                    },
                    lambda **_kwargs: ToolResult(True, "ok"),
                )
            }

        def execute(self, name, arguments, **kwargs):
            progress = kwargs.get("progress_callback")
            if progress is not None:
                progress("translate", 15, "detail")
            return ToolResult(True, "ok", {"stage": arguments["stage"]})

    calls = {"n": 0}

    def request_tools(self, messages, tools, on_text_delta=None, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return AgentRequestResult(
                True,
                tool_calls=[AgentToolCall("call-1", "set_stage", {"stage": "extract"})],
            )
        return AgentRequestResult(True, text="完成")

    monkeypatch.setattr(TaskRequester, "request_tools", request_tools)
    config = Config(agent_platform=0)
    config.platforms = [{
        "id": 0,
        "api_format": Base.APIFormat.OPENAI,
        "api_key": ["test"],
        "api_url": "https://example.invalid",
        "model": "test-model",
    }]
    service = AgentService(
        config_loader=lambda: config,
        dispatcher=_Dispatcher(),
        max_iterations=4,
    )
    result = service.run("播报阶段", callback=lambda event, payload: events.append((event, payload)))

    assert result.success is True
    assert service.snapshot()["stage"] == "extract"
    assert ("tool_progress", {"stage": "translate", "percent": 15, "detail": "detail"}) in events
    assert ("stage", {"stage": "extract"}) in events
