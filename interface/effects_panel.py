"""Effects library: categorised cards with thumbnails and on/off switches."""
from __future__ import annotations

import math
import random

import cv2
import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (QBrush, QColor, QImage, QLinearGradient, QPainter, QPainterPath, QPen,
                           QPixmap, QPolygonF, QRadialGradient)
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QLineEdit, QScrollArea, QSizePolicy,
                               QVBoxLayout, QWidget)

from interface import theme
from interface.widgets import ToggleSwitch, section

THUMB_W, THUMB_H = 78, 54


def _qc(h, a=255):
    c = QColor(h)
    c.setAlpha(a)
    return c


def paint_thumbnail(effect) -> QPixmap:
    """Procedural thumbnail that hints at what each effect looks like."""
    w, h = THUMB_W * 2, THUMB_H * 2
    pm = QPixmap(w, h)
    pm.fill(QColor("#0b0e15"))
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    c1, c2 = theme.CATEGORY_COLORS.get(effect.category, (theme.CYAN, theme.MAGENTA))
    rnd = random.Random(effect.id)
    eid = effect.id
    g = QLinearGradient(0, 0, w, h)
    g.setColorAt(0, QColor("#0d1220"))
    g.setColorAt(1, QColor("#141026"))
    p.fillRect(0, 0, w, h, g)

    if eid in ("filter_frame", "glass_prism"):
        quad = QPolygonF([QPointF(40, 30), QPointF(150, 22), QPointF(140, 98), QPointF(48, 104)])
        if eid == "filter_frame":
            p.setBrush(QColor("#1a38ff"))
            p.setPen(Qt.NoPen)
            p.drawPolygon(quad)
            p.setBrush(QColor("#ff20dc"))
            for yy in range(28, 106, 7):
                for xx in range(40, 152, 7):
                    if quad.containsPoint(QPointF(xx, yy), Qt.OddEvenFill):
                        rr = 1 + 2.6 * (0.5 + 0.5 * math.sin(xx * 0.05) * math.cos(yy * 0.07))
                        p.drawEllipse(QPointF(xx, yy), rr, rr)
            p.setPen(QPen(QColor("white"), 2.5))
            p.setBrush(Qt.NoBrush)
            p.drawPolygon(quad)
        else:
            p.fillRect(0, 0, w, h, QColor(40, 50, 140, 120))
            for k in range(4, 0, -1):
                off = QPointF(-k * 7, k * 3)
                p.setPen(QPen(QColor(200, 220, 255, 60 + 20 * (4 - k)), 1.2))
                p.drawPolygon(quad.translated(off))
            p.setBrush(QColor(220, 232, 255, 200))
            p.setPen(QPen(QColor("white"), 2))
            p.drawPolygon(quad)
    elif eid == "finger_bands":
        bands = [(20, 45), (45, 75), (75, 105)]
        for i, (a, b) in enumerate(bands):
            poly = QPolygonF([QPointF(15, a + 6), QPointF(170, a - 6), QPointF(170, b - 6), QPointF(15, b + 6)])
            if i == 0:
                gr = QLinearGradient(15, 0, 170, 0)
                for t, col in ((0, "#0a2cff"), (0.35, "#00e0ff"), (0.5, "#ffe000"), (0.65, "#ff2000"), (1, "#0a2cff")):
                    gr.setColorAt(t, QColor(col))
                p.setBrush(gr)
            elif i == 1:
                p.setBrush(QColor("black"))
            else:
                p.setBrush(QColor("#0a1040"))
            p.setPen(QPen(QColor("white"), 1))
            p.drawPolygon(poly)
            if i == 1:
                p.setPen(QPen(QColor("white"), 1.2))
                p.drawEllipse(QPointF(95, 60), 14, 10)
                p.drawLine(QPointF(70, 58), QPointF(120, 58))
            if i == 2:
                p.setPen(QPen(QColor("#30f0e0"), 1))
                for yy in range(a, b, 4):
                    p.drawLine(QPointF(20 + rnd.random() * 30, yy), QPointF(150 + rnd.random() * 20, yy - 4))
    elif eid in ("skeleton", "hand_link"):
        def hand(cx, cy, s, col):
            pts = [(0, 0), (-18, -10), (-28, -22), (-34, -34), (-38, -44), (-12, -40), (-14, -58), (-15, -70),
                   (-16, -80), (0, -42), (0, -62), (0, -76), (0, -88), (11, -40), (13, -58), (14, -70),
                   (15, -79), (20, -34), (25, -48), (28, -57), (30, -65)]
            pts = [QPointF(cx + x * s, cy + y * s) for x, y in pts]
            con = [(0, 1), (1, 2), (2, 3), (3, 4), (0, 5), (5, 6), (6, 7), (7, 8), (5, 9), (9, 10), (10, 11),
                   (11, 12), (9, 13), (13, 14), (14, 15), (15, 16), (13, 17), (0, 17), (17, 18), (18, 19), (19, 20)]
            for glow, wdt in ((60, 6), (255, 2)):
                p.setPen(QPen(_qc(col, glow), wdt, Qt.SolidLine, Qt.RoundCap))
                for a, b in con:
                    p.drawLine(pts[a], pts[b])
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("white"))
            for q in pts:
                p.drawEllipse(q, 2.2, 2.2)
            return pts
        if eid == "skeleton":
            hand(70, 112, 1.0, theme.CYAN)
            hand(135, 112, 1.0, theme.MAGENTA)
        else:
            a = hand(50, 112, 0.9, "#35f29a")
            b = hand(150, 112, 0.9, "#35f29a")
            p.setPen(QPen(QColor("white"), 1.5))
            for i in (4, 8, 12):
                p.drawLine(a[i], b[i])
    elif eid in ("liquid_warp", "finger_lens", "kaleidoscope", "colour"):
        img = np.zeros((h, w, 3), np.uint8)
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        if eid == "liquid_warp":
            v = np.sin(xx * 0.06 + np.sin(yy * 0.05) * 3) * 0.5 + 0.5
            img[..., 0] = (80 + 150 * v).astype(np.uint8)
            img[..., 1] = (40 + 60 * (1 - v)).astype(np.uint8)
            img[..., 2] = (200 * (1 - v) + 40).astype(np.uint8)
        elif eid == "finger_lens":
            dx, dy = xx - w / 2, yy - h / 2
            r = np.sqrt(dx * dx + dy * dy)
            k = np.where(r < 45, 0.55 + 0.45 * (r / 45) ** 2, 1.0)
            gx, gy = (w / 2 + dx * k), (h / 2 + dy * k)
            grid = ((gx // 12 + gy // 12) % 2).astype(np.float32)
            img[..., 0] = (30 + 60 * grid).astype(np.uint8)
            img[..., 1] = (40 + 120 * grid).astype(np.uint8)
            img[..., 2] = (90 + 150 * grid).astype(np.uint8)
        elif eid == "kaleidoscope":
            dx, dy = xx - w / 2, yy - h / 2
            a = np.arctan2(dy, dx)
            seg = np.pi / 4
            a = np.abs(np.mod(a, seg) - seg / 2)
            r = np.sqrt(dx * dx + dy * dy)
            v = np.sin(a * 18 + r * 0.12)
            hue = ((r * 1.2 + a * 120) % 180).astype(np.uint8)
            hsv = np.dstack([hue, np.full_like(hue, 230), (150 + 100 * v).clip(0, 255).astype(np.uint8)])
            img = cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB)
        else:
            hue = ((xx * 0.9 + yy * 0.4) % 180).astype(np.uint8)
            hsv = np.dstack([hue, np.full_like(hue, 220), np.full_like(hue, 240)])
            img = cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB)
        img = np.ascontiguousarray(img)
        qi = QImage(img.data, w, h, 3 * w, QImage.Format_RGB888)
        p.drawImage(0, 0, qi)
        if eid == "finger_lens":
            p.setPen(QPen(QColor("#7fe8ff"), 2))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QPointF(w / 2, h / 2), 45, 45)
    elif eid == "shockwave":
        for k in range(5):
            p.setPen(QPen(_qc("#a6f6ff", 255 - k * 45), 3 - k * 0.4))
            p.drawEllipse(QPointF(w / 2, h / 2), 12 + k * 16, 12 + k * 16)
    elif eid == "portal":
        rg = QRadialGradient(w / 2, h / 2, 50)
        rg.setColorAt(0, QColor("#000000"))
        rg.setColorAt(0.6, QColor("#3a1060"))
        rg.setColorAt(1, QColor("#ff7a18"))
        p.setBrush(rg)
        p.setPen(QPen(QColor("#ffd23f"), 3))
        p.drawEllipse(QPointF(w / 2, h / 2), 48, 48)
        for k in range(3):
            p.setPen(QPen(_qc("#ff7a18", 200), 2))
            p.drawArc(QRectF(w / 2 - 56 - k * 6, h / 2 - 56 - k * 6, 112 + k * 12, 112 + k * 12), k * 1200, 1800)
    elif eid == "particles":
        for _ in range(130):
            x, y = rnd.random() * w, rnd.random() * h
            r = rnd.random() * 3 + 0.6
            col = QColor(c1) if rnd.random() < 0.6 else QColor(c2)
            rg = QRadialGradient(x, y, r * 3)
            rg.setColorAt(0, col)
            col2 = QColor(col)
            col2.setAlpha(0)
            rg.setColorAt(1, col2)
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(rg))
            p.drawEllipse(QPointF(x, y), r * 3, r * 3)
    elif eid == "energy":
        for glow, wd in ((60, 9), (140, 4), (255, 1.6)):
            p.setPen(QPen(_qc("#7fd6ff" if glow < 255 else "#ffffff", glow), wd, Qt.SolidLine, Qt.RoundCap,
                          Qt.RoundJoin))
            path = QPainterPath(QPointF(20, 62))
            r2 = random.Random(5)
            for x in range(30, 175, 12):
                path.lineTo(QPointF(x, 62 + r2.uniform(-18, 18)))
            p.drawPath(path)
        rg = QRadialGradient(170, 62, 22)
        rg.setColorAt(0, QColor("white"))
        rg.setColorAt(1, QColor(79, 195, 255, 0))
        p.setBrush(rg)
        p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(170, 62), 22, 22)
    elif eid == "geometry":
        pts = []
        for k in range(12):
            a = k * math.tau / 12 + 0.3
            pts.append(QPointF(w / 2 + math.cos(a) * 52 * (1 if k % 2 else 0.6), h / 2 + math.sin(a) * 48 * (1 if k % 2 else 0.6)))
        for i in range(len(pts)):
            for j in range(i + 1, len(pts)):
                if (i + j) % 3 == 0:
                    p.setPen(QPen(_qc(c1 if i % 2 else c2, 150), 1))
                    p.drawLine(pts[i], pts[j])
    p.end()
    return pm.scaled(THUMB_W, THUMB_H, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)


def rounded(pm: QPixmap, radius: int = 9) -> QPixmap:
    out = QPixmap(pm.size())
    out.fill(Qt.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, pm.width(), pm.height()), radius, radius)
    p.setClipPath(path)
    p.drawPixmap(0, 0, pm)
    p.end()
    return out


class EffectCard(QFrame):
    clicked = Signal(object)
    toggled = Signal(object, bool)

    def __init__(self, effect, parent=None):
        super().__init__(parent)
        self.effect = effect
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(74)
        self._selected = False
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 8, 10, 8)
        lay.setSpacing(10)
        self.thumb = QLabel()
        self.thumb.setFixedSize(THUMB_W, THUMB_H)
        self.thumb.setPixmap(rounded(paint_thumbnail(effect)))
        lay.addWidget(self.thumb)
        col = QVBoxLayout()
        col.setSpacing(2)
        top = QHBoxLayout()
        self.name = QLabel(effect.name)
        self.name.setObjectName("h2")
        top.addWidget(self.name, 1)
        self.switch = ToggleSwitch(effect.enabled)
        self.switch.toggled.connect(lambda on: self.toggled.emit(self.effect, on))
        top.addWidget(self.switch)
        col.addLayout(top)
        self.desc = QLabel(self._two_lines(effect.description))
        self.desc.setObjectName("dim")
        self.desc.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.desc.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.name.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.setToolTip(f"<b>{effect.name}</b><br>{effect.description}")
        col.addWidget(self.desc)
        col.addStretch()
        lay.addLayout(col, 1)
        self._style()

    @staticmethod
    def _two_lines(text: str, max_chars: int = 27) -> str:
        words, lines, cur = text.split(), [], ""
        for w in words:
            if len(cur) + len(w) + 1 > max_chars:
                lines.append(cur)
                cur = w
                if len(lines) == 2:
                    break
            else:
                cur = f"{cur} {w}".strip()
        else:
            lines.append(cur)
        if len(lines) > 2 or (len(lines) == 2 and len(" ".join(lines)) < len(text)):
            lines = lines[:2]
            lines[1] = lines[1].rstrip(".,:;") + "…"
        return "\n".join(lines[:2])

    def set_live_thumbnail(self, rgb: np.ndarray):
        h, w = rgb.shape[:2]
        s = max(THUMB_W / w, THUMB_H / h)
        small = cv2.resize(rgb, (max(int(w * s), THUMB_W), max(int(h * s), THUMB_H)), interpolation=cv2.INTER_AREA)
        y0 = (small.shape[0] - THUMB_H) // 2
        x0 = (small.shape[1] - THUMB_W) // 2
        crop = np.ascontiguousarray(small[y0:y0 + THUMB_H, x0:x0 + THUMB_W])
        qi = QImage(crop.data, THUMB_W, THUMB_H, 3 * THUMB_W, QImage.Format_RGB888).copy()
        self.thumb.setPixmap(rounded(QPixmap.fromImage(qi)))

    def sync(self):
        self.switch.set_silent(self.effect.enabled)
        self._style()

    def set_selected(self, sel: bool):
        self._selected = sel
        self._style()

    def _style(self):
        border = theme.CYAN if self._selected else (("#2a4b55" if self.effect.enabled else theme.BORDER))
        bg = "#131c26" if self._selected else theme.CARD
        self.setStyleSheet(f"EffectCard {{ background:{bg}; border:1px solid {border}; border-radius:12px; }}"
                           f"EffectCard:hover {{ background:{theme.CARD_HOVER}; }}")

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit(self.effect)
        super().mousePressEvent(e)


class EffectsPanel(QFrame):
    selected = Signal(object)
    toggled = Signal(object, bool)

    def __init__(self, effects, parent=None):
        super().__init__(parent)
        self.setObjectName("panel")
        self.cards: dict[str, EffectCard] = {}
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 14, 6, 12)
        outer.setSpacing(8)
        head = QHBoxLayout()
        t = QLabel("Effects Library")
        t.setObjectName("h1")
        head.addWidget(t)
        head.addStretch()
        self.count = QLabel()
        self.count.setObjectName("chip")
        head.addWidget(self.count)
        head.addSpacing(6)
        outer.addLayout(head)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search effects...")
        self.search.textChanged.connect(self._filter)
        outer.addWidget(self.search)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        body = QWidget()
        self.body_lay = QVBoxLayout(body)
        self.body_lay.setContentsMargins(0, 0, 6, 0)
        self.body_lay.setSpacing(6)
        self.sections: dict[str, QLabel] = {}
        cats = sorted({e.category for e in effects},
                      key=lambda c: theme.CATEGORY_ORDER.index(c) if c in theme.CATEGORY_ORDER else 99)
        for cat in cats:
            lab = section(cat)
            self.sections[cat] = lab
            self.body_lay.addWidget(lab)
            for e in effects:
                if e.category != cat:
                    continue
                card = EffectCard(e)
                card.clicked.connect(self.selected.emit)
                card.toggled.connect(self._on_toggle)
                self.cards[e.id] = card
                self.body_lay.addWidget(card)
        self.body_lay.addStretch()
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)
        self.update_count()

    def _on_toggle(self, effect, on):
        self.toggled.emit(effect, on)
        self.cards[effect.id].sync()
        self.update_count()

    def update_count(self):
        n = sum(1 for c in self.cards.values() if c.effect.enabled)
        self.count.setText(f"{n} active")

    def sync_all(self):
        for c in self.cards.values():
            c.sync()
        self.update_count()

    def select(self, effect):
        for c in self.cards.values():
            c.set_selected(c.effect is effect)

    def _filter(self, text):
        text = text.lower().strip()
        visible_cats = set()
        for c in self.cards.values():
            e = c.effect
            show = not text or text in e.name.lower() or text in e.description.lower() or text in e.category.lower()
            c.setVisible(show)
            if show:
                visible_cats.add(e.category)
        for cat, lab in self.sections.items():
            lab.setVisible(cat in visible_cats)
