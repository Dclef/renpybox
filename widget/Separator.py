from PyQt5.QtWidgets import QWidget
from PyQt5.QtWidgets import QVBoxLayout
from qfluentwidgets import isDarkTheme, qconfig


class Separator(QWidget):

    def __init__(self, parent: QWidget = None, horizontal: bool = False) -> None:
        super().__init__(parent)

        if horizontal == True:
            # 设置容器
            self.root = QVBoxLayout(self)
            self.root.setContentsMargins(4, 0, 4, 0) # 左、上、右、下

            # 添加分割线
            self.line = QWidget(self)
            self.line.setFixedWidth(1)
            self.root.addWidget(self.line)
        else:
            # 设置容器
            self.root = QVBoxLayout(self)
            self.root.setContentsMargins(0, 4, 0, 4) # 左、上、右、下

            # 添加分割线
            self.line = QWidget(self)
            self.line.setFixedHeight(1)
            self.root.addWidget(self.line)

        # 设置初始颜色
        self._update_color()
        
        # 监听主题变化
        qconfig.themeChanged.connect(self._update_color)

    def _update_color(self):
        """根据主题更新分割线颜色"""
        if isDarkTheme():
            self.line.setStyleSheet("QWidget { background-color: #404040; }")
        else:
            self.line.setStyleSheet("QWidget { background-color: #C0C0C0; }")