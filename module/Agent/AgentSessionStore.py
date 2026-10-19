"""Agent 会话历史的落盘存储。

每个会话一个 JSON 文件，放在 ``storage/agent_sessions/`` 下（应用目录，
已被 .gitignore 忽略）。只存展示所需的 UI 消息与恢复模型上下文用的
service 消息，不碰任何密钥：平台配置仍由 ``config.json`` 管理。
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Any

from base.AppPaths import AppPaths

SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
FILE_SUFFIX = ".json"
SCHEMA_VERSION = 1
# 单文件上限：Agent 消息里可能带很长的工具输出，超过就丢弃最旧的会话，
# 避免用户的磁盘被历史聊天悄悄吃掉。
MAX_SESSION_BYTES = 8 * 1024 * 1024
MAX_TITLE_CHARS = 40


def _now() -> float:
    return round(time.time(), 3)


def session_title(messages: list[dict[str, Any]]) -> str:
    """用第一条用户消息当标题；没有就退回「新会话」。"""
    for message in messages or ():
        if not isinstance(message, dict) or message.get("role") != "user":
            continue
        text = str(message.get("content") or "").strip()
        if not text:
            continue
        # 折叠换行，标题只占一行。
        text = re.sub(r"\s+", " ", text)
        return text[:MAX_TITLE_CHARS] + ("…" if len(text) > MAX_TITLE_CHARS else "")
    return "新会话"


class AgentSessionStore:
    """会话历史的读写入口；所有写入都是「临时文件 + 原子替换」。"""

    def __init__(self, root: str | Path | None = None) -> None:
        self._root = Path(root) if root is not None else AppPaths.detect().app("storage", "agent_sessions")
        self._lock = threading.Lock()

    @property
    def root(self) -> Path:
        return self._root

    def _ensure_root(self) -> None:
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, session_id: str) -> Path:
        value = str(session_id or "")
        if not SESSION_ID_PATTERN.match(value):
            raise ValueError("会话编号不合法")
        return self._root / f"{value}{FILE_SUFFIX}"

    def save(self, *, session_id: str, messages: list[dict[str, Any]],
             context: list[dict[str, Any]] | None = None,
             created_at: float | None = None,
             metrics: dict[str, Any] | None = None) -> dict[str, Any] | None:
        """写入一个会话；内容为空时删除该会话并返回 None。"""

        if not messages:
            self.delete(session_id)
            return None
        payload = {
            "schema_version": SCHEMA_VERSION,
            "id": session_id,
            "title": session_title(messages),
            "created_at": round(float(created_at or _now()), 3),
            "updated_at": _now(),
            "messages": messages,
            "context": context or [],
            "metrics": metrics or {},
        }
        encoded = json.dumps(payload, ensure_ascii=False, default=str)
        if len(encoded.encode("utf-8")) > MAX_SESSION_BYTES:
            # 太大的会话不落盘，避免把磁盘写满；界面仍可正常使用。
            return None
        with self._lock:
            self._ensure_root()
            path = self._path(session_id)
            temp = path.with_suffix(".json.tmp")
            temp.write_text(encoded, encoding="utf-8")
            os.replace(temp, path)
        return payload

    def load(self, session_id: str) -> dict[str, Any] | None:
        try:
            path = self._path(session_id)
        except ValueError:
            return None
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(payload, dict) or payload.get("schema_version") != SCHEMA_VERSION:
            return None
        return payload

    def delete(self, session_id: str) -> bool:
        try:
            path = self._path(session_id)
        except ValueError:
            return False
        with self._lock:
            try:
                path.unlink()
                return True
            except FileNotFoundError:
                return False
            except OSError:
                return False

    def list_sessions(self) -> list[dict[str, Any]]:
        """按最近更新倒序列出会话摘要；损坏的文件直接跳过。"""

        if not self._root.is_dir():
            return []
        summaries: list[dict[str, Any]] = []
        for path in self._root.glob(f"*{FILE_SUFFIX}"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if not isinstance(payload, dict) or payload.get("schema_version") != SCHEMA_VERSION:
                continue
            session_id = str(payload.get("id") or path.stem)
            if not SESSION_ID_PATTERN.match(session_id):
                continue
            messages = payload.get("messages")
            summaries.append({
                "id": session_id,
                "title": str(payload.get("title") or "新会话"),
                "created_at": float(payload.get("created_at") or 0.0),
                "updated_at": float(payload.get("updated_at") or 0.0),
                "message_count": len(messages) if isinstance(messages, list) else 0,
            })
        summaries.sort(key=lambda item: item["updated_at"], reverse=True)
        return summaries

    def prune(self, keep: int = 50) -> int:
        """只保留最近 ``keep`` 个会话，返回删除数量。"""

        summaries = self.list_sessions()
        removed = 0
        for summary in summaries[max(0, int(keep)):]:
            if self.delete(str(summary["id"])):
                removed += 1
        return removed
