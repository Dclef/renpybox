from pathlib import Path
from types import SimpleNamespace

import pytest

from module.Agent.ToolDispatcher import ToolDispatcher
from module.Agent.tools.pipeline_tools import (
    decompile_rpyc_files,
    refresh_replace_fallback,
    run_project_extraction,
    translation_status,
)
from module.Agent.tools.translation_tools import old_new_replace_confirmation_context
from module.Agent.types import ToolResult
from module.Config import Config
from module.Engine.Engine import Engine


def _config_for(root: Path) -> Config:
    config = Config()
    config.platforms = []
    config.renpy_project_path = str(root)
    config.renpy_game_folder = str(root)
    config.renpy_tl_folder = str(root / "game" / "tl" / "chinese")
    config.input_folder = str(root / "game" / "tl" / "chinese")
    config.target_language = "ZH"
    config.max_workers = 8
    config.save = lambda: config
    return config


class _FakeEngine:
    def __init__(self, *, busy: bool = False, status: Engine.Status = Engine.Status.IDLE) -> None:
        self.busy = busy
        self._status = status
        self.calls: list[tuple[object, object]] = []
        self.translator = None

    def try_set_status(self, expected, status) -> bool:
        self.calls.append((expected, status))
        return not self.busy

    def release_status(self, expected) -> bool:
        self.calls.append((expected, Engine.Status.IDLE))
        return True

    def get_status(self) -> Engine.Status:
        return self._status

    def get_running_task_count(self) -> int:
        return 2 if self._status == Engine.Status.TRANSLATING else 0

    def has_stop_barrier(self) -> bool:
        return False

    def has_single_tasks(self) -> bool:
        return False


def test_decompile_requires_trusted_game_dir(monkeypatch) -> None:
    import module.Agent.tools.pipeline_tools as pipeline_tools

    captured: dict[str, object] = {}

    def fake_handler(**kwargs):
        captured.update(kwargs)
        return ToolResult(True, "ok")

    monkeypatch.setattr(pipeline_tools, "decompile_rpyc_files", fake_handler)
    dispatcher = ToolDispatcher(engine=_FakeEngine())

    assert dispatcher.execute("decompile_rpyc_files").code == "CONFIRMATION_REQUIRED"
    assert dispatcher.execute("decompile_rpyc_files", confirmed=True).code == "CONFIRMATION_STALE"

    result = dispatcher.execute(
        "decompile_rpyc_files",
        confirmed=True,
        trusted_context={"game_dir": "E:/Game/game"},
    )
    assert result.success is True
    assert captured["confirmed_game_dir"] == "E:/Game/game"


def test_run_project_extraction_requires_trusted_project_root(monkeypatch) -> None:
    import module.Agent.tools.pipeline_tools as pipeline_tools

    captured: dict[str, object] = {}

    def fake_handler(**kwargs):
        captured.update(kwargs)
        return ToolResult(True, "ok")

    monkeypatch.setattr(pipeline_tools, "run_project_extraction", fake_handler)
    dispatcher = ToolDispatcher(engine=_FakeEngine())

    assert dispatcher.execute("run_project_extraction").code == "CONFIRMATION_REQUIRED"
    assert dispatcher.execute("run_project_extraction", confirmed=True).code == "CONFIRMATION_STALE"

    result = dispatcher.execute(
        "run_project_extraction",
        confirmed=True,
        trusted_context={"project_root": "E:/Game"},
    )
    assert result.success is True
    assert captured["confirmed_project_root"] == "E:/Game"


def test_pipeline_write_tools_reject_busy_engine(monkeypatch) -> None:
    import module.Agent.tools.pipeline_tools as pipeline_tools

    monkeypatch.setattr(
        pipeline_tools,
        "decompile_rpyc_files",
        lambda **kwargs: ToolResult(True, "ok"),
    )
    dispatcher = ToolDispatcher(engine=_FakeEngine(busy=True))
    result = dispatcher.execute(
        "decompile_rpyc_files",
        confirmed=True,
        trusted_context={"game_dir": "E:/Game/game"},
    )
    assert result.code == "ENGINE_BUSY"


def test_decompile_rpyc_files_project_not_set() -> None:
    config = Config()
    config.platforms = []
    result = decompile_rpyc_files(config_loader=lambda: config)
    assert result.code == "PROJECT_NOT_SET"


def test_decompile_rpyc_files_rejects_stale_confirmation(tmp_path) -> None:
    confirmed_root = tmp_path / "Confirmed"
    current_root = tmp_path / "Current"
    confirmed_game = confirmed_root / "game"
    current_game = current_root / "game"
    confirmed_game.mkdir(parents=True)
    current_game.mkdir(parents=True)
    (current_game / "script.rpyc").write_bytes(b"rpyc")
    config = _config_for(current_root)

    result = decompile_rpyc_files(
        config_loader=lambda: config,
        confirmed_game_dir=str(confirmed_game.resolve()),
    )

    assert result.code == "CONFIRMATION_STALE"


def test_decompile_rpyc_files_success(tmp_path, monkeypatch) -> None:
    root = tmp_path / "Game"
    game = root / "game"
    game.mkdir(parents=True)
    (game / "script.rpyc").write_bytes(b"rpyc")
    config = _config_for(root)

    monkeypatch.setattr(
        "module.Agent.tools.pipeline_tools.decompile_target",
        lambda *_args, **_kwargs: {"success": True, "method": "unrpyc"},
    )

    result = decompile_rpyc_files(
        config_loader=lambda: config,
        confirmed_game_dir=str(game.resolve()),
    )

    assert result.success is True
    assert result.data["decompiled_count"] == 1
    assert result.data["method"] == "unrpyc"


def test_run_project_extraction_need_decompile(tmp_path, monkeypatch) -> None:
    root = tmp_path / "Game"
    game = root / "game"
    game.mkdir(parents=True)
    (game / "script.rpyc").write_bytes(b"rpyc")
    config = _config_for(root)

    monkeypatch.setattr(
        "module.Agent.tools.pipeline_tools.detect_game_status",
        lambda *_args, **_kwargs: ("need_decompile", "need decompile"),
    )

    result = run_project_extraction(
        config_loader=lambda: config,
        confirmed_project_root=str(root.resolve()),
    )

    assert result.code == "NEED_DECOMPILE"
    assert result.data["next_tool"] == "decompile_rpyc_files"


def test_run_project_extraction_success(tmp_path, monkeypatch) -> None:
    root = tmp_path / "Game"
    game = root / "game"
    tl_dir = game / "tl" / "chinese"
    tl_dir.mkdir(parents=True)
    (game / "script.rpy").write_text("label start:\n    return\n", encoding="utf-8")
    config = _config_for(root)
    extract_result = SimpleNamespace(
        success=True,
        tl_dir=tl_dir,
        incremental_dir=None,
        new_strings=3,
        cancelled=False,
    )

    monkeypatch.setattr(
        "module.Agent.tools.pipeline_tools.detect_game_status",
        lambda *_args, **_kwargs: ("ready", "ready"),
    )
    monkeypatch.setattr(
        "module.Agent.tools.pipeline_tools.extract_project_text",
        lambda *_args, **_kwargs: (True, "ok", extract_result),
    )

    result = run_project_extraction(
        config_loader=lambda: config,
        confirmed_project_root=str(root.resolve()),
    )

    assert result.success is True
    assert result.data["entry_count"] == 3
    assert result.data["incremental"] is False
    assert Path(result.data["tl_dir"]) == tl_dir


def test_translation_status_project_not_set() -> None:
    config = Config()
    config.platforms = []
    result = translation_status(config_loader=lambda: config)
    assert result.code == "PROJECT_NOT_SET"


def test_translation_status_while_engine_is_translating(tmp_path, monkeypatch) -> None:
    root = tmp_path / "Game"
    (root / "game").mkdir(parents=True)
    config = _config_for(root)
    fake_engine = _FakeEngine(status=Engine.Status.TRANSLATING)
    fake_engine.translator = SimpleNamespace(
        extras={"progress": {"line": 5, "total_line": 10}},
    )

    monkeypatch.setattr(Engine, "get", lambda: fake_engine)
    monkeypatch.setattr(
        "module.Agent.tools.pipeline_tools.resolve_translation_output",
        lambda _config: None,
    )

    dispatcher = ToolDispatcher(config_loader=lambda: config, engine=fake_engine)
    result = dispatcher.execute("translation_status")

    assert result.success is True
    assert result.data["engine_status"] == Engine.Status.TRANSLATING.value
    assert result.data["running"]["running"] == 2
    assert result.data["progress"]["line"] == 5
    assert result.data["progress"]["percent"] == 50.0


def test_refresh_replace_fallback_up_to_date(tmp_path) -> None:
    root = tmp_path / "Game"
    tl_dir = root / "game" / "tl" / "chinese"
    tl_dir.mkdir(parents=True)
    tl_dir.joinpath("strings.rpy").write_text(
        'translate chinese strings:\n\n'
        '    # renpybox: replace-only\n'
        '    old "Choice"\n'
        '    new "选项"\n',
        encoding="utf-8",
    )
    config = _config_for(root)
    context = old_new_replace_confirmation_context(config_loader=lambda: config)

    import module.Agent.tools.inspection_tools as inspection_tools

    original = inspection_tools._old_new_summary

    def fake_summary(_paths):
        data = original(_paths)
        data["needs_refresh"] = False
        return data

    import module.Agent.tools.pipeline_tools as pipeline_tools

    pipeline_tools._old_new_summary = fake_summary
    try:
        result = refresh_replace_fallback(
            config_loader=lambda: config,
            confirmed_context=context,
        )
    finally:
        pipeline_tools._old_new_summary = original

    assert result.success is True
    assert result.data["refreshed"] is False


def test_refresh_replace_fallback_writes_hook(tmp_path) -> None:
    root = tmp_path / "Game"
    tl_dir = root / "game" / "tl" / "chinese"
    tl_dir.mkdir(parents=True)
    tl_dir.joinpath("strings.rpy").write_text(
        'translate chinese strings:\n\n'
        '    # renpybox: replace-only\n'
        '    old "Choice"\n'
        '    new "选项"\n',
        encoding="utf-8",
    )
    config = _config_for(root)
    (tl_dir / "replace_text_auto.rpyc").write_bytes(b"stale")
    context = old_new_replace_confirmation_context(config_loader=lambda: config)

    result = refresh_replace_fallback(
        config_loader=lambda: config,
        confirmed_context=context,
    )

    assert result.success is True
    assert result.data["refreshed"] is True
    assert result.data["pair_count"] == 1
    assert (tl_dir / "replace_text_auto.rpy").is_file()


def test_dispatcher_registers_pipeline_tools() -> None:
    dispatcher = ToolDispatcher()
    for name, confirmation, idle in (
        ("decompile_rpyc_files", True, True),
        ("run_project_extraction", True, True),
        ("translation_status", False, False),
        ("refresh_replace_fallback", True, True),
    ):
        tool = dispatcher.tools[name]
        assert tool.requires_confirmation is confirmation
        assert tool.requires_idle_engine is idle
