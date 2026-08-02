import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

from frontend.RenpyToolbox.GameModPage import GameModPage


APP = QApplication.instance() or QApplication([])


def test_game_mod_page_has_buttons_and_disables_them_while_running():
    page = GameModPage("game-mod")

    assert page.urm_install_button.text() == "安装"
    assert page.urm_uninstall_button.text() == "卸载"
    assert page.quick_menu_install_button.text() == "安装"
    assert page.quick_menu_uninstall_button.text() == "卸载"
    assert all(button.isEnabled() for button in page._buttons)

    page._set_running(True)

    assert not any(button.isEnabled() for button in page._buttons)
    page.close()
