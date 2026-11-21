"""Portals: swirling gateways that open between your hands."""
from __future__ import annotations

import math

import numpy as np

from effects.base_effect import Effect, FrameContext, Param, lerp, smooth_toward
from rendering.shader_manager import float_array, vec_array

STYLES = ("Vortex tunnel", "Kaleido world", "Inverted dimension", "Thermal dimension")


class PortalEffect(Effect):
    id = "portal"
    name = "Portal"
    description = ("Hold both hands open facing each other to tear open a portal between them — "
                   "move them apart to grow it. With one hand, open your palm to summon a small "
                   "portal; close your fist to collapse it.")
    category = "Portals"
    default_order = 30
    uses_image = True
    uses_overlay = True
    PARAMS = [
        Param("style", "Interior", "choice", STYLES[0], choices=STYLES),
        Param("color_a", "Rim colour A", "color", "#ff7a18"),
        Param("color_b", "Rim colour B", "color", "#ffd23f"),
        Param("size", "Size", "float", 1.0, 0.3, 2.0),
        Param("spin", "Spin speed", "float", 1.0, -4.0, 4.0),
        Param("twist", "Tunnel twist", "float", 1.2, 0.0, 4.0),
        Param("rings", "Ring layers", "int", 3, 1, 6, 1),
        Param("sparks", "Rim sparks", "bool", True),
        Param("lens", "Space bending", "float", 0.6, 0.0, 2.0),
        Param("one_hand", "One-hand portal (open palm)", "bool", True),
    ]

    def __init__(self):
        super().__init__()
        self._portals: list[dict] = []
        self._state: dict = {}
        self._rng = np.random.default_rng(3)
        self._sparks = np.zeros((0, 4))   # angle, radius_rel, speed, life

    def reset(self):
        self._state.clear()
        self._sparks = np.zeros((0, 4))

    def _target_portals(self, ctx: FrameContext):
        out = []
        pair = ctx.two_hands()
        if pair:
            a, b = pair
            ga, gb = ctx.gesture(a), ctx.gesture(b)
            open_ = min(ga.openness if ga else 0.5, gb.openness if gb else 0.5)
            c = (a.palm_uv + b.palm_uv) * 0.5
            d = float(np.linalg.norm(a.palm_center - b.palm_center))
            rad = d * 0.42 * self.p("size")
            ang = math.atan2(b.palm_center[1] - a.palm_center[1], b.palm_center[0] - a.palm_center[0])
            op = float(np.clip((open_ - 0.25) / 0.45, 0, 1)) * min(a.presence, b.presence)
            out.append(("two", c, rad, op, ang))
        elif self.p("one_hand"):
            for h in ctx.hands:
                g = ctx.gesture(h)
                if not g:
                    continue
                op = float(np.clip((g.openness - 0.55) / 0.3, 0, 1)) * h.presence
                rad = h.scale * (1.0 + 1.4 * g.spread) * self.p("size")
                out.append((h.hand_id, h.palm_uv, rad, op, h.rotation))
        return out

    def update(self, ctx: FrameContext):
        targets = self._target_portals(ctx)
        seen = set()
        for key, c, rad, op, ang in targets:
            seen.add(key)
            st = self._state.setdefault(key, {"c": np.array(c), "r": rad, "open": 0.0, "spin": 0.0, "ang": ang})
            k = 1 - 0.5 ** (ctx.dt / 0.06)
            st["c"] = st["c"] + (np.array(c) - st["c"]) * k
            st["r"] = lerp(st["r"], rad, k)
            st["open"] = smooth_toward(st["open"], op, ctx.dt, 0.18 if op > st["open"] else 0.1)
            st["spin"] += ctx.dt * self.p("spin") * (1.0 + 0.5 * math.sin(ctx.t * 0.7))
            st["ang"] = ang
        for key in list(self._state):
            if key not in seen:
                st = self._state[key]
                st["open"] = smooth_toward(st["open"], 0.0, ctx.dt, 0.08)
                if st["open"] < 0.01:
                    del self._state[key]
        self._portals = sorted(self._state.values(), key=lambda s: -s["open"])[:2]

        # sparks orbiting the rim
        if self.p("sparks") and self._portals:
            n_new = int(ctx.dt * 220 * sum(p["open"] for p in self._portals))
            if n_new:
                new = np.column_stack([self._rng.uniform(0, 2 * math.pi, n_new),
                                       self._rng.uniform(0.95, 1.12, n_new),
                                       self._rng.uniform(1.5, 4.0, n_new) * np.sign(self.p("spin") or 1),
                                       self._rng.uniform(0.4, 1.0, n_new)])
                self._sparks = np.vstack([self._sparks, new])[-900:]
        if len(self._sparks):
            self._sparks[:, 0] += self._sparks[:, 2] * ctx.dt
            self._sparks[:, 1] += ctx.dt * 0.25
            self._sparks[:, 3] -= ctx.dt * 0.9
            self._sparks = self._sparks[self._sparks[:, 3] > 0]

    def render_image(self, r, ctx: FrameContext):
        ps = [p for p in self._portals if p["open"] > 0.01]
        if not ps:
            return
        r.image_pass("portal.frag", {
            "u_portals": vec_array([(p["c"][0], p["c"][1], p["r"], p["open"] * ctx.intensity) for p in ps], 2, 4),
            "u_spin": float_array([p["spin"] for p in ps], 2), "u_np": len(ps),
            "u_style": STYLES.index(self.p("style")), "u_twist": self.p("twist"),
            "u_lens": self.p("lens"), "u_tint": self.col("color_a")})

    def draw(self, canvas, ctx: FrameContext):
        ca, cb = np.array(self.col("color_a")), np.array(self.col("color_b"))
        H = ctx.height
        for p in self._portals:
            op = p["open"] * ctx.intensity
            if op < 0.01:
                continue
            c = p["c"]
            R = p["r"] * p["open"]
            # layered rotating arcs
            for k in range(self.p("rings")):
                rr = R * (1.0 + 0.06 * k)
                n_arcs = 3 + k
                for j in range(n_arcs):
                    a0 = p["spin"] * (1.0 + 0.4 * k) * (-1 if k % 2 else 1) + j * 2 * math.pi / n_arcs
                    span = 2 * math.pi / n_arcs * (0.55 + 0.25 * math.sin(ctx.t * 1.3 + k + j))
                    ang = np.linspace(a0, a0 + span, 18)
                    pts = np.column_stack([c[0] + np.cos(ang) * rr / ctx.aspect, c[1] + np.sin(ang) * rr])
                    col = ca + (cb - ca) * (k / max(self.p("rings") - 1, 1))
                    canvas.polyline(pts, col * 1.3, width=2.6 - 0.3 * k, glow=9.0, alpha=op * (0.9 - 0.12 * k))
            canvas.ring(c, R * H, 2.0, (1.0, 0.95, 0.8), glow=14.0, alpha=op * 0.9)
            canvas.ring(c, R * H * 1.02, 6.0, tuple(ca), glow=20.0, alpha=op * 0.35)
            if len(self._sparks):
                sp = self._sparks
                ang = sp[:, 0]
                rad = R * sp[:, 1]
                pos = np.column_stack([c[0] + np.cos(ang) * rad / ctx.aspect, c[1] + np.sin(ang) * rad])
                cols = ca[None, :] * (1 - sp[:, 3:4]) + cb[None, :] * sp[:, 3:4]
                canvas.sprites(pos, 2.2, cols * 1.5, alpha=sp[:, 3] * op, glow=5.0, soft=0.6)
