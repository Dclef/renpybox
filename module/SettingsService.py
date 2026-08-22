"""配置的内存态与延迟持久化服务。"""

from __future__ import annotations

import threading
from collections.abc import Callable, Mapping
from dataclasses import fields
from pathlib import Path
from typing import Any

from module.Config import Config


class SettingsService:
    """持有一份配置快照，并把高频编辑合并成一次原子保存。"""

    def __init__(
        self,
        config: Config | None = None,
        *,
        path: str | Path | None = None,
        debounce_seconds: float = 0.5,
    ) -> None:
        if debounce_seconds < 0:
            raise ValueError("debounce_seconds must be non-negative")
        self._path = str(path) if path is not None else Config.CONFIG_PATH
        self._debounce_seconds = debounce_seconds
        self._lock = threading.RLock()
        self._timer: threading.Timer | None = None
        self._closed = False
        self._config = config if config is not None else Config().load(self._path)

    @property
    def config(self) -> Config:
        """返回当前内存配置；字段修改应通过 ``update`` 或 ``edit``。"""
        with self._lock:
            return self._config

    @property
    def path(self) -> str:
        """返回配置持久化路径。"""
        return self._path

    def reload(self) -> Config:
        """从磁盘重新载入当前配置快照，并取消待保存计时器。"""
        with self._lock:
            self._ensure_open()
            self._cancel_timer_locked()
            self._config = Config().load(self._path)
            return self._config

    def update(self, values: Mapping[str, Any], *, immediate: bool = False) -> Config:
        """更新配置字段并按 debounce 策略持久化。"""
        if not isinstance(values, Mapping):
            raise TypeError("values must be a mapping")

        def apply(config: Config) -> None:
            field_names = {field.name for field in fields(config)}
            unknown = set(values) - field_names
            if unknown:
                raise AttributeError(f"Unknown config fields: {sorted(unknown)!r}")
            for key, value in values.items():
                setattr(config, key, value)

        return self.edit(apply, immediate=immediate)

    def edit(
        self,
        mutator: Callable[[Config], Any],
        *,
        immediate: bool = False,
    ) -> Config:
        """在锁内修改配置；``immediate`` 使用严格原子保存。"""
        if not callable(mutator):
            raise TypeError("mutator must be callable")
        with self._lock:
            self._ensure_open()
            mutator(self._config)
            if immediate:
                self._cancel_timer_locked()
                self._config.save(self._path, strict=True)
            else:
                self._schedule_save_locked()
            return self._config

    def save_now(self) -> Config:
        """取消延迟保存并立即严格写盘。"""
        with self._lock:
            self._ensure_open()
            self._cancel_timer_locked()
            self._config.save(self._path, strict=True)
            return self._config

    def close(self, *, save: bool = True) -> None:
        """停止延迟计时器；默认先严格保存最后一份配置。"""
        with self._lock:
            if self._closed:
                return
            self._cancel_timer_locked()
            if save:
                self._config.save(self._path, strict=True)
            self._closed = True

    def _schedule_save_locked(self) -> None:
        self._cancel_timer_locked()
        if self._debounce_seconds == 0:
            self._config.save(self._path, strict=True)
            return
        self._timer = threading.Timer(self._debounce_seconds, self._save_from_timer)
        self._timer.daemon = True
        self._timer.start()

    def _save_from_timer(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._timer = None
            self._config.save(self._path, strict=True)

    def _cancel_timer_locked(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("SettingsService is closed")
