from __future__ import annotations

from PyQt5.QtCore import QEasingCurve
from PyQt5.QtCore import QRectF
from PyQt5.QtCore import Qt
from PyQt5.QtCore import QVariantAnimation
from PyQt5.QtCore import pyqtProperty
from PyQt5.QtGui import QColor
from PyQt5.QtGui import QLinearGradient
from PyQt5.QtGui import QPainter
from PyQt5.QtGui import QPainterPath
from PyQt5.QtWidgets import QWidget
from qfluentwidgets import ProgressBar
from qfluentwidgets import isDarkTheme


class DownloadProgressBar(ProgressBar):
    """带圆角轨道、渐变填充与流光动效的下载进度条。

    qfluentwidgets 自带的 ProgressBar 轨道只是一条 1px 直线，配合 4px 的条高在
    卡片里显得很单薄，这里整体重绘：轨道做成同高的胶囊，填充用主题色渐变，并在
    下载进行中叠一层缓慢移动的高光，让“正在传输”这件事看得出来。
    """

    BAR_HEIGHT = 8

    # 靛蓝渐变与应用主色保持一致：浅色主题向深处收一档，深色主题向亮处提。
    LIGHT_BAR_START = QColor("#6366F1")
    LIGHT_BAR_END = QColor("#4338CA")
    DARK_BAR_START = QColor("#A5B4FC")
    DARK_BAR_END = QColor("#6366F1")

    LIGHT_TRACK = QColor(0, 0, 0, 26)
    DARK_TRACK = QColor(255, 255, 255, 32)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(self.BAR_HEIGHT)
        self.setTextVisible(False)

        self._shimmer = 0.0
        self._shimmer_ani = QVariantAnimation(self)
        self._shimmer_ani.setStartValue(0.0)
        self._shimmer_ani.setEndValue(1.0)
        self._shimmer_ani.setDuration(1400)
        self._shimmer_ani.setLoopCount(-1)
        self._shimmer_ani.setEasingCurve(QEasingCurve.Linear)
        self._shimmer_ani.valueChanged.connect(self._on_shimmer_changed)

    # 流光 ------------------------------------------------------------------
    def _on_shimmer_changed(self, value: object) -> None:
        try:
            self._shimmer = float(value)
        except (TypeError, ValueError):
            self._shimmer = 0.0
        self.update()

    def getShimmer(self) -> float:
        return self._shimmer

    def setShimmer(self, value: float) -> None:
        self._shimmer = float(value)
        self.update()

    def startShimmer(self) -> None:
        if self._shimmer_ani.state() != QVariantAnimation.Running:
            self._shimmer_ani.start()

    def stopShimmer(self) -> None:
        self._shimmer_ani.stop()
        self._shimmer = 0.0
        self.update()

    def hideEvent(self, event) -> None:
        # 隐藏后没人看得见，让定时器停下来别白烧 CPU。
        self.stopShimmer()
        super().hideEvent(event)

    # 绘制 ------------------------------------------------------------------
    def _bar_gradient(self, width: float) -> QLinearGradient:
        dark = isDarkTheme()
        gradient = QLinearGradient(0, 0, max(1.0, width), 0)
        gradient.setColorAt(0, self.DARK_BAR_START if dark else self.LIGHT_BAR_START)
        gradient.setColorAt(1, self.DARK_BAR_END if dark else self.LIGHT_BAR_END)
        return gradient

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHints(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)

        height = float(self.height())
        width = float(self.width())
        radius = height / 2

        # 轨道
        painter.setBrush(self.DARK_TRACK if isDarkTheme() else self.LIGHT_TRACK)
        painter.drawRoundedRect(QRectF(0, 0, width, height), radius, radius)

        span = self.maximum() - self.minimum()
        if span <= 0:
            return

        ratio = max(0.0, min(1.0, (self.val - self.minimum()) / span))
        filled = width * ratio
        if filled <= 0:
            return

        # 已完成部分：宽度不足一个圆角时仍按胶囊画，避免出现方角小块。
        filled = max(filled, height)
        bar_rect = QRectF(0, 0, min(filled, width), height)
        bar_path = QPainterPath()
        bar_path.addRoundedRect(bar_rect, radius, radius)

        if self.isError():
            painter.setBrush(
                QColor(255, 153, 164) if isDarkTheme() else QColor(196, 43, 28)
            )
        elif self.isPaused():
            painter.setBrush(
                QColor(252, 225, 0) if isDarkTheme() else QColor(157, 93, 0)
            )
        else:
            painter.setBrush(self._bar_gradient(bar_rect.width()))
        painter.drawPath(bar_path)

        if (
            self._shimmer_ani.state() != QVariantAnimation.Running
            or self.isError()
            or self.isPaused()
        ):
            return

        # 高光限制在已完成区域内滑动，宽度取条长的 1/3。
        painter.setClipPath(bar_path)
        glow_width = max(height * 4, bar_rect.width() / 3)
        glow_x = -glow_width + self._shimmer * (bar_rect.width() + glow_width)
        glow = QLinearGradient(glow_x, 0, glow_x + glow_width, 0)
        glow.setColorAt(0.0, QColor(255, 255, 255, 0))
        glow.setColorAt(0.5, QColor(255, 255, 255, 70))
        glow.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.setBrush(glow)
        painter.drawRect(bar_rect)

    shimmer = pyqtProperty(float, getShimmer, setShimmer)
