"""Reusable custom widgets."""
from __future__ import annotations

from PySide6.QtCore import (Property, QEasingCurve, QPropertyAnimation, QRectF, QSize, Qt,
                            Signal)
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QHBoxLayout, QLabel, QPushButton,
                               QSlider, QVBoxLayout, QWidget)

from interface import theme


class ToggleSwitch(QCheckBox):
    """Animated pill switch."""

    def __init__(self, checked: bool = False, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(38, 22)
        self._pos = 1.0 if checked else 0.0
        self.setChecked(checked)
        self._anim = QPropertyAnimation(self, b"knob", self)
        self._anim.setDuration(140)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self.toggled.connect(self._animate)

    def sizeHint(self):
        return QSize(38, 22)

    def hitButton(self, pos):
        return self.rect().contains(pos)

    def _animate(self, on):
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def set_silent(self, on: bool):
        self.blockSignals(True)
        self.setChecked(on)
        self._pos = 1.0 if on else 0.0
        self.blockSignals(False)
        self.update()

    def _get(self):
        return self._pos

    def _set(self, v):
        self._pos = v
        self.update()

    knob = Property(float, _get, _set)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(1, 1, self.width() - 2, self.height() - 2)
        off = QColor(theme.BORDER)
        on = QColor(theme.CYAN)
        c = QColor(int(off.red() + (on.red() - off.red()) * self._pos * 0.35),
                   int(off.green() + (on.green() - off.green()) * self._pos * 0.35),
                   int(off.blue() + (on.blue() - off.blue()) * self._pos * 0.35))
        p.setPen(QPen(on if self._pos > 0.5 else QColor("#2f3850"), 1))
        p.setBrush(c)
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        d = r.height() - 6
        x = r.left() + 3 + (r.width() - d - 6) * self._pos
        p.setPen(Qt.NoPen)
        p.setBrush(on if self._pos > 0.5 else QColor(theme.MUTED))
        p.drawEllipse(QRectF(x, r.top() + 3, d, d))


class LabeledSlider(QWidget):
    """Label + value readout + slider, mapping a float range."""
    valueChanged = Signal(float)

    def __init__(self, label: str, lo: float, hi: float, value: float, step: float = 0.01,
                 decimals: int | None = None, suffix: str = "", tip: str = "", parent=None):
        super().__init__(parent)
        self.lo, self.hi, self.step = lo, hi, step
        self.decimals = decimals if decimals is not None else (0 if step >= 1 else (1 if step >= 0.1 else 2))
        self.suffix = suffix
        self._steps = max(1, int(round((hi - lo) / step)))
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 2, 0, 2)
        lay.setSpacing(3)
        top = QHBoxLayout()
        self.label = QLabel(label)
        self.label.setObjectName("muted")
        self.readout = QLabel()
        self.readout.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        top.addWidget(self.label)
        top.addStretch()
        top.addWidget(self.readout)
        lay.addLayout(top)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, self._steps)
        self.slider.setCursor(Qt.PointingHandCursor)
        lay.addWidget(self.slider)
        if tip:
            self.setToolTip(tip)
        self.slider.valueChanged.connect(self._changed)
        self.set_value(value, silent=True)

    def value(self) -> float:
        v = self.lo + self.slider.value() * (self.hi - self.lo) / self._steps
        return round(v) if self.decimals == 0 else v

    def set_value(self, v: float, silent: bool = False):
        pos = int(round((float(v) - self.lo) / (self.hi - self.lo) * self._steps)) if self.hi > self.lo else 0
        if silent:
            self.slider.blockSignals(True)
        self.slider.setValue(pos)
        self.slider.blockSignals(False)
        self._update_readout()

    def _update_readout(self):
        v = self.value()
        self.readout.setText(f"{v:.{self.decimals}f}{self.suffix}")

    def _changed(self, _):
        self._update_readout()
        self.valueChanged.emit(self.value())


class ColorButton(QPushButton):
    colorChanged = Signal(str)

    def __init__(self, color: str = "#ffffff", parent=None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(64, 26)
        self._color = color
        self.clicked.connect(self._pick)
        self._apply()

    def color(self) -> str:
        return self._color

    def set_color(self, c: str):
        self._color = c
        self._apply()

    def _apply(self):
        self.setStyleSheet(f"background:{self._color}; border:2px solid {theme.BORDER}; border-radius:8px;")

    def _pick(self):
        c = QColorDialog.getColor(QColor(self._color), self.window(), "Pick a colour")
        if c.isValid():
            self.set_color(c.name())
            self.colorChanged.emit(c.name())


class Row(QWidget):
    """Label on the left, widget on the right."""

    def __init__(self, label: str, widget: QWidget, tip: str = "", parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 3, 0, 3)
        lab = QLabel(label)
        lab.setObjectName("muted")
        lab.setWordWrap(True)
        lay.addWidget(lab, 1)
        lay.addWidget(widget, 0, Qt.AlignRight)
        if tip:
            self.setToolTip(tip)


def section(text: str) -> QLabel:
    lab = QLabel(text.upper())
    lab.setObjectName("section")
    return lab


class SegmentedControl(QWidget):
    changed = Signal(str)

    def __init__(self, options, current: str, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self.buttons = {}
        for o in options:
            b = QPushButton(o)
            b.setObjectName("seg")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, o=o: self.set_value(o, emit=True))
            lay.addWidget(b)
            self.buttons[o] = b
        self.set_value(current)

    def set_value(self, v, emit=False):
        for k, b in self.buttons.items():
            b.setChecked(k == v)
        self._value = v
        if emit:
            self.changed.emit(v)

    def value(self):
        return self._value
