"""无 Qt 的 Agent 会话、流式快照与工具确认桥接。"""

from __future__ import annotations

import copy
import threading
import time
import uuid
from typing import Any, Callable

from module.Agent.AgentService import AgentService
from module.Agent.types import AgentRunResult
from base.LogManager import LogManager


class AgentSession:
    def __init__(self, service: AgentService, notify: Callable[[dict], None]) -> None:
        self.service = service
        self.notify = notify
        self.session_id = uuid.uuid4().hex
        self._lock = threading.Lock()
        self._revision = 0
        self._run_id = 0
        self._status = "idle"
        self._messages: list[dict[str, Any]] = []
        self._confirmation: dict[str, Any] | None = None
        self._confirmation_result: bool | None = None
        self._confirmation_event = threading.Event()
        self._cancel_event = threading.Event()
        self._thread: threading.Thread | None = None

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return copy.deepcopy({
                "session_id": self.session_id,
                "revision": self._revision,
                "run_id": self._run_id,
                "status": self._status,
                "messages": self._messages,
                "confirmation": self._confirmation,
            })

    def _publish(self) -> None:
        with self._lock:
            data = {"session_id": self.session_id, "revision": self._revision}
        self.notify({"type": "event", "event": "AGENT_UPDATE", "data": data})

    def start(self, text: str, thinking_level: str) -> dict[str, Any]:
        text = text.strip()
        if not text:
            raise ValueError("消息不能为空")
        with self._lock:
            if self._status != "idle":
                raise RuntimeError("Agent 正在处理任务，请先等待完成或停止")
            self._run_id += 1
            self._status = "running"
            self._cancel_event = threading.Event()
            self._confirmation = None
            message = {
                "id": f"{self._run_id}-assistant",
                "role": "assistant",
                "content": "",
                "reasoning": "",
                "tools": [],
                "status": "running",
                "error": "",
            }
            self._messages.extend([
                {"id": f"{self._run_id}-user", "role": "user", "content": text},
                message,
            ])
            self._messages = self._messages[-100:]
            self._revision += 1
            self._thread = threading.Thread(
                target=self._run,
                args=(text, thinking_level, message, self._cancel_event),
                name="renpybox-agent",
                daemon=True,
            )
            worker = self._thread
        self._publish()
        worker.start()
        return self.snapshot()

    def _event(self, message: dict[str, Any], event: str, payload: dict[str, Any]) -> None:
        with self._lock:
            if event == "reply_delta":
                message["content"] += str(payload.get("text", ""))
            elif event == "reply":
                message["content"] = str(payload.get("message", ""))
            elif event == "reasoning_delta":
                message["reasoning"] += str(payload.get("text", ""))
            elif event == "request":
                message["iteration"] = payload.get("iteration", 1)
            elif event == "error":
                message["error"] = str(payload.get("message", ""))
            elif event == "tool_start":
                message["tools"].append({**payload, "status": "running"})
            elif event == "tool_done":
                tool = next((
                    entry for entry in reversed(message["tools"])
                    if entry["name"] == payload.get("name") and entry["status"] == "running"
                ), None)
                if tool is None:
                    tool = {}
                    message["tools"].append(tool)
                tool.update({**payload, "status": "done" if payload.get("success") else "failed"})
            self._revision += 1
        self._publish()

    def _request_confirmation(self, name: str, payload: dict[str, Any]) -> bool | None:
        confirmation_id = uuid.uuid4().hex
        with self._lock:
            if self._cancel_event.is_set():
                return False
            self._confirmation_result = None
            self._confirmation_event.clear()
            self._confirmation = {
                **copy.deepcopy(payload),
                "id": confirmation_id,
                "name": name,
                "expires_at": time.time() + self.service.confirmation_timeout,
            }
            self._revision += 1
        self._publish()
        received = self._confirmation_event.wait(self.service.confirmation_timeout)
        with self._lock:
            result = False if self._cancel_event.is_set() else (self._confirmation_result if received else None)
            self._confirmation = None
            self._revision += 1
        self._publish()
        return result

    def confirm(self, confirmation_id: str, approved: bool) -> dict[str, Any]:
        with self._lock:
            pending = self._confirmation
            if self._status != "running" or pending is None or pending["id"] != confirmation_id:
                raise RuntimeError("此确认已失效，请刷新当前会话")
            if time.time() >= pending["expires_at"]:
                raise RuntimeError("工具确认已超时")
            self._confirmation_result = approved
            self._confirmation = None
            self._confirmation_event.set()
            self._revision += 1
        self._publish()
        return self.snapshot()

    def _run(self, text: str, thinking_level: str, message: dict[str, Any], cancel_event: threading.Event) -> None:
        try:
            result = self.service.run(
                text,
                callback=lambda event, payload: self._event(message, event, payload),
                confirmation_callback=self._request_confirmation,
                thinking_level=thinking_level,
                cancel_event=cancel_event,
            )
        except Exception as exc:
            LogManager.get().error("Agent 执行失败", exc)
            result = AgentRunResult(False, "Agent 执行失败，请检查接口配置和后端日志", code="INTERNAL_ERROR")
        with self._lock:
            message["status"] = "cancelled" if cancel_event.is_set() or result.code in {"CANCELLED", "USER_CANCELLED"} else ("done" if result.success else "failed")
            if result.success:
                message["content"] = result.message
            else:
                message["error"] = result.message
            for tool in message["tools"]:
                if tool["status"] == "running":
                    tool["status"] = message["status"]
            self._confirmation = None
            self._status = "idle"
            self._revision += 1
        self._publish()

    def cancel(self) -> dict[str, Any]:
        with self._lock:
            running = self._status != "idle"
            if running:
                self._status = "stopping"
                self._cancel_event.set()
                self._confirmation_result = False
                self._confirmation = None
                self._confirmation_event.set()
                self._revision += 1
        if running:
            self.service.cancel()
            self._publish()
        return self.snapshot()

    def reset(self) -> dict[str, Any]:
        with self._lock:
            if self._status != "idle":
                raise RuntimeError("请先停止当前任务，再新建会话")
            self.service.reset()
            self._messages = []
            self._confirmation = None
            self._revision += 1
        self._publish()
        return self.snapshot()

    def close(self) -> None:
        self.cancel()
        worker = self._thread
        if worker is not None:
            worker.join(timeout=3)
        if worker is None or not worker.is_alive():
            self.service.reset()
