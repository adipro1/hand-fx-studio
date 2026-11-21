"""Hand-frame effects recreated from the reference videos.

* FilterFrameEffect  – ref 02/04: polygon between both hands' thumb & index tips,
                       stylised filter inside; close the frame to switch filter.
* FingerBandsEffect  – ref 03: strips between matching fingertips, each with its own filter.
* GlassPrismEffect   – ref 01: glass slab with time echoes, facets and refraction.
"""
from __future__ import annotations

from collections import deque

import numpy as np

from effects.base_effect import Effect, FrameContext, Param, smooth_toward
from rendering import filter_modes as fm
from rendering.shader_manager import float_array, int_array, vec_array

TIP_ORDER = (4, 8, 12, 16, 20)


def two_hand_quad(ctx: FrameContext) -> tuple[np.ndarray, float, float] | None:
    """[left index, right index, right thumb, left thumb] in uv, min presence, mean scale."""
    pair = ctx.two_hands()
    if not pair:
        return None
    a, b = pair
    quad = np.array([a.lm[8, :2], b.lm[8, :2], b.lm[4, :2], a.lm[4, :2]], dtype="f4")
    return quad, min(a.presence, b.presence), (a.scale + b.scale) * 0.5


def one_hand_poly(ctx: FrameContext) -> tuple[np.ndarray, float, float] | None:
    if len(ctx.hands) != 1:
        return None
    h = ctx.hands[0]
    poly = np.array([h.lm[i, :2] for i in TIP_ORDER], dtype="f4")
    return poly, h.presence, h.scale


def span_aspect(poly: np.ndarray, aspect: float) -> float:
    p = poly.copy()
    p[:, 0] *= aspect
    d = np.linalg.norm(p[:, None, :] - p[None, :, :], axis=-1)
    return float(d.max())


def centroid(poly: np.ndarray) -> np.ndarray:
    return poly.mean(axis=0)


class FilterFrameEffect(Effect):
    id = "filter_frame"
    name = "Filter Frame"
    description = ("Make an L-shape with both hands: the area between your thumbs and index "
                   "fingers becomes a lens with a stylised filter. Touch the fingertips "
                   "together to close the frame and switch to the next filter.")
    category = "Reference FX"
    default_order = 40
    uses_image = True
    uses_overlay = True
    PARAMS = [
        Param("filter", "Filter", "choice", fm.FILTER_NAMES[0], choices=fm.FILTER_NAMES),
        Param("pinch_cycle", "Close frame to switch filter", "bool", True),
        Param("shuffle", "Random next filter", "bool", False),
        Param("one_hand", "One hand: fingertip lens", "bool", True),
        Param("cell", "Dot / pixel size", "float", 7.0, 3.0, 24.0, 0.5),
        Param("amount", "Filter strength", "float", 0.6, 0.0, 1.0),
        Param("outline", "Outline thickness", "float", 2.5, 0.0, 10.0, 0.5),
        Param("auto_outline", "Outline colour from filter", "bool", True),
        Param("outline_color", "Outline colour", "color", "#ffffff"),
        Param("edge_glow", "Outline glow", "float", 0.35, 0.0, 1.5),
        Param("lens_zoom", "Lens magnification", "float", 0.0, 0.0, 0.8),
        Param("chroma", "Chromatic split", "float", 0.0, 0.0, 0.06, 0.002),
        Param("outside_dim", "Dim outside", "float", 0.0, 0.0, 0.9),
        Param("corners", "Corner markers", "bool", True),
    ]

    def __init__(self):
        super().__init__()
        self._poly: np.ndarray | None = None
        self._mix = 0.0
        self._closed = False
        self._closed_time = 0.0
        self._idx = fm.index_of(self.p("filter"))
        self._flash = 0.0
        self._two = False
        self._rng = np.random.default_rng()

    def on_param_changed(self, key):
        if key == "filter":
            self._idx = fm.index_of(self.p("filter"))

    @property
    def mode(self) -> fm.FilterMode:
        return fm.FILTERS[self._idx]

    def next_filter(self, step: int = 1):
        if self.p("shuffle"):
            choices = [i for i in range(len(fm.FILTERS)) if i != self._idx]
            self._idx = int(self._rng.choice(choices))
        else:
            self._idx = (self._idx + step) % len(fm.FILTERS)
        self.params["filter"] = fm.FILTERS[self._idx].name
        self._flash = 1.0

    def update(self, ctx: FrameContext):
        q = two_hand_quad(ctx)
        self._two = q is not None
        if q is None and self.p("one_hand"):
            q = one_hand_poly(ctx)
        target = 0.0
        if q is not None:
            poly, presence, scale = q
            self._poly = poly
            target = presence
            if self._two and self.p("pinch_cycle"):
                span = span_aspect(poly, ctx.aspect)
                if not self._closed and span < scale * 0.55:
                    self._closed = True
                    self._closed_time = 0.0
                elif self._closed:
                    self._closed_time += ctx.dt
                    if span > scale * 1.1:
                        self._closed = False
                        if self._closed_time > 0.12:
                            self.next_filter()
        self._mix = smooth_toward(self._mix, target, ctx.dt, 0.06)
        self._flash = max(0.0, self._flash - ctx.dt * 2.5)
        self.status = f"Filter: {self.mode.name}" + ("  (closed)" if self._closed else "")

    def render_image(self, r, ctx: FrameContext):
        if self._poly is None or self._mix < 0.01:
            return
        m = self.mode
        poly = self._poly
        outline = m.outline if self.p("auto_outline") else self.col("outline_color")
        r.image_pass("region.frag", {
            "u_poly": vec_array(poly, 8), "u_n": len(poly), "u_mode": m.shader_id,
            "u_amount": self.p("amount"), "u_cell": self.p("cell") * (m.cell / 7.0) * r.height / 720.0,
            "u_c1": m.c1, "u_c2": m.c2, "u_mix": self._mix * ctx.intensity,
            "u_outline_col": tuple(outline), "u_outline_w": self.p("outline") * r.height / 720.0,
            "u_stepped": 1 if m.stepped else 0, "u_refract": self.p("lens_zoom"),
            "u_chroma": self.p("chroma"), "u_outside_dim": self.p("outside_dim") * self._mix,
            "u_outside_tint": (1.0, 1.0, 1.0), "u_outside_tint_amt": 0.0,
            "u_centroid": tuple(centroid(poly)),
        })

    def draw(self, canvas, ctx: FrameContext):
        if self._poly is None or self._mix < 0.01:
            return
        m = self.mode
        col = m.outline if self.p("auto_outline") else self.col("outline_color")
        a = self._mix * ctx.intensity
        g = self.p("edge_glow")
        if g > 0 and not m.stepped:
            canvas.polyline(self._poly, col, width=self.p("outline") * 0.6, glow=8.0, alpha=a * g, closed=True)
        if self.p("corners"):
            for p in self._poly:
                canvas.circle(p, 3.0 + 4.0 * self._flash, col, glow=6.0, alpha=a)
        if self._flash > 0:
            c = centroid(self._poly)
            canvas.ring(c, 20 + (1 - self._flash) * 160, 3.0 * self._flash, col, glow=10, alpha=self._flash * a)


class FingerBandsEffect(Effect):
    id = "finger_bands"
    name = "Finger Bands"
    description = ("Hold both hands up facing each other: strips between matching fingertips "
                   "each show a different layer of reality — thermal, edge sketch, scanlines (reference 03).")
    category = "Reference FX"
    default_order = 42
    uses_image = True
    uses_overlay = True
    PARAMS = [
        Param("band1", "Top band", "choice", "Thermal", choices=fm.FILTER_NAMES),
        Param("band2", "Band 2", "choice", "Edge Sketch", choices=fm.FILTER_NAMES),
        Param("band3", "Band 3", "choice", "Scanline Glitch", choices=fm.FILTER_NAMES),
        Param("band4", "Band 4", "choice", "Rainbow Heat", choices=fm.FILTER_NAMES),
        Param("extended_only", "Only extended fingers", "bool", True),
        Param("cell", "Dot / pixel size", "float", 6.0, 3.0, 20.0, 0.5),
        Param("amount", "Filter strength", "float", 0.6, 0.0, 1.0),
        Param("line_width", "Divider lines", "float", 1.2, 0.0, 6.0, 0.1),
        Param("line_color", "Divider colour", "color", "#ffffff"),
        Param("tip_glow", "Fingertip hot spots", "bool", True),
    ]

    def __init__(self):
        super().__init__()
        self._alive = np.zeros(5)
        self._pair = None

    def update(self, ctx: FrameContext):
        pair = ctx.two_hands()
        self._pair = pair
        target = np.zeros(5)
        if pair:
            a, b = pair
            for i in range(5):
                if self.p("extended_only"):
                    ok = min(a.extension[i], b.extension[i]) > 0.35
                else:
                    ok = True
                target[i] = 1.0 if ok else 0.0
            target *= min(a.presence, b.presence)
        k = 1.0 - 0.5 ** (ctx.dt / 0.07)
        self._alive += (target - self._alive) * k

    def _bands(self):
        if not self._pair:
            return [], []
        a, b = self._pair
        fingers = [i for i in range(5) if self._alive[i] > 0.02]
        quads, alive = [], []
        for f0, f1 in zip(fingers[:-1], fingers[1:]):
            t0, t1 = TIP_ORDER[f0], TIP_ORDER[f1]
            q = np.array([a.lm[t0, :2], b.lm[t0, :2], b.lm[t1, :2], a.lm[t1, :2]], dtype="f4")
            quads.append(q)
            alive.append(min(self._alive[f0], self._alive[f1]))
        # assign filters from the top of the screen downwards
        order = np.argsort([q[:, 1].mean() for q in quads]) if quads else []
        return [quads[i] for i in order][:4], [alive[i] for i in order][:4]

    def render_image(self, r, ctx: FrameContext):
        quads, alive = self._bands()
        if not quads:
            return
        modes = [fm.by_name(self.p(f"band{i + 1}")) for i in range(4)]
        r.image_pass("bands.frag", {
            "u_quads": vec_array(np.concatenate(quads), 16), "u_nb": len(quads),
            "u_modes": int_array([m.shader_id for m in modes], 4),
            "u_alive": float_array(np.asarray(alive) * ctx.intensity, 4),
            "u_amount": self.p("amount"), "u_cell": self.p("cell") * r.height / 720.0,
            "u_c1": fm.NAVY, "u_c2": fm.CYAN,
            "u_line_col": self.col("line_color"), "u_line_w": 0.0,
        })

    def draw(self, canvas, ctx: FrameContext):
        if not self._pair:
            return
        a, b = self._pair
        col = self.col("line_color")
        for i in range(5):
            al = self._alive[i] * ctx.intensity
            if al < 0.02:
                continue
            t = TIP_ORDER[i]
            if self.p("line_width") > 0:
                canvas.line(a.lm[t, :2], b.lm[t, :2], col, self.p("line_width"), 3.0, al * 0.85)
            if self.p("tip_glow"):
                for h in (a, b):
                    canvas.circle(h.lm[t, :2], 5.0, (1.0, 0.35, 0.1), glow=10.0, alpha=al * 0.8, soft=0.7)


class GlassPrismEffect(Effect):
    id = "glass_prism"
    name = "Glass Prism"
    description = ("A slab of glass held between your hands: the world inside is bright and "
                   "refracted, while echoes of the frame trail behind your movement (reference 01).")
    category = "Reference FX"
    default_order = 44
    uses_image = True
    uses_overlay = True
    PARAMS = [
        Param("echoes", "Echo count", "int", 4, 0, 8, 1),
        Param("echo_lag", "Echo delay (s)", "float", 0.06, 0.02, 0.25, 0.01),
        Param("brightness", "Glass brightness", "float", 0.5, 0.0, 1.0),
        Param("tint", "Glass tint", "color", "#c8dcff"),
        Param("refraction", "Refraction", "float", 0.08, 0.0, 0.5),
        Param("chroma", "Prism dispersion", "float", 0.015, 0.0, 0.06, 0.001),
        Param("outside_dim", "Dim outside", "float", 0.35, 0.0, 0.9),
        Param("outside_tint", "Outside tint", "color", "#4a5cff"),
        Param("facets", "Refraction facets", "bool", True),
        Param("glint_a", "Glint colour A", "color", "#30f0ff"),
        Param("glint_b", "Glint colour B", "color", "#ff40d0"),
        Param("line_width", "Edge thickness", "float", 1.3, 0.3, 5.0, 0.1),
    ]

    def __init__(self):
        super().__init__()
        self._hist: deque = deque(maxlen=240)
        self._poly = None
        self._mix = 0.0

    def reset(self):
        self._hist.clear()

    def update(self, ctx: FrameContext):
        q = two_hand_quad(ctx) or one_hand_poly(ctx)
        target = 0.0
        if q is not None:
            poly, presence, _ = q
            if self._poly is not None and len(self._poly) != len(poly):
                self._hist.clear()
            self._poly = poly
            self._hist.append((ctx.t, poly.copy()))
            target = presence
        self._mix = smooth_toward(self._mix, target, ctx.dt, 0.08)
        while self._hist and ctx.t - self._hist[0][0] > 2.5:
            self._hist.popleft()

    def _echo(self, t_back: float, now: float):
        target = now - t_back
        best = None
        for t, p in reversed(self._hist):
            best = p
            if t <= target:
                break
        return best

    def render_image(self, r, ctx: FrameContext):
        if self._poly is None or self._mix < 0.01:
            return
        tint = np.array(self.col("tint"))
        r.image_pass("region.frag", {
            "u_poly": vec_array(self._poly, 8), "u_n": len(self._poly), "u_mode": 10,
            "u_amount": 1.0, "u_cell": 7.0, "u_c1": tuple(tint * (0.6 + 0.6 * self.p("brightness"))),
            "u_c2": (1.0, 1.0, 1.0), "u_mix": self._mix * ctx.intensity,
            "u_outline_col": (1.0, 1.0, 1.0), "u_outline_w": 0.0, "u_stepped": 0,
            "u_refract": self.p("refraction"), "u_chroma": self.p("chroma"),
            "u_outside_dim": self.p("outside_dim") * self._mix * ctx.intensity,
            "u_outside_tint": self.col("outside_tint"), "u_outside_tint_amt": 0.55 * self._mix,
            "u_centroid": tuple(centroid(self._poly)),
        })

    def draw(self, canvas, ctx: FrameContext):
        if self._poly is None or self._mix < 0.01:
            return
        a = self._mix * ctx.intensity
        lw = self.p("line_width")
        cur = self._poly
        n = len(cur)
        ga, gb = self.col("glint_a"), self.col("glint_b")
        echoes = []
        for k in range(1, self.p("echoes") + 1):
            e = self._echo(k * self.p("echo_lag"), ctx.t)
            if e is not None and len(e) == n:
                echoes.append(e)
        for k, e in enumerate(echoes):
            fade = 1.0 - (k + 1) / (len(echoes) + 1)
            canvas.polyline(e, (0.85, 0.9, 1.0), width=lw * 0.8, glow=2.0, alpha=a * fade * 0.7, closed=True)
            if self.p("facets"):
                for i in range(n):
                    j = (i + 1) % n
                    c0 = (*ga, 0.10 * fade * a) if i % 2 == 0 else (*gb, 0.10 * fade * a)
                    c1 = (1.0, 1.0, 1.0, 0.02 * a)
                    canvas.polygon([cur[i], cur[j], e[j], e[i]], ga, additive=True,
                                   colors=[c0, c0, c1, c1])
                    canvas.line(cur[i], e[i], (0.9, 0.95, 1.0), lw * 0.6, 1.5, a * fade * 0.6)
        # glints at the corners
        for i, p in enumerate(cur):
            canvas.circle(p, 2.5, ga if i % 2 else gb, glow=7.0, alpha=a * 0.9)
        canvas.polyline(cur, (1.0, 1.0, 1.0), width=lw, glow=3.0, alpha=a, closed=True)
