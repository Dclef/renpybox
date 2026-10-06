import pytest

from base.Base import Base
from module.Project.ProjectStore import ProjectStore
from module.Renpy.ProjectPaths import RenpyProjectPaths


@pytest.fixture()
def store(monkeypatch: pytest.MonkeyPatch):
    with monkeypatch.context() as patch:
        patch.setattr(Base, "subscribe", lambda *a, **k: None)
        instance = ProjectStore()
    emitted: list[tuple] = []
    monkeypatch.setattr(
        instance, "emit", lambda event, data: emitted.append((event, data))
    )
    return instance, emitted


class _FakeConfig:

    def __init__(self) -> None:
        self.renpy_project_path = "old/root"
        self.renpy_game_folder = "old/root"
        self.renpy_tl_folder = "old/tl"
        self.input_folder = "old/input"
        self.output_folder = "old/output"
        self.saved = 0

    def save(self) -> None:
        self.saved += 1


def _fake_paths(tmp_path, monkeypatch: pytest.MonkeyPatch) -> RenpyProjectPaths:
    project_root = tmp_path / "MyGame"
    (project_root / "game").mkdir(parents = True)
    (project_root / "game" / "tl" / "chinese").mkdir(parents = True)
    paths = RenpyProjectPaths.from_path(project_root)
    assert paths is not None
    return paths


def test_apply_resolved_writes_three_identity_fields_and_derives_empty_run_folders(
    store, tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """空运行目录仍是派生态：应回落到本项目的标准目录。"""
    instance, emitted = store
    config = _FakeConfig()
    config.input_folder = ""
    config.output_folder = ""
    paths = _fake_paths(tmp_path, monkeypatch)

    instance.apply_resolved(config, paths)

    assert config.renpy_project_path == str(paths.project_root)
    assert config.renpy_game_folder == str(paths.project_root)
    assert config.renpy_tl_folder == str(paths.tl_language_dir)
    assert config.input_folder == str(paths.tl_language_dir)
    assert config.output_folder == str(paths.translation_output_dir)
    assert config.saved == 1
    assert emitted == [(
        Base.Event.PROJECT_CHANGED,
        {"project_root": str(paths.project_root)},
    )]


@pytest.mark.parametrize("field", ["input_folder", "output_folder"])
def test_apply_resolved_keeps_user_chosen_run_folder(
    store, tmp_path, monkeypatch: pytest.MonkeyPatch, field: str
) -> None:
    """用户自己选的目录不能被规范项目路径改写回 game/tl/<lang>。"""
    instance, _ = store
    config = _FakeConfig()
    custom = tmp_path / "MyOwnFolder" / "trans"
    custom.mkdir(parents = True)
    setattr(config, field, str(custom))
    other = "output_folder" if field == "input_folder" else "input_folder"
    setattr(config, other, "")
    paths = _fake_paths(tmp_path, monkeypatch)

    instance.apply_resolved(config, paths)

    assert getattr(config, field) == str(custom)
    # 另一个字段是空值时照旧派生。
    expected = (
        str(paths.translation_output_dir)
        if field == "input_folder"
        else str(paths.tl_language_dir)
    )
    assert getattr(config, other) == expected


@pytest.mark.parametrize("field", ["input_folder", "output_folder"])
def test_apply_resolved_refreshes_stale_derived_folders_from_other_project(
    store, tmp_path, monkeypatch: pytest.MonkeyPatch, field: str
) -> None:
    """上一个项目遗留的派生态必须跟随新项目，否则会卡在旧路径。"""
    instance, _ = store
    config = _FakeConfig()
    old_project = tmp_path / "OldGame"
    if field == "input_folder":
        stale = old_project / "game" / "tl" / "chinese"
    else:
        stale = old_project / "RenpyBox_Translation" / "chinese"
    stale.mkdir(parents = True)
    setattr(config, field, str(stale))
    paths = _fake_paths(tmp_path, monkeypatch)

    instance.apply_resolved(config, paths)

    expected = (
        str(paths.tl_language_dir)
        if field == "input_folder"
        else str(paths.translation_output_dir)
    )
    assert getattr(config, field) == expected


def test_apply_resolved_refreshes_stale_incremental_folder(
    store, tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """旧增量暂存目录也是派生态，切项目后必须让位给新的主目录。"""
    instance, _ = store
    config = _FakeConfig()
    stale = tmp_path / "OldGame" / "RenpyBox_Translation" / "chinese_new"
    stale.mkdir(parents = True)
    config.input_folder = str(stale)
    paths = _fake_paths(tmp_path, monkeypatch)

    instance.apply_resolved(config, paths)

    assert config.input_folder == str(paths.tl_language_dir)


def test_apply_resolved_honors_explicit_run_folders(
    store, tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    instance, _ = store
    config = _FakeConfig()
    paths = _fake_paths(tmp_path, monkeypatch)

    instance.apply_resolved(
        config, paths,
        input_folder = "custom/input",
        output_folder = "custom/output",
    )
    assert config.input_folder == "custom/input"
    assert config.output_folder == "custom/output"


def test_apply_resolved_mutates_extra_fields_before_single_save(
    store, tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    instance, _ = store
    config = _FakeConfig()
    paths = _fake_paths(tmp_path, monkeypatch)

    instance.apply_resolved(
        config,
        paths,
        mutate = lambda current: setattr(current, "renpy_hook_translate", True),
    )

    assert config.renpy_hook_translate is True
    assert config.saved == 1


def test_apply_resolved_can_defer_persistence_for_runtime_paths(
    store, tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    instance, emitted = store
    config = _FakeConfig()
    paths = _fake_paths(tmp_path, monkeypatch)

    instance.apply_resolved(config, paths, persist = False)

    assert config.renpy_project_path == str(paths.project_root)
    assert config.saved == 0
    assert emitted == []

    instance.persist(config, emit = False)
    assert config.saved == 1


def test_save_edited_paths_only_touches_three_fields(store) -> None:
    instance, emitted = store
    config = _FakeConfig()

    instance.save_edited_paths(config, "new/root", "new/game", "new/tl")

    assert config.renpy_project_path == "new/root"
    assert config.renpy_game_folder == "new/game"
    assert config.renpy_tl_folder == "new/tl"
    # 表单语义：运行目录不动
    assert config.input_folder == "old/input"
    assert config.output_folder == "old/output"
    assert config.saved == 1
    assert emitted[0][0] == Base.Event.PROJECT_CHANGED
    assert emitted[0][1] == {"project_root": "new/root"}


def test_save_edited_paths_keeps_blank_semantics(store) -> None:
    """表单空串原样写入（历史行为）：不默认填充。"""
    instance, _ = store
    config = _FakeConfig()

    instance.save_edited_paths(config, "", "", "")

    assert config.renpy_project_path == ""
    assert config.renpy_game_folder == ""
    assert config.renpy_tl_folder == ""
    assert config.saved == 1


def test_save_edited_paths_applies_extra_fields_before_single_save(store) -> None:
    instance, _ = store
    config = _FakeConfig()

    instance.save_edited_paths(
        config,
        "new/root",
        "new/game",
        "new/tl",
        mutate = lambda current: setattr(current, "target_language", "ZH"),
    )

    assert config.target_language == "ZH"
    assert config.saved == 1
