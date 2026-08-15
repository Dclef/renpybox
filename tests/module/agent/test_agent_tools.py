from pathlib import Path
from dataclasses import replace
from module.Agent.ToolDispatcher import ToolDispatcher
from module.Agent.AgentPromptBuilder import AgentPromptBuilder
from module.Agent.types import ToolResult
from module.Agent.tools.archive_tools import unpack_rpa_files
from module.Agent.tools.project_tools import list_rpa_files, set_project
from module.Agent.tools.translation_tools import (
    old_new_replace_confirmation_context,
    optimize_old_new_translations,
)
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
        "inspect_translation_project",
        "list_rpa_files",
        "scan_script_errors",
        "unpack_rpa_files",
        "optimize_old_new_translations",
    ]
    assert "path" in dispatcher.tools["set_project"].parameters_schema["properties"]
    for name in (
        "get_project_info",
        "inspect_translation_project",
        "list_rpa_files",
        "scan_script_errors",
        "unpack_rpa_files",
        "optimize_old_new_translations",
    ):
        schema = dispatcher.tools[name].parameters_schema
        assert "game_dir" not in schema.get("properties", {})
        assert "project_root" not in schema.get("properties", {})
        assert "path" not in schema.get("properties", {})
    unpack = dispatcher.tools["unpack_rpa_files"]
    assert unpack.requires_confirmation is True
    assert unpack.requires_idle_engine is True
    optimize = dispatcher.tools["optimize_old_new_translations"]
    assert optimize.requires_confirmation is True
    assert optimize.requires_idle_engine is True
    inspect = dispatcher.tools["inspect_translation_project"]
    assert inspect.requires_confirmation is False
    assert inspect.requires_idle_engine is False


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
    assert "不要使用 Emoji" in zh
    assert "Do not use Emoji" in en
    assert "确认/取消按钮" in zh
    assert "Confirm and Cancel buttons" in en


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


def test_old_new_tool_requires_confirmation_and_trusted_context() -> None:
    dispatcher = ToolDispatcher(engine=_FakeEngine())
    tool = dispatcher.tools["optimize_old_new_translations"]
    dispatcher._tools["optimize_old_new_translations"] = replace(
        tool,
        handler=lambda _confirmed_context: ToolResult(
            True,
            "ok",
            {"context": _confirmed_context},
        ),
    )

    assert dispatcher.execute("optimize_old_new_translations").code == "CONFIRMATION_REQUIRED"
    assert dispatcher.execute(
        "optimize_old_new_translations",
        confirmed=True,
    ).code == "CONFIRMATION_STALE"

    context = {"game_dir": "E:/Game/game", "signature": "stable"}
    result = dispatcher.execute(
        "optimize_old_new_translations",
        confirmed=True,
        trusted_context=context,
    )
    assert result.success is True
    assert result.data["context"] == context


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


def test_old_new_optimization_uses_confirmed_project_and_writes_hook(tmp_path) -> None:
    root = tmp_path / "MyGame"
    tl_dir = root / "game" / "tl" / "chinese"
    tl_dir.mkdir(parents=True)
    tl_dir.joinpath("strings.rpy").write_text(
        'translate chinese strings:\n\n'
        '    old "Choice"\n'
        '    new "选项"\n',
        encoding="utf-8",
    )
    config = _config_for(root)
    context = old_new_replace_confirmation_context(config_loader=lambda: config)

    result = optimize_old_new_translations(
        config_loader=lambda: config,
        confirmed_context=context,
    )

    assert result.success is True
    assert result.data["old_new_count"] == 1
    output = tl_dir / "replace_text_auto.rpy"
    assert output.is_file()
    assert '.replace("Choice", "选项")' in output.read_text(encoding="utf-8")

    second_context = old_new_replace_confirmation_context(config_loader=lambda: config)
    second = optimize_old_new_translations(
        config_loader=lambda: config,
        confirmed_context=second_context,
    )
    assert second.success is True
    assert Path(second.data["backup_path"]).is_file()


def test_old_new_optimization_rejects_stale_confirmation(tmp_path) -> None:
    root = tmp_path / "MyGame"
    tl_dir = root / "game" / "tl" / "chinese"
    tl_dir.mkdir(parents=True)
    tl_dir.joinpath("strings.rpy").write_text(
        'translate chinese strings:\n\n'
        '    old "Choice"\n'
        '    new "选项"\n',
        encoding="utf-8",
    )
    config = _config_for(root)
    context = old_new_replace_confirmation_context(config_loader=lambda: config)
    context["signature"] = "stale"

    result = optimize_old_new_translations(
        config_loader=lambda: config,
        confirmed_context=context,
    )

    assert result.success is False
    assert result.code == "CONFIRMATION_STALE"
    assert not (tl_dir / "replace_text_auto.rpy").exists()


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


def test_list_rpa_reports_whether_scripts_are_already_available(tmp_path) -> None:
    root = tmp_path / "Game"
    game = root / "game"
    game.mkdir(parents=True)
    (game / "archive.rpa").write_bytes(b"rpa")
    config = _config_for(root)

    archive_only = list_rpa_files(config_loader=lambda: config)

    assert archive_only.data["unpack_required"] is True
    assert archive_only.data["rpa_state"] == "required"
    assert archive_only.data["rpy_count"] == 0
    assert archive_only.data["rpyc_count"] == 0

    (game / "script.rpy").write_text("label start:\n    return\n", encoding="utf-8")
    scripts_available = list_rpa_files(config_loader=lambda: config)

    assert scripts_available.data["unpack_required"] is False
    assert scripts_available.data["rpa_state"] == "scripts_present"
    assert scripts_available.data["rpy_count"] == 1


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
