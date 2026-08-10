import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

from frontend.RenpyToolbox.GameModPage import GameModPage


APP = QApplication.instance() or QApplication([])


def test_game_mod_page_has_buttons_and_disables_them_while_running(tmp_path):
    page = GameModPage("game-mod")

    assert page.gallery_install_button.text() == "安装"
    assert page.gallery_uninstall_button.text() == "卸载"
    assert page.urm_install_button.text() == "安装"
    assert page.urm_uninstall_button.text() == "卸载"
    assert page.simple_modifier_install_button.text() == "安装"
    assert page.simple_modifier_uninstall_button.text() == "卸载"
    assert page.legacy_dumuqiao_cleanup_button.text() == "删除旧版独木桥"
    assert page.legacy_dumuqiao_cleanup_button.isHidden()
    assert not hasattr(page, "quick_menu_install_button")
    assert all(button.isEnabled() for button in page._buttons)

    game_dir = tmp_path / "game"
    game_dir.mkdir()
    (game_dir / "dumuqiao.rpy").write_text("legacy", encoding="utf-8")
    page.game_dir_edit.setText(str(game_dir))
    page._refresh_status()
    assert not page.legacy_dumuqiao_cleanup_button.isHidden()
    assert "检测到旧版独木桥" in page.legacy_dumuqiao_label.text()

    page._set_running(True)

    assert not any(button.isEnabled() for button in page._buttons)
    page.close()
