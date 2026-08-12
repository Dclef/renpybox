"""Agent 后台工作线程。"""

from __future__ import annotations

from PyQt5.QtCore import QThread, pyqtSignal

from module.Agent.AgentService import AgentService


class AgentWorker(QThread):
    """在后台执行一轮 Agent 会话，避免网络请求阻塞页面。"""

    event = pyqtSignal(str, object)
    finished = pyqtSignal(object)

    def __init__(self, service: AgentService, message: str) -> None:
        super().__init__()
        self.service = service
        self.message = message

    def run(self) -> None:
        result = self.service.run(self.message, callback=self._on_event)
        self.finished.emit(result)

    def cancel(self) -> None:
        self.service.cancel()

    def _on_event(self, event_name: str, payload: dict) -> None:
        self.event.emit(event_name, payload)
