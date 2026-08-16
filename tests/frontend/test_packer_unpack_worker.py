import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

import frontend.RenpyToolbox.PackUnpackPage as pack_page_module
from frontend.RenpyToolbox.PackUnpackPage import UnpackWorker


APP = QApplication.instance() or QApplication([])


def test_unpack_worker_reuses_shared_packer(monkeypatch) -> None:
    captured = {}

    class PackerStub:
        def unpack_rpa_files(self, game_dir, **kwargs):
            captured.update(game_dir=game_dir, **kwargs)
            kwargs["progress_callback"]("external")
            return {
                "success": True,
                "method": "external",
                "count": 3,
                "message": "ignored",
            }

    monkeypatch.setattr(pack_page_module, "Packer", PackerStub)
    worker = UnpackWorker("game", direct=True, script_only=True)
    progress = []
    results = []
    worker.progress.connect(progress.append)
    worker.finished.connect(results.append)

    worker.run()

    assert captured["game_dir"] == "game"
    assert captured["direct"] is True
    assert captured["script_only"] is True
    assert captured["remove_archives"] is False
    assert callable(captured["progress_callback"])
    assert progress == ["正在解包…"]
    assert results == [{
        "level": "success",
        "title": "完成",
        "message": "已解包 3 个 RPA 文件",
    }]


def test_unpack_worker_localizes_module_errors_by_language(monkeypatch) -> None:
    from base.BaseLanguage import BaseLanguage
    from module.Localizer.Localizer import Localizer
    from module.Tool.Packer import PackerUnpackError

    class RaisingPacker:
        def unpack_rpa_files(self, game_dir, **kwargs):
            raise PackerUnpackError("UNSAFE_INDEX", "无法安全读取 RPA 索引，已拒绝解包")

    monkeypatch.setattr(pack_page_module, "Packer", RaisingPacker)
    original = Localizer.get_app_language()
    try:
        Localizer.set_app_language(BaseLanguage.Enum.EN)
        worker = UnpackWorker("game", direct=True, script_only=False)
        results = []
        worker.finished.connect(results.append)
        worker.run()
        assert "could not be read safely" in results[0]["message"]
        assert not any("\u4e00" <= ch <= "\u9fff" for ch in results[0]["message"])

        Localizer.set_app_language(BaseLanguage.Enum.ZH)
        worker = UnpackWorker("game", direct=True, script_only=False)
        results = []
        worker.finished.connect(results.append)
        worker.run()
        assert "无法安全读取" in results[0]["message"]
    finally:
        Localizer.set_app_language(original)


def test_unpack_worker_localizes_failure_result(monkeypatch) -> None:
    from base.BaseLanguage import BaseLanguage
    from module.Localizer.Localizer import Localizer

    class FailingPacker:
        def unpack_rpa_files(self, game_dir, **kwargs):
            return {
                "success": False,
                "method": "none",
                "count": 0,
                "code": "UNAVAILABLE",
                "message": "未找到可解包的 RPA 文件，或所有解包方式均失败",
            }

    monkeypatch.setattr(pack_page_module, "Packer", FailingPacker)
    original = Localizer.get_app_language()
    try:
        Localizer.set_app_language(BaseLanguage.Enum.EN)
        worker = UnpackWorker("game", direct=True, script_only=False)
        results = []
        worker.finished.connect(results.append)
        worker.run()
        assert results[0]["message"] == (
            "No unpackable RPA files were found, or every unpacking method failed."
        )

        Localizer.set_app_language(BaseLanguage.Enum.ZH)
        worker = UnpackWorker("game", direct=True, script_only=False)
        results = []
        worker.finished.connect(results.append)
        worker.run()
        assert results[0]["message"] == "未找到可解包的 RPA 文件，或所有解包方式均失败。"
    finally:
        Localizer.set_app_language(original)


def test_unpack_worker_unknown_error_falls_back(monkeypatch) -> None:
    """非 Packer 异常走通用兜底文案，不把异常文本直接抛给界面。"""

    class RaisingPacker:
        def unpack_rpa_files(self, game_dir, **kwargs):
            raise RuntimeError("boom")

    monkeypatch.setattr(pack_page_module, "Packer", RaisingPacker)
    worker = UnpackWorker("game", direct=True, script_only=False)
    results = []
    worker.finished.connect(results.append)
    worker.run()

    assert results[0]["level"] == "error"
    assert "boom" not in results[0]["message"]
