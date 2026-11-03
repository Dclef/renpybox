import json
from pathlib import Path

from module.Agent.AgentSessionStore import (
    MAX_TITLE_CHARS,
    SCHEMA_VERSION,
    AgentSessionStore,
    session_title,
)


def _messages(text: str = "查看项目") -> list[dict]:
    return [
        {"id": "1-user", "role": "user", "content": text},
        {"id": "1-assistant", "role": "assistant", "content": "完成", "tools": [], "status": "done"},
    ]


def test_save_and_load_roundtrip(tmp_path) -> None:
    store = AgentSessionStore(tmp_path)

    saved = store.save(session_id="abc123", messages=_messages(), context=[{"role": "user", "content": "上下文"}])

    assert saved is not None
    assert saved["title"] == "查看项目"
    payload = store.load("abc123")
    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["messages"][0]["content"] == "查看项目"
    assert payload["context"] == [{"role": "user", "content": "上下文"}]


def test_save_empty_messages_deletes_session(tmp_path) -> None:
    store = AgentSessionStore(tmp_path)
    store.save(session_id="abc123", messages=_messages())

    assert store.save(session_id="abc123", messages=[]) is None
    assert store.load("abc123") is None


def test_list_sessions_sorts_by_updated_at_desc(tmp_path) -> None:
    store = AgentSessionStore(tmp_path)
    store.save(session_id="old", messages=_messages("旧任务"), created_at=1.0)
    store.save(session_id="new", messages=_messages("新任务"), created_at=2.0)

    sessions = store.list_sessions()

    assert [item["id"] for item in sessions] == ["new", "old"]
    assert sessions[0]["message_count"] == 2


def test_list_sessions_skips_corrupted_files(tmp_path) -> None:
    store = AgentSessionStore(tmp_path)
    store.save(session_id="good", messages=_messages())
    (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")
    (tmp_path / "wrongschema.json").write_text('{"schema_version": 99}', encoding="utf-8")

    assert [item["id"] for item in store.list_sessions()] == ["good"]


def test_delete_and_missing_delete(tmp_path) -> None:
    store = AgentSessionStore(tmp_path)
    store.save(session_id="abc123", messages=_messages())

    assert store.delete("abc123") is True
    assert store.delete("abc123") is False


def test_rejects_path_like_session_ids(tmp_path) -> None:
    store = AgentSessionStore(tmp_path)

    for value in ("../escape", "a/b", "", "x" * 65, "会话"):
        assert store.load(value) is None
        assert store.delete(value) is False


def test_prune_keeps_most_recent(tmp_path) -> None:
    store = AgentSessionStore(tmp_path)
    for index in range(5):
        store.save(session_id=f"s{index}", messages=_messages(f"任务{index}"), created_at=float(index))

    removed = store.prune(keep=2)

    assert removed == 3
    assert len(store.list_sessions()) == 2


def test_session_title_uses_first_user_message_and_folds_newlines() -> None:
    assert session_title([]) == "新会话"
    assert session_title([{"role": "assistant", "content": "先说话"}]) == "新会话"
    assert session_title([{"role": "user", "content": "  多行\n标题  "}]) == "多行 标题"
    long_title = session_title([{"role": "user", "content": "字" * 80}])
    assert len(long_title) == MAX_TITLE_CHARS + 1
    assert long_title.endswith("…")


def test_oversized_session_is_not_written(tmp_path) -> None:
    store = AgentSessionStore(tmp_path)
    huge = [{"id": "1-user", "role": "user", "content": "字" * (9 * 1024 * 1024)}]

    assert store.save(session_id="big", messages=huge) is None
    assert store.load("big") is None


def test_stage_and_budget_round_trip(tmp_path: Path) -> None:
    """阶段与预算要能随会话落盘并读回，供历史会话恢复状态栏。"""

    store = AgentSessionStore(root = tmp_path)
    store.save(
        session_id = "abc",
        messages = [{"role": "user", "content": "翻完这个项目"}],
        stage = "translate",
        budget = {"context_window": 200000, "max_iterations": 12},
    )

    payload = store.load("abc")

    assert payload is not None
    assert payload["stage"] == "translate"
    assert payload["budget"]["context_window"] == 200000


def test_legacy_session_without_stage_loads_fine(tmp_path: Path) -> None:
    """旧会话文件没有 stage / budget，必须照样能加载（schema 版本不变）。"""

    store = AgentSessionStore(root = tmp_path)
    store._ensure_root()
    legacy = {
        "schema_version": SCHEMA_VERSION,
        "id": "legacy",
        "title": "旧会话",
        "created_at": 1.0,
        "updated_at": 1.0,
        "messages": [{"role": "user", "content": "旧消息"}],
        "context": [],
        "metrics": {},
    }
    (tmp_path / "legacy.json").write_text(
        json.dumps(legacy, ensure_ascii = False),
        encoding = "utf-8",
    )

    payload = store.load("legacy")

    assert payload is not None
    # 旧文件没有这两个键，读取侧必须用 .get() 兜底而不是抛异常
    assert payload.get("stage", "") == ""
    assert payload.get("budget", {}) == {}
