import os
from collections import Counter

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtGui import QImage
from PyQt5.QtWidgets import QApplication

from widget.WaveformWidget import WaveformWidget


APP = QApplication.instance() or QApplication([])


def _render(widget: WaveformWidget) -> QImage:
    image = QImage(widget.size(), QImage.Format_ARGB32)
    image.fill(0)
    widget.render(image)
    return image


def _non_background_pixels(image: QImage) -> int:
    pixels = [
        image.pixelColor(x, y).getRgb()
        for y in range(image.height())
        for x in range(image.width())
    ]
    background = Counter(pixels).most_common(1)[0][0]
    return sum(pixel != background for pixel in pixels)


def test_waveform_uses_geometry_bars_instead_of_font_glyphs() -> None:
    widget = WaveformWidget()
    widget.set_matrix_size(16, 8)
    widget.show()
    APP.processEvents()

    idle_pixels = _non_background_pixels(_render(widget))
    for value in (0, 2, 5, 3, 8, 4):
        widget.add_value(value)
    APP.processEvents()

    assert _non_background_pixels(_render(widget)) > idle_pixels
    widget.close()
