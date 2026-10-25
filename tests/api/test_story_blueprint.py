"""剧情蓝图：扫描口径（真实进度/占位/控制流）与接口、asset 安全规则。"""

import base64
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.routes import story_blueprint
from module.Config import Config
from module.Story.BlueprintScanner import read_label, scan
from module.Story.SceneImageIndex import SceneImageIndex, clear_indexes
from module.Story.TranslationIndex import TranslationIndex

# 1x1 PNG，够 asset 接口校验 content-type。
_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)

SCRIPT = """\
label start:
    scene bg room
    e "Hello there"
    menu:
        "Go out":
            jump outside
        "Stay":
            jump ending

label outside:
    scene bg street
    e "It is dark"
    jump ending

label ending:
    scene black
    e "The end"
    return
"""

TL_SCRIPT = """\
translate chinese start_aaaaaaaa:
    # e "Hello there"
    e "你好"

translate chinese outside_bbbbbbbb:
    # e "It is dark"
    e "It is dark"

translate chinese strings:
    old "Go out"
    new "外出"

translate chinese strings:
    old "Stay"
    new "留下"
"""


def _make_project(tmp_path: Path) -> dict:
    game = tmp_path / "game"
    (game / "images" / "bg").mkdir(parents=True)
    (game / "images" / "bg" / "room.webp").write_bytes(_PNG)
    (game / "images" / "bg" / "street.webp").write_bytes(_PNG)
    (game / "script.rpy").write_text(SCRIPT, encoding="utf-8")
    tl = game / "tl" / "chinese"
    tl.mkdir(parents=True)
    (tl / "script.rpy").write_text(TL_SCRIPT, encoding="utf-8")
    return {
        "project_root": tmp_path,
        "game_dir": game,
        "tl_dir": tl,
        "language": "chinese",
    }


def _nodes(result: dict) -> dict:
    return {node["id"]: node for node in result["nodes"]}


def test_scan_reports_real_progress_and_placeholders(tmp_path):
    project = _make_project(tmp_path)
    clear_indexes()

    result = scan(project["game_dir"], project["tl_dir"], "chinese")
    nodes = _nodes(result)

    # 真中文：start 有 1 行中文；outside 的译文是英文原文（占位）；ending 没有 tl 块。
    assert nodes["start"]["zh"] == 1
    assert nodes["start"]["status"] == "done"
    assert nodes["outside"]["zh"] == 0
    assert nodes["outside"]["tl_blocks"] == 1
    assert nodes["outside"]["placeholder"] is True
    assert nodes["ending"]["tl_blocks"] == 0
    assert nodes["ending"]["placeholder"] is False

    assert result["stats"] == {
        "chapters": 1,
        "labels": 3,
        "say_lines": 3,
        "zh_lines": 1,
        "cache_lines": 0,
        "translated_labels": 0,
        "labels_with_image": 2,
        "edges": 3,
        "menu_edges": 2,
        "jump_edges": 1,
        "placeholder_labels": 1,
        "progress_source": "tl",
    }
    assert result["chapters"] == [
        {
            "id": "script",
            "file": "script.rpy",
            "labels": 3,
            "say": 3,
            "zh": 1,
            "cache_zh": 0,
            "progress": 1,
        }
    ]


def test_scan_keeps_menu_option_text_and_drops_unknown_targets(tmp_path):
    project = _make_project(tmp_path)
    clear_indexes()

    result = scan(project["game_dir"], project["tl_dir"], "chinese")
    menu_edges = {
        (edge["from"], edge["to"]): edge
        for edge in result["edges"]
        if edge["kind"] == "menu"
    }

    assert menu_edges[("start", "outside")]["option_src"] == "Go out"
    assert menu_edges[("start", "outside")]["option_zh"] == "外出"
    assert menu_edges[("start", "ending")]["option_zh"] == "留下"
    # `return` 和「jump 到不存在的 label」都不画边。
    assert [edge["kind"] for edge in result["edges"]].count("jump") == 1


def test_scan_title_uses_translation_comment_and_scene_image(tmp_path):
    project = _make_project(tmp_path)
    clear_indexes()

    nodes = _nodes(scan(project["game_dir"], project["tl_dir"], "chinese"))
    assert nodes["start"]["title_src"] == "Hello there"
    assert nodes["start"]["title_zh"] == "你好"
    # outside 的 new 是英文原文，不能拿来当标题。
    assert nodes["outside"]["title_zh"] is None
    assert nodes["start"]["image"]["path"] == "images/bg/room.webp"
    # 画面来源写清楚：这张是 scene 背景，不是 show 兜底图。
    assert nodes["start"]["image"]["source"] == "scene"
    # scene black 是颜色不是文件，按解析失败处理。
    assert nodes["ending"]["image"] is None


SHOW_SCRIPT = """\
label showonly:
    scene black
    show cap1
    e "One"
    show cap2
    e "Two"
    return

label scene_first:
    scene bg room
    show cap1
    e "Hi"
    return

label hidden:
    show cap1
    hide cap1
    e "Gone"
    return

label interface:
    show screen hud
    show expression "images/logo.png"
    e "UI"
    return
"""


def _make_show_project(tmp_path: Path) -> dict:
    """scene 全是黑场、画面全靠 show 的工程（真实欧美 galgame 的常见形态）。"""
    project = _make_project(tmp_path)
    game = project["game_dir"]
    for name in ("cap1", "cap2"):
        (game / "images" / f"{name}.jpg").write_bytes(_PNG)
    (game / "script.rpy").write_text(SHOW_SCRIPT, encoding="utf-8")
    return project


def test_scan_falls_back_to_show_when_scene_is_black(tmp_path):
    project = _make_show_project(tmp_path)
    clear_indexes()

    nodes = _nodes(scan(project["game_dir"], project["tl_dir"], "chinese"))

    # scene 只有黑场：退回 label 结束时还在显示的 show 图（cap2 是最后一张）。
    assert nodes["showonly"]["image"]["path"] == "images/cap2.jpg"
    assert nodes["showonly"]["image"]["source"] == "show"
    assert nodes["showonly"]["show_image_count"] == 2

    # scene 能落到文件时仍然优先，show 只作为兜底。
    assert nodes["scene_first"]["image"]["path"] == "images/bg/room.webp"
    assert nodes["scene_first"]["image"]["source"] == "scene"
    assert nodes["scene_first"]["show_image_count"] == 1

    # hide 之后的 show 不算「label 结束时观众看到的画面」。
    assert nodes["hidden"]["image"] is None
    assert nodes["hidden"]["show_image_count"] == 0

    # show screen / show expression 是界面与内联表达式，不是按标签找文件。
    assert nodes["interface"]["image"] is None
    assert nodes["interface"]["show_image_count"] == 0


def test_read_label_reports_same_show_fallback(tmp_path):
    project = _make_show_project(tmp_path)
    clear_indexes()

    detail = read_label(project["game_dir"], "script", "showonly")

    assert detail["image"]["path"] == "images/cap2.jpg"
    assert detail["image"]["source"] == "show"
    assert detail["show_image_count"] == 2
    # 详情和画布必须一致：hide 掉的图在详情里也不能冒出来。
    hidden = read_label(project["game_dir"], "script", "hidden")
    assert hidden["image"] is None
    assert hidden["show_image_count"] == 0


def test_show_image_source_survives_blueprint_endpoint(tmp_path):
    project = _make_show_project(tmp_path)
    clear_indexes()

    response = _client(_bound_config(project)).get("/api/story-blueprint")

    assert response.status_code == 200
    nodes = {node["id"]: node for node in response.json()["nodes"]}
    assert nodes["showonly"]["image"]["source"] == "show"
    assert nodes["showonly"]["show_image_count"] == 2
    assert nodes["scene_first"]["image"]["source"] == "scene"


def test_scene_image_index_resolves_files_definitions_and_conditions(tmp_path):
    game = tmp_path / "game"
    (game / "images").mkdir(parents=True)
    (game / "images" / "hall.webp").write_bytes(_PNG)
    (game / "script.rpy").write_text(
        'image bg hall = "images/hall.webp"\n'
        'image side eileen = ConditionSwitch("side eileen smile.webp", "True")\n',
        encoding="utf-8",
    )
    index = SceneImageIndex(game)

    assert index.resolve("bg hall")["path"] == "images/hall.webp"
    condition = index.resolve("side eileen")
    assert condition["note"] == "条件分支，按默认分支推测"
    # 文件索引兜底：整串找不到时按「分类 名字」丢前缀。
    assert index.resolve("bg hall night")["path"] == "images/hall.webp"
    assert index.resolve("black") is None


def _client(config: Config) -> TestClient:
    app = FastAPI()
    app.include_router(story_blueprint.router)
    app.state.config = config
    return TestClient(app)


def _bound_config(project: dict) -> Config:
    config = Config()
    config.renpy_project_path = str(project["project_root"])
    config.renpy_game_folder = ""
    config.renpy_tl_folder = ""
    config.input_folder = ""
    config.output_folder = ""
    return config


def test_blueprint_endpoint_returns_contract(tmp_path):
    project = _make_project(tmp_path)
    client = _client(_bound_config(project))

    response = client.get("/api/story-blueprint")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["project"]["language"] == "chinese"
    assert payload["stats"]["labels"] == 3
    assert {node["id"] for node in payload["nodes"]} == {"start", "outside", "ending"}


def test_blueprint_endpoint_requires_bound_project(tmp_path):
    config = Config()
    config.renpy_project_path = ""
    config.renpy_game_folder = ""
    config.renpy_tl_folder = ""
    config.input_folder = ""
    config.output_folder = ""

    response = _client(config).get("/api/story-blueprint")

    assert response.status_code == 409


def test_readiness_reports_ready_for_unpacked_project(tmp_path):
    project = _make_project(tmp_path)

    payload = _client(_bound_config(project)).get("/api/story-blueprint/readiness").json()

    assert payload["stage"] == "ready"
    assert payload["rpy_files"] == 1
    assert payload["rpa_files"] == 0
    assert payload["has_tl"] is True
    assert payload["language"] == "chinese"


def test_readiness_reports_unbound_without_project():
    config = Config()
    config.renpy_project_path = ""
    config.renpy_game_folder = ""
    config.renpy_tl_folder = ""
    config.input_folder = ""
    config.output_folder = ""

    payload = _client(config).get("/api/story-blueprint/readiness").json()

    assert payload["stage"] == "unbound"
    assert payload["rpy_files"] == 0


def test_readiness_reports_packed_when_only_archives(tmp_path):
    """打包过的游戏没有 .rpy：必须判成 packed，前端才会引导去解包。"""
    game = tmp_path / "game"
    game.mkdir(parents=True)
    (game / "archive.rpa").write_bytes(b"RPA-3.0 fake")
    project = {
        "project_root": tmp_path,
        "game_dir": game,
        "tl_dir": game / "tl" / "chinese",
        "language": "chinese",
    }

    payload = _client(_bound_config(project)).get("/api/story-blueprint/readiness").json()

    assert payload["stage"] == "packed"
    assert payload["rpa_files"] == 1
    assert payload["rpy_files"] == 0
    assert payload["has_tl"] is False


def test_readiness_reports_no_script_for_empty_game_folder(tmp_path):
    game = tmp_path / "game"
    (game / "images").mkdir(parents=True)
    project = {
        "project_root": tmp_path,
        "game_dir": game,
        "tl_dir": game / "tl" / "chinese",
        "language": "chinese",
    }

    payload = _client(_bound_config(project)).get("/api/story-blueprint/readiness").json()

    assert payload["stage"] == "no_script"


def test_readiness_ignores_rpy_under_tl_and_cache(tmp_path):
    """tl/ 与 cache/ 下的 .rpy 是译文或缓存，不算「有脚本源码」。"""
    project = _make_project(tmp_path)
    game = project["game_dir"]
    (game / "script.rpy").unlink()
    (game / "cache").mkdir()
    (game / "cache" / "bytecode.rpy").write_text("label x:\n    pass\n", encoding="utf-8")

    payload = _client(_bound_config(project)).get("/api/story-blueprint/readiness").json()

    assert payload["rpy_files"] == 0
    assert payload["stage"] == "no_script"


def test_asset_endpoint_serves_images_and_rejects_unsafe_paths(tmp_path):
    project = _make_project(tmp_path)
    client = _client(_bound_config(project))

    ok = client.get("/api/story-blueprint/asset", params={"path": "images/bg/room.webp"})
    assert ok.status_code == 200
    assert ok.headers["content-type"] == "image/webp"

    traversal = client.get("/api/story-blueprint/asset", params={"path": "../secret.webp"})
    assert traversal.status_code == 400

    script = client.get("/api/story-blueprint/asset", params={"path": "script.rpy"})
    assert script.status_code == 403

    missing = client.get("/api/story-blueprint/asset", params={"path": "images/none.webp"})
    assert missing.status_code == 404


@pytest.mark.parametrize("language", ["chinese"])
def test_scan_handles_missing_tl_dir(tmp_path, language):
    game = tmp_path / "game"
    game.mkdir()
    (game / "script.rpy").write_text('label start:\n    e "Hi"\n', encoding="utf-8")

    result = scan(game, tmp_path / "game" / "tl" / language, language)

    assert result["stats"]["labels"] == 1
    assert result["stats"]["zh_lines"] == 0
    assert result["nodes"][0]["status"] == "todo"


def test_scan_merges_cache_translations_as_real_progress(tmp_path):
    project = _make_project(tmp_path)
    clear_indexes()
    translations = TranslationIndex(
        {
            ("script.rpy", "Hello there"): ("你好呀",),
            ("script.rpy", "It is dark"): ("天黑了",),
        }
    )

    result = scan(project["game_dir"], project["tl_dir"], "chinese", translations.fork())
    nodes = _nodes(result)

    # 缓存里有译文才是「真的翻过」：outside 在 tl 里是英文占位，但缓存有中文。
    assert nodes["start"]["cache_zh"] == 1
    assert nodes["start"]["status"] == "done"
    assert nodes["outside"]["cache_zh"] == 1
    assert nodes["outside"]["status"] == "done"
    assert nodes["outside"]["placeholder"] is False
    assert nodes["ending"]["status"] == "todo"
    assert nodes["start"]["title_zh"] == "你好呀"
    assert result["stats"]["cache_lines"] == 2
    assert result["stats"]["translated_labels"] == 2
    assert result["stats"]["progress_source"] == "cache"
    assert result["chapters"][0]["cache_zh"] == 2


def test_scan_counts_repeated_source_lines_once_each(tmp_path):
    game = tmp_path / "game"
    game.mkdir()
    (game / "script.rpy").write_text(
        'label talk:\n    e "Same"\n    e "Same"\n    e "Same"\n',
        encoding="utf-8",
    )
    translations = TranslationIndex({("script.rpy", "Same"): ("一样", "一样", "一样")})

    result = scan(game, game / "tl" / "chinese", "chinese", translations.fork())

    assert result["nodes"][0]["cache_zh"] == 3
    assert result["nodes"][0]["status"] == "done"


def test_read_label_returns_line_level_translations(tmp_path):
    project = _make_project(tmp_path)
    clear_indexes()
    translations = TranslationIndex({("script.rpy", "Hello there"): ("你好呀",)})

    detail = read_label(project["game_dir"], "script", "start", translations.fork())

    assert detail is not None
    assert detail["say"] == 1
    assert detail["cache_zh"] == 1
    assert detail["status"] == "done"
    assert detail["lines"] == [
        {
            "line": 3,
            "speaker": "e",
            "src": "Hello there",
            "dst": "你好呀",
            "status": "done",
        }
    ]


def test_label_endpoint_returns_lines_and_404s_unknown_label(tmp_path):
    project = _make_project(tmp_path)
    client = _client(_bound_config(project))

    response = client.get("/api/story-blueprint/label", params={"chapter": "script", "id": "start"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert [line["src"] for line in payload["lines"]] == ["Hello there"]
    # 没绑缓存时只能看 tl：这里是真中文，但接口不读 tl，逐行译文为空。
    assert payload["lines"][0]["dst"] is None

    missing = client.get("/api/story-blueprint/label", params={"chapter": "script", "id": "nope"})
    assert missing.status_code == 404
