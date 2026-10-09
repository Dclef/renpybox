"""更新 API：状态查询与动作触发（VersionManager 用替身，不访问 GitHub）。"""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes import update
from base.Base import Base
from base.VersionManager import VersionManager


class FakeManager:
    Status = VersionManager.Status

    def __init__(self):
        self.status = VersionManager.Status.NONE
        self.version = "0.8.1"
        self.latest = {}
        self.downloaded_size = 0
        self.total_size = 0
        self.error = ""
        self.events = []
        self._download_active = False

    def get_update_state(self):
        return {
            "status": self.status,
            "version": self.version,
            "latest": dict(self.latest),
            "downloaded_size": self.downloaded_size,
            "total_size": self.total_size,
            "error": self.error,
        }

    def get_version(self):
        return self.version

    def emit(self, event, data=None):
        self.events.append((event, data or {}))
        if event == Base.Event.APP_UPDATE_CHECK_START:
            self.latest = {"tag_name": "v0.9.0", "body": "fixture"}
            self.status = VersionManager.Status.NEW_VERSION
        elif event == Base.Event.APP_UPDATE_DOWNLOAD_START:
            self.status = VersionManager.Status.UPDATING
            self._download_active = True
            self.downloaded_size = 10
            self.total_size = 100
        elif event == Base.Event.APP_UPDATE_DOWNLOAD_CANCEL:
            self.status = VersionManager.Status.NEW_VERSION
            self._download_active = False
        elif event == Base.Event.APP_UPDATE_EXTRACT:
            self.status = VersionManager.Status.NONE

    def cancel_download(self):
        if not self._download_active:
            return False
        self._download_active = False
        self.status = VersionManager.Status.NEW_VERSION
        return True


@pytest.fixture
def update_client():
    app = FastAPI()
    app.include_router(update.router)
    manager = FakeManager()
    app.state.version_manager = manager
    with TestClient(app) as client:
        yield SimpleNamespace(client=client, manager=manager)


def test_get_update_state_and_check(update_client):
    client = update_client.client
    manager = update_client.manager

    empty = client.get("/api/update").json()
    assert empty["status"] == "NONE"
    assert empty["new_version"] is False

    checked = client.post("/api/update/check", json={"manual": True}).json()
    assert checked["status"] == "NEW_VERSION"
    assert checked["new_version"] is True
    assert checked["latest"]["tag_name"] == "v0.9.0"
    assert manager.events[0][0] == Base.Event.APP_UPDATE_CHECK_START


def test_download_cancel_and_install(update_client):
    client = update_client.client
    manager = update_client.manager

    assert client.post("/api/update/download").status_code == 400
    client.post("/api/update/check", json={"manual": True})

    downloading = client.post("/api/update/download").json()
    assert downloading["status"] == "UPDATING"

    cancelled = client.post("/api/update/cancel").json()
    assert cancelled["status"] == "NEW_VERSION"

    manager.status = VersionManager.Status.DOWNLOADED
    installed = client.post("/api/update/install").json()
    assert installed["ok"] is True
    assert any(event == Base.Event.APP_UPDATE_EXTRACT for event, _ in manager.events)


def test_changelog_endpoint(update_client):
    body = update_client.client.get("/api/update/changelog").json()
    assert "markdown" in body
    assert "empty" in body
