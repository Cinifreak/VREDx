# Created by Scott Rafferty @ Pyre Labs for use with the wider visualisation community.

"""Material preview swatch driven by VRED's native preview API."""

from collections import deque

from PySide6 import QtCore, QtGui, QtWidgets

from ..vredbridge import vred_api
from . import style

_SWATCH_SIZE = 220
_PLACEHOLDER = "Send to VRED to see a preview"
_BLACK_KEY_THRESHOLD = 20


def _is_letterbox_pixel(color):
    return (color.red() <= _BLACK_KEY_THRESHOLD
            and color.green() <= _BLACK_KEY_THRESHOLD
            and color.blue() <= _BLACK_KEY_THRESHOLD)


def prepare_preview_image(image, background=None):
    """Replace VRED's black letterbox with the panel background color."""
    if image is None or image.isNull():
        return image
    background = background or style.PANEL_BG
    keyed = image.convertToFormat(QtGui.QImage.Format.Format_ARGB32)
    width = keyed.width()
    height = keyed.height()
    if width < 2 or height < 2:
        return keyed

    replace = set()
    queue = deque()
    for x in range(width):
        for y in (0, height - 1):
            if _is_letterbox_pixel(keyed.pixelColor(x, y)):
                queue.append((x, y))
    for y in range(height):
        for x in (0, width - 1):
            if _is_letterbox_pixel(keyed.pixelColor(x, y)):
                queue.append((x, y))

    while queue:
        x, y = queue.popleft()
        if (x, y) in replace:
            continue
        color = keyed.pixelColor(x, y)
        if not _is_letterbox_pixel(color):
            continue
        replace.add((x, y))
        keyed.setPixelColor(x, y, background)
        if x > 0:
            queue.append((x - 1, y))
        if x + 1 < width:
            queue.append((x + 1, y))
        if y > 0:
            queue.append((x, y - 1))
        if y + 1 < height:
            queue.append((x, y + 1))
    return keyed


class _PreviewSwatch(QtWidgets.QWidget):
    """Paints the preview centered on the panel background."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._image = None
        self._message = _PLACEHOLDER
        self.setFixedSize(_SWATCH_SIZE, _SWATCH_SIZE)
        self.setAttribute(QtCore.Qt.WA_OpaquePaintEvent, True)

    def set_image(self, image):
        self._image = image
        self._message = ""
        self.update()

    def set_message(self, text):
        self._image = None
        self._message = text or _PLACEHOLDER
        self.update()

    def _fit_size(self):
        if self._image is None or self._image.isNull():
            return QtCore.QSize(0, 0)
        return QtCore.QSize(self._image.size()).scaled(
            self.size(), QtCore.Qt.KeepAspectRatio)

    def paintEvent(self, _event):
        painter = QtGui.QPainter(self)
        painter.fillRect(self.rect(), style.PANEL_BG)
        if self._image is not None and not self._image.isNull():
            fit = self._fit_size()
            x = (self.width() - fit.width()) // 2
            y = (self.height() - fit.height()) // 2
            target = QtCore.QRect(x, y, fit.width(), fit.height())
            painter.drawImage(target, self._image)
            return
        if self._message:
            painter.setPen(QtGui.QColor(128, 128, 136))
            painter.drawText(self.rect(),
                             QtCore.Qt.AlignCenter | QtCore.Qt.TextWordWrap,
                             self._message)


class PreviewPanel(QtWidgets.QWidget):
    """Shows VRED's cached material swatch on the v-ball geometry."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("VredXPreviewPanel")
        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(self.backgroundRole(), style.PANEL_BG)
        self.setPalette(palette)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        self.swatch = _PreviewSwatch(self)
        layout.addWidget(self.swatch, 0, QtCore.Qt.AlignHCenter)

        self.status = QtWidgets.QLabel("", self)
        self.status.setWordWrap(True)
        self.status.setStyleSheet("color: #9a9a9f;")
        layout.addWidget(self.status)

        self.show_placeholder(_PLACEHOLDER)

    # ---------------------------------------------------------------- public

    @QtCore.Slot(object)
    def show_image(self, image):
        """Display a QImage swatch (scaled to fit)."""
        if image is None or image.isNull():
            self.show_placeholder("Preview not available yet")
            return
        image = prepare_preview_image(image)
        self.swatch.set_image(image)
        self.status.clear()

    def show_placeholder(self, text=_PLACEHOLDER):
        self.swatch.set_message(text)
        self.status.clear()

    def set_refreshing(self):
        self.show_placeholder("Rendering preview…")
