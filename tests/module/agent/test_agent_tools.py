from pathlib import Path
from module.Agent.ToolDispatcher import ToolDispatcher
from module.Agent.tools.project_tools import set_project
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
    config.save = lambda: config
    return config


def test_dispatcher_exposes_exactly_four_tools_without_model_paths() -> None:
    dispatcher = ToolDispatcher()
    assert list(dispatcher.tools) == [
        "set_project",
        "get_project_info",
        "list_rpa_files",
        "scan_script_errors",
    ]
    assert "path" in dispatcher.tools["set_project"].parameters_schema["properties"]
    for name in ("get_project_info", "list_rpa_files", "scan_script_errors"):
        schema = dispatcher.tools[name].parameters_schema
        assert "game_dir" not in schema.get("properties", {})
        assert "project_root" not in schema.get("properties", {})
        assert "path" not in schema.get("properties", {})


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
