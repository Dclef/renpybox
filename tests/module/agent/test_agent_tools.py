from pathlib import Path
from dataclasses import replace
from module.Agent.ToolDispatcher import ToolDispatcher
from module.Agent.AgentPromptBuilder import AgentPromptBuilder
from module.Agent.types import ToolResult
from module.Agent.tools.archive_tools import unpack_rpa_files
from module.Agent.tools.project_tools import set_project
from module.Config import Config
from module.Engine.Engine import Engine
from module.Localizer.Localizer import Localizer
from base.BaseLanguage import BaseLanguage


def _config_for(root: Path) -> Config:
    config = Config()
    config.platforms = []
    config.renpy_project_path = str(root)
    config.renpy_game_folder = str(root)
    config.renpy_tl_folder = str(root / "game" / "tl" / "chinese")
    config.input_folder = str(root / "game" / "tl" / "chinese")
    config.target_language = "ZH"
    config.save = lambda: config
    return config


def test_dispatcher_exposes_tools_without_model_paths() -> None:
    dispatcher = ToolDispatcher()
    assert list(dispatcher.tools) == [
        "set_project",
        "get_project_info",
        "list_rpa_files",
        "scan_script_errors",
        "unpack_rpa_files",
    ]
    assert "path" in dispatcher.tools["set_project"].parameters_schema["properties"]
    for name in ("get_project_info", "list_rpa_files", "scan_script_errors", "unpack_rpa_files"):
        schema = dispatcher.tools[name].parameters_schema
        assert "game_dir" not in schema.get("properties", {})
        assert "project_root" not in schema.get("properties", {})
        assert "path" not in schema.get("properties", {})
    unpack = dispatcher.tools["unpack_rpa_files"]
    assert unpack.requires_confirmation is True
    assert unpack.requires_idle_engine is True


def test_dispatcher_tool_descriptions_follow_localizer() -> None:
    original = Localizer.get_app_language()
    try:
        Localizer.set_app_language(BaseLanguage.Enum.ZH)
        zh = ToolDispatcher().tools["list_rpa_files"].description
        Localizer.set_app_language(BaseLanguage.Enum.EN)
        en = ToolDispatcher().tools["list_rpa_files"].description
    finally:
        Localizer.set_app_language(original)

    assert zh == "列出当前项目 game 目录中的 RPA 文件。目录由服务端配置注入。"
    assert en == "List RPA files in the current project game folder. The server injects the path."


def test_agent_system_prompt_follows_localizer() -> None:
    original = Localizer.get_app_language()
    try:
        Localizer.set_app_language(BaseLanguage.Enum.ZH)
        zh = AgentPromptBuilder.build_system_prompt(Config())
        Localizer.set_app_language(BaseLanguage.Enum.EN)
        en = AgentPromptBuilder.build_system_prompt(Config())
    finally:
        Localizer.set_app_language(original)

    assert "项目助手" in zh
    assert "project assistant" in en


def test_unpack_tool_cannot_run_without_confirmation(tmp_path, monkeypatch) -> None:
    root = tmp_path / "MyGame"
    game = root / "game"
    game.mkdir(parents=True)
    (game / "archive.rpa").write_bytes(b"rpa")
    config = _config_for(root)
    called = []
    dispatcher = ToolDispatcher(config_loader=lambda: config, engine=_FakeEngine())
    tool = dispatcher.tools["unpack_rpa_files"]
    dispatcher._tools["unpack_rpa_files"] = replace(
        tool,
        handler=lambda: called.append(True) or ToolResult(True, "ok"),
    )

    result = dispatcher.execute("unpack_rpa_files")

    assert result.code == "CONFIRMATION_REQUIRED"
    assert called == []


def test_unpack_tool_uses_configured_game_dir_and_keeps_archives(tmp_path) -> None:
    root = tmp_path / "MyGame"
    game = root / "game"
    game.mkdir(parents=True)
    (game / "archive.rpa").write_bytes(b"rpa")
    config = _config_for(root)
    calls = []

    class PackerStub:
        def unpack_rpa_files(self, game_dir, **kwargs):
            calls.append((game_dir, kwargs))
            return {"success": True, "method": "direct", "count": 1}

    result = unpack_rpa_files(
        config_loader=lambda: config,
        packer_factory=PackerStub,
        confirmed_game_dir=str(game.resolve()),
    )

    assert result.success is True
    assert calls == [(
        str(game.resolve()),
        {"direct": True, "script_only": False, "remove_archives": False},
    )]
    assert result.data["archives_removed"] is False


def test_unpack_tool_rejects_changed_project_after_confirmation(tmp_path) -> None:
    confirmed_root = tmp_path / "ConfirmedGame"
    current_root = tmp_path / "CurrentGame"
    confirmed_game = confirmed_root / "game"
    current_game = current_root / "game"
    confirmed_game.mkdir(parents=True)
    current_game.mkdir(parents=True)
    (confirmed_game / "archive.rpa").write_bytes(b"rpa")
    (current_game / "archive.rpa").write_bytes(b"rpa")
    config = _config_for(current_root)
    called = []

    class PackerStub:
        def unpack_rpa_files(self, *_args, **_kwargs):
            called.append(True)
            return {"success": True, "method": "direct", "count": 1}

    result = unpack_rpa_files(
        config_loader=lambda: config,
        packer_factory=PackerStub,
        confirmed_game_dir=str(confirmed_game.resolve()),
    )

    assert result.success is False
    assert result.code == "CONFIRMATION_STALE"
    assert called == []


def test_confirmed_unpack_tool_requires_trusted_context(tmp_path) -> None:
    root = tmp_path / "MyGame"
    (root / "game").mkdir(parents=True)
    dispatcher = ToolDispatcher(
        config_loader=lambda: _config_for(root),
        engine=_FakeEngine(),
    )

    result = dispatcher.execute("unpack_rpa_files", confirmed=True)

    assert result.success is False
    assert result.code == "CONFIRMATION_STALE"


def test_confirmed_unpack_tool_holds_exclusive_engine_status(tmp_path) -> None:
    root = tmp_path / "MyGame"
    game = root / "game"
    game.mkdir(parents=True)
    (game / "archive.rpa").write_bytes(b"rpa")
    config = _config_for(root)
    engine = _FakeEngine()
    dispatcher = ToolDispatcher(config_loader=lambda: config, engine=engine)
    tool = dispatcher.tools["unpack_rpa_files"]
    dispatcher._tools["unpack_rpa_files"] = replace(
        tool,
        handler=lambda _confirmed_game_dir: ToolResult(
            True,
            "ok",
            {"game_dir": _confirmed_game_dir},
        ),
    )

    result = dispatcher.execute(
        "unpack_rpa_files",
        confirmed=True,
        trusted_context={"game_dir": str(game.resolve())},
    )

    assert result.success is True
    assert result.data["game_dir"] == str(game.resolve())
    assert engine.calls[0] == (Engine.Status.IDLE, Engine.Status.AGENT)
    assert engine.calls[-1] == (Engine.Status.AGENT, Engine.Status.IDLE)


def test_set_project_rejects_non_renpy_directory_without_saving(tmp_path) -> None:
    config = Config()
    saved = False

    def save() -> Config:
        nonlocal saved
        saved = True
        return config

    config.save = save
    result = set_project(str(tmp_path), config=config)

    assert result.success is False
    assert result.code == "INVALID_PROJECT_PATH"
    assert saved is False


def test_set_project_reports_normalized_project_and_language(tmp_path) -> None:
    root = tmp_path / "MyGame"
    (root / "game" / "tl" / "chinese").mkdir(parents=True)
    config = Config()
    config.save = lambda: config

    result = set_project(str(root), config=config)

    assert result.success is True
    assert result.data["project_root"] == str(root.resolve())
    assert result.data["game_dir"] == str((root / "game").resolve())
    assert result.data["language"] == "chinese"
    assert config.renpy_project_path == str(root.resolve())


def test_config_injected_tools_report_project_not_set_and_reject_extra_path() -> None:
    config = Config()
    config.platforms = []
    dispatcher = ToolDispatcher(config_loader=lambda: config)

    result = dispatcher.execute("list_rpa_files")
    assert result.code == "PROJECT_NOT_SET"

    result = dispatcher.execute("list_rpa_files", {"game_dir": "C:/Windows"})
    assert result.code == "INVALID_TOOL_ARGUMENTS"


class _FakeEngine:
    def __init__(self, busy: bool = False) -> None:
        self.busy = busy
        self.calls: list[tuple[object, object]] = []

    def try_set_status(self, expected, status) -> bool:
        self.calls.append((expected, status))
        return not self.busy

    def release_status(self, expected) -> bool:
        self.calls.append((expected, Engine.Status.IDLE))
        return True


def test_set_project_uses_exclusive_engine_status(tmp_path) -> None:
    root = tmp_path / "MyGame"
    (root / "game").mkdir(parents=True)
    config = Config()
    config.save = lambda: config
    engine = _FakeEngine()
    dispatcher = ToolDispatcher(config_loader=lambda: config, engine=engine)

    result = dispatcher.execute("set_project", {"path": str(root)})

    assert result.success is True
    assert engine.calls[0] == (Engine.Status.IDLE, Engine.Status.AGENT)
    assert engine.calls[-1] == (Engine.Status.AGENT, Engine.Status.IDLE)


def test_set_project_is_rejected_when_engine_is_busy(tmp_path) -> None:
    root = tmp_path / "MyGame"
    (root / "game").mkdir(parents=True)
    config = Config()
    engine = _FakeEngine(busy=True)
    dispatcher = ToolDispatcher(config_loader=lambda: config, engine=engine)

    result = dispatcher.execute("set_project", {"path": str(root)})

    assert result.success is False
    assert result.code == "ENGINE_BUSY"
