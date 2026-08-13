"""Agent 后台工作线程。"""

from __future__ import annotations

import threading

from PyQt5.QtCore import QThread, pyqtSignal

from module.Agent.AgentService import AgentService


class AgentWorker(QThread):
    """在后台执行一轮 Agent 会话，避免网络请求阻塞页面。"""

    event = pyqtSignal(str, object)
    finished = pyqtSignal(object)
    confirmation_requested = pyqtSignal(str, object)

    def __init__(
        self,
        service: AgentService,
        message: str,
        thinking_level: str | None = None,
    ) -> None:
        super().__init__()
        self.service = service
        self.message = message
        self.thinking_level = thinking_level
        self._confirmation_event = threading.Event()
        self._confirmation_result: bool | None = None
        self._cancel_event = threading.Event()

    def run(self) -> None:
        result = self.service.run(
            self.message,
            callback=self._on_event,
            confirmation_callback=self._request_confirmation,
            thinking_level=self.thinking_level,
            cancel_event=self._cancel_event,
        )
        self.finished.emit(result)

    def cancel(self) -> None:
        self._cancel_event.set()
        self._confirmation_result = False
        self._confirmation_event.set()
        self.service.cancel()

    def resolve_confirmation(self, approved: bool) -> None:
        if self._cancel_event.is_set():
            return
        self._confirmation_result = bool(approved)
        self._confirmation_event.set()

    def _request_confirmation(self, name: str, payload: dict) -> bool | None:
        self._confirmation_result = None
        self._confirmation_event.clear()
        if self._cancel_event.is_set():
            return False
        self.confirmation_requested.emit(name, payload)
        if not self._confirmation_event.wait(self.service.confirmation_timeout):
            return None
        return self._confirmation_result

    def _on_event(self, event_name: str, payload: dict) -> None:
        self.event.emit(event_name, payload)
