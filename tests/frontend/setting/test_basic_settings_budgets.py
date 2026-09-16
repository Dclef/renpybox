import dataclasses
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

from frontend.Setting.BasicSettingsPage import BasicSettingsPage
from module.Config import Config

_APP = None


def test_balanced_throughput_button_only_changes_three_budgets(tmp_path, monkeypatch):
    global _APP
    app = QApplication.instance() or QApplication([])
    _APP = app
    config_path = tmp_path / "config.json"
    monkeypatch.setattr(Config, "CONFIG_PATH", str(config_path))
    config = Config(
        token_threshold=7,
        max_batch_source_tokens=0,
        max_output_tokens=8192,
        max_workers=8,
        rpm_threshold=120,
        request_timeout=240,
        max_round=5,
        result_checker_retry_count_threshold=True,
    )
    config.save(str(config_path), strict=True)
    page = BasicSettingsPage("test", None)
    before = dataclasses.asdict(Config().load())

    try:
        page.balanced_throughput_button.click()
        app.processEvents()
        after = dataclasses.asdict(Config().load())
        expected = dict(before, token_threshold=20, max_batch_source_tokens=0, max_output_tokens=0)
        assert after == expected
        assert page._token_threshold_spin.value() == 20
        assert page._max_batch_source_tokens_spin.value() == 0
        assert page._max_output_tokens_spin.value() == 0

        page._max_batch_source_tokens_spin.setValue(2048)
        page._max_output_tokens_spin.setValue(16384)
        edited = Config().load()
        assert edited.max_batch_source_tokens == 2048
        assert edited.max_output_tokens == 16384
        assert edited.max_workers == 8
    finally:
        page.close()
        page.deleteLater()
        app.processEvents()
