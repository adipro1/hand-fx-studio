"""Energy effects: lightning, plasma orbs, palm fields, beams and energy trails."""
from __future__ import annotations

import math
from collections import deque

import numpy as np

from core.hand_tracker import TIPS
from effects.base_effect import Effect, FrameContext, Param


def lightning_path(a: np.ndarray, b: np.ndarray, rng, jag: float, depth: int = 6) -> np.ndarray:
    """Midpoint-displacement lightning bolt between a and b (aspect space)."""
    pts = np.array([a, b], dtype=np.float32)
    disp = np.linalg.norm(b - a) * jag
    for _ in range(depth):
        mids = (pts[:-1] + pts[1:]) * 0.5
        d = pts[1:] - pts[:-1]
        n = np.column_stack([-d[:, 1], d[:, 0]])
        n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-9
        mids += n * rng.normal(0, disp, (len(mids), 1))
        out = np.empty((len(pts) + len(mids), 2), np.float32)
        out[0::2] = pts
        out[1::2] = mids
        pts = out
        disp *= 0.55
    return pts


class EnergyEffect(Effect):
    id = "energy"
    name = "Energy"
    description = ("Lightning crackles between the fingertips of your two hands, a plasma orb "
                   "forms in your pinch, open palms radiate energy fields, and fast moves leave "
                   "energy trails. Point both index fingers at each other to fire a beam.")
    category = "Energy"
    default_order = 120
    uses_overlay = True
    PARAMS = [
        Param("color", "Energy colour", "color", "#4fc3ff"),
        Param("core_color", "Core colour", "color", "#ffffff"),
        Param("lightning", "Lightning between hands", "bool", True),
        Param("lightning_fingers", "Lightning fingers", "choice", "All tips",
              choices=("All tips", "Index only", "Index + Thumb")),
        Param("pinch_arc", "Arc inside each hand", "bool", True),
        Param("orbs", "Pinch orbs", "bool", True),
        Param("palm_field", "Palm energy field", "bool", True),
        Param("beam", "Pointing beam", "bool", True),
        Param("trails", "Energy trails on fast moves", "bool", True),
        Param("jaggedness", "Jaggedness", "float", 0.18, 0.02, 0.5),
        Param("flicker", "Flicker rate", "float", 24.0, 2.0, 60.0, 1.0),
        Param("intensity", "Intensity", "float", 1.0, 0.1, 2.5),
        Param("thickness", "Thickness", "float", 1.0, 0.3, 3.0),
    ]

    def __init__(self):
        super().__init__()
        self.rng = np.random.default_rng(11)
        self._bolts: list[tuple[np.ndarray, float]] = []
        self._next_regen = 0.0
        self._trails: dict[int, deque] = {}

    def reset(self):
        self._trails.clear()

    def update(self, ctx: FrameContext):
        if self.p("trails"):
            for h in ctx.hands:
                dq = self._trails.setdefault(h.hand_id, deque(maxlen=40))
                dq.append((ctx.t, h.palm_center.copy(), h.speed))
            for k in list(self._trails):
                dq = self._trails[k]
                while dq and ctx.t - dq[0][0] > 0.35:
                    dq.popleft()
                if not dq:
                    del self._trails[k]
        if ctx.t >= self._next_regen:
            self._next_regen = ctx.t + 1.0 / self.p("flicker")
            self._bolts = self._make_bolts(ctx)

    def _make_bolts(self, ctx):
        bolts = []
        jag = self.p("jaggedness")
        pair = ctx.two_hands()
        if self.p("lightning") and pair:
            a, b = pair
            sel = self.p("lightning_fingers")
            ids = TIPS if sel == "All tips" else ((8,) if sel == "Index only" else (4, 8))
            scale = (a.scale + b.scale) * 0.5
            for i in ids:
                pa, pb = a.pts[i], b.pts[i]
                d = float(np.linalg.norm(pb - pa))
                # closer hands -> stronger, more stable lightning
                strength = float(np.clip(1.6 - d / (scale * 6.0), 0.15, 1.0))
                if self.rng.random() > 0.25 + 0.75 * strength:
                    continue
                path = lightning_path(pa, pb, self.rng, jag)
                bolts.append((path, strength))
                if self.rng.random() < 0.35:   # side branch
                    k = self.rng.integers(len(path) // 4, 3 * len(path) // 4)
                    end = path[k] + self.rng.normal(0, d * 0.25, 2)
                    bolts.append((lightning_path(path[k], end, self.rng, jag, 4), strength * 0.5))
        if self.p("pinch_arc"):
            for h in ctx.hands:
                g = ctx.gesture(h)
                if g is None or h.presence < 0.8:
                    continue
                if 0.15 < g.pinch < 0.92:
                    bolts.append((lightning_path(h.pts[4], h.pts[8], self.rng, jag * 1.3, 4), 0.7))
        return bolts

    def draw(self, canvas, ctx: FrameContext):
        A = ctx.aspect
        col = np.array(self.col("color"))
        core = np.array(self.col("core_color"))
        I = self.p("intensity") * ctx.intensity
        th = self.p("thickness")

        # energy trails
        if self.p("trails"):
            for dq in self._trails.values():
                if len(dq) < 3:
                    continue
                pts = np.array([p for _, p, _ in dq])
                sp = np.array([s for _, _, s in dq])
                strength = np.clip((sp[1:] - 0.8) / 1.5, 0, 1)
                if strength.max() < 0.05:
                    continue
                uv = np.column_stack([pts[:, 0] / A, pts[:, 1]])
                k = np.linspace(0, 1, len(uv) - 1)
                canvas.polyline(uv, col * 1.5, glow=14.0, alphas=k * strength * I, widths=th * (2 + 14 * k * strength))

        # lightning
        for path, s in self._bolts:
            uv = np.column_stack([path[:, 0] / A, path[:, 1]])
            canvas.polyline(uv, col * 1.4, width=th * 2.6 * s, glow=7.0, alpha=0.35 * I * s)
            canvas.polyline(uv, core, width=th * 1.0 * s, glow=2.0, alpha=0.8 * I * s)

        for h in ctx.hands:
            g = ctx.gesture(h)
            if g is None:
                continue
            pr = h.presence * I
            # plasma orb in the pinch
            if self.p("orbs") and g.pinch > 0.15:
                c = (h.lm[4, :2] + h.lm[8, :2]) * 0.5
                gap = float(np.linalg.norm(h.pts[4] - h.pts[8]))
                r_px = max(gap * 0.42, 0.012) * ctx.height
                wob = 1.0 + 0.08 * math.sin(ctx.t * 13.0)
                canvas.circle(c, r_px * 1.8 * wob, col, glow=r_px * 0.8, alpha=0.25 * pr, soft=1.0)
                canvas.circle(c, r_px * wob, col * 1.4, glow=r_px * 0.6, alpha=0.75 * pr, soft=0.6)
                canvas.circle(c, r_px * 0.45, core * 1.5, glow=8.0, alpha=pr, soft=0.4)
                # orbiting plasma motes
                n = 10
                ang = ctx.t * np.linspace(2.0, 4.5, n) + np.arange(n) * 2.4
                rr = r_px * (0.9 + 0.35 * np.sin(ctx.t * 3 + np.arange(n))) / ctx.height
                pos = np.column_stack([c[0] + np.cos(ang) * rr / A, c[1] + np.sin(ang) * rr * 0.6])
                canvas.sprites(pos, 2.0, core, alpha=pr * 0.9, glow=5.0, soft=0.5)
            # palm field
            if self.p("palm_field") and g.openness > 0.65 and g.pinch < 0.5:
                f = (g.openness - 0.65) / 0.35 * pr
                c = h.palm_uv
                R = h.scale * 1.3 * ctx.height
                for k in range(3):
                    rr = R * (0.7 + 0.25 * k + 0.05 * math.sin(ctx.t * 4 + k))
                    canvas.ring(c, rr, 1.5, col * 1.3, glow=8.0, alpha=f * (0.7 - 0.18 * k))
                for j in range(6):
                    a0 = ctx.t * (1.5 if j % 2 else -1.1) + j * math.pi / 3
                    ang = np.linspace(a0, a0 + 0.6, 8)
                    pts = np.column_stack([c[0] + np.cos(ang) * R * 1.15 / ctx.height / A,
                                           c[1] + np.sin(ang) * R * 1.15 / ctx.height])
                    canvas.polyline(pts, core, width=2.0, glow=6.0, alpha=f * 0.7)
                canvas.circle(c, R * 0.6, col, glow=R * 0.3, alpha=f * 0.18, soft=1.0)

        # pointing beam
        pair = ctx.two_hands()
        if self.p("beam") and pair:
            a, b = pair
            ga, gb = ctx.gesture(a), ctx.gesture(b)
            if ga and gb and ga.point > 0.5 and gb.point > 0.5:
                s = min(ga.point, gb.point) * I
                p, q = a.lm[8, :2], b.lm[8, :2]
                w = 6.0 + 3.0 * math.sin(ctx.t * 30)
                canvas.line(p, q, col * 1.6, w * th, 18.0, 0.8 * s)
                canvas.line(p, q, core, w * 0.35 * th, 4.0, s)
                for pt in (p, q):
                    canvas.circle(pt, 9 * th, core, glow=16.0, alpha=s, soft=0.5)
