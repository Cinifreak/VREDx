# Created by Scott Rafferty @ Pyre Labs for use with the wider visualisation community.

"""Blender-inspired color picker for MaterialX color inputs."""

import math

from PySide6 import QtCore, QtGui, QtWidgets

from . import style

_WHEEL_SIZE = 180
_STRIP_WIDTH = 16
_WHEEL_GAP = 5
_INNER_WIDTH = _WHEEL_SIZE + _WHEEL_GAP + _STRIP_WIDTH
_PANEL_PAD = 8
_PICKER_WIDTH = _INNER_WIDTH + _PANEL_PAD * 2
_ROW_GAP = 2
_PICKER_QSS = """
QTabWidget#VredXModeTabs::pane {
    border: none; background: transparent; padding: 0; margin: 0;
}
QTabWidget#VredXModeTabs QTabBar::tab {
    min-width: 0; padding: 5px 4px;
}
QFrame#VredXSliderRow {
    background: #232325; border: 1px solid #1a1a1c; border-radius: 3px;
}
"""


def pick_color(initial, parent=None):
    """Modal color picker; returns (r, g, b) floats in 0..1 or None."""
    dialog = VredColorDialog(initial, parent)
    if dialog.exec() != QtWidgets.QDialog.Accepted:
        return None
    color = dialog.selected_color()
    return color.redF(), color.greenF(), color.blueF()


class _ColorWheel(QtWidgets.QWidget):
    """Circular hue/saturation picker (Blender-style)."""

    color_changed = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._hue = 0.0
        self._sat = 1.0
        self._cache = None
        self.setFixedSize(_WHEEL_SIZE, _WHEEL_SIZE)
        self.setMouseTracking(True)

    def set_hs(self, hue, saturation):
        self._hue = max(0.0, min(1.0, float(hue)))
        self._sat = max(0.0, min(1.0, float(saturation)))
        self.update()

    def hue_sat(self):
        return self._hue, self._sat

    def _radius(self):
        return min(self.width(), self.height()) / 2.0 - 6.0

    def _center(self):
        return QtCore.QPointF(self.width() / 2.0, self.height() / 2.0)

    def _ensure_cache(self):
        if self._cache is not None:
            return
        size = self.size()
        image = QtGui.QImage(size, QtGui.QImage.Format.Format_ARGB32)
        cx = size.width() / 2.0
        cy = size.height() / 2.0
        radius = self._radius()
        for y in range(size.height()):
            for x in range(size.width()):
                dx = x - cx + 0.5
                dy = y - cy + 0.5
                dist = math.hypot(dx, dy)
                if dist > radius:
                    image.setPixelColor(x, y, QtGui.QColor(0, 0, 0, 0))
                    continue
                angle = math.atan2(dy, dx)
                hue = (angle / (2.0 * math.pi)) % 1.0
                sat = min(1.0, dist / radius)
                color = QtGui.QColor.fromHsvF(hue, sat, 1.0)
                image.setPixelColor(x, y, color)
        self._cache = QtGui.QPixmap.fromImage(image)

    def paintEvent(self, _event):
        self._ensure_cache()
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        if self._cache is not None:
            painter.drawPixmap(0, 0, self._cache)
        center = self._center()
        radius = self._radius()
        angle = self._hue * 2.0 * math.pi
        dist = self._sat * radius
        handle = QtCore.QPointF(
            center.x() + math.cos(angle) * dist,
            center.y() + math.sin(angle) * dist)
        painter.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255), 2))
        painter.setBrush(QtCore.Qt.NoBrush)
        painter.drawEllipse(handle, 5.0, 5.0)
        painter.setPen(QtGui.QPen(QtGui.QColor(20, 20, 22), 1))
        painter.drawEllipse(handle, 5.0, 5.0)

    def _pick_at(self, pos):
        center = self._center()
        dx = pos.x() - center.x()
        dy = pos.y() - center.y()
        dist = math.hypot(dx, dy)
        radius = self._radius()
        if dist > radius and dist > 0:
            scale = radius / dist
            dx *= scale
            dy *= scale
            dist = radius
        angle = math.atan2(dy, dx)
        self._hue = (angle / (2.0 * math.pi)) % 1.0
        self._sat = min(1.0, dist / max(radius, 0.001))
        self.update()
        self.color_changed.emit()

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self._pick_at(event.position())

    def mouseMoveEvent(self, event):
        if event.buttons() & QtCore.Qt.LeftButton:
            self._pick_at(event.position())


class _ValueStrip(QtWidgets.QWidget):
    """Vertical value (brightness) slider."""

    value_changed = QtCore.Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._hue = 0.0
        self._sat = 1.0
        self._val = 1.0
        self.setFixedSize(_STRIP_WIDTH, _WHEEL_SIZE)
        self.setMouseTracking(True)

    def set_hs(self, hue, saturation):
        self._hue = hue
        self._sat = saturation
        self.update()

    def set_value(self, value):
        self._val = max(0.0, min(1.0, float(value)))
        self.update()

    def value(self):
        return self._val

    def paintEvent(self, _event):
        painter = QtGui.QPainter(self)
        top = QtGui.QColor.fromHsvF(self._hue, self._sat, 1.0)
        bottom = QtGui.QColor.fromHsvF(self._hue, self._sat, 0.0)
        grad = QtGui.QLinearGradient(0, 0, 0, self.height())
        grad.setColorAt(0.0, top)
        grad.setColorAt(1.0, bottom)
        painter.fillRect(self.rect(), grad)
        painter.setPen(QtGui.QPen(QtGui.QColor(20, 20, 22), 1))
        painter.drawRect(0, 0, self.width() - 1, self.height() - 1)
        y = int((1.0 - self._val) * (self.height() - 1))
        painter.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255), 2))
        painter.drawLine(0, y, self.width(), y)

    def _pick_at(self, pos):
        self._val = max(0.0, min(
            1.0, 1.0 - pos.y() / max(1, self.height() - 1)))
        self.update()
        self.value_changed.emit(self._val)

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self._pick_at(event.position())

    def mouseMoveEvent(self, event):
        if event.buttons() & QtCore.Qt.LeftButton:
            self._pick_at(event.position())


class _ChannelRow(QtWidgets.QWidget):
    """Label + slider + numeric field inside a bordered container."""

    value_changed = QtCore.Signal(float)

    def __init__(self, label, minimum, maximum, decimals, parent=None):
        super().__init__(parent)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding,
            QtWidgets.QSizePolicy.Fixed)

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, _ROW_GAP, 0, _ROW_GAP)
        outer.setSpacing(0)

        box = QtWidgets.QFrame(self)
        box.setObjectName("VredXSliderRow")
        box.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding,
            QtWidgets.QSizePolicy.Fixed)
        layout = QtWidgets.QHBoxLayout(box)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(6)
        name = QtWidgets.QLabel(label, box)
        name.setFixedWidth(14)
        layout.addWidget(name)
        self.slider = QtWidgets.QSlider(QtCore.Qt.Horizontal, box)
        self.slider.setRange(0, 1000)
        self.slider.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding,
            QtWidgets.QSizePolicy.Fixed)
        self.spin = QtWidgets.QDoubleSpinBox(box)
        self.spin.setRange(minimum, maximum)
        self.spin.setDecimals(decimals)
        self.spin.setSingleStep(1.0 / (10 ** decimals))
        self.spin.setFixedWidth(58)
        self.spin.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
        layout.addWidget(self.slider, 1)
        layout.addWidget(self.spin)
        outer.addWidget(box)

        self._minimum = minimum
        self._maximum = maximum
        self._updating = False
        self.slider.valueChanged.connect(self._from_slider)
        self.spin.valueChanged.connect(self._from_spin)

    def set_value(self, value):
        self._updating = True
        value = max(self._minimum, min(self._maximum, float(value)))
        self.spin.setValue(value)
        span = self._maximum - self._minimum
        if span > 0:
            t = (value - self._minimum) / span
            self.slider.blockSignals(True)
            self.slider.setValue(int(round(t * 1000)))
            self.slider.blockSignals(False)
        self._updating = False

    def value(self):
        return self.spin.value()

    def _from_slider(self, ticks):
        if self._updating:
            return
        span = self._maximum - self._minimum
        value = self._minimum + span * ticks / 1000.0
        self._updating = True
        self.spin.setValue(value)
        self._updating = False
        self.value_changed.emit(value)

    def _from_spin(self, value):
        if self._updating:
            return
        span = self._maximum - self._minimum
        if span > 0:
            t = (value - self._minimum) / span
            self.slider.blockSignals(True)
            self.slider.setValue(int(round(t * 1000)))
            self.slider.blockSignals(False)
        self.value_changed.emit(value)


class _PickerPanel(QtWidgets.QWidget):
    """Wheel + value strip + RGB/HSV/Hex controls."""

    color_changed = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._syncing = False
        self.setFixedWidth(_PICKER_WIDTH)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(_PANEL_PAD, _PANEL_PAD, _PANEL_PAD, _PANEL_PAD)
        layout.setSpacing(8)

        wheel_container = QtWidgets.QWidget(self)
        wheel_container.setFixedWidth(_INNER_WIDTH)
        wheel_row = QtWidgets.QHBoxLayout(wheel_container)
        wheel_row.setContentsMargins(0, 0, 0, 0)
        wheel_row.setSpacing(_WHEEL_GAP)
        self._wheel = _ColorWheel(wheel_container)
        self._wheel.color_changed.connect(self._from_wheel)
        wheel_row.addWidget(self._wheel)
        self._strip = _ValueStrip(wheel_container)
        self._strip.value_changed.connect(self._from_strip)
        wheel_row.addWidget(self._strip)
        layout.addWidget(wheel_container, 0, QtCore.Qt.AlignLeft)

        self._mode_tabs = QtWidgets.QTabWidget(self)
        self._mode_tabs.setObjectName("VredXModeTabs")
        self._mode_tabs.setDocumentMode(True)
        self._mode_tabs.setFixedWidth(_INNER_WIDTH)
        self._mode_tabs.tabBar().setExpanding(True)
        self._rows = {}
        for mode, labels, ranges in (
            ("RGB", "RGB", ((0.0, 1.0),) * 3),
            ("HSV", "HSV", ((0.0, 1.0),) * 3),
        ):
            page = QtWidgets.QWidget()
            page.setMinimumWidth(_INNER_WIDTH)
            form = QtWidgets.QVBoxLayout(page)
            form.setContentsMargins(0, 0, 0, 0)
            form.setSpacing(0)
            self._rows[mode] = []
            for label, (lo, hi) in zip(labels, ranges):
                row = _ChannelRow(label, lo, hi, 3, page)
                row.value_changed.connect(self._from_channels)
                form.addWidget(row)
                self._rows[mode].append(row)
            form.addStretch(1)
            self._mode_tabs.addTab(page, mode)

        hex_page = QtWidgets.QWidget()
        hex_page.setMinimumWidth(_INNER_WIDTH)
        hex_outer = QtWidgets.QVBoxLayout(hex_page)
        hex_outer.setContentsMargins(0, _ROW_GAP, 0, _ROW_GAP)
        hex_box = QtWidgets.QFrame(hex_page)
        hex_box.setObjectName("VredXSliderRow")
        hex_box.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding,
            QtWidgets.QSizePolicy.Fixed)
        hex_layout = QtWidgets.QHBoxLayout(hex_box)
        hex_layout.setContentsMargins(6, 4, 6, 4)
        hex_layout.setSpacing(6)
        hex_layout.addWidget(QtWidgets.QLabel("#", hex_box))
        self._hex_edit = QtWidgets.QLineEdit(hex_box)
        self._hex_edit.setMaxLength(6)
        self._hex_edit.setPlaceholderText("RRGGBB")
        self._hex_edit.editingFinished.connect(self._from_hex)
        hex_layout.addWidget(self._hex_edit, 1)
        hex_outer.addWidget(hex_box)
        hex_outer.addStretch(1)
        self._mode_tabs.addTab(hex_page, "Hex")
        self._mode_tabs.currentChanged.connect(self._mode_changed)
        layout.addWidget(self._mode_tabs, 0, QtCore.Qt.AlignLeft)

    def set_color(self, color: QtGui.QColor):
        self._syncing = True
        h, s, v, _ = color.getHsvF()
        if h < 0:
            h = 0.0
        self._wheel.set_hs(h, s)
        self._strip.set_hs(h, s)
        self._strip.set_value(v)
        self._rows["RGB"][0].set_value(color.redF())
        self._rows["RGB"][1].set_value(color.greenF())
        self._rows["RGB"][2].set_value(color.blueF())
        self._rows["HSV"][0].set_value(h)
        self._rows["HSV"][1].set_value(s)
        self._rows["HSV"][2].set_value(v)
        self._hex_edit.blockSignals(True)
        self._hex_edit.setText(color.name()[1:].upper())
        self._hex_edit.blockSignals(False)
        self._syncing = False

    def current_color(self):
        h, s = self._wheel.hue_sat()
        v = self._strip.value()
        return QtGui.QColor.fromHsvF(h, s, v)

    def _from_wheel(self):
        if self._syncing:
            return
        h, s = self._wheel.hue_sat()
        v = self._strip.value()
        self._set_from_hsv(h, s, v)

    def _from_strip(self, _value):
        if self._syncing:
            return
        self._from_wheel()

    def _from_channels(self, _value):
        if self._syncing:
            return
        mode = self._mode_tabs.tabText(self._mode_tabs.currentIndex())
        if mode == "RGB":
            color = QtGui.QColor.fromRgbF(
                self._rows["RGB"][0].value(),
                self._rows["RGB"][1].value(),
                self._rows["RGB"][2].value())
            self._apply_color(color)
        elif mode == "HSV":
            self._set_from_hsv(
                self._rows["HSV"][0].value(),
                self._rows["HSV"][1].value(),
                self._rows["HSV"][2].value())

    def _from_hex(self):
        if self._syncing:
            return
        text = self._hex_edit.text().strip().lstrip("#")
        if len(text) != 6:
            return
        color = QtGui.QColor("#" + text)
        if color.isValid():
            self._apply_color(color)

    def _set_from_hsv(self, h, s, v):
        self._apply_color(QtGui.QColor.fromHsvF(h, s, v))

    def _apply_color(self, color):
        self._syncing = True
        self.set_color(color)
        self._syncing = False
        self.color_changed.emit()

    def _mode_changed(self, _index):
        pass


class VredColorDialog(QtWidgets.QDialog):
    """MaterialX-friendly color picker (wheel + RGB/HSV/hex)."""

    def __init__(self, initial=None, parent=None):
        super().__init__(parent)
        self.setObjectName("VredXRoot")
        self.setWindowTitle("Pick Color")
        self.setModal(True)
        self.setStyleSheet(style.WIDGET_QSS + _PICKER_QSS)
        style.apply_vred_appearance(self)

        initial = (initial if isinstance(initial, QtGui.QColor)
                   else QtGui.QColor(128, 128, 128))
        self._color = QtGui.QColor(initial)

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        self._picker = _PickerPanel(self)
        self._picker.color_changed.connect(self._on_color_changed)
        root.addWidget(self._picker)

        buttons = QtWidgets.QHBoxLayout()
        buttons.setSpacing(8)
        ok = QtWidgets.QPushButton("OK", self)
        cancel = QtWidgets.QPushButton("Cancel", self)
        ok.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding,
            QtWidgets.QSizePolicy.Fixed)
        cancel.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding,
            QtWidgets.QSizePolicy.Fixed)
        ok.clicked.connect(self.accept)
        cancel.clicked.connect(self.reject)
        buttons.addWidget(ok, 1)
        buttons.addWidget(cancel, 1)
        root.addLayout(buttons)

        self._picker.set_color(self._color)
        self._lock_dialog_size()

    def _lock_dialog_size(self):
        """Prevent the user from resizing the picker window."""
        self.setSizeGripEnabled(False)
        self.setWindowFlag(QtCore.Qt.MSWindowsFixedSizeDialogHint, True)
        self.adjustSize()
        self.setFixedSize(self.size())

    def selected_color(self):
        return QtGui.QColor(self._color)

    def _on_color_changed(self):
        self._color = self._picker.current_color()
