"""工程文件绑定回归：自动创建真正落地、切换工程不残留旧绑定、解绑后可再次导入。"""

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes import project
from base.Base import Base
from base.BaseLanguage import BaseLanguage
from module.Cache.CacheItem import CacheItem
from module.Cache.CacheProject import CacheProject
from module.Config import Config
from module.Engine.Engine import Engine
from module.Project.ProjectFile import ProjectFile


@pytest.fixture(autouse = True)
def fresh_engine(monkeypatch) -> Engine:
    engine = Engine()
    monkeypatch.setattr(Engine, "__instance__", engine, raising = False)
    return engine


@pytest.fixture
def config(tmp_path: Path) -> Config:
    value = Config()
    value.input_folder = str(tmp_path / "input")
    value.output_folder = str(tmp_path / "output")
    value.renpy_project_path = value.renpy_game_folder = value.renpy_tl_folder = ""
    value.project_file_path = value.project_file_output = ""
    value.target_language = BaseLanguage.Enum.ZH
    value.max_workers = 16
    value.platforms = [{"id": 0, "name": "demo", "api_key": ["sk-live"]}]
    value.save(strict = True)
    return value


def _project_root(tmp_path: Path, name: str) -> Path:
    root = tmp_path / name
    game = root / "game"
    (game / "tl" / "chinese").mkdir(parents = True)
    (game / "script.rpy").write_text("label start:\n", encoding = "utf-8")
    return root


def _client(config: Config) -> TestClient:
    app = FastAPI()
    app.include_router(project.router)
    app.state.config = config
    return TestClient(app)


def _items(*texts: str) -> list[CacheItem]:
    return [
        CacheItem(
            src = text,
            dst = f"{text}-译",
            file_path = "game/script.rpy",
            row = index,
            status = Base.TranslationStatus.TRANSLATED,
        )
        for index, text in enumerate(texts, 1)
    ]


def _rbox(path: Path, *, project_root: Path, items = None) -> Path:
    path.parent.mkdir(parents = True, exist_ok = True)
    ProjectFile.export(
        path,
        CacheProject(id = "seeded"),
        _items("keep-1") if items is None else items,
        project_root = str(project_root),
        settings = {},
        app_version = "test",
    )
    return path


def _binding(config: Config) -> dict:
    with _client(config) as client:
        response = client.get("/api/project/file/binding")
    assert response.status_code == 200, response.text
    return response.json()


def test_resolve_auto_creates_rbox_in_project_root(tmp_path, config, fresh_engine) -> None:
    """绑定工程后默认 .rbox 直接落在项目根，不再套 RenpyBox_Translation/<语言>。"""
    root = _project_root(tmp_path, "MyGame")
    with _client(config) as client:
        response = client.post("/api/project/resolve", json = {"path": str(root)})
    assert response.status_code == 200, response.text
    body = response.json()
    target = root / "MyGame.rbox"
    assert Path(body["auto_created_project_file"]) == target
    assert body["auto_create_error"] == ""
    assert target.is_file()
    assert Path(config.project_file_path) == target
    assert Path(config.project_file_output) == root / "RenpyBox_Translation" / "chinese"
    payload = _binding(config)
    assert payload["bound"] is True
    assert Path(payload["path"]) == target
    assert payload["exists"] is True
    assert Path(payload["default_path"]) == target
    assert "RenpyBox_Translation" not in payload["default_path"]
    assert fresh_engine.get_status() == Engine.Status.IDLE


def test_resolve_binds_existing_default_rbox_instead_of_failing(tmp_path, config, fresh_engine) -> None:
    """默认位置已经有上次留下的 .rbox：直接绑定它，不能报「已存在」又留着旧绑定。"""
    root = _project_root(tmp_path, "Chp3")
    target = _rbox(root / "Chp3.rbox", project_root = root)
    with _client(config) as client:
        response = client.post("/api/project/resolve", json = {"path": str(root)})
    assert response.status_code == 200, response.text
    body = response.json()
    assert Path(body["auto_created_project_file"]) == target
    assert body["auto_create_error"] == ""
    assert Path(config.project_file_path) == target
    assert [item.get_src() for item in ProjectFile.load(target).items] == ["keep-1"]
    payload = _binding(config)
    assert payload["bound"] is True
    assert payload["exists"] is True


def test_switch_project_rebinds_and_keeps_old_rbox(tmp_path, config, fresh_engine) -> None:
    """Chp2 → Chp3：新工程拿到新绑定，旧 .rbox 保留，配置里不残留旧路径。"""
    old_root = _project_root(tmp_path, "Chp2")
    with _client(config) as client:
        assert client.post("/api/project/resolve", json = {"path": str(old_root)}).status_code == 200
    old_rbox = old_root / "Chp2.rbox"
    assert old_rbox.is_file()

    new_root = _project_root(tmp_path, "Chp3")
    with _client(config) as client:
        response = client.post("/api/project/resolve", json = {"path": str(new_root)})
    assert response.status_code == 200, response.text
    new_rbox = new_root / "Chp3.rbox"
    assert Path(response.json()["auto_created_project_file"]) == new_rbox
    assert Path(config.project_file_path) == new_rbox
    assert Path(config.project_file_output) == new_root / "RenpyBox_Translation" / "chinese"
    assert "Chp2" not in str(Config().load().project_file_path)
    assert old_rbox.is_file(), "旧工程文件必须保留"
    payload = _binding(config)
    assert Path(payload["path"]) == new_rbox
    assert payload["bound"] is True


def test_unbind_then_import_same_rbox_binds_again(tmp_path, config, fresh_engine) -> None:
    """解除绑定后再导入刚解绑的 .rbox：不能报「找不到工程文件」。"""
    root = _project_root(tmp_path, "MyGame")
    with _client(config) as client:
        assert client.post("/api/project/resolve", json = {"path": str(root)}).status_code == 200
    target = root / "MyGame.rbox"
    assert target.is_file()

    with _client(config) as client:
        unbound = client.post("/api/project/file/unbind")
        assert unbound.status_code == 200, unbound.text
        assert unbound.json()["bound"] is False
        again = client.post("/api/project/file/import", json = {"path": str(target), "bind": True})
    assert again.status_code == 200, again.text
    assert again.json()["bound"] is True
    assert Path(again.json()["project_file_path"]) == target
    assert Path(config.project_file_path) == target
    payload = _binding(config)
    assert payload["bound"] is True
    assert payload["exists"] is True


def test_unbind_reports_unbound_and_keeps_snapshot(tmp_path, config, fresh_engine) -> None:
    """解绑后 /file/binding 必须明确 bound=false，且快照文件留着。"""
    root = _project_root(tmp_path, "MyGame")
    with _client(config) as client:
        assert client.post("/api/project/resolve", json = {"path": str(root)}).status_code == 200
        target = root / "MyGame.rbox"
        assert client.post("/api/project/file/unbind").status_code == 200
    payload = _binding(config)
    assert payload["bound"] is False
    assert payload["path"] == ""
    assert payload["exists"] is False
    assert target.is_file()
    assert Path(payload["default_path"]) == target


def test_stale_binding_from_other_project_is_ignored(tmp_path, config, fresh_engine) -> None:
    """旧工程残留绑定（作用域与当前输出不符）不得显示为已绑定。"""
    old_root = _project_root(tmp_path, "Chp2")
    old_rbox = _rbox(old_root / "Chp2.rbox", project_root = old_root)
    new_root = _project_root(tmp_path, "Chp3")
    config.renpy_project_path = str(new_root)
    config.renpy_game_folder = str(new_root)
    config.renpy_tl_folder = str(new_root / "game" / "tl" / "chinese")
    config.input_folder = str(new_root / "game" / "tl" / "chinese")
    config.output_folder = str(new_root / "RenpyBox_Translation" / "chinese")
    config.project_file_path = str(old_rbox)
    config.project_file_output = str(old_root / "RenpyBox_Translation" / "chinese")
    config.save(strict = True)

    payload = _binding(config)
    assert payload["bound"] is False
    assert payload["path"] == ""

    with _client(config) as client:
        response = client.post("/api/project/resolve", json = {"path": str(new_root)})
    assert response.status_code == 200, response.text
    assert Path(config.project_file_path) == new_root / "Chp3.rbox"
    assert old_rbox.is_file()
