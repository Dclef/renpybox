import threading
import time

from base.Base import Base
from base.BaseLanguage import BaseLanguage
from module.Cache.CacheItem import CacheItem
from module.Config import Config
from module.Engine.Engine import Engine
from module.Engine.TaskRequester import TaskRequester
from module.Engine.Translator.Translator import Translator
from module.Engine.Translator.TranslatorTask import TranslatorTask


def _platform() -> dict:
    return {
        "api_url": "https://example.invalid/v1",
        "api_format": Base.APIFormat.OPENAI,
        "model": "test-model",
    }


def _config() -> Config:
    return Config(
        source_language = BaseLanguage.Enum.EN,
        target_language = BaseLanguage.Enum.ZH,
        translation_output_protocol = Config.OUTPUT_PROTOCOL_STRUCTURED,
    )


class _CacheStub:
    def get_project(self):
        return None

    def get_items(self):
        return []


def _translator_stub() -> Translator:
    translator = Translator.__new__(Translator)
    translator.data_lock = threading.Lock()
    translator._active_executor = None
    translator._translation_thread = None
    translator._translation_run_id = 0
    translator._active_run_cancel_event = None
    translator._run_context = threading.local()
    translator._stop_watcher = None
    translator._stop_watcher_lock = threading.Lock()
    translator._translation_run_initialized = False
    translator._active_cache_output_folder = ""
    translator.cache_manager = _CacheStub()
    translator.print = lambda *args, **kwargs: None
    translator.info = lambda *args, **kwargs: None
    translator.warning = lambda *args, **kwargs: None
    translator.error = lambda *args, **kwargs: None
    translator.emit = lambda *args, **kwargs: None
    return translator


def test_translation_start_registers_thread_before_start(monkeypatch) -> None:
    translator = _translator_stub()
    engine = Engine.get()
    previous_status = engine.get_status()
    observed: dict[str, object] = {}

    class FakeThread:
        def __init__(self, *, target, args, name):
            self.target = target
            self.args = args
            self.name = name

        def is_alive(self) -> bool:
            return False

        def start(self) -> None:
            observed["registered"] = translator._translation_thread is self
            observed["status"] = engine.get_status()

    monkeypatch.setattr(
        "module.Engine.Translator.Translator.threading.Thread",
        FakeThread,
    )
    engine.set_status(Engine.Status.IDLE)
    try:
        translator.translation_start(Base.Event.TRANSLATION_START, {})

        assert observed == {
            "registered": True,
            "status": Engine.Status.TRANSLATING,
        }
    finally:
        translator._translation_thread = None
        engine.set_status(previous_status)


def test_stale_translation_run_cannot_clear_new_thread_or_status() -> None:
    translator = _translator_stub()
    engine = Engine.get()
    previous_status = engine.get_status()
    new_thread = threading.Thread(target = lambda: None)
    translator._translation_run_id = 2
    translator._translation_thread = new_thread
    engine.set_status(Engine.Status.TRANSLATING)

    try:
        translator.translation_start_task(
            Base.Event.TRANSLATION_START,
            {},
            run_id = 1,
            cancel_event = threading.Event(),
        )

        assert translator._translation_thread is new_thread
        assert engine.get_status() == Engine.Status.TRANSLATING
    finally:
        translator._translation_thread = None
        engine.set_status(previous_status)


def test_bound_run_cancel_event_survives_global_reset() -> None:
    run_cancel_event = threading.Event()
    run_cancel_event.set()
    TaskRequester.CANCEL_EVENT.clear()
    TaskRequester.bind_run_cancel_event(run_cancel_event)
    try:
        TaskRequester.reset()

        assert run_cancel_event.is_set()
        assert TaskRequester.is_cancel_requested()
    finally:
        TaskRequester.unbind_run_cancel_event()
        TaskRequester.CANCEL_EVENT.clear()


def test_async_client_close_does_not_wait_for_registry_lock() -> None:
    TaskRequester.CLIENT_REGISTRY.clear()
    TaskRequester.LOCK.acquire()
    close_thread = None
    try:
        start = time.monotonic()
        close_thread = TaskRequester.close_all_clients_async()
        elapsed = time.monotonic() - start

        assert elapsed < 0.2
        assert close_thread is not None
        assert close_thread.is_alive()
    finally:
        TaskRequester.LOCK.release()
        if close_thread is not None:
            close_thread.join(1)


def test_stop_watcher_does_not_count_itself() -> None:
    translator = _translator_stub()
    engine = Engine.get()
    previous_status = engine.get_status()
    TaskRequester.CANCEL_EVENT.clear()
    engine.set_status(Engine.Status.TRANSLATING)

    try:
        Translator.translation_stop(translator, Base.Event.TRANSLATION_STOP, {})
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            if engine.get_status() == Engine.Status.IDLE and translator._stop_watcher is None:
                break
            time.sleep(0.01)

        assert engine.get_status() == Engine.Status.IDLE
        assert translator._stop_watcher is None
        assert TaskRequester.CANCEL_EVENT.is_set() is False
    finally:
        TaskRequester.CANCEL_EVENT.clear()
        engine.set_status(previous_status)


def test_close_all_clients_releases_registry_lock_before_close() -> None:
    entered = threading.Event()
    acquired = threading.Event()

    class Client:
        def close(self) -> None:
            entered.set()
            if TaskRequester.LOCK.acquire(timeout = 0.5):
                acquired.set()
                TaskRequester.LOCK.release()

    client = Client()
    key = ("https://example.invalid", "test", Base.APIFormat.OPENAI, 1)
    TaskRequester.CLIENT_REGISTRY.clear()
    TaskRequester.CLIENT_REGISTRY[key] = client
    try:
        TaskRequester.close_all_clients()
        assert entered.is_set()
        assert acquired.is_set()
        assert TaskRequester.CLIENT_REGISTRY == {}
    finally:
        TaskRequester.CLIENT_REGISTRY.clear()


def test_stale_closed_client_cannot_remove_new_same_key_client() -> None:
    class Client:
        def __init__(self) -> None:
            self.closed = False

        def close(self) -> None:
            self.closed = True

    url = "https://example.invalid/v1"
    api_key = "test-key"
    timeout = 30
    cache_key = (url, api_key, Base.APIFormat.OPENAI, timeout)
    old_client = Client()
    new_client = Client()
    requester = TaskRequester.__new__(TaskRequester)
    requester.platform = {
        "api_url": url,
        "api_key": [api_key],
        "api_format": Base.APIFormat.OPENAI,
    }
    requester.config = Config(request_timeout = timeout)
    requester.warning = lambda *args, **kwargs: None

    TaskRequester.CLIENT_REGISTRY.clear()
    TaskRequester.CLIENT_GENERATIONS.clear()
    TaskRequester.CLIENT_REGISTRY[cache_key] = new_client
    TaskRequester.CLIENT_GENERATIONS[cache_key] = 2
    try:
        recovered = requester._recover_closed_cached_client(
            RuntimeError("client has been closed"),
            client = old_client,
            key = api_key,
        )

        assert recovered is True
        assert old_client.closed is True
        assert new_client.closed is False
        assert TaskRequester.CLIENT_REGISTRY[cache_key] is new_client
        assert TaskRequester.CLIENT_GENERATIONS[cache_key] == 2
    finally:
        TaskRequester.CLIENT_REGISTRY.clear()
        TaskRequester.CLIENT_GENERATIONS.clear()


def test_cancelled_request_does_not_record_retry_metadata(monkeypatch) -> None:
    task = TranslatorTask(
        _config(),
        _platform(),
        False,
        [CacheItem(src = "Hello")],
        [],
    )

    def cancelled_request(self, messages):
        TaskRequester.CANCEL_EVENT.set()
        return True, None, None, None, None

    monkeypatch.setattr(TaskRequester, "request", cancelled_request)
    TaskRequester.CANCEL_EVENT.clear()
    try:
        result = task.request(
            task.items,
            task.processors,
            task.precedings,
            task.local_flag,
            0,
        )
        assert result.get("cancelled") is True
        assert TranslatorTask.RETRY_METADATA_KEY not in task.items[0].get_metadata()
        assert task.items[0].get_retry_count() == 0
    finally:
        TaskRequester.CANCEL_EVENT.clear()


def test_old_cancelled_thread_stays_cancelled_after_new_run_reset() -> None:
    started = threading.Event()
    release = threading.Event()
    observed = []

    def old_worker() -> None:
        started.set()
        release.wait(2)
        observed.append(TaskRequester.is_cancel_requested())

    worker = threading.Thread(target = old_worker, name = "ENGINE_OLD_TRANSLATION")
    TaskRequester.CANCELLED_THREADS.clear()
    TaskRequester.CANCEL_EVENT.clear()
    worker.start()
    assert started.wait(1)
    try:
        TaskRequester.cancel_all_clients(
            asynchronous = False,
            threads = (worker,),
        )
        # 新一轮 reset 会清除全局事件，但不能复活旧线程。
        TaskRequester.reset()
        release.set()
        worker.join(2)
        assert observed == [True]
    finally:
        release.set()
        worker.join(2)
        TaskRequester.CANCEL_EVENT.clear()
        TaskRequester.CANCELLED_THREADS.clear()


def test_rpm_only_configuration_uses_bounded_worker_count(monkeypatch) -> None:
    translator = _translator_stub()
    translator.config = Config(max_workers = 0, rpm_threshold = 120)
    translator.platform = {"api_url": "https://example.invalid/v1"}
    translator.debug = lambda *args, **kwargs: None
    monkeypatch.setattr(
        "module.Engine.Translator.Translator.httpx.get",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("offline")),
    )

    max_workers, rpm = translator.initialize_max_workers()

    assert max_workers == 8
    assert rpm == 120
