"""写回失败的提示截断与明细落盘。

``FileManager.write_to_path`` 汇总多个 writer 的异常时，异常文本可能长达数 KB，
直接塞进 Toast 既不可读也定位不到原因。本模块锁定三条约定：
- 抛出的 RuntimeError 以「部分文件写回失败：」开头，单条消息不超过 1500 字符；
- 逐 writer 的完整异常落到 output_folder/writeback_failures.json；
- REINJECT 的后台线程是守护线程，失败 Toast 不超过 800 字符且保留关键子串。
"""

import json
import types

import pytest

import module.Engine.Translator.Translator as translator_module
import module.File.FileManager as file_manager_module
from base.Base import Base
from module.Config import Config
from module.Engine.Translator.Translator import Translator
from module.File.FileManager import FileManager


WRITER_NAMES = (
    "RENPYTRANSLATIONSJSON",
    "MD",
    "TXT",
    "ASS",
    "SRT",
    "EPUB",
    "XLSX",
    "WOLFXLSX",
    "RENPYHOOK",
    "RENPYSOURCE",
    "RENPY",
    "TRANS",
    "KVJSON",
    "MESSAGEJSON",
)


def _long_detail(prefix: str, size: int = 4000) -> str:
    """构造远超提示上限的异常文本，模拟 RENPYSOURCE 的逐条「译文未生效」。"""
    return f"{prefix}：" + "；".join(
        f"译文未生效(第{index}条)：虚构的写回细节" for index in range(size // 20)
    )


def _patch_writers(monkeypatch, failures: dict[str, Exception]) -> None:
    """把全部 writer 换成替身，只让 failures 里点名的 writer 抛异常。"""

    class FakeWriter:
        def __init__(self, name: str):
            self.name = name

        def write_to_path(self, _items):
            error = failures.get(self.name)
            if error is not None:
                raise error

    for name in WRITER_NAMES:
        monkeypatch.setattr(
            file_manager_module,
            name,
            lambda _config, writer_name=name: FakeWriter(writer_name),
        )


def test_single_writer_failure_reports_brief_message_and_full_detail(tmp_path, monkeypatch):
    output_folder = tmp_path / "RenpyBox_Translation" / "chinese"
    config = Config()
    config.output_folder = str(output_folder)
    full_detail = _long_detail("RENPYSOURCE 源码写回未完整完成")
    _patch_writers(monkeypatch, {"RENPYSOURCE": RuntimeError(full_detail)})

    with pytest.raises(RuntimeError) as excinfo:
        FileManager(config).write_to_path([])

    message = str(excinfo.value)
    assert message.startswith("部分文件写回失败：")
    assert len(message) <= 1500
    assert "RENPYSOURCE" in message
    assert "writeback_failures.json" in message

    report_path = output_folder / "writeback_failures.json"
    assert report_path.is_file()
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert len(payload) == 1
    assert payload[0]["writer"] == "RENPYSOURCE"
    assert payload[0]["error_type"] == "RuntimeError"
    # 落盘的是完整异常，不是截断后的摘要。
    assert payload[0]["message"] == full_detail


def test_two_writer_failures_still_fit_message_limit(tmp_path, monkeypatch):
    output_folder = tmp_path / "chinese"
    config = Config()
    config.output_folder = str(output_folder)
    first = _long_detail("RENPYSOURCE 源码写回未完整完成")
    second = _long_detail("RENPY 写回未完整完成")
    _patch_writers(
        monkeypatch,
        {"RENPYSOURCE": RuntimeError(first), "RENPY": ValueError(second)},
    )

    with pytest.raises(RuntimeError) as excinfo:
        FileManager(config).write_to_path([])

    message = str(excinfo.value)
    assert message.startswith("部分文件写回失败：")
    assert len(message) <= 1500

    payload = json.loads((output_folder / "writeback_failures.json").read_text(encoding="utf-8"))
    assert len(payload) == 2
    assert {entry["writer"] for entry in payload} == {"RENPYSOURCE", "RENPY"}
    assert payload[1]["error_type"] == "ValueError"
    assert {entry["message"] for entry in payload} == {first, second}


def test_every_writer_failing_keeps_message_within_limit(tmp_path, monkeypatch):
    """14 个 writer 全失败时，提示仍要落在 1500 字符以内，明细一条不少。"""
    output_folder = tmp_path / "chinese"
    config = Config()
    config.output_folder = str(output_folder)
    failures = {
        name: RuntimeError(_long_detail(f"{name} 写回失败"))
        for name in WRITER_NAMES
    }
    _patch_writers(monkeypatch, failures)

    with pytest.raises(RuntimeError) as excinfo:
        FileManager(config).write_to_path([])

    message = str(excinfo.value)
    assert message.startswith("部分文件写回失败：")
    assert len(message) <= 1500
    assert "writeback_failures.json" in message
    assert message.endswith("）")

    payload = json.loads((output_folder / "writeback_failures.json").read_text(encoding="utf-8"))
    assert [entry["writer"] for entry in payload] == list(WRITER_NAMES)


def test_failure_report_write_error_does_not_mask_original_error(tmp_path, monkeypatch):
    """诊断文件自身写不出来时，原写回异常必须照常抛出。"""
    config = Config()
    # 让 output_folder 指向一个已存在的普通文件，mkdir/写盘一定失败。
    blocker = tmp_path / "blocked"
    blocker.write_text("not a directory", encoding="utf-8")
    config.output_folder = str(blocker)
    detail = _long_detail("RENPYSOURCE 源码写回未完整完成")
    _patch_writers(monkeypatch, {"RENPYSOURCE": RuntimeError(detail)})

    with pytest.raises(RuntimeError) as excinfo:
        FileManager(config).write_to_path([])

    message = str(excinfo.value)
    assert message.startswith("部分文件写回失败：")
    assert len(message) <= 1500
    assert "RENPYSOURCE" in message


def _make_reinject_translator(monkeypatch, error: Exception):
    toasts: list[dict] = []
    calls: list[str] = []

    class FakeFileManager:
        def __init__(self, _config):
            pass

        def write_to_path(self, _items):
            calls.append("write")
            raise error

    monkeypatch.setattr(file_manager_module, "FileManager", FakeFileManager)
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

    thread_kwargs: dict = {}
    started: list[bool] = []

    class RecordingThread:
        def __init__(self, target = None, args = (), **kwargs):
            thread_kwargs.update(kwargs)
            self._target = target
            self._args = args

        def start(self):
            started.append(True)
            self._target(*self._args)

    monkeypatch.setattr(translator_module.threading, "Thread", RecordingThread)

    translator = Translator.__new__(Translator)
    translator.config = types.SimpleNamespace(
        output_folder = "fictional_output",
        output_folder_open_on_finish = False,
    )
    translator.info = lambda *_args, **_kwargs: None
    translator.warning = lambda *_args, **_kwargs: None
    translator.error = lambda *_args, **_kwargs: None
    translator.emit = lambda _event, data: toasts.append(data)

    return translator, calls, toasts, thread_kwargs, started


def test_cache_reinject_uses_daemon_thread_and_brief_error_toast(monkeypatch):
    error = RuntimeError("部分文件写回失败：" + _long_detail("RENPYSOURCE", 1600))
    assert len(str(error)) > 800
    translator, calls, toasts, thread_kwargs, started = _make_reinject_translator(
        monkeypatch,
        error,
    )

    translator.translation_cache_reinject("event", {})

    # 应用退出不能被重新注入的后台线程拖住。
    assert thread_kwargs.get("daemon") is True
    assert started == [True]
    assert calls == ["write"]
    assert [toast["type"] for toast in toasts] == [Base.ToastType.ERROR]

    message = toasts[0]["message"]
    assert len(message) <= 800
    assert "部分文件写回失败" in message
    # 截断后的摘要仍然可读，不能让原始异常整段糊在 Toast 里。
    assert message.endswith("…")
    assert str(error) not in message
