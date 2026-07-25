from pathlib import Path
from types import SimpleNamespace
import sqlite3

from module.Cache.CacheDB import CacheDB
from module.Cache.CacheProject import CacheProject
from module.Renpy.ProjectPaths import (
    RenpyProjectPaths,
    read_run_manifest,
    resolve_translation_output,
    translation_output_candidates,
    write_run_manifest,
)


def _config(paths: RenpyProjectPaths, output: Path | None = None):
    return SimpleNamespace(
        renpy_project_path = str(paths.project_root),
        renpy_game_folder = str(paths.project_root),
        renpy_tl_folder = str(paths.tl_language_dir),
        input_folder = str(paths.tl_language_dir),
        output_folder = str(output or paths.translation_output_dir),
    )


def _write_json_cache(output: Path) -> None:
    cache = output / "cache"
    cache.mkdir(parents = True, exist_ok = True)
    (cache / "items.json").write_text("[]", encoding = "utf-8")
    (cache / "project.json").write_text("{}", encoding = "utf-8")


def test_run_manifest_keeps_incremental_cache_after_config_switch(tmp_path):
    project = tmp_path / "game-project"
    (project / "game" / "tl" / "chinese").mkdir(parents = True)
    paths = RenpyProjectPaths.from_path(project / "game" / "tl")
    assert paths is not None

    incremental = project / "RenpyBox_Translation" / "chinese_new"
    (incremental / "cache").mkdir(parents = True)
    (incremental / "cache" / "items.json").write_text("[]", encoding = "utf-8")
    (incremental / "cache" / "project.json").write_text("{}", encoding = "utf-8")
    write_run_manifest(
        paths,
        incremental,
        input_folder = project / "game" / "tl" / "chinese_new",
        run_kind = "incremental",
    )

    # 模拟翻译完成后配置恢复到主输出目录；校对页仍应命中最近增量缓存。
    config = _config(paths)
    assert resolve_translation_output(config) == incremental.resolve()
    manifest = read_run_manifest(paths)
    assert manifest is not None
    assert manifest["project_key"] == paths.project_key
    assert manifest["run_kind"] == "incremental"


def test_explicit_non_main_output_wins_over_stale_manifest(tmp_path):
    project = tmp_path / "game-project"
    (project / "game" / "tl" / "chinese").mkdir(parents = True)
    paths = RenpyProjectPaths.from_path(project)
    assert paths is not None
    main = paths.translation_output_dir
    delta = main.parent / "chinese_new"
    for output in (main, delta):
        (output / "cache").mkdir(parents = True, exist_ok = True)
        (output / "cache" / "items.json").write_text("[]", encoding = "utf-8")
        (output / "cache" / "project.json").write_text("{}", encoding = "utf-8")
    write_run_manifest(paths, main, run_kind = "translation")

    # 配置明确指向增量目录时，不应被旧的主目录清单抢走。
    config = _config(paths, output = delta)
    assert resolve_translation_output(config) == delta.resolve()


def test_preferred_cache_cannot_override_explicit_output(tmp_path):
    project = tmp_path / "game-project"
    (project / "game" / "tl" / "chinese").mkdir(parents = True)
    paths = RenpyProjectPaths.from_path(project)
    assert paths is not None
    main = paths.translation_output_dir
    delta = main.parent / "chinese_new"
    for output in (main, delta):
        (output / "cache").mkdir(parents = True, exist_ok = True)
        (output / "cache" / "items.json").write_text("[]", encoding = "utf-8")
        (output / "cache" / "project.json").write_text("{}", encoding = "utf-8")

    config = _config(paths, output = delta)
    assert resolve_translation_output(config, preferred = main) == delta.resolve()

    config.output_folder = str(main)
    write_run_manifest(paths, main, run_kind = "translation")
    assert resolve_translation_output(config, preferred = delta) == main.resolve()


def test_corrupt_sqlite_items_do_not_hide_valid_main_cache(tmp_path):
    project = tmp_path / "game-project"
    (project / "game" / "tl" / "chinese").mkdir(parents = True)
    paths = RenpyProjectPaths.from_path(project)
    assert paths is not None
    main = paths.translation_output_dir
    delta = main.parent / "chinese_new"
    (main / "cache").mkdir(parents = True)
    (main / "cache" / "items.json").write_text("[]", encoding = "utf-8")
    (main / "cache" / "project.json").write_text("{}", encoding = "utf-8")

    db_path = delta / "cache" / "cache.db"
    db_path.parent.mkdir(parents = True)
    CacheDB(str(db_path)).set_project(CacheProject())
    with sqlite3.connect(db_path) as connection:
        connection.execute("INSERT INTO items (data) VALUES (?)", ("not-json",))
        connection.commit()

    write_run_manifest(paths, delta, run_kind = "incremental")
    config = _config(paths)
    assert resolve_translation_output(config) == main.resolve()


def test_stale_hook_manifest_prefers_stable_caches_before_hook_output(tmp_path):
    project = tmp_path / "game-project"
    (project / "game" / "tl" / "chinese").mkdir(parents = True)
    paths = RenpyProjectPaths.from_path(project)
    assert paths is not None

    main = paths.translation_output_dir
    delta = main.parent / "chinese_new"
    hook = paths.application_target_dir
    for output in (main, delta, hook):
        _write_json_cache(output)

    write_run_manifest(
        paths,
        hook,
        input_folder = hook,
        application_target_dir = hook,
        run_kind = "hook",
    )
    # 模拟 Hook 中途退出：全局配置尚未恢复，仍指向 game/tl/<lang>。
    config = _config(paths, output = hook)

    candidates = translation_output_candidates(config)
    assert candidates[:3] == [main.resolve(), delta.resolve(), hook.resolve()]
    assert resolve_translation_output(config) == main.resolve()
    # 校对页可能记住上一次载入的 Hook 目录；残留 preferred 也不能把
    # 临时 Hook 缓存重新提到稳定缓存之前。
    preferred_candidates = translation_output_candidates(config, preferred = hook)
    assert preferred_candidates[:3] == [main.resolve(), delta.resolve(), hook.resolve()]
    assert resolve_translation_output(config, preferred = hook) == main.resolve()

    # 主缓存不可用时尝试增量缓存；两者都不可用后才允许回退 Hook。
    (main / "cache" / "items.json").unlink()
    assert resolve_translation_output(config) == delta.resolve()
    (delta / "cache" / "items.json").unlink()
    assert resolve_translation_output(config) == hook.resolve()


def test_run_manifest_from_other_project_is_ignored(tmp_path):
    project = tmp_path / "game-project"
    other = tmp_path / "other-project"
    (project / "game" / "tl" / "chinese").mkdir(parents = True)
    (other / "RenpyBox_Translation" / "chinese_new" / "cache").mkdir(parents = True)
    paths = RenpyProjectPaths.from_path(project)
    assert paths is not None

    # 手工写入不匹配的项目键，确保不会跨项目加载。
    manifest = paths.run_manifest_path
    manifest.parent.mkdir(parents = True, exist_ok = True)
    manifest.write_text(
        '{"schema_version": 1, "project_key": "other|chinese", '
        f'"project_root": "{other}", "language": "chinese", '
        f'"output_folder": "{other / "RenpyBox_Translation" / "chinese_new"}"}}',
        encoding = "utf-8",
    )

    config = _config(paths)
    assert read_run_manifest(paths) is None
    assert resolve_translation_output(config) == paths.translation_output_dir.resolve()


def test_run_manifest_from_other_language_is_ignored(tmp_path):
    project = tmp_path / "game-project"
    (project / "game" / "tl" / "chinese").mkdir(parents = True)
    paths = RenpyProjectPaths.from_path(project)
    assert paths is not None
    manifest = paths.run_manifest_path
    manifest.parent.mkdir(parents = True, exist_ok = True)
    manifest.write_text(
        '{"schema_version": 1, '
        f'"project_key": "{paths.project_key}", '
        f'"project_root": "{project}", "language": "chinese", '
        f'"output_folder": "{project / "RenpyBox_Translation" / "english"}"}}',
        encoding = "utf-8",
    )
    assert read_run_manifest(paths) is None


def test_run_manifest_from_other_tl_language_is_ignored(tmp_path):
    project = tmp_path / "game-project"
    (project / "game" / "tl" / "chinese").mkdir(parents = True)
    paths = RenpyProjectPaths.from_path(project)
    assert paths is not None
    manifest = paths.run_manifest_path
    manifest.parent.mkdir(parents = True, exist_ok = True)
    manifest.write_text(
        '{"schema_version": 1, '
        f'"project_key": "{paths.project_key}", '
        f'"project_root": "{project}", "language": "chinese", '
        f'"output_folder": "{project / "game" / "tl" / "english"}"}}',
        encoding = "utf-8",
    )
    assert read_run_manifest(paths) is None


def test_new_and_invalid_language_names_normalize_to_main_language(tmp_path):
    project = tmp_path / "game-project"
    (project / "game" / "tl" / "chinese").mkdir(parents = True)
    paths = RenpyProjectPaths.from_path(project / "game" / "tl" / "chinese_new")
    assert paths is not None
    assert paths.language == "chinese"

    invalid = RenpyProjectPaths.from_path(project / "game" / "tl" / "None")
    assert invalid is not None
    assert invalid.language == "chinese"


def test_current_input_wins_over_missing_stale_project_fields(tmp_path):
    """切换项目后，残留的不存在专用路径不能遮蔽当前输入目录。"""
    current = tmp_path / "current-project"
    (current / "game" / "tl" / "chinese").mkdir(parents = True)

    config = type("ConfigStub", (), {
        "renpy_project_path": str(tmp_path / "removed-project"),
        "renpy_game_folder": str(tmp_path / "removed-project"),
        "renpy_tl_folder": "",
        "input_folder": str(current / "game" / "tl" / "chinese"),
        "output_folder": "",
    })()

    paths = RenpyProjectPaths.from_config(config)

    assert paths is not None
    assert paths.project_root == current.resolve()


def test_current_tl_input_language_overrides_stale_language(tmp_path):
    """新的 tl 输入目录应覆盖旧项目残留的语言字段。"""
    stale = tmp_path / "stale-project"
    current = tmp_path / "current-project"
    (stale / "game" / "tl" / "chinese").mkdir(parents = True)
    # 同时保留另一个语言目录，确保不会因目录枚举顺序误选中文。
    (current / "game" / "tl" / "chinese").mkdir(parents = True)
    (current / "game" / "tl" / "japanese").mkdir(parents = True)
    (current / "game" / "tl" / "japanese_new").mkdir(parents = True)

    config = type("ConfigStub", (), {
        "renpy_project_path": str(stale),
        "renpy_game_folder": str(stale),
        "renpy_tl_folder": str(stale / "game" / "tl" / "chinese"),
        "input_folder": "",
        "output_folder": "",
    })()

    for input_name in ("japanese", "japanese_new"):
        config.input_folder = str(current / "game" / "tl" / input_name)
        paths = RenpyProjectPaths.from_config(config)

        assert paths is not None
        assert paths.project_root == current.resolve()
        assert paths.language == "japanese"
        assert paths.tl_language_dir == (current / "game" / "tl" / "japanese").resolve()


def test_nested_tl_file_input_keeps_language_and_project(tmp_path):
    """选择 tl/<lang> 下的脚本时，不能回退到旧配置语言。"""
    stale = tmp_path / "stale-project"
    current = tmp_path / "current-project"
    (stale / "game" / "tl" / "chinese").mkdir(parents = True)
    script = current / "game" / "tl" / "japanese" / "sub" / "story.rpy"
    script.parent.mkdir(parents = True)
    script.write_text("# test", encoding = "utf-8")

    config = type("ConfigStub", (), {
        "renpy_project_path": str(stale),
        "renpy_game_folder": str(stale),
        "renpy_tl_folder": str(stale / "game" / "tl" / "chinese"),
        "input_folder": str(script),
        "output_folder": "",
    })()

    paths = RenpyProjectPaths.from_config(config)

    assert paths is not None
    assert paths.project_root == current.resolve()
    assert paths.language == "japanese"
    assert paths.tl_language_dir == (current / "game" / "tl" / "japanese").resolve()


def test_missing_tl_language_input_is_not_replaced_by_existing_language(tmp_path):
    """新语言目录尚未创建时，也应保留用户明确选择的目录名。"""
    project = tmp_path / "project"
    (project / "game" / "tl" / "chinese").mkdir(parents = True)
    missing = project / "game" / "tl" / "japanese"
    config = type("ConfigStub", (), {
        "renpy_project_path": str(project),
        "renpy_game_folder": str(project),
        "renpy_tl_folder": str(project / "game" / "tl" / "chinese"),
        "input_folder": str(missing),
        "output_folder": "",
    })()

    paths = RenpyProjectPaths.from_config(config)

    assert paths is not None
    assert paths.language == "japanese"
    assert paths.tl_language_dir == missing.resolve()


def test_explicit_tl_input_wins_over_existing_stale_tl_field(tmp_path):
    """旧 tl 字段仍存在时，明确的新输入也必须优先。"""
    stale = tmp_path / "stale-project"
    current = tmp_path / "current-project"
    (stale / "game" / "tl" / "chinese").mkdir(parents = True)
    (current / "game" / "tl" / "chinese").mkdir(parents = True)
    (current / "game" / "tl" / "japanese_new").mkdir(parents = True)

    config = type("ConfigStub", (), {
        "renpy_project_path": str(current),
        "renpy_game_folder": str(current),
        "renpy_tl_folder": str(stale / "game" / "tl" / "chinese"),
        "input_folder": str(current / "game" / "tl" / "japanese_new"),
        "output_folder": "",
    })()

    paths = RenpyProjectPaths.from_config(config)

    assert paths is not None
    assert paths.project_root == current.resolve()
    assert paths.language == "japanese"
