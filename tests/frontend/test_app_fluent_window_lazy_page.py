from PyQt5.QtWidgets import QApplication
from PyQt5.QtWidgets import QWidget

from frontend.AppFluentWindow import LazyPage


APP = QApplication.instance() or QApplication([])


def test_lazy_page_does_not_load_on_attribute_probe() -> None:
    loaded: list[str] = []

    def loader() -> QWidget:
        loaded.append("loaded")
        return QWidget()

    page = LazyPage("lazy_page", "测试页面", loader)

    assert hasattr(page, "unknown_page_method") is False
    assert loaded == []


def test_lazy_toolbox_get_tool_page_loads_once() -> None:
    loaded: list[str] = []
    tool_page = QWidget()

    class FakeToolbox(QWidget):
        def get_tool_page(self, key: str) -> QWidget:
            assert key == "proofreading"
            return tool_page

    def loader() -> QWidget:
        loaded.append("loaded")
        return FakeToolbox()

    page = LazyPage("lazy_toolbox_page", "工具箱", loader)

    assert page.get_tool_page("proofreading") is tool_page
    assert page.get_tool_page("proofreading") is tool_page
    assert loaded == ["loaded"]
