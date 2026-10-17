"""翻译启动票据：并发的第二个 /start 必须在 HTTP 层被挡住。

票据只用来合并「检查状态」与「投递事件」之间的空档，不改变引擎状态——
真正的 IDLE→TRANSLATING 仍由翻译线程在启动临界区内凭票完成。
"""
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes import translation
from module.Config import Config
from module.Engine.Engine import Engine


def _bound_config(tmp_path: Path) -> Config:
    project = tmp_path / "Demo"
    game = project / "game"
    tl = game / "tl" / "chinese"
    tl.mkdir(parents = True)
    (tl / "script.rpy").write_text(
        'translate chinese strings:\n    old "a"\n    new "a"\n',
        encoding = "utf-8",
    )

    config = Config()
    config.renpy_project_path = str(project)
    config.renpy_game_folder = str(game)
    config.renpy_tl_folder = str(tl)
    config.input_folder = str(tl)
    config.output_folder = str(tmp_path / "out")
    return config


@pytest.fixture
def start_app(tmp_path, monkeypatch):
    config = _bound_config(tmp_path)
    # 不读不写真实用户配置。
    monkeypatch.setattr(Config, "load", lambda self, path = None: self)
    monkeypatch.setattr(Config, "save", lambda self, path = None, *, strict = False: self)

    engine = Engine()
    monkeypatch.setattr(Engine, "get", classmethod(lambda cls: engine))

    emitted: list[tuple] = []
    monkeypatch.setattr(
        translation,
        "_emit",
        lambda event, data: emitted.append((event, dict(data))),
    )

    app = FastAPI()
    app.state.config = config
    app.include_router(translation.router)

    return {
        "client": TestClient(app),
        "engine": engine,
        "config": config,
        "emitted": emitted,
    }


def _post_start(client: TestClient, request_id: str):
    return client.post(
        "/api/translation/start",
        json = {"status": "TRANSLATING", "request_id": request_id},
    )


def test_second_start_is_rejected_while_reservation_held(start_app) -> None:
    client = start_app["client"]
    engine = start_app["engine"]
    emitted = start_app["emitted"]

    first = _post_start(client, "a")
    second = _post_start(client, "b")

    assert first.json()["accepted"] is True
    assert second.json()["accepted"] is False
    assert second.json()["reason"] == "ENGINE_BUSY"
    # 被拒的请求不得投递事件。
    assert [data["request_id"] for _, data in emitted] == ["a"]
    # 票据不占状态：引擎仍是 IDLE，真正的占位交给翻译线程。
    assert engine.get_status() == Engine.Status.IDLE
    assert engine.has_translation_reservation() is True


def test_claimed_reservation_moves_engine_to_translating(start_app) -> None:
    client = start_app["client"]
    engine = start_app["engine"]
    emitted = start_app["emitted"]

    _post_start(client, "a")
    reservation = emitted[0][1]["start_reservation"]
    assert reservation

    assert engine.claim_translation_reservation(reservation) is True
    assert engine.get_status() == Engine.Status.TRANSLATING
    # 一次性票据：重复凭票不得二次占位。
    assert engine.claim_translation_reservation(reservation) is False
    assert engine.get_status() == Engine.Status.TRANSLATING


def test_claim_with_foreign_reservation_is_rejected(start_app) -> None:
    client = start_app["client"]
    engine = start_app["engine"]

    _post_start(client, "a")

    assert engine.claim_translation_reservation("not-my-ticket") is False
    assert engine.get_status() == Engine.Status.IDLE
    assert engine.has_translation_reservation() is True


def test_rejected_start_releases_reservation(start_app) -> None:
    client = start_app["client"]
    engine = start_app["engine"]

    bad = client.post("/api/translation/start", json = {"status": "NOT_A_STATUS"})
    assert bad.status_code == 400
    # 400 路径必须归还票据，否则后续启动会被自家人堵住。
    assert engine.has_translation_reservation() is False

    ok = _post_start(client, "c")
    assert ok.json()["accepted"] is True


def test_expired_reservation_does_not_block_start(monkeypatch) -> None:
    engine = Engine()
    monkeypatch.setattr(Engine, "RESERVATION_TTL", 0.0)

    first = engine.reserve_translation()
    assert first
    assert engine.has_translation_reservation() is False
    # 过期票据不拦下一次预占。
    second = engine.reserve_translation()
    assert second
    assert second != first


def test_claim_requires_idle_engine(start_app) -> None:
    client = start_app["client"]
    engine = start_app["engine"]

    _post_start(client, "a")
    reservation = engine.start_reservation

    # 票据有效期内被别的任务占走状态：凭票也不得强占。
    engine.set_status(Engine.Status.TESTING)
    assert engine.claim_translation_reservation(reservation) is False
    assert engine.get_status() == Engine.Status.TESTING
    # 票据已销毁，不再挂在引擎上。
    assert engine.has_translation_reservation() is False
