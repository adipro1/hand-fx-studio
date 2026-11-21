"""Hand tracking visualisation: skeleton, joints, pulses, fingertip trails, hand links."""
from __future__ import annotations

from collections import deque

import numpy as np

from core.hand_tracker import FINGERS, HAND_CONNECTIONS, TIPS
from effects.base_effect import Effect, FrameContext, Param, hsv

STYLES = ("Neon", "Classic", "Minimal", "Plasma", "Hologram")
# bone chains from wrist to each fingertip (for travelling pulses)
CHAINS = [(0,) + f for f in FINGERS]


class SkeletonEffect(Effect):
    id = "skeleton"
    name = "Hand Skeleton"
    description = "Glowing landmarks and bones on all 21 hand points, with pulses and fingertip trails."
    category = "Tracking"
    default_order = 140
    uses_overlay = True
    PARAMS = [
        Param("style", "Style", "choice", "Neon", choices=STYLES),
        Param("left_color", "Left hand colour", "color", "#00e5ff"),
        Param("right_color", "Right hand colour", "color", "#ff2bd6"),
        Param("line_width", "Line thickness", "float", 2.5, 0.5, 10.0, 0.1),
        Param("joint_size", "Joint size", "float", 4.0, 0.0, 14.0, 0.1),
        Param("glow", "Glow", "float", 6.0, 0.0, 20.0, 0.5),
        Param("opacity", "Opacity", "float", 1.0, 0.0, 1.0),
        Param("pulses", "Energy pulses along bones", "bool", True),
        Param("trails", "Fingertip trails", "bool", True),
        Param("trail_length", "Trail length (s)", "float", 0.45, 0.05, 2.0, 0.05),
        Param("trail_fingers", "Trail fingers", "choice", "Index", choices=("Index", "All tips", "Thumb + Index")),
        Param("depth_scale", "Scale with distance", "bool", True),
    ]

    def __init__(self):
        super().__init__()
        self._trails: dict[tuple[int, int], deque] = {}

    def reset(self):
        self._trails.clear()

    def _trail_ids(self):
        mode = self.p("trail_fingers")
        if mode == "All tips":
            return TIPS
        if mode == "Thumb + Index":
            return (4, 8)
        return (8,)

    def update(self, ctx: FrameContext):
        if not self.p("trails"):
            self._trails.clear()
            return
        alive = set()
        for h in ctx.hands:
            if h.presence < 0.99:
                continue
            for tid in self._trail_ids():
                key = (h.hand_id, tid)
                alive.add(key)
                dq = self._trails.setdefault(key, deque(maxlen=120))
                dq.append((ctx.t, float(h.lm[tid, 0]), float(h.lm[tid, 1])))
        L = self.p("trail_length")
        for key in list(self._trails):
            dq = self._trails[key]
            while dq and ctx.t - dq[0][0] > L:
                dq.popleft()
            if not dq:
                del self._trails[key]

    def _hand_color(self, h, style, t, i=0):
        if style == "Classic":
            return (0.15, 1.0, 0.25)
        if style == "Minimal":
            return (1.0, 1.0, 1.0)
        if style == "Plasma":
            return hsv(t * 0.15 + i * 0.045 + (0.5 if h.label == "Right" else 0.0), 0.85, 1.0)
        if style == "Hologram":
            return (0.45, 0.85, 1.0)
        return self.col("left_color") if h.label == "Left" else self.col("right_color")

    def draw(self, canvas, ctx: FrameContext):
        style = self.p("style")
        op = self.p("opacity") * ctx.intensity
        lw0 = self.p("line_width")
        js0 = self.p("joint_size")
        glow = self.p("glow")
        t = ctx.t

        # trails first (beneath the skeleton)
        if self.p("trails"):
            for (hid, tid), dq in self._trails.items():
                if len(dq) < 2:
                    continue
                pts = np.array([(x, y) for _, x, y in dq], dtype="f4")
                n = len(pts) - 1
                k = np.linspace(0.0, 1.0, n, dtype="f4")
                h = next((hh for hh in ctx.hands if hh.hand_id == hid), None)
                col = self._hand_color(h, style, t, tid) if h else (1, 1, 1)
                canvas.polyline(pts, col, glow=glow * 0.8, alphas=k * k * op * 0.9,
                                widths=lw0 * (0.3 + 1.7 * k))

        for h in ctx.hands:
            a = op * h.presence
            pts = h.lm[:, :2]
            s = float(np.clip(h.scale / 0.16, 0.6, 1.8)) if self.p("depth_scale") else 1.0
            lw = lw0 * s
            js = js0 * s
            if style == "Classic":
                segs = np.zeros((len(HAND_CONNECTIONS), 11), dtype="f4")
                for i, (p, q) in enumerate(HAND_CONNECTIONS):
                    segs[i, 0:4] = (*pts[p], *pts[q])
                segs[:, 4:7] = (0.15, 1.0, 0.25)
                segs[:, 7] = a
                segs[:, 8] = lw * 1.2
                segs[:, 9] = glow * 0.15
                segs[:, 10] = 0.0
                canvas.segments(segs)
                canvas.sprites(pts, js * 1.3, (1.0, 0.05, 0.05), alpha=a, glow=0.0, soft=0.0, additive=False)
                continue

            segs = np.zeros((len(HAND_CONNECTIONS), 11), dtype="f4")
            for i, (p, q) in enumerate(HAND_CONNECTIONS):
                segs[i, 0:4] = (*pts[p], *pts[q])
                segs[i, 4:7] = self._hand_color(h, style, t, i)
            segs[:, 7] = a * (0.55 if style == "Minimal" else 0.7)
            segs[:, 8] = lw * (0.5 if style == "Minimal" else 1.0)
            segs[:, 9] = 0.0 if style == "Minimal" else glow * 0.6
            segs[:, 10] = 1.0
            canvas.segments(segs)

            if style == "Hologram":
                # scanning band across the hand
                band = (t * 0.8) % 1.0
                for i, (p, q) in enumerate(HAND_CONNECTIONS):
                    y = (pts[p][1] + pts[q][1]) * 0.5
                    ymin, ymax = pts[:, 1].min(), pts[:, 1].max()
                    rel = (y - ymin) / max(ymax - ymin, 1e-3)
                    if abs(rel - band) < 0.12:
                        canvas.line(pts[p], pts[q], (0.8, 1.0, 1.0), lw * 1.6, glow * 1.5, a)

            if js > 0:
                cols = np.array([self._hand_color(h, style, t, i) for i in range(21)], dtype="f4")
                canvas.sprites(pts, js, cols, alpha=a * 0.75, glow=glow * 0.35, soft=0.0)
                canvas.sprites(pts, js * 0.45, (1.0, 1.0, 1.0), alpha=a * 0.9, glow=0.0, soft=0.0)
                # brighter fingertips
                tips = pts[list(TIPS)]
                canvas.sprites(tips, js * 1.4, cols[list(TIPS)], alpha=a * 0.35, glow=glow * 0.8, soft=0.6)

            if self.p("pulses") and style != "Minimal":
                for ci, chain in enumerate(CHAINS):
                    cp = pts[list(chain)]
                    seg_len = np.linalg.norm(np.diff(cp, axis=0), axis=1)
                    total = seg_len.sum()
                    if total < 1e-4:
                        continue
                    for k in range(2):
                        ph = (t * 0.9 + ci * 0.17 + k * 0.5) % 1.0
                        d = ph * total
                        acc = np.cumsum(seg_len)
                        j = int(np.searchsorted(acc, d))
                        j = min(j, len(seg_len) - 1)
                        prev = acc[j - 1] if j > 0 else 0.0
                        f = (d - prev) / max(seg_len[j], 1e-6)
                        pos = cp[j] + (cp[j + 1] - cp[j]) * f
                        fade = np.sin(ph * np.pi)
                        canvas.circle(pos, lw * 1.2, (1.0, 1.0, 1.0), glow=glow * 1.5, alpha=a * fade, soft=0.8)


class HandLinkEffect(Effect):
    id = "hand_link"
    name = "Hand Link"
    description = "Technical HUD lines connecting matching fingertips of both hands (reference 04)."
    category = "Tracking"
    default_order = 145
    uses_overlay = True
    PARAMS = [
        Param("fingers", "Connect", "choice", "Index + Thumb",
              choices=("Index + Thumb", "All fingers", "Index only", "Palms")),
        Param("color", "Colour", "color", "#ffffff"),
        Param("width", "Line thickness", "float", 1.6, 0.5, 8.0, 0.1),
        Param("double", "Double line", "bool", True),
        Param("glow", "Glow", "float", 2.0, 0.0, 20.0, 0.5),
        Param("dashes", "Travelling data packets", "bool", True),
        Param("opacity", "Opacity", "float", 0.9, 0.0, 1.0),
    ]

    def draw(self, canvas, ctx: FrameContext):
        pair = ctx.two_hands()
        if not pair:
            return
        a, b = pair
        alpha = self.p("opacity") * min(a.presence, b.presence) * ctx.intensity
        mode = self.p("fingers")
        if mode == "All fingers":
            ids = TIPS
        elif mode == "Index only":
            ids = (8,)
        elif mode == "Palms":
            ids = (0, 9)
        else:
            ids = (8, 4)
        col = self.col("color")
        w = self.p("width")
        g = self.p("glow")
        off = 3.0 / ctx.height
        for i in ids:
            p, q = a.lm[i, :2], b.lm[i, :2]
            canvas.line(p, q, col, w, g, alpha)
            if self.p("double"):
                d = q - p
                n = np.array([-d[1], d[0] * ctx.aspect])
                n /= max(np.linalg.norm(n), 1e-6)
                n = np.array([n[0] / ctx.aspect, n[1]]) * off * 2.0
                canvas.line(p + n, q + n, col, w * 0.6, 0.0, alpha * 0.6)
            if self.p("dashes"):
                for k in range(3):
                    ph = (ctx.t * 0.6 + k / 3.0 + i * 0.07) % 1.0
                    pos = p + (q - p) * ph
                    canvas.circle(pos, w * 1.6, col, glow=g * 2 + 3, alpha=alpha * np.sin(ph * np.pi))
        # corner brackets on the linked fingertips
        for h in (a, b):
            for i in ids:
                canvas.ring(h.lm[i, :2], 7.0, 1.2, col, glow=g, alpha=alpha * 0.8)
