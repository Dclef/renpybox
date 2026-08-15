"""Agent 后台工作线程。"""

from __future__ import annotations

import threading

from PyQt5.QtCore import QThread, pyqtSignal

from module.Agent.AgentService import AgentService


class AgentWorker(QThread):
    """在后台执行一轮 Agent 会话，避免网络请求阻塞页面。"""

    # 不能命名为 event/finished：与 QThread 的 C++ 内建符号冲突，
    # 线程对象销毁时会触发 "native Qt signal is not callable" 崩溃。
    agent_event = pyqtSignal(str, object)
    completed = pyqtSignal(object)
    confirmation_requested = pyqtSignal(str, object)

    def __init__(
        self,
        service: AgentService,
        message: str,
        thinking_level: str | None = None,
        auto_confirm_unpack: bool = False,
    ) -> None:
        super().__init__()
        self.service = service
        self.message = message
        self.thinking_level = thinking_level
        self._auto_confirm_unpack = bool(auto_confirm_unpack)
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
        self.completed.emit(result)

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
        # 用户勾选「不再询问」后，解包确认直接放行；
        # 服务端仍会核对确认上下文快照，项目变化时照样拒绝执行。
        if self._auto_confirm_unpack and name == "unpack_rpa_files":
            self._auto_confirm_unpack = False
            return True
        self.confirmation_requested.emit(name, payload)
        if not self._confirmation_event.wait(self.service.confirmation_timeout):
            return None
        return self._confirmation_result

    def _on_event(self, event_name: str, payload: dict) -> None:
        self.agent_event.emit(event_name, payload)


class AgentToolWorker(QThread):
    """执行一次已由界面确认的工具，不经过模型请求。"""

    agent_event = pyqtSignal(str, object)
    completed = pyqtSignal(object)

    def __init__(
        self,
        service: AgentService,
        tool_name: str,
        trusted_context: dict,
    ) -> None:
        super().__init__()
        self.service = service
        self.tool_name = str(tool_name or "")
        self.trusted_context = dict(trusted_context or {})
        self._cancel_event = threading.Event()

    def run(self) -> None:
        result = self.service.run_confirmed_tool(
            self.tool_name,
            trusted_context=self.trusted_context,
            callback=self._on_event,
            cancel_event=self._cancel_event,
        )
        self.completed.emit(result)

    def cancel(self) -> None:
        self._cancel_event.set()
        self.service.cancel()

    def _on_event(self, event_name: str, payload: dict) -> None:
        self.agent_event.emit(event_name, payload)
