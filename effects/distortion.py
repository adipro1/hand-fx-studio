"""Reality distortion: the webcam image itself is bent by your hands."""
from __future__ import annotations

import math

import numpy as np

from core.hand_tracker import TIPS
from effects.base_effect import Effect, FrameContext, Param, smooth_toward
from rendering.shader_manager import int_array, vec_array

FINGER_SETS = {"Index": (8,), "Thumb + Index": (4, 8), "All tips": TIPS, "Palms": (9,)}


class LiquidWarpEffect(Effect):
    id = "liquid_warp"
    name = "Liquid Space"
    description = ("Drag the world like liquid. Your fingertips push the image around and it "
                   "slowly flows back, with chromatic fringes on fast moves.")
    category = "Distortion"
    default_order = 10
    uses_image = True
    PARAMS = [
        Param("strength", "Strength", "float", 1.0, 0.0, 2.5),
        Param("fingers", "Fingers", "choice", "All tips", choices=tuple(FINGER_SETS)),
        Param("brush", "Brush size", "float", 0.07, 0.02, 0.25),
        Param("persistence", "Persistence", "float", 0.35, 0.02, 0.95,
              tip="How long the liquid keeps moving after your hand passes."),
        Param("flow", "Self-flow", "float", 0.6, 0.0, 2.0),
        Param("turbulence", "Turbulence", "float", 0.4, 0.0, 2.0),
        Param("chroma", "Chromatic aberration", "float", 1.2, 0.0, 4.0),
    ]

    def __init__(self):
        super().__init__()
        self._prev: dict = {}
        self._splats = []
        self._field = None

    def setup_gpu(self, r):
        for obj in getattr(self, "_fbo", []) + getattr(self, "_tex", []):
            obj.release()
        w, h = max(r.width // 3, 32), max(r.height // 3, 32)
        self._tex = [r.make_texture(w, h, 4, "f2") for _ in range(2)]
        self._fbo = [r.ctx.framebuffer([t]) for t in self._tex]
        for f in self._fbo:
            f.clear(0, 0, 0, 0)
        self._cur = 0

    def reset(self):
        self._prev.clear()
        if self._gpu_ready:
            for f in self._fbo:
                f.clear(0, 0, 0, 0)

    def update(self, ctx: FrameContext):
        ids = FINGER_SETS[self.p("fingers")]
        splats = []
        seen = set()
        for h in ctx.hands:
            if h.presence < 0.5:
                continue
            for i in ids:
                key = (h.hand_id, i)
                seen.add(key)
                p = np.array([h.lm[i, 0] * ctx.aspect, h.lm[i, 1]])
                prev = self._prev.get(key)
                self._prev[key] = p
                if prev is None or ctx.dt <= 0:
                    continue
                v = (p - prev) / ctx.dt
                sp = np.linalg.norm(v)
                if sp > 6.0:
                    v *= 6.0 / sp
                splats.append((h.lm[i, 0], h.lm[i, 1], self.p("brush") * (0.6 + h.scale * 2.5), v))
        for k in list(self._prev):
            if k not in seen:
                del self._prev[k]
        self._splats = splats[:12]

    def render_image(self, r, ctx: FrameContext):
        s = self._splats
        prog = r.shaders.program("liquid_sim.frag")
        r.fullscreen(prog, self._fbo[1 - self._cur], {"u_prev": self._tex[self._cur]}, {
            "u_splat": vec_array([(x, y, rad, 1.6 * self.p("strength")) for x, y, rad, _ in s], 12, 4),
            "u_splat_vel": vec_array([v for *_, v in s], 12, 2), "u_ns": len(s),
            "u_dt": ctx.dt, "u_decay": self.p("persistence"), "u_advect": self.p("flow"),
            "u_turbulence": self.p("turbulence")})
        self._cur = 1 - self._cur
        r.image_pass("warp.frag", {
            "u_field_amt": ctx.intensity, "u_np": 0, "u_nw": 0, "u_chroma": self.p("chroma"),
            "u_wave_width": 0.03, "u_ripple_freq": 20.0}, {"u_field": self._tex[self._cur]})


class FingerLensEffect(Effect):
    id = "finger_lens"
    name = "Finger Lens"
    description = ("Bend space at your fingertips. Pinch lens: the gap between thumb and index "
                   "becomes a magnifying bubble. Twist: rotate your wrist to swirl the world.")
    category = "Distortion"
    default_order = 12
    uses_image = True
    uses_overlay = True
    PARAMS = [
        Param("mode", "Mode", "choice", "Pinch lens",
              choices=("Pinch lens", "Fingertip bulge", "Black hole", "Twist", "Ripple")),
        Param("strength", "Strength", "float", 0.6, 0.0, 1.5),
        Param("size", "Size", "float", 1.0, 0.3, 3.0),
        Param("chroma", "Chromatic aberration", "float", 0.6, 0.0, 3.0),
        Param("rim", "Glowing rim", "bool", True),
        Param("rim_color", "Rim colour", "color", "#7fe8ff"),
    ]

    def __init__(self):
        super().__init__()
        self._pts = []
        self._twist: dict[int, float] = {}

    def update(self, ctx: FrameContext):
        mode = self.p("mode")
        st = self.p("strength") * ctx.intensity
        size = self.p("size")
        pts = []
        for h in ctx.hands:
            g = ctx.gesture(h)
            pr = h.presence
            if mode == "Pinch lens":
                c = (h.lm[4, :2] + h.lm[8, :2]) * 0.5
                gap = np.linalg.norm((h.pts[4] - h.pts[8]))
                rad = max(gap * 0.75, h.scale * 0.25) * size
                pts.append((c[0], c[1], rad, 0.55 * st * pr, 0, (0, 0)))
            elif mode == "Fingertip bulge":
                for i in TIPS:
                    if h.extension[TIPS.index(i)] > 0.4:
                        pts.append((h.lm[i, 0], h.lm[i, 1], h.scale * 0.55 * size, 0.45 * st * pr, 0, (0, 0)))
            elif mode == "Black hole":
                c = h.palm_uv
                openness = g.openness if g else 0.5
                pts.append((c[0], c[1], h.scale * 2.2 * size, -0.9 * st * pr * (0.3 + openness), 0, (0, 0)))
                pts.append((c[0], c[1], h.scale * 2.2 * size, 2.5 * st * pr, 1, (0, 0)))
            elif mode == "Twist":
                tw = self._twist.get(h.hand_id, h.rotation)
                tw = smooth_toward(tw, h.rotation, ctx.dt, 0.08)
                self._twist[h.hand_id] = tw
                c = h.palm_uv
                spread = g.spread if g else 0.5
                pts.append((c[0], c[1], h.scale * (1.6 + 2.0 * spread) * size, tw * 3.0 * st * pr, 1, (0, 0)))
            elif mode == "Ripple":
                for i in (8, 4):
                    pts.append((h.lm[i, 0], h.lm[i, 1], h.scale * 1.6 * size, 1.4 * st * pr, 2, (0, 0)))
        self._pts = pts[:12]

    def render_image(self, r, ctx: FrameContext):
        if not self._pts:
            return
        r.image_pass("warp.frag", {
            "u_field_amt": 0.0, "u_pts": vec_array([p[:4] for p in self._pts], 12, 4),
            "u_types": int_array([p[4] for p in self._pts], 12),
            "u_dirs": vec_array([p[5] for p in self._pts], 12, 2), "u_np": len(self._pts),
            "u_nw": 0, "u_chroma": self.p("chroma"), "u_wave_width": 0.03, "u_ripple_freq": 18.0})

    def draw(self, canvas, ctx: FrameContext):
        if not self.p("rim") or self.p("mode") not in ("Pinch lens", "Black hole"):
            return
        col = self.col("rim_color")
        for x, y, rad, st, t, _ in self._pts:
            if t != 0:
                continue
            px = rad * ctx.height
            canvas.ring((x, y), px * (0.98 if st > 0 else 0.45), 1.2, col, glow=6.0, alpha=min(abs(st) * 1.2, 1.0))


class ShockwaveEffect(Effect):
    id = "shockwave"
    name = "Shockwaves"
    description = ("Close your fist, clap your hands together or burst your palm open to send "
                   "a shockwave rippling through reality.")
    category = "Distortion"
    default_order = 14
    uses_image = True
    uses_overlay = True
    PARAMS = [
        Param("on_fist", "Trigger: close fist", "bool", True),
        Param("on_burst", "Trigger: fist -> open palm", "bool", True),
        Param("on_clap", "Trigger: hands together", "bool", True),
        Param("on_pinch", "Trigger: pinch (small)", "bool", False),
        Param("speed", "Speed", "float", 1.1, 0.2, 3.0),
        Param("amplitude", "Amplitude", "float", 0.03, 0.0, 0.1, 0.002),
        Param("rings", "Glowing rings", "bool", True),
        Param("color", "Ring colour", "color", "#a6f6ff"),
    ]

    def __init__(self):
        super().__init__()
        self.waves: list[list] = []   # [x, y, t0, scale]

    def reset(self):
        self.waves.clear()

    def spawn(self, uv, t, scale=1.0):
        self.waves.append([float(uv[0]), float(uv[1]), t, scale])
        self.waves = self.waves[-8:]

    def update(self, ctx: FrameContext):
        for name, hid, data in ctx.events:
            if name == "fist_close" and self.p("on_fist"):
                self.spawn(data["uv"], ctx.t, 1.0)
            elif name == "palm_burst" and self.p("on_burst"):
                self.spawn(data["uv"], ctx.t, 1.3)
            elif name == "hands_together" and self.p("on_clap"):
                self.spawn(data["uv"], ctx.t, 1.6)
            elif name == "pinch_start" and self.p("on_pinch"):
                p = data["pos"]
                self.spawn((p[0] / ctx.aspect, p[1]), ctx.t, 0.4)
        life = 1.6 / self.p("speed")
        self.waves = [w for w in self.waves if ctx.t - w[2] < life * w[3]]
        ctx.shared["shockwaves"] = self.waves

    def _wave_params(self, ctx):
        out = []
        for x, y, t0, sc in self.waves:
            age = ctx.t - t0
            rad = age * 0.9 * self.p("speed") * sc
            amp = self.p("amplitude") * sc * math.exp(-age * 1.8) * ctx.intensity
            out.append((x, y, rad, amp))
        return out

    def render_image(self, r, ctx: FrameContext):
        if not self.waves:
            return
        w = self._wave_params(ctx)
        r.image_pass("warp.frag", {"u_field_amt": 0.0, "u_np": 0, "u_waves": vec_array(w, 8, 4),
                                   "u_nw": len(w), "u_wave_width": 0.045, "u_chroma": 1.5,
                                   "u_ripple_freq": 20.0})

    def draw(self, canvas, ctx: FrameContext):
        if not self.p("rings"):
            return
        col = self.col("color")
        for x, y, rad, amp in self._wave_params(ctx):
            a = min(amp / max(self.p("amplitude"), 1e-4), 1.0)
            canvas.ring((x, y), rad * ctx.height, 2.5 * a + 0.5, col, glow=10.0, alpha=a * 0.8)


class KaleidoscopeEffect(Effect):
    id = "kaleidoscope"
    name = "Kaleidoscope"
    description = ("Mirror the world into a kaleidoscope centred between your hands. Raise "
                   "more fingers for more mirror segments; rotate your wrist to spin it.")
    category = "Distortion"
    default_order = 25
    uses_image = True
    PARAMS = [
        Param("segments", "Base segments", "int", 6, 2, 16, 1),
        Param("finger_count", "Fingers add segments", "bool", True),
        Param("spin", "Auto spin speed", "float", 0.15, -2.0, 2.0),
        Param("wrist_spin", "Wrist controls rotation", "bool", True),
        Param("zoom", "Zoom", "float", 1.0, 0.4, 3.0),
        Param("amount", "Mix", "float", 1.0, 0.0, 1.0),
        Param("local", "Only around hands", "bool", False),
        Param("hue", "Rainbow shift", "float", 0.0, 0.0, 2.0),
        Param("needs_hands", "Only when hands visible", "bool", True),
    ]

    def __init__(self):
        super().__init__()
        self._center = np.array([0.5, 0.5])
        self._seg = 6.0
        self._rot = 0.0
        self._amount = 0.0
        self._radius = 0.4

    def update(self, ctx: FrameContext):
        hands = [h for h in ctx.hands if h.presence > 0.3]
        target_amt = 0.0
        if hands:
            c = np.mean([h.palm_uv for h in hands], axis=0)
            self._center = self._center + (c - self._center) * (1 - 0.5 ** (ctx.dt / 0.08))
            fingers = sum(float(np.sum(h.extension > 0.5)) for h in hands)
            seg = self.p("segments") + (fingers if self.p("finger_count") else 0)
            self._seg = smooth_toward(self._seg, seg, ctx.dt, 0.15)
            if self.p("wrist_spin"):
                self._rot = smooth_toward(self._rot, -hands[0].rotation * 2.0, ctx.dt, 0.1)
            target_amt = 1.0
            if len(hands) >= 2:
                self._radius = float(np.linalg.norm(hands[0].palm_center - hands[1].palm_center)) * 0.7
            else:
                self._radius = hands[0].scale * 3.0
        elif not self.p("needs_hands"):
            target_amt = 1.0
            self._center += (np.array([0.5, 0.5]) - self._center) * 0.05
        self._amount = smooth_toward(self._amount, target_amt, ctx.dt, 0.2)
        self._rot += self.p("spin") * ctx.dt

    def render_image(self, r, ctx: FrameContext):
        if self._amount < 0.01:
            return
        r.image_pass("kaleido.frag", {
            "u_center": tuple(self._center), "u_segments": float(round(self._seg * 2) / 2),
            "u_rotation": self._rot, "u_zoom": self.p("zoom"),
            "u_amount": self._amount * self.p("amount") * ctx.intensity,
            "u_radius": max(self._radius, 0.1) if self.p("local") else -1.0,
            "u_hue": self.p("hue")})
