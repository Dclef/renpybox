"""``POST /api/project/resolve`` 的项目绑定副作用。

覆盖 Electron 端缺失的两项 Qt5 行为：
  * 按真实 ``tl/<lang>`` 目录推断 ``target_language``（frontend/Project/ProjectPage.py:151-153）
  * 绑定后创建输出目录（frontend/Project/ProjectPage.py:215）
"""

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes import project
from base.BaseLanguage import BaseLanguage
from module.Config import Config
from module.Renpy.ProjectPaths import guess_language_from_folder_name


def _client(config: Config) -> TestClient:
    app = FastAPI()
    app.include_router(project.router)
    app.state.config = config
    return TestClient(app)


def _config() -> Config:
    return Config()


def test_resolve_infers_target_language_from_real_tl_folder(tmp_path: Path) -> None:
    """Qt5 会在绑定时按 tl/<lang> 改写 target_language；API 必须一致。"""
    game = tmp_path / "MyGame" / "game"
    (game / "tl" / "japanese").mkdir(parents = True)
    (game / "script.rpy").write_text("label start:\n", encoding = "utf-8")
    config = _config()
    assert config.target_language != BaseLanguage.Enum.JA

    with _client(config) as client:
        response = client.post(
            "/api/project/resolve",
            json = {"path": str(tmp_path / "MyGame")},
        )

    assert response.status_code == 200
    assert config.target_language == BaseLanguage.Enum.JA
    assert config.renpy_tl_folder == str(game / "tl" / "japanese")
    # 路径解析出的语言目录名与推断结果一致（Qt5 用同一映射表）。
    assert guess_language_from_folder_name(Path(config.renpy_tl_folder).name) == BaseLanguage.Enum.JA


def test_resolve_keeps_target_language_when_no_language_folder_is_detected(tmp_path: Path) -> None:
    """推不出真实 ``tl/<lang>`` 时保留用户当前选择（Qt5 语义）。"""
    game = tmp_path / "MyGame" / "game"
    (game / "tl" / "esperanto").mkdir(parents = True)
    (game / "script.rpy").write_text("label start:\n", encoding = "utf-8")
    config = _config()
    config.target_language = BaseLanguage.Enum.JA
    config.renpy_project_path = str(tmp_path / "MyGame")
    config.renpy_game_folder = str(game)
    config.renpy_tl_folder = ""
    config.input_folder = ""
    config.output_folder = ""
    config.save(strict = True)

    with _client(config) as client:
        response = client.post("/api/project/resolve", json = {"path": str(tmp_path / "MyGame")})

    assert response.status_code == 200
    assert config.renpy_tl_folder == str(game / "tl" / "esperanto")
    # esperanto 不在语言映射表里，且没有其它已知 tl 目录 → 不动用户选择。
    assert config.target_language == BaseLanguage.Enum.JA


def test_resolve_creates_missing_output_folder(tmp_path: Path) -> None:
    """绑定项目后 RenpyBox_Translation/<lang> 必须存在，否则首个任务直接失败。"""
    game = tmp_path / "MyGame" / "game"
    (game / "tl" / "chinese").mkdir(parents = True)
    config = _config()
    config.renpy_project_path = ""
    config.renpy_game_folder = ""
    config.renpy_tl_folder = ""
    config.input_folder = ""
    config.output_folder = ""
    expected = tmp_path / "MyGame" / "RenpyBox_Translation" / "chinese"
    assert not expected.exists()

    with _client(config) as client:
        assert client.post("/api/project/resolve", json = {"path": str(tmp_path / "MyGame")}).status_code == 200

    assert config.output_folder == str(expected)
    assert expected.is_dir()


def test_resolve_keeps_existing_custom_output_folder_and_creates_it(tmp_path: Path) -> None:
    """用户自选输出目录原样保留，同样按需创建（Qt5 语义）。"""
    game = tmp_path / "MyGame" / "game"
    (game / "tl" / "chinese").mkdir(parents = True)
    custom = tmp_path / "MyOwnOutput"
    config = _config()
    config.output_folder = str(custom)

    with _client(config) as client:
        assert client.post("/api/project/resolve", json = {"path": str(game)}).status_code == 200

    assert config.output_folder == str(custom)
    assert custom.is_dir()


def test_resolve_ignores_output_folder_mkdir_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """mkdir 失败不能影响绑定响应：路径照写，接口仍返回 200。"""
    game = tmp_path / "MyGame" / "game"
    (game / "tl" / "chinese").mkdir(parents = True)
    blocked = tmp_path / "Blocked"
    blocked.write_text("not a folder", encoding = "utf-8")
    config = _config()
    config.output_folder = str(blocked)

    logged: list[str] = []
    from base import LogManager as log_manager_module

    monkeypatch.setattr(
        log_manager_module.LogManager,
        "warning",
        lambda self, msg, e = None, file = True, console = True: logged.append(f"{msg} {e}"),
    )

    with _client(config) as client:
        response = client.post("/api/project/resolve", json = {"path": str(game)})

    assert response.status_code == 200
    assert config.output_folder == str(blocked)
    assert blocked.is_file()
    assert logged, "mkdir 失败应写入日志"


def test_resolve_french_despite_misleading_english_parent(tmp_path: Path) -> None:
    """父路径含 english 时仍只看 tl/<lang> basename；french 不得误判 EN。"""
    # 父目录名故意带 english，旧子串逻辑会误判。
    game = tmp_path / "english_studio" / "MyGame" / "game"
    (game / "tl" / "french").mkdir(parents = True)
    (game / "script.rpy").write_text("label start:\n", encoding = "utf-8")
    config = _config()
    config.target_language = BaseLanguage.Enum.JA

    with _client(config) as client:
        response = client.post(
            "/api/project/resolve",
            json = {"path": str(tmp_path / "english_studio" / "MyGame")},
        )

    assert response.status_code == 200
    assert config.target_language == BaseLanguage.Enum.FR
    assert Path(config.renpy_tl_folder).name == "french"


def test_resolve_keeps_target_when_tl_language_missing(tmp_path: Path) -> None:
    """tl/<lang> 尚未创建时不得改写 target_language。"""
    game = tmp_path / "MyGame" / "game"
    game.mkdir(parents = True)
    (game / "script.rpy").write_text("label start:\n", encoding = "utf-8")
    # 仅有空 tl 根，没有语言子目录；from_path 会落到默认 chinese 名但目录不存在。
    (game / "tl").mkdir()
    config = _config()
    config.target_language = BaseLanguage.Enum.KO

    with _client(config) as client:
        response = client.post("/api/project/resolve", json = {"path": str(tmp_path / "MyGame")})

    assert response.status_code == 200
    assert config.target_language == BaseLanguage.Enum.KO


def test_resolve_unknown_tl_folder_keeps_existing_target(tmp_path: Path) -> None:
    """未知语言目录名（如 weekend）保留用户当前 target_language。"""
    game = tmp_path / "MyGame" / "game"
    (game / "tl" / "weekend").mkdir(parents = True)
    (game / "script.rpy").write_text("label start:\n", encoding = "utf-8")
    config = _config()
    config.target_language = BaseLanguage.Enum.DE

    with _client(config) as client:
        assert client.post("/api/project/resolve", json = {"path": str(tmp_path / "MyGame")}).status_code == 200

    assert config.target_language == BaseLanguage.Enum.DE
    assert Path(config.renpy_tl_folder).name == "weekend"
