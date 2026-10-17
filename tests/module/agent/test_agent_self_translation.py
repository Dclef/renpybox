"""Agent 自带翻译工具（read_translation_batch / write_translation_batch）的用例。"""

from __future__ import annotations

from pathlib import Path

from base.Base import Base
from module.Agent.AgentService import AgentService
from module.Agent.ToolDispatcher import ToolDispatcher
from module.Agent.types import AgentRequestResult, AgentToolCall, ToolDef, ToolResult
from module.Engine.TaskRequester import TaskRequester
from module.Agent.tools.agent_translation_tools import (
    MAX_BATCH_SIZE,
    read_translation_batch,
    write_translation_batch,
)
from module.Cache.CacheItem import CacheItem
from module.Cache.CacheManager import CacheManager
from module.Cache.CacheProject import CacheProject
from module.Config import Config
from module.Engine.Engine import Engine


def _config_for(root: Path) -> Config:
    config = Config()
    config.platforms = []
    config.renpy_project_path = str(root)
    config.renpy_game_folder = str(root / "game")
    config.input_folder = str(root / "game" / "tl" / "chinese")
    config.output_folder = str(root / "output")
    config.target_language = "ZH"
    config.max_workers = 1
    config.save = lambda: config
    return config


def _make_item(row: int, src: str, *, status: Base.TranslationStatus) -> CacheItem:
    item = CacheItem()
    item.set_file_path("game/tl/chinese/script.rpy")
    item.set_row(row)
    item.set_src(src)
    item.set_file_type(CacheItem.FileType.NONE)
    item.set_text_type(CacheItem.TextType.RENPY)
    item.set_status(status)
    return item


def _seed_cache(config: Config, items: list[CacheItem]) -> None:
    output = Path(str(config.output_folder))
    output.mkdir(parents = True, exist_ok = True)
    manager = CacheManager(service = False)
    project = CacheProject()
    manager.set_project(project)
    manager.set_items(items)
    assert manager.save_to_file(project, items, str(output)) is True


def _load_items(config: Config) -> list[CacheItem]:
    manager = CacheManager(service = False)
    manager.load_items_from_file(str(config.output_folder))
    return manager.get_items()


class _FakeEngine:
    def __init__(self, *, status: Engine.Status = Engine.Status.IDLE) -> None:
        self._status = status
        self.translator = None

    def try_set_status(self, expected, status) -> bool:
        return self._status == Engine.Status.IDLE

    def release_status(self, expected) -> bool:
        return True

    def get_status(self) -> Engine.Status:
        return self._status

    def get_running_task_count(self) -> int:
        return 1 if self._status == Engine.Status.TRANSLATING else 0

    def has_stop_barrier(self) -> bool:
        return False

    def has_single_tasks(self) -> bool:
        return False


def test_read_translation_batch_returns_pending_items(tmp_path: Path) -> None:
    config = _config_for(tmp_path)
    _seed_cache(config, [
        _make_item(1, "Hello", status = Base.TranslationStatus.UNTRANSLATED),
        _make_item(2, "World", status = Base.TranslationStatus.UNTRANSLATED),
        _make_item(3, "Done", status = Base.TranslationStatus.TRANSLATED),
        _make_item(4, "Skipped", status = Base.TranslationStatus.EXCLUDED),
    ])

    result = read_translation_batch(config_loader = lambda: config)

    assert result.success is True
    assert result.data["remaining"] == 2
    assert [item["src"] for item in result.data["items"]] == ["Hello", "World"]
    # id 由文件相对路径与行号组成，写回时要用它定位
    assert result.data["items"][0]["id"].endswith("1")


def test_read_translation_batch_respects_batch_size_and_char_budget(tmp_path: Path) -> None:
    config = _config_for(tmp_path)
    _seed_cache(config, [
        _make_item(row, "x" * 100, status = Base.TranslationStatus.UNTRANSLATED)
        for row in range(1, 11)
    ])

    result = read_translation_batch(config_loader = lambda: config, batch_size = 3)

    assert len(result.data["items"]) == 3
    assert result.data["remaining"] == 10

    budget = read_translation_batch(
        config_loader = lambda: config,
        batch_size = MAX_BATCH_SIZE,
        max_chars = 500,
    )
    # 单条 100 字符，预算 500 至少返回 5 条，且不会超出预算太多
    assert 5 <= len(budget.data["items"]) <= 6


def test_read_translation_batch_reports_missing_output_folder(tmp_path: Path) -> None:
    config = _config_for(tmp_path)
    config.output_folder = ""

    result = read_translation_batch(config_loader = lambda: config)

    assert result.success is False
    assert result.code == "TRANSLATION_TARGET_MISSING"


def test_write_translation_batch_persists_translation(tmp_path: Path) -> None:
    config = _config_for(tmp_path)
    _seed_cache(config, [
        _make_item(1, "Hello", status = Base.TranslationStatus.UNTRANSLATED),
        _make_item(2, "World", status = Base.TranslationStatus.UNTRANSLATED),
    ])

    batch = read_translation_batch(config_loader = lambda: config)
    ids = [item["id"] for item in batch.data["items"]]

    result = write_translation_batch(
        config_loader = lambda: config,
        translations = [
            {"id": ids[0], "dst": "你好"},
            {"id": ids[1], "dst": "世界"},
        ],
    )

    assert result.success is True
    assert result.data["written"] == 2

    stored = {item.get_row(): item for item in _load_items(config)}
    assert stored[1].get_dst() == "你好"
    assert stored[2].get_dst() == "世界"
    assert Base.is_item_completed(stored[1].get_status()) is True

    # 写回后不应再读到待译条目
    again = read_translation_batch(config_loader = lambda: config)
    assert again.data["remaining"] == 0


def test_write_translation_batch_rejects_unknown_and_empty_ids(tmp_path: Path) -> None:
    config = _config_for(tmp_path)
    _seed_cache(config, [_make_item(1, "Hello", status = Base.TranslationStatus.UNTRANSLATED)])

    result = write_translation_batch(
        config_loader = lambda: config,
        translations = [
            {"id": "game/tl/chinese/other.rpy｜999", "dst": "无主"},
            {"id": "", "dst": "空 id"},
            {"id": "x", "dst": "   "},
            "not-a-dict",
        ],
    )

    assert result.success is False
    assert result.code == "NOTHING_WRITTEN"
    assert len(result.data["rejected"]) == 4
    assert _load_items(config)[0].get_dst() == ""


def test_write_translation_batch_requires_translations(tmp_path: Path) -> None:
    config = _config_for(tmp_path)

    result = write_translation_batch(config_loader = lambda: config, translations = [])

    assert result.success is False
    assert result.code == "TRANSLATIONS_REQUIRED"


def test_write_translation_batch_rejects_translations_that_lose_placeholders(
    tmp_path: Path,
) -> None:
    config = _config_for(tmp_path)
    _seed_cache(config, [
        _make_item(1, "Hello", status = Base.TranslationStatus.UNTRANSLATED),
        _make_item(
            2,
            "Cash: _RENPYBOX_0_1_ gold",
            status = Base.TranslationStatus.UNTRANSLATED,
        ),
    ])

    batch = read_translation_batch(config_loader = lambda: config)
    ids = [item["id"] for item in batch.data["items"]]

    result = write_translation_batch(
        config_loader = lambda: config,
        translations = [
            {"id": ids[0], "dst": "你好"},
            # 丢掉了占位符，必须被引擎的校验器拦下
            {"id": ids[1], "dst": "金币：黄金"},
        ],
    )

    assert result.success is True
    assert result.data["written"] == 1
    assert result.data["failed"] == 1
    assert result.data["failed_items"][0]["id"] == ids[1]
    assert result.data["failed_items"][0]["code"] != "NONE"

    stored = {item.get_row(): item for item in _load_items(config)}
    assert Base.is_item_completed(stored[1].get_status()) is True
    # 不合格条目被打回未翻译，下一批还会取到它
    assert stored[2].get_status() == Base.TranslationStatus.UNTRANSLATED
    again = read_translation_batch(config_loader = lambda: config)
    assert [item["id"] for item in again.data["items"]] == [ids[1]]


def test_translation_tools_are_registered_and_validate_arguments() -> None:
    dispatcher = ToolDispatcher(engine = _FakeEngine())

    tools = dispatcher.tools
    assert "read_translation_batch" in tools
    assert "write_translation_batch" in tools
    assert tools["read_translation_batch"].requires_confirmation is False
    assert tools["read_translation_batch"].requires_idle_engine is True
    assert tools["write_translation_batch"].requires_idle_engine is True

    assert (
        dispatcher.execute("read_translation_batch", {"batch_size": "3"}).code
        == "INVALID_TOOL_ARGUMENTS"
    )
    assert (
        dispatcher.execute("write_translation_batch", {"translations": "nope"}).code
        == "INVALID_TOOL_ARGUMENTS"
    )


def test_translation_tools_are_blocked_while_engine_busy() -> None:
    dispatcher = ToolDispatcher(engine = _FakeEngine(status = Engine.Status.TRANSLATING))

    result = dispatcher.execute("read_translation_batch", {})

    assert result.success is False
    assert result.code == "ENGINE_BUSY"


def _agent_config() -> Config:
    config = Config(agent_platform = 0)
    config.platforms = [{
        "id": 0,
        "api_format": Base.APIFormat.OPENAI,
        "api_key": ["test"],
        "api_url": "https://example.invalid",
        "model": "test-model",
    }]
    return config


class _LoopDispatcher:
    """模拟只会调用一个长任务工具的调度器。"""

    def __init__(self, *, continues: bool) -> None:
        self.continues = continues
        self.calls: list[str] = []
        self.tools = {
            "read_translation_batch": ToolDef(
                "read_translation_batch",
                "读取待译条目",
                {"type": "object", "properties": {}, "additionalProperties": False},
                lambda: ToolResult(True, "一批", {"remaining": 10}, continues=self.continues),
                result_limit = 12_000,
            )
        }

    def execute(self, name, arguments, *, confirmed=False, trusted_context=None, cancel_check=None):
        self.calls.append(name)
        return self.tools[name].handler()


def _always_calls_tool(monkeypatch, *, continues: bool, max_iterations: int, max_long: int):
    dispatcher = _LoopDispatcher(continues = continues)
    counter = {"n": 0}

    def request_tools(self, messages, tools):
        counter["n"] += 1
        return AgentRequestResult(
            True,
            tool_calls = [AgentToolCall(f"call-{counter['n']}", "read_translation_batch", {})],
        )

    monkeypatch.setattr(TaskRequester, "request_tools", request_tools)
    service = AgentService(
        config_loader = lambda: _agent_config(),
        dispatcher = dispatcher,
        max_iterations = max_iterations,
        max_long_iterations = max_long,
    )
    return service.run("翻译这个项目"), counter, dispatcher


def test_long_task_iterations_are_not_capped_by_normal_budget(monkeypatch) -> None:
    result, counter, dispatcher = _always_calls_tool(
        monkeypatch,
        continues = True,
        max_iterations = 2,
        max_long = 5,
    )

    # 普通预算是 2 轮，但长任务预算把它顶到 5 轮才收尾。
    assert result.success is False
    assert result.code == "MAX_ITERATIONS"
    assert counter["n"] == 5
    assert len(dispatcher.calls) == 5


def test_ordinary_tool_calls_still_use_normal_budget(monkeypatch) -> None:
    result, counter, dispatcher = _always_calls_tool(
        monkeypatch,
        continues = False,
        max_iterations = 2,
        max_long = 5,
    )

    assert result.success is False
    assert result.code == "MAX_ITERATIONS"
    assert counter["n"] == 2
    assert len(dispatcher.calls) == 2


class _HeavyDispatcher:
    """每轮都返回很大的工具结果，用于触发单回合内裁剪。"""

    def __init__(self) -> None:
        self.calls = 0
        self.tools = {
            "read_translation_batch": ToolDef(
                "read_translation_batch",
                "读取待译条目",
                {"type": "object", "properties": {}, "additionalProperties": False},
                lambda: ToolResult(True, "x" * 3000, {"remaining": 99}, continues=True),
            )
        }

    def execute(self, name, arguments, *, confirmed=False, trusted_context=None, cancel_check=None):
        self.calls += 1
        return self.tools[name].handler()


def test_long_run_trims_history_within_a_single_turn(monkeypatch) -> None:
    dispatcher = _HeavyDispatcher()
    counter = {"n": 0}

    def request_tools(self, messages, tools):
        counter["n"] += 1
        return AgentRequestResult(
            True,
            tool_calls = [AgentToolCall(f"call-{counter['n']}", "read_translation_batch", {})],
        )

    monkeypatch.setattr(TaskRequester, "request_tools", request_tools)
    service = AgentService(
        config_loader = lambda: _agent_config(),
        dispatcher = dispatcher,
        max_iterations = 2,
        max_long_iterations = 6,
        max_context_chars = 4096,
    )

    result = service.run("翻译整个项目")

    assert result.code == "MAX_ITERATIONS"
    # 系统提示与当前用户诉求必须保留
    assert service.messages[0]["role"] == "system"
    assert service.messages[1]["role"] == "user"
    # 裁剪必须按助手消息为边界，不能留下没有对应调用的工具消息
    for index, message in enumerate(service.messages):
        if message.get("role") == "tool":
            assert index > 0
            assert service.messages[index - 1].get("role") in {"assistant", "tool"}
    # 上下文不能随轮次线性增长
    tool_messages = [item for item in service.messages if item.get("role") == "tool"]
    assert len(tool_messages) <= 2
