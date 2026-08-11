import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

import frontend.RenpyToolbox.PackUnpackPage as pack_page_module
from frontend.RenpyToolbox.PackUnpackPage import (
    PackUnpackPage,
    PackWorker,
    _parse_rpa_size_limit,
)


APP = QApplication.instance() or QApplication([])


class _SignalStub:
    def connect(self, _callback) -> None:
        pass


def test_custom_split_limit_is_passed_to_worker(
    tmp_path: Path,
    monkeypatch,
) -> None:
    captured = {}

    class WorkerStub:
        progress = _SignalStub()
        finished = _SignalStub()

        def __init__(
            self,
            src_dir: str,
            output_file: str,
            max_part_size_bytes: int | None = None,
        ) -> None:
            captured["src_dir"] = src_dir
            captured["output_file"] = output_file
            captured["max_part_size_bytes"] = max_part_size_bytes

        def isRunning(self) -> bool:
            return False

        def start(self) -> None:
            captured["started"] = True

    monkeypatch.setattr(pack_page_module, "PackWorker", WorkerStub)
    source_dir = tmp_path / "images"
    source_dir.mkdir()
    output_path = tmp_path / "images.rpa"
    page = PackUnpackPage("pack_unpack")
    page.pack_src_dir_edit.setText(str(source_dir))
    page.pack_output_edit.setText(str(output_path))
    assert page.pack_split_check.isChecked() is False
    assert page.pack_part_size_edit.text() == "1G"
    assert page.pack_part_size_edit.isEnabled() is False
    page.pack_split_check.setChecked(True)
    assert page.pack_part_size_edit.isEnabled() is True
    page.pack_part_size_edit.setText("1.5G")

    page._pack()

    assert captured == {
        "src_dir": str(source_dir),
        "output_file": str(output_path),
        "max_part_size_bytes": 1536 * 1024 * 1024,
        "started": True,
    }


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1G", 1024 ** 3),
        ("1GB", 1024 ** 3),
        ("1GiB", 1024 ** 3),
        ("1.5G", 1536 * 1024 ** 2),
        ("1024M", 1024 ** 3),
        ("1024MiB", 1024 ** 3),
        ("1024", 1024 ** 3),
    ],
)
def test_size_limit_accepts_common_units(value: str, expected: int) -> None:
    assert _parse_rpa_size_limit(value) == expected


@pytest.mark.parametrize("value", ["", "0G", "-1G", "1TB", "abc"])
def test_size_limit_rejects_invalid_values(value: str) -> None:
    with pytest.raises(ValueError):
        _parse_rpa_size_limit(value)


def test_worker_reports_success_after_core_has_published(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_path = tmp_path / "archive.rpa"
    worker = PackWorker(str(tmp_path), str(output_path))

    class PackerStub:
        def pack_from_dir(self, *_args, **_kwargs):
            worker.should_stop = True
            return [output_path]

    monkeypatch.setattr(pack_page_module, "Packer", PackerStub)
    results = []
    worker.finished.connect(lambda success, message: results.append((success, message)))

    worker.run()

    assert results == [(True, "打包完成，共生成 1 个 RPA 文件")]
