"""写回失败时的兜底注入与子线程错误反馈。

``FileManager.write_to_path`` 现在会抛出异常而不是静默记录，本模块锁定三条
由此产生的调用方约定：
- 主流程写回失败仍要先尝试一次兜底注入，再把异常抛给调用方；
- 手动导出与缓存重新注入跑在子线程里，必须自行发出错误 Toast。
"""

import json
import os
import types

import pytest

import module.Engine.Translator.Translator as translator_module
import module.File.FileManager as file_manager_module
from base.Base import Base
from module.Cache.CacheManager import CacheManager
from module.Cache.CacheProject import CacheProject
from module.Config import Config
from module.Engine.Translator.Translator import Translator
from module.File.RENPY import RENPY
from module.Renpy.ProjectPaths import RenpyProjectPaths, write_run_manifest


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

    # FileManager 在 Translator 里是函数内延迟导入（module/Engine/Translator/
    # Translator.py 的 check_and_wirte_result / translation_manual_export /
    # translation_cache_reinject 都写 `from module.File.FileManager import
    # FileManager`），模块上没有这个属性，必须打真实模块路径才拦得住。
    monkeypatch.setattr(file_manager_module, "FileManager", FakeFileManager)
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


@pytest.mark.parametrize("write_fails", [True, False])
def test_manual_export_reports_result_after_writeback(monkeypatch, write_fails):
    error = RuntimeError("部分文件写回失败：RENPYSOURCE: 译文未生效") if write_fails else None
    translator, calls, toasts = _make_translator(monkeypatch, write_error = error)

    class FakeCacheManager:
        def copy_items(self):
            return []

    translator.cache_manager = FakeCacheManager()
    translator.mtool_optimizer_postprocess = lambda _items: None
    translator._translation_run_initialized = True

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
    expected_type = Base.ToastType.ERROR if write_fails else Base.ToastType.SUCCESS
    assert [toast["type"] for toast in toasts] == [expected_type]
    if write_fails:
        assert "部分文件写回失败" in toasts[0]["message"]
    else:
        assert os.path.abspath(translator.config.output_folder) in toasts[0]["message"]


def test_idle_manual_export_uses_resolved_cache_directory(monkeypatch):
    """翻译结束后仍可导出；目录以当前项目的缓存解析结果为准。"""
    translator = Translator.__new__(Translator)
    calls = []
    translator._resolve_project_status_output_folder = lambda data: "project/output"
    translator.translation_cache_reinject = lambda event, data: calls.append((event, data))
    monkeypatch.setattr(translator_module.Engine, "get", staticmethod(
        lambda: types.SimpleNamespace(get_status=lambda: translator_module.Engine.Status.IDLE)
    ))
    translator.translation_manual_export("export", {})
    assert calls == [("export", {"output_folder": "project/output"})]


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


@pytest.mark.parametrize("export_kind", ["manual", "automatic"])
def test_cache_export_preserves_configured_source_directory(tmp_path, monkeypatch, export_kind):
    input_dir = tmp_path / "game" / "tl" / "chinese"
    output_dir = tmp_path / "RenpyBox_Translation" / "chinese"
    input_dir.mkdir(parents=True)
    source = input_dir / "fictional_signal.rpy"
    original = (
        'translate chinese signal_11111111:\n'
        '    # guide "The fictional signal appears."\n'
        '    guide "The fictional signal appears."\n'
    )
    source.write_text(original, encoding="utf-8")
    config = Config()
    config.input_folder = str(input_dir)
    config.output_folder = str(output_dir)
    items = RENPY(config).read_from_path([str(source)])
    assert len(items) == 1
    items[0].set_dst("The fictional signal is translated.")
    items[0].set_status(Base.TranslationStatus.TRANSLATED)
    CacheManager(service=False).save_to_file(
        project=CacheProject(id="fictional-cache-export"),
        items=items,
        output_folder=str(output_dir),
        strict=True,
    )
    translator = Translator.__new__(Translator)
    translator.config = config
    toasts = []
    translator.emit = lambda _event, data: toasts.append(data)
    translator.info = lambda *_args, **_kwargs: None
    translator.warning = lambda *_args, **_kwargs: None
    translator.error = lambda *_args, **_kwargs: None
    translator._resolve_project_status_output_folder = lambda _data: str(output_dir)
    monkeypatch.setattr(translator_module.Config, "load", lambda _self: config)

    class ImmediateThread:
        def __init__(self, target, args=(), **_kwargs):
            self.target = target
            self.args = args

        def start(self):
            self.target(*self.args)

    monkeypatch.setattr(translator_module.threading, "Thread", ImmediateThread)

    if export_kind == "manual":
        translator.translation_cache_reinject("export", {"output_folder": str(output_dir)})
        assert [toast["type"] for toast in toasts] == [Base.ToastType.SUCCESS]
    else:
        (output_dir / "writeback_report_renpy.json").write_text(
            json.dumps([{"translated_items": 1, "applied": 0}]),
            encoding="utf-8",
        )
        translator._auto_reinject_on_writeback_fail(items)

    assert "The fictional signal is translated." in (output_dir / source.name).read_text(encoding="utf-8")
    assert source.read_text(encoding="utf-8") == original
    assert config.input_folder == str(input_dir)


@pytest.mark.parametrize("export_kind", ["manual", "proofreading"])
def test_cache_export_restores_incremental_input_from_manifest(tmp_path, monkeypatch, export_kind):
    main_input = tmp_path / "game" / "tl" / "chinese"
    delta_input = main_input.parent / "chinese_new"
    main_output = tmp_path / "RenpyBox_Translation" / "chinese"
    delta_output = main_output.parent / "chinese_new"
    main_input.mkdir(parents=True)
    delta_input.mkdir()
    main_source = main_input / "fictional_signal.rpy"
    delta_source = delta_input / main_source.name
    main_text = (
        'translate chinese main_11111111:\n'
        '    # guide "The fictional main signal."\n'
        '    guide "The fictional main signal."\n'
    )
    delta_text = (
        'translate chinese delta_22222222:\n'
        '    # guide "The fictional new signal."\n'
        '    guide "The fictional new signal."\n'
    )
    main_source.write_text(main_text, encoding="utf-8")
    delta_source.write_text(delta_text, encoding="utf-8")
    config = Config()
    config.input_folder = str(delta_input)
    config.output_folder = str(delta_output)
    config.cache_use_sqlite = False
    items = RENPY(config).read_from_path([str(delta_source)])
    assert len(items) == 1
    items[0].set_dst("虚构的新信号。")
    items[0].set_status(Base.TranslationStatus.TRANSLATED)
    monkeypatch.setattr(Config, "load", lambda _self: config)
    CacheManager(service=False).save_to_file(
        project=CacheProject(id="fictional-incremental-export"),
        items=items,
        output_folder=str(delta_output),
        strict=True,
    )
    paths = RenpyProjectPaths.from_path(tmp_path, "chinese")
    assert paths is not None
    write_run_manifest(paths, delta_output, input_folder=delta_input, run_kind="incremental")
    config.input_folder = str(main_input)
    config.output_folder = str(main_output)

    class ImmediateThread:
        def __init__(self, target, args=(), **_kwargs):
            self.target = target
            self.args = args

        def start(self):
            self.target(*self.args)

    monkeypatch.setattr(translator_module.threading, "Thread", ImmediateThread)
    if export_kind == "manual":
        translator = Translator.__new__(Translator)
        toasts = []
        translator.emit = lambda _event, data: toasts.append(data)
        translator.info = lambda *_args, **_kwargs: None
        translator.warning = lambda *_args, **_kwargs: None
        translator.error = lambda *_args, **_kwargs: None

        translator.translation_cache_reinject("export", {"output_folder": str(delta_output)})

        assert [toast["type"] for toast in toasts] == [Base.ToastType.SUCCESS]
    else:
        from frontend.Proofreading.ProofreadingPage import ProofreadingPage

        loaded = []
        results = []
        page = types.SimpleNamespace(
            _load_in_progress=False,
            _cache_project_key="",
            _cache_output_folder="",
            _warning_check_id=0,
            items_loaded=types.SimpleNamespace(emit=loaded.extend),
            export_done=types.SimpleNamespace(emit=lambda *result: results.append(result)),
            _start_warning_check=lambda *_args: None,
            _cache_load_error_message=ProofreadingPage._cache_load_error_message,
            emit=lambda *_args: None,
            error=lambda *_args, **_kwargs: None,
        )

        ProofreadingPage.load_data(page)
        assert len(loaded) == 1
        ProofreadingPage.export_data(page)

        assert results == [(True, "")]

    assert config.input_folder == str(delta_input)
    assert config.output_folder == str(delta_output)
    assert "虚构的新信号。" in (delta_output / delta_source.name).read_text(encoding="utf-8")
    assert main_source.read_text(encoding="utf-8") == main_text
    assert delta_source.read_text(encoding="utf-8") == delta_text
