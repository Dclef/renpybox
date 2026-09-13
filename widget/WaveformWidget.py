import time

from PyQt5.QtCore import Qt
from PyQt5.QtCore import QRectF
from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QColor
from PyQt5.QtGui import QFont
from PyQt5.QtGui import QPainter
from PyQt5.QtWidgets import QLabel
from PyQt5.QtWidgets import QSizePolicy

from widget.ThemeHelper import get_theme_accent_color

class WaveformWidget(QLabel):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # 自动填充背景
        # self.setAutoFillBackground(True)

        # 设置字体
        self.font = QFont("Consolas", 8)

        # 每个字符所占用的空间
        self.point_size = self.font.pointSize()

        # 历史数据
        self.history = [0]

        # 设置矩阵大小
        self.set_matrix_size(50, 20)

        # 刷新率
        self.refresh_rate = 2

        # 最近一次添加数据的时间
        self.last_add_value_time = 0

        # 开始刷新
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(int(1000 / self.refresh_rate))

    # 刷新
    def tick(self):
        if time.time() - self.last_add_value_time >= (1 / self.refresh_rate):
            # 如果周期内数据没有更新，则重复最后一个数据
            self.repeat()

        # 刷新界面
        self.update()

    def paintEvent(self, event):
        # 用原生几何图形绘制吞吐柱条，避免 Unicode 方块依赖字体回退。
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 归一化以增大波形起伏
        min_val = min(self.history)
        max_val = max(self.history)
        if max_val - min_val == 0 and self.history[0] == 0:
            values = [0 for i in self.history]
        elif max_val - min_val == 0 and self.history[0] != 0:
            values = [1 for i in self.history]
        else:
            values = [(v - min_val) / (max_val - min_val) for v in self.history]

        accent = QColor(get_theme_accent_color())
        has_throughput = max_val > 0
        if not has_throughput:
            # 空闲时保留一条低对比度基线，不制造虚假的吞吐数据。
            baseline = QColor(accent)
            baseline.setAlpha(56)
            painter.setPen(baseline)
            painter.drawLine(0, self.height() - 1, self.width(), self.height() - 1)
            return

        accent.setAlpha(218)
        painter.setBrush(accent)
        painter.setPen(Qt.NoPen)
        count = max(1, self.matrix_width)
        slot_width = self.width() / count
        gap = min(2.0, max(0.5, slot_width * 0.24))
        for index, value in enumerate(values[-count:]):
            bar_height = max(2.0, (self.height() - 4) * value)
            x = index * slot_width + gap / 2
            width = max(1.0, slot_width - gap)
            y = self.height() - bar_height
            painter.drawRoundedRect(QRectF(x, y, width, bar_height), 1.5, 1.5)

    # 重复最后的数据
    def repeat(self):
        self.add_value(self.history[-1] if len(self.history) > 0 else 0)

    # 添加数据
    def add_value(self, value: int):
        if len(self.history) >= self.matrix_width:
            self.history.pop(0)

        self.history.append(value)

        # 记录下最后添加数据的时间
        self.last_add_value_time = time.time()

    # 设置矩阵大小
    def set_matrix_size(self, width: int, height: int):
        self.matrix_width = width
        self.matrix_height = height
        self.max_width = self.matrix_width * self.point_size
        self.max_height = self.matrix_height * self.point_size
        self.setMinimumWidth(0)
        self.setFixedHeight(self.max_height)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.history = [0 for i in range(self.matrix_width)]
