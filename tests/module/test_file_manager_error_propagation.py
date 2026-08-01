import pytest

import module.File.FileManager as file_manager_module
from module.Config import Config
from module.File.FileManager import FileManager


def test_writeback_reports_errors_after_running_remaining_writers(monkeypatch):
    calls: list[str] = []
    writer_names = (
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

    class DummyWriter:
        def __init__(self, name: str):
            self.name = name

        def write_to_path(self, _items):
            calls.append(self.name)
            if self.name == "TXT":
                raise OSError("fictional writer failure")

    for name in writer_names:
        monkeypatch.setattr(
            file_manager_module,
            name,
            lambda _config, writer_name=name: DummyWriter(writer_name),
        )

    with pytest.raises(RuntimeError, match="TXT.*fictional writer failure"):
        FileManager(Config()).write_to_path([])

    assert calls == list(writer_names)


def test_read_reports_partial_failure_instead_of_returning_incomplete_project(
    tmp_path, monkeypatch
):
    calls: list[str] = []
    reader_names = (
        "RENPYTRANSLATIONSJSON",
        "MD",
        "TXT",
        "ASS",
        "SRT",
        "EPUB",
        "XLSX",
        "WOLFXLSX",
        "RENPY",
        "TRANS",
        "KVJSON",
        "MESSAGEJSON",
    )

    class DummyReader:
        def __init__(self, name: str):
            self.name = name

        def read_from_path(self, _paths):
            calls.append(self.name)
            if self.name == "TXT":
                raise OSError("fictional reader failure")
            return []

    for name in reader_names:
        monkeypatch.setattr(
            file_manager_module,
            name,
            lambda _config, reader_name=name: DummyReader(reader_name),
        )

    config = Config()
    config.input_folder = str(tmp_path)
    with pytest.raises(RuntimeError, match="TXT.*fictional reader failure"):
        FileManager(config).read_from_path()

    assert calls == list(reader_names)
