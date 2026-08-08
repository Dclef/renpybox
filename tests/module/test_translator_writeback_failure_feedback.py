"""写回失败时的兜底注入与子线程错误反馈。

``FileManager.write_to_path`` 现在会抛出异常而不是静默记录，本模块锁定三条
由此产生的调用方约定：
- 主流程写回失败仍要先尝试一次兜底注入，再把异常抛给调用方；
- 手动导出与缓存重新注入跑在子线程里，必须自行发出错误 Toast。
"""

import types

import pytest

import module.Engine.Translator.Translator as translator_module
from base.Base import Base
from module.Engine.Translator.Translator import Translator


def _make_translator(monkeypatch, *, write_error: Exception | None):
    """构造一个只装配本测试所需依赖的 Translator。"""
    calls: list[str] = []
    toasts: list[dict] = []

    class FakeFileManager:
        def __init__(self, _config):
            pass

        def write_to_path(self, _items):
            calls.append("write")
            if write_error is not None:
                raise write_error

    class FakeResultChecker:
        def __init__(self, *_args, **_kwargs):
            pass

        def check(self):
            calls.append("check")

    monkeypatch.setattr(translator_module, "FileManager", FakeFileManager)
    monkeypatch.setattr(translator_module, "ResultChecker", FakeResultChecker)

    translator = Translator.__new__(Translator)
    translator.config = types.SimpleNamespace(
        output_folder = "fictional_output",
        output_folder_open_on_finish = False,
    )
    translator.info = lambda *_a, **_k: None
    translator.warning = lambda *_a, **_k: None
    translator.error = lambda *_a, **_k: None
    translator.print = lambda *_a, **_k: None
    translator.emit = lambda _event, data: toasts.append(data)
    translator._auto_reinject_on_writeback_fail = lambda _items: calls.append("reinject")

    return translator, calls, toasts


def test_writeback_failure_still_attempts_reinject_then_reraises(monkeypatch):
    error = RuntimeError("部分文件写回失败：RENPY: 译文未完整写入")
    translator, calls, _toasts = _make_translator(monkeypatch, write_error = error)

    with pytest.raises(RuntimeError, match = "部分文件写回失败"):
        translator.check_and_wirte_result([])

    # 兜底注入必须在异常向上传播之前跑过一次。
    assert calls == ["check", "write", "reinject"]


def test_successful_writeback_still_runs_reinject_check(monkeypatch):
    translator, calls, _toasts = _make_translator(monkeypatch, write_error = None)

    translator.check_and_wirte_result([])

    assert calls == ["check", "write", "reinject"]


def test_manual_export_emits_error_toast_on_writeback_failure(monkeypatch):
    error = RuntimeError("部分文件写回失败：RENPYSOURCE: 译文未生效")
    translator, calls, toasts = _make_translator(monkeypatch, write_error = error)

    class FakeCacheManager:
        def copy_items(self):
            return []

    translator.cache_manager = FakeCacheManager()
    translator.mtool_optimizer_postprocess = lambda _items: None

    started: list = []
    monkeypatch.setattr(
        translator_module.Engine,
        "get",
        staticmethod(
            lambda: types.SimpleNamespace(
                get_status = lambda: translator_module.Engine.Status.TRANSLATING
            )
        ),
    )

    class ImmediateThread:
        def __init__(self, target = None, args = (), **_kwargs):
            self._target = target
            self._args = args

        def start(self):
            started.append(True)
            self._target(*self._args)

    monkeypatch.setattr(translator_module.threading, "Thread", ImmediateThread)

    # 子线程异常不得逃逸；用户必须收到错误 Toast。
    translator.translation_manual_export("event", {})

    assert started == [True]
    assert calls == ["check", "write", "reinject"]
    assert [toast["type"] for toast in toasts] == [Base.ToastType.ERROR]
    assert "部分文件写回失败" in toasts[0]["message"]


def test_cache_reinject_emits_error_toast_instead_of_success(monkeypatch):
    error = RuntimeError("部分文件写回失败：RENPY: 写入失败")
    translator, calls, toasts = _make_translator(monkeypatch, write_error = error)

    monkeypatch.setattr(
        translator_module.Config,
        "load",
        lambda self, path = None: types.SimpleNamespace(output_folder = "fictional_output"),
    )

    class FakeCacheManager:
        def __init__(self, *_args, **_kwargs):
            pass

        def load_items_from_file(self, *_args, **_kwargs):
            return None

        def get_items(self):
            return [object()]

    monkeypatch.setattr(translator_module, "CacheManager", FakeCacheManager)

    class ImmediateThread:
        def __init__(self, target = None, args = (), **_kwargs):
            self._target = target
            self._args = args

        def start(self):
            self._target(*self._args)

    monkeypatch.setattr(translator_module.threading, "Thread", ImmediateThread)

    translator.translation_cache_reinject("event", {})

    assert calls == ["write"]
    # 失败后必须提前返回，不能再发成功 Toast。
    assert [toast["type"] for toast in toasts] == [Base.ToastType.ERROR]
    assert "部分文件写回失败" in toasts[0]["message"]
