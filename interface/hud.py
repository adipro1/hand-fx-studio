"""Cinematic sci-fi HUD drawn with QPainter.

The same ``HudRenderer.draw`` paints over the live preview (UI thread) and over
every recorded video frame (recorder thread, on a QImage), so what you see is
what gets recorded. It only reads a ``core.telemetry.Telemetry`` snapshot.
"""
from __future__ import annotations

import math

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QImage, QLinearGradient, QPainter, QPainterPath, QPen

from core.telemetry import Telemetry

STYLES = {
    "Cyber": {"p": (0, 229, 255), "s": (255, 46, 196), "a": (255, 214, 64), "w": (255, 70, 90), "t": (220, 246, 255)},
    "Military": {"p": (80, 255, 120), "s": (190, 255, 90), "a": (255, 200, 60), "w": (255, 80, 60), "t": (210, 255, 215)},
    "Synthwave": {"p": (255, 92, 190), "s": (255, 160, 60), "a": (120, 220, 255), "w": (255, 60, 90), "t": (255, 230, 245)},
}
STYLE_NAMES = list(STYLES)
DETAILS = ["Full", "Minimal"]


def _c(rgb, a=255) -> QColor:
    return QColor(rgb[0], rgb[1], rgb[2], int(max(0, min(255, a))))


class HudRenderer:
    def __init__(self, style: str = "Cyber", detail: str = "Full"):
        self.style = style if style in STYLES else "Cyber"
        self.detail = detail
        self._fonts: dict = {}
        self._cards: dict = {}

    # ------------------------------------------------------------------ helpers
    def _font(self, px: float, bold=False) -> QFont:
        key = (int(px * 2), bold)
        f = self._fonts.get(key)
        if f is None:
            f = QFont("Consolas")
            f.setStyleHint(QFont.Monospace)
            f.setPixelSize(max(7, int(round(px))))
            f.setBold(bold)
            f.setLetterSpacing(QFont.AbsoluteSpacing, px * 0.08)
            self._fonts[key] = f
        return f

    def _text(self, p, x, y, s, px, col, bold=False, align="l", glow=True):
        p.setFont(self._font(px, bold))
        fm = p.fontMetrics()
        w = fm.horizontalAdvance(s)
        if align == "r":
            x -= w
        elif align == "c":
            x -= w / 2
        if glow:
            g = QColor(col)
            g.setAlpha(min(70, col.alpha() // 3))
            p.setPen(g)
            p.drawText(QPointF(x + 1, y + 1), s)
        p.setPen(col)
        p.drawText(QPointF(x, y), s)
        return w

    @staticmethod
    def _pen(col, w, style=Qt.SolidLine):
        pen = QPen(col, w)
        pen.setStyle(style)
        pen.setCapStyle(Qt.FlatCap)
        return pen

    def _panel(self, p, r: QRectF, title, k):
        C = STYLES[self.style]
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(4, 10, 18, 120))
        path = QPainterPath()
        c = 8 * k
        path.moveTo(r.left() + c, r.top())
        path.lineTo(r.right(), r.top())
        path.lineTo(r.right(), r.bottom() - c)
        path.lineTo(r.right() - c, r.bottom())
        path.lineTo(r.left(), r.bottom())
        path.lineTo(r.left(), r.top() + c)
        path.closeSubpath()
        p.drawPath(path)
        p.setBrush(Qt.NoBrush)
        p.setPen(self._pen(_c(C["p"], 120), 1.0 * k))
        p.drawPath(path)
        p.setPen(Qt.NoPen)
        p.setBrush(_c(C["p"], 200))
        p.drawRect(QRectF(r.left() + c, r.top() - 1.5 * k, 40 * k, 3 * k))
        p.setBrush(Qt.NoBrush)
        self._text(p, r.left() + 8 * k, r.top() + 15 * k, title, 10.5 * k, _c(C["p"]), bold=True)
        return r.top() + 22 * k

    def _bar(self, p, x, y, w, h, v, col, k):
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 28))
        p.drawRect(QRectF(x, y, w, h))
        segs = 14
        sw = w / segs
        n = int(round(max(0.0, min(1.0, v)) * segs))
        p.setBrush(col)
        for i in range(n):
            p.drawRect(QRectF(x + i * sw + 0.5, y, sw - 1.2 * k, h))
        p.setBrush(Qt.NoBrush)

    # ------------------------------------------------------------------ main entry
    def draw(self, p: QPainter, rect: QRectF, tel: Telemetry, crop=(0.0, 0.0, 1.0, 1.0), safe=(0.0, 0.0)):
        """Paint the HUD into ``rect``. ``crop`` = (u0, v0, uw, vh): the source-uv window
        that ``rect`` shows (for 9:16 / 1:1 crops)."""
        W, H = rect.width(), rect.height()
        if W < 50 or H < 50:
            return
        k = min(W, H) / 720.0
        if H > W:
            k = W / 620.0              # vertical video: scale to width
        k = max(0.45, k)
        C = STYLES[self.style]
        t = tel.t
        u0, v0, uw, vh = crop

        def m(u, v):
            return QPointF(rect.x() + (u - u0) / uw * W, rect.y() + (v - v0) / vh * H)

        p.save()
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        p.setClipRect(rect)
        full = self.detail != "Minimal"
        vertical = H > W * 1.2
        L, T, R, B = rect.left(), rect.top(), rect.right(), rect.bottom()
        # keep HUD furniture out of areas covered by app UI (Instagram Story top bar / reply box)
        T += H * safe[0]
        B -= H * safe[1]
        pad = 14 * k

        # ---- ambient: vignette ticks, scan sweep, faint grid
        if full:
            sweep = T + ((t * 0.18) % 1.0) * H
            g = QLinearGradient(0, sweep - 60 * k, 0, sweep)
            g.setColorAt(0, _c(C["p"], 0))
            g.setColorAt(1, _c(C["p"], 22))
            p.fillRect(QRectF(L, sweep - 60 * k, W, 60 * k), QBrush(g))
            p.setPen(self._pen(_c(C["p"], 70), 1.0 * k))
            p.drawLine(QPointF(L, sweep), QPointF(R, sweep))
            p.setPen(self._pen(_c(C["p"], 60), 1.0 * k))
            step = 40 * k
            n = int(W / step)
            for i in range(1, n):
                x = L + i * step
                ln = (6 if i % 5 else 12) * k
                p.drawLine(QPointF(x, T + 2 * k), QPointF(x, T + 2 * k + ln))
                p.drawLine(QPointF(x, B - 2 * k), QPointF(x, B - 2 * k - ln))
            n = int(H / step)
            for i in range(1, n):
                y = T + i * step
                ln = (6 if i % 5 else 12) * k
                p.drawLine(QPointF(L + 2 * k, y), QPointF(L + 2 * k + ln, y))
                p.drawLine(QPointF(R - 2 * k, y), QPointF(R - 2 * k - ln, y))

        # ---- frame corners
        cl = 46 * k
        p.setPen(self._pen(_c(C["p"], 230), 2.4 * k))
        for (x, y, dx, dy) in ((L + pad, T + pad, 1, 1), (R - pad, T + pad, -1, 1),
                               (L + pad, B - pad, 1, -1), (R - pad, B - pad, -1, -1)):
            p.drawLine(QPointF(x, y), QPointF(x + dx * cl, y))
            p.drawLine(QPointF(x, y), QPointF(x, y + dy * cl))

        # ---- top bar
        ty = T + pad + 22 * k
        self._text(p, L + pad + 12 * k, ty, "HAND FX STUDIO", 15 * k, _c(C["t"]), bold=True)
        if full:
            self._text(p, L + pad + 12 * k, ty + 16 * k, "// NEURAL MOTION CAPTURE  " + tel.session,
                       9.5 * k, _c(C["p"], 200))
        rx = R - pad - 12 * k
        if tel.recording:
            fr = int((tel.rec_time % 1.0) * 30)
            hh, rem = divmod(int(tel.rec_time), 3600)
            mm, ss = divmod(rem, 60)
            tc = f"{hh:02d}:{mm:02d}:{ss:02d}:{fr:02d}"
            w = self._text(p, rx, ty, tc, 16 * k, _c(C["t"]), bold=True, align="r")
            if int(t * 2) % 2 == 0:
                p.setPen(Qt.NoPen)
                p.setBrush(_c(C["w"], 240))
                p.drawEllipse(QPointF(rx - w - 50 * k, ty - 5.5 * k), 5.5 * k, 5.5 * k)
                p.setBrush(Qt.NoBrush)
            self._text(p, rx - w - 12 * k, ty, "REC", 13 * k, _c(C["w"]), bold=True, align="r")
            if full:
                self._text(p, rx, ty + 16 * k, f"FRM {tel.rec_frames:06d}  ·  {tel.wall}", 9.5 * k,
                           _c(C["p"], 200), align="r")
        else:
            self._text(p, rx, ty, "LIVE", 14 * k, _c(C["p"]), bold=True, align="r")
            if full:
                self._text(p, rx, ty + 16 * k, tel.wall, 9.5 * k, _c(C["p"], 200), align="r")

        # ---- hands
        for h in tel.hands:
            if h.presence < 0.35:
                continue
            pc = m(*h.palm)
            if not rect.adjusted(-30 * k, -30 * k, 30 * k, 30 * k).contains(pc):
                continue                              # hand is outside the cropped video
            col = _c(C["p"] if h.label == "Right" else C["s"], 255 * min(1.0, h.presence))
            colA = QColor(col)
            # bbox brackets
            x0, y0, x1, y1 = h.bbox
            a, b = m(x0, y0), m(x1, y1)
            bx0, by0, bx1, by1 = a.x() - 14 * k, a.y() - 14 * k, b.x() + 14 * k, b.y() + 14 * k
            bl = 16 * k
            colA.setAlpha(int(170 * h.presence))
            p.setPen(self._pen(colA, 1.6 * k))
            for (x, y, dx, dy) in ((bx0, by0, 1, 1), (bx1, by0, -1, 1), (bx0, by1, 1, -1), (bx1, by1, -1, -1)):
                p.drawLine(QPointF(x, y), QPointF(x + dx * bl, y))
                p.drawLine(QPointF(x, y), QPointF(x, y + dy * bl))
            # palm reticle
            c = m(*h.palm)
            r0 = 26 * k
            spin = t * 90 * (1 if h.label == "Right" else -1)
            p.setPen(self._pen(col, 2.0 * k))
            arc = QRectF(c.x() - r0, c.y() - r0, 2 * r0, 2 * r0)
            for i in range(3):
                p.drawArc(arc, int((spin + i * 120) * 16), int(70 * 16))
            r1 = r0 + 8 * k
            p.setPen(self._pen(colA, 1.0 * k, Qt.DotLine))
            p.drawEllipse(c, r1, r1)
            p.setPen(self._pen(col, 1.2 * k))
            for ang in (0, 90, 180, 270):
                ca, sa = math.cos(math.radians(ang)), math.sin(math.radians(ang))
                p.drawLine(QPointF(c.x() + ca * (r1 + 2 * k), c.y() + sa * (r1 + 2 * k)),
                           QPointF(c.x() + ca * (r1 + 9 * k), c.y() + sa * (r1 + 9 * k)))
            # rotation needle
            rot = h.rotation
            p.setPen(self._pen(_c(C["a"], 230), 1.6 * k))
            p.drawLine(c, QPointF(c.x() + math.sin(rot) * r0 * 0.8, c.y() - math.cos(rot) * r0 * 0.8))
            # fingertip markers
            if full:
                p.setPen(self._pen(colA, 1.0 * k))
                for tu, tv in h.tips:
                    q = m(float(tu), float(tv))
                    s = 4 * k
                    p.drawLine(QPointF(q.x() - s, q.y()), QPointF(q.x() + s, q.y()))
                    p.drawLine(QPointF(q.x(), q.y() - s), QPointF(q.x(), q.y() + s))
                ix = m(float(h.tips[1][0]), float(h.tips[1][1]))
                self._text(p, ix.x() + 7 * k, ix.y() - 6 * k,
                           f"{h.index_xyz[0]:.2f},{h.index_xyz[1]:.2f},{h.index_xyz[2]:+.2f}", 8 * k, colA, glow=False)
            # info card on the outer side of the hand, with a leader line
            side = 1 if c.x() > L + W / 2 else -1
            cw, ch = 172 * k, (92 if full else 36) * k
            cx = (bx1 + 18 * k) if side > 0 else (bx0 - 18 * k - cw)
            if cx < L + pad or cx + cw > R - pad:        # no room outside: tuck above the hand
                cx = min(max(L + pad, c.x() - cw / 2 + side * 40 * k), R - pad - cw)
                cy = by0 - ch - 16 * k
            else:
                cy = by0
            top_lim = T + pad + (270 if full and vertical else 200 if full else 50) * k
            cy = max(top_lim, min(B - pad - ch - (120 if full else 20) * k, cy))
            prev = self._cards.get(h.hand_id)
            if prev is not None and abs(prev[0] - cx) < W * 0.4:
                cx = prev[0] + (cx - prev[0]) * 0.18
                cy = prev[1] + (cy - prev[1]) * 0.18
            self._cards[h.hand_id] = (cx, cy)
            anchor = QPointF(cx if side > 0 else cx + cw, cy + 10 * k)
            p.setPen(self._pen(colA, 1.0 * k))
            corner = QPointF(bx1 if anchor.x() > c.x() else bx0, by0)
            p.drawLine(corner, QPointF(anchor.x() - side * 10 * k, anchor.y()))
            p.drawLine(QPointF(anchor.x() - side * 10 * k, anchor.y()), anchor)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(4, 10, 18, 135))
            p.drawRect(QRectF(cx, cy, cw, ch))
            p.setBrush(col)
            p.drawRect(QRectF(cx, cy, 3 * k, ch))
            p.setBrush(Qt.NoBrush)
            who = "R-HAND" if h.label == "Right" else "L-HAND"
            self._text(p, cx + 9 * k, cy + 14 * k, f"{who} // {h.gesture}", 10.5 * k, col, bold=True)
            self._text(p, cx + 9 * k, cy + 28 * k, f"CONF {h.confidence * 100:3.0f}%   SPD {h.speed:4.1f}",
                       8.5 * k, _c(C["t"], 220), glow=False)
            if full:
                yy = cy + 38 * k
                for lab, v in (("PINCH", h.pinch), ("SPRD", h.spread), ("OPEN", h.openness)):
                    self._text(p, cx + 9 * k, yy + 7 * k, lab, 8 * k, _c(C["t"], 200), glow=False)
                    self._bar(p, cx + 52 * k, yy, 80 * k, 7 * k, v, col, k)
                    self._text(p, cx + cw - 6 * k, yy + 7 * k, f"{v * 100:3.0f}", 8 * k, _c(C["t"], 200),
                               align="r", glow=False)
                    yy += 13 * k
                self._text(p, cx + 9 * k, yy + 7 * k, f"ROT {math.degrees(h.rotation):+5.0f}°", 8 * k,
                           _c(C["a"], 230), glow=False)

        # ---- rangefinder between hands
        hs = [h for h in tel.hands if h.presence > 0.5]
        if len(hs) >= 2:
            a, b = m(*hs[0].palm), m(*hs[1].palm)
            p.setPen(self._pen(_c(C["a"], 170), 1.2 * k, Qt.DashLine))
            p.drawLine(a, b)
            mid = (a + b) / 2
            ang = math.degrees(math.atan2(b.y() - a.y(), b.x() - a.x()))
            self._text(p, mid.x(), mid.y() - 8 * k, f"Δ {tel.two_distance * 100:4.1f}  ∠ {ang:+4.0f}°",
                       9.5 * k, _c(C["a"]), bold=True, align="c")

        # ---- pinned frame tags
        for pin in tel.pins:
            poly = pin["poly"]
            i = int(np.argmin(poly[:, 1] * 3 + poly[:, 0]))
            q = m(float(poly[i, 0]), float(poly[i, 1]))
            qx = min(max(q.x() + 4 * k, L + pad), R - pad - 190 * k)
            qy = max(q.y() - 7 * k, T + pad + 60 * k)
            self._text(p, qx, qy, f"PIN-{pin['id']:02d} // {pin['name'].upper()}",
                       9 * k, _c(C["a"] if pin.get("grabbed") else C["t"], 235), bold=True)

        if full:
            self._panels(p, QRectF(L, T, W, B - T), tel, k, C, vertical, pad)

        # ---- event flash callout (glitch text)
        if tel.flash:
            txt, age = tel.flash
            a = max(0.0, 1.0 - age / 1.2)
            y = T + H * (0.2 if vertical else 0.24)
            px = 30 * k
            jitter = (3 * k * math.sin(age * 90)) if age < 0.35 else 0
            self._text(p, L + W / 2 + jitter, y, txt, px, _c(C["s"], 170 * a), bold=True, align="c", glow=False)
            self._text(p, L + W / 2 - jitter, y, txt, px, _c(C["p"], 170 * a), bold=True, align="c", glow=False)
            self._text(p, L + W / 2, y, txt, px, _c(C["t"], 255 * a), bold=True, align="c")
            p.setPen(self._pen(_c(C["p"], 160 * a), 1.2 * k))
            p.drawLine(QPointF(L + W / 2 - 160 * k, y + 10 * k), QPointF(L + W / 2 + 160 * k, y + 10 * k))

        # ---- countdown
        if tel.countdown > 0:
            n = int(math.ceil(tel.countdown))
            frac = tel.countdown - (n - 1)
            p.fillRect(rect, QColor(0, 0, 0, 90))
            c = QPointF(L + W / 2, T + H / 2)
            r = 90 * k
            p.setPen(self._pen(_c(C["p"], 120), 2 * k))
            p.drawEllipse(c, r, r)
            p.setPen(self._pen(_c(C["p"]), 5 * k))
            p.drawArc(QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r), 90 * 16, int(-360 * 16 * (1 - frac)))
            self._text(p, c.x(), c.y() + 30 * k, str(n), 88 * k, _c(C["t"]), bold=True, align="c")
            self._text(p, c.x(), c.y() + r + 34 * k, "ARMING CAPTURE", 14 * k, _c(C["p"]), bold=True, align="c")
        p.restore()

    # ------------------------------------------------------------------ side / bottom panels
    def _panels(self, p, rect, tel, k, C, vertical, pad):
        L, T, R, B = rect.left(), rect.top(), rect.right(), rect.bottom()
        W = rect.width()
        pw = 168 * k
        top = T + pad + 56 * k
        # SYSTEM
        rows = [("FPS", f"{tel.fps:5.1f}"), ("RENDER", f"{tel.render_ms:4.1f} ms"),
                ("INFER", f"{tel.infer_ms:4.1f} ms"), ("TRACK", f"{tel.track_fps:4.0f} Hz"),
                ("CAMERA", f"{tel.cam_fps:4.0f} Hz"), ("RES", tel.cam_res), ("HANDS", str(len(tel.hands)))]
        if vertical:
            rows = rows[:5]
        ph = (26 + 13 * len(rows) + (12 if tel.gpu else 0)) * k
        r = QRectF(L + pad + 6 * k, top, pw, ph)
        y = self._panel(p, r, "SYSTEM", k)
        for lab, val in rows:
            self._text(p, r.left() + 9 * k, y + 7 * k, lab, 8.5 * k, _c(C["t"], 190), glow=False)
            self._text(p, r.right() - 8 * k, y + 7 * k, val, 8.5 * k, _c(C["p"]), align="r", glow=False)
            y += 13 * k
        if tel.gpu:
            g = tel.gpu.replace("(R)", "").replace("Graphics", "").strip()[:24]
            self._text(p, r.left() + 9 * k, y + 7 * k, g.upper(), 7.5 * k, _c(C["p"], 160), glow=False)

        # ACTIVE FX
        fx = tel.effects[: (5 if vertical else 8)]
        extra = [("PRESET", tel.preset[:16].upper())]
        if tel.filter_name:
            extra.append(("FILTER", tel.filter_name[:16].upper()))
        if tel.pins:
            extra.append(("PINNED", str(len(tel.pins))))
        ph = (26 + 12 * len(fx) + 13 * len(extra) + 4) * k
        r = QRectF(R - pad - 6 * k - pw, top, pw, ph)
        y = self._panel(p, r, "ACTIVE FX", k)
        for lab, val in extra:
            self._text(p, r.left() + 9 * k, y + 7 * k, lab, 8.5 * k, _c(C["t"], 190), glow=False)
            self._text(p, r.right() - 8 * k, y + 7 * k, val, 8.5 * k, _c(C["a"]), align="r", glow=False)
            y += 13 * k
        y += 3 * k
        for i, name in enumerate(fx):
            blink = 255 if (int(tel.t * 4) + i) % 9 else 140
            p.setPen(Qt.NoPen)
            p.setBrush(_c(C["p"], blink))
            p.drawRect(QRectF(r.left() + 10 * k, y + 1 * k, 5 * k, 5 * k))
            p.setBrush(Qt.NoBrush)
            self._text(p, r.left() + 21 * k, y + 7 * k, name.upper()[:20], 8 * k, _c(C["t"], 220), glow=False)
            y += 12 * k

        # bottom: motion graph + radar + event log
        bh = 92 * k
        by = B - pad - 8 * k - bh
        gw = min(230 * k, W * (0.42 if vertical else 0.24))
        r = QRectF(L + pad + 6 * k, by, gw, bh)
        y = self._panel(p, r, "MOTION ENERGY", k)
        gx0, gx1, gy0, gy1 = r.left() + 8 * k, r.right() - 8 * k, y + 2 * k, r.bottom() - 8 * k
        p.setPen(self._pen(QColor(255, 255, 255, 30), 1 * k))
        for i in range(1, 4):
            yy = gy0 + (gy1 - gy0) * i / 4
            p.drawLine(QPointF(gx0, yy), QPointF(gx1, yy))
        for lab, colk in (("Left", "s"), ("Right", "p")):
            arr = tel.speed_hist.get(lab)
            if arr is None or len(arr) < 2:
                continue
            path = QPainterPath()
            n = len(arr)
            for i, v in enumerate(arr):
                x = gx0 + (gx1 - gx0) * i / (n - 1)
                yv = gy1 - (gy1 - gy0) * min(float(v) / 8.0, 1.0)
                path.moveTo(x, yv) if i == 0 else path.lineTo(x, yv)
            p.setPen(self._pen(_c(C[colk], 230), 1.5 * k))
            p.drawPath(path)
        self._text(p, gx1, y - 4 * k, "L", 8 * k, _c(C["s"]), align="r", glow=False)
        self._text(p, gx1 - 10 * k, y - 4 * k, "R", 8 * k, _c(C["p"]), align="r", glow=False)

        # radar
        rr = bh * 0.5 - 6 * k
        rc = QPointF(r.right() + 16 * k + rr, by + bh / 2)
        if not vertical and rc.x() + rr < R - pad - 240 * k:
            p.setPen(self._pen(_c(C["p"], 90), 1 * k))
            p.drawEllipse(rc, rr, rr)
            p.drawEllipse(rc, rr * 0.5, rr * 0.5)
            p.drawLine(QPointF(rc.x() - rr, rc.y()), QPointF(rc.x() + rr, rc.y()))
            p.drawLine(QPointF(rc.x(), rc.y() - rr), QPointF(rc.x(), rc.y() + rr))
            sw = (tel.t * 120) % 360
            p.setPen(self._pen(_c(C["p"], 200), 1.6 * k))
            p.drawLine(rc, QPointF(rc.x() + rr * math.cos(math.radians(sw)), rc.y() - rr * math.sin(math.radians(sw))))
            for h in tel.hands:
                dx, dy = (h.palm[0] - 0.5) * 2, (h.palm[1] - 0.5) * 2
                p.setPen(Qt.NoPen)
                p.setBrush(_c(C["p"] if h.label == "Right" else C["s"]))
                p.drawEllipse(QPointF(rc.x() + dx * rr * 0.9, rc.y() + dy * rr * 0.9), 3.5 * k, 3.5 * k)
                p.setBrush(Qt.NoBrush)

        # event log
        ew = 232 * k if not vertical else W - 2 * pad - 12 * k - gw - 8 * k
        if vertical:
            r = QRectF(R - pad - 6 * k - ew, by, ew, bh)
        else:
            r = QRectF(R - pad - 6 * k - ew, by, ew, bh)
        y = self._panel(p, r, "EVENT LOG", k)
        lines = tel.events[-5:]
        for i, (ts, txt) in enumerate(lines):
            a = 255 if i == len(lines) - 1 else 150 + 20 * i
            s = f"> {ts[-8:]} {txt}"
            maxc = int((r.width() - 16 * k) / (8 * k * 0.58))
            self._text(p, r.left() + 8 * k, y + 7 * k, s[:maxc], 8 * k,
                       _c(C["a"] if i == len(lines) - 1 else C["t"], a), glow=False)
            y += 12 * k


def draw_on_rgb(hud: HudRenderer, frame: np.ndarray, tel: Telemetry, crop=(0.0, 0.0, 1.0, 1.0),
                safe=(0.0, 0.0)) -> np.ndarray:
    """Draw the HUD in place onto a contiguous HxWx3 uint8 RGB array (any thread)."""
    h, w = frame.shape[:2]
    img = QImage(frame.data, w, h, 3 * w, QImage.Format_RGB888)
    p = QPainter(img)
    try:
        hud.draw(p, QRectF(0, 0, w, h), tel, crop, safe)
    finally:
        p.end()
    return frame
