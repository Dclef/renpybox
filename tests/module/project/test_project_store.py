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


def test_apply_resolved_writes_five_fields_saves_and_emits(
    store, tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    instance, emitted = store
    config = _FakeConfig()
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
