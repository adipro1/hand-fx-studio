"""Live preview with heads-up display."""
from __future__ import annotations

import time

import cv2
import numpy as np
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from core.gesture_recognition import GESTURE_LABELS
from interface import theme


class PreviewWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(320, 200)
        self.setAttribute(Qt.WA_OpaquePaintEvent)
        self._img: QImage | None = None
        self._buf: np.ndarray | None = None
        self.message: str | None = "Starting camera..."
        self.submessage: str = ""
        self.fps = 0.0
        self.hud = True
        self.gestures: list[tuple[str, str, float]] = []   # (label, gesture, pinch)
        self.status = ""
        self.recording = False
        self.rec_time = 0.0
        self.crop_guide: str | None = None
        self.crop_focus = 0.5
        self._toast: tuple[float, str] | None = None
        self._img_rect = QRectF()
        self.cine = None          # interface.hud.HudRenderer when the cinematic HUD is shown
        self.telemetry = None

    # ------------------------------------------------------------------
    def set_frame(self, rgb: np.ndarray):
        h, w = rgb.shape[:2]
        avail_w, avail_h = self.width(), self.height()
        s = min(avail_w / w, avail_h / h)
        tw, th = max(int(w * s), 2), max(int(h * s), 2)
        if (tw, th) != (w, h):
            interp = cv2.INTER_AREA if s < 1 else cv2.INTER_LINEAR
            rgb = cv2.resize(rgb, (tw, th), interpolation=interp)
        self._buf = np.ascontiguousarray(rgb)
        self._img = QImage(self._buf.data, tw, th, 3 * tw, QImage.Format_RGB888)
        self._img_rect = QRectF((avail_w - tw) / 2, (avail_h - th) / 2, tw, th)
        self.message = None
        self.update()

    def toast(self, text: str):
        self._toast = (time.perf_counter(), text)
        self.update()

    # ------------------------------------------------------------------
    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(theme.BG))
        p.setRenderHint(QPainter.Antialiasing)
        r = self._img_rect
        if self._img is not None:
            path = QPainterPath()
            path.addRoundedRect(r, 14, 14)
            p.setClipPath(path)
            p.drawImage(r.topLeft(), self._img)
            if self.crop_guide:
                self._draw_crop_guide(p, r)
            if self.cine is not None and self.telemetry is not None:
                hr, crop = self._crop_rect(r)
                try:
                    self.cine.draw(p, hr, self.telemetry, crop)
                except Exception:  # never let the HUD break the preview
                    import logging
                    logging.getLogger("hfx").exception("hud")
                p.setClipping(False)
            else:
                p.setClipping(False)
                if self.hud:
                    self._draw_hud(p, r)
        if self.message:
            self._draw_message(p)
        if self._toast:
            self._draw_toast(p, r if self._img is not None else QRectF(self.rect()))

    def _crop_rect(self, r: QRectF):
        target = {"9:16": 9 / 16, "1:1": 1.0}.get(self.crop_guide or "")
        if not target:
            return r, (0.0, 0.0, 1.0, 1.0)
        cw = r.height() * target
        x = r.left() + self.crop_focus * r.width() - cw / 2
        x = max(r.left(), min(r.right() - cw, x))
        return QRectF(x, r.top(), cw, r.height()), ((x - r.left()) / r.width(), 0.0, cw / r.width(), 1.0)

    def _draw_crop_guide(self, p: QPainter, r: QRectF):
        target = {"9:16": 9 / 16, "1:1": 1.0}.get(self.crop_guide)
        if not target:
            return
        cw = r.height() * target
        x = r.left() + self.crop_focus * r.width() - cw / 2
        x = max(r.left(), min(r.right() - cw, x))
        shade = QColor(0, 0, 0, 140)
        p.fillRect(QRectF(r.left(), r.top(), x - r.left(), r.height()), shade)
        p.fillRect(QRectF(x + cw, r.top(), r.right() - x - cw, r.height()), shade)
        p.setPen(QPen(QColor(255, 255, 255, 120), 1, Qt.DashLine))
        p.setBrush(Qt.NoBrush)
        p.drawRect(QRectF(x, r.top() + 1, cw, r.height() - 2))

    def _chip(self, p: QPainter, x: float, y: float, text: str, color: str, dot: str | None = None) -> float:
        f = QFont(theme.FONT.split(",")[0], 9)
        f.setWeight(QFont.DemiBold)
        p.setFont(f)
        w = p.fontMetrics().horizontalAdvance(text) + (30 if dot else 18)
        rr = QRectF(x, y, w, 24)
        p.setPen(QPen(QColor(255, 255, 255, 30), 1))
        p.setBrush(QColor(8, 10, 16, 170))
        p.drawRoundedRect(rr, 12, 12)
        tx = x + 9
        if dot:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(dot))
            p.drawEllipse(QRectF(x + 9, y + 8, 8, 8))
            tx += 13
        p.setPen(QColor(color))
        p.drawText(QRectF(tx, y, w, 24), Qt.AlignVCenter | Qt.AlignLeft, text)
        return w

    def _draw_hud(self, p: QPainter, r: QRectF):
        x, y = r.left() + 12, r.top() + 12
        if not self.gestures:
            self._chip(p, x, y, "No hands — raise your hands into view", theme.MUTED, theme.DIM)
        for label, g, pinch in self.gestures:
            dot = theme.CYAN if label == "Left" else theme.MAGENTA
            txt = f"{label}  ·  {GESTURE_LABELS.get(g, g)}"
            if pinch > 0.05:
                txt += f"  ·  pinch {int(pinch * 100)}%"
            x += self._chip(p, x, y, txt, theme.TEXT, dot) + 6
        fps_txt = f"{self.fps:4.0f} FPS"
        f = QFont(theme.FONT.split(",")[0], 9)
        p.setFont(f)
        w = p.fontMetrics().horizontalAdvance(fps_txt) + 18
        col = theme.GREEN if self.fps >= 24 else ("#ffc94d" if self.fps >= 15 else theme.RED)
        self._chip(p, r.right() - w - 12, r.top() + 12, fps_txt, col)
        if self.status:
            self._chip(p, r.left() + 12, r.bottom() - 36, self.status, theme.CYAN)
        if self.recording:
            m, s = divmod(int(self.rec_time), 60)
            blink = int(time.perf_counter() * 2) % 2 == 0
            txt = f"REC  {m:02d}:{s:02d}"
            w = 92
            self._chip(p, r.right() - w - 12, r.bottom() - 36, txt, "#ffffff", theme.RED if blink else "#5a1d2c")

    def _draw_message(self, p: QPainter):
        p.setPen(QColor(theme.TEXT))
        f = QFont(theme.FONT.split(",")[0], 15)
        f.setWeight(QFont.DemiBold)
        p.setFont(f)
        rr = QRectF(self.rect()).adjusted(40, 0, -40, -30)
        p.drawText(rr, Qt.AlignCenter | Qt.TextWordWrap, self.message)
        if self.submessage:
            p.setPen(QColor(theme.MUTED))
            p.setFont(QFont(theme.FONT.split(",")[0], 10))
            p.drawText(QRectF(self.rect()).adjusted(60, 70, -60, 0), Qt.AlignHCenter | Qt.AlignVCenter | Qt.TextWordWrap,
                       self.submessage)

    def _draw_toast(self, p: QPainter, r: QRectF):
        t0, text = self._toast
        age = time.perf_counter() - t0
        if age > 2.2:
            self._toast = None
            return
        a = min(1.0, (2.2 - age) / 0.4) * min(1.0, age / 0.12)
        f = QFont(theme.FONT.split(",")[0], 12)
        f.setWeight(QFont.DemiBold)
        p.setFont(f)
        w = p.fontMetrics().horizontalAdvance(text) + 40
        rr = QRectF(r.center().x() - w / 2, r.top() + 54, w, 38)
        p.setPen(QPen(QColor(34, 227, 255, int(160 * a)), 1))
        p.setBrush(QColor(8, 10, 16, int(200 * a)))
        p.drawRoundedRect(rr, 19, 19)
        p.setPen(QColor(255, 255, 255, int(255 * a)))
        p.drawText(rr, Qt.AlignCenter, text)
