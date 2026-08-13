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
