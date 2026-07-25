from types import SimpleNamespace

import frontend.RenpyToolbox.FontReplacePage as font_page_module
from frontend.RenpyToolbox.FontReplacePage import FontReplacePage


class _SignalStub:
    def __init__(self) -> None:
        self.values = []

    def emit(self, *values) -> None:
        self.values.append(values)


class _ImmediateThread:
    instances = []

    def __init__(self, *, target, daemon: bool) -> None:
        self.target = target
        self.daemon = daemon
        self.started = False
        self.__class__.instances.append(self)

    def start(self) -> None:
        self.started = True
        self.target()


def test_replace_all_fonts_schedules_worker_and_emits_result(tmp_path, monkeypatch) -> None:
    game_dir = tmp_path / "game"
    game_dir.mkdir()
    source_font = tmp_path / "font.ttf"
    source_font.write_bytes(b"font")

    calls = []
    running_states = []
    signal = _SignalStub()
    page = SimpleNamespace(
        game_dir_edit=SimpleNamespace(text=lambda: str(game_dir)),
        custom_font_edit=SimpleNamespace(text=lambda: str(source_font)),
        detected_fonts=["old.ttf"],
        replace_all_check=SimpleNamespace(isChecked=lambda: True),
        old_font_edit=SimpleNamespace(text=lambda: ""),
        auto_backup_check=SimpleNamespace(isChecked=lambda: True),
        replacer=SimpleNamespace(
            safe_replace_font=lambda **kwargs: (
                calls.append(kwargs) or (True, "完成", {"replaced_files": 1})
            ),
        ),
        font_replace_done=signal,
        _scan_game_dir=lambda path: None,
        _set_replace_running=running_states.append,
    )
    _ImmediateThread.instances = []
    monkeypatch.setattr(font_page_module.threading, "Thread", _ImmediateThread)

    FontReplacePage._replace_all_fonts(page)

    assert running_states == [True]
    assert len(_ImmediateThread.instances) == 1
    assert _ImmediateThread.instances[0].daemon is True
    assert _ImmediateThread.instances[0].started is True
    assert calls == [{
        "game_dir": str(game_dir),
        "source_font_path": str(source_font),
        "original_fonts": ["old.ttf"],
        "create_backup": True,
    }]
    assert signal.values == [(True, "完成", {"replaced_files": 1})]
