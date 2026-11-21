"""GPU-rendered, NumPy-simulated particle system driven by your hands.

Physics runs in aspect-corrected space (x * aspect, y) so motion is isotropic.
"""
from __future__ import annotations

import math

import numpy as np

from core.hand_tracker import TIPS
from effects.base_effect import Effect, FrameContext, Param

MODES = {
    # name: (palette hue range, life, speed, gravity, drag, size, glow, swirl)
    "Neon":     ((0.48, 0.92), 1.6, 0.25, 0.0, 1.6, 2.6, 5.0, 0.6),
    "Fire":     ((0.0, 0.11), 1.0, 0.20, -0.55, 2.0, 3.4, 6.0, 0.9),
    "Sparks":   ((0.08, 0.15), 0.8, 0.70, 1.20, 0.8, 1.6, 4.0, 0.1),
    "Stardust": ((0.55, 0.75), 3.0, 0.08, 0.0, 2.5, 1.8, 3.0, 0.4),
    "Vortex":   ((0.70, 1.05), 2.2, 0.20, 0.0, 1.0, 2.2, 5.0, 0.0),
    "Rainbow":  ((0.0, 1.0), 1.8, 0.22, 0.0, 1.6, 2.6, 5.0, 0.7),
    "Plexus":   ((0.50, 0.58), 3.5, 0.06, 0.0, 2.8, 1.8, 3.0, 0.3),
}
EMITTERS = ("Extended fingertips", "Index finger", "Palms", "All landmarks")


def hsv_np(h, s=1.0, v=1.0) -> np.ndarray:
    """Vectorised HSV -> RGB for arrays of hues."""
    h = np.mod(h, 1.0)[:, None]
    k = np.mod(np.array([5.0, 3.0, 1.0])[None, :] + h * 6.0, 6.0)
    return (v - v * s * np.clip(np.minimum(k, 4.0 - k), 0.0, 1.0)).astype(np.float32)


class ParticlesEffect(Effect):
    id = "particles"
    name = "Particle Field"
    description = ("Glowing particles stream from your fingertips. Pinch to pull them in, open "
                   "your palm to push them away, close your fist to make them explode. With two "
                   "hands, particles flow between them.")
    category = "Particles"
    default_order = 110
    uses_overlay = True
    PARAMS = [
        Param("mode", "Style", "choice", "Neon", choices=tuple(MODES)),
        Param("emitter", "Emit from", "choice", EMITTERS[0], choices=EMITTERS),
        Param("count", "Max particles", "int", 3000, 200, 12000, 100),
        Param("rate", "Emission rate", "float", 1.0, 0.0, 4.0),
        Param("speed", "Speed", "float", 1.0, 0.1, 3.0),
        Param("size", "Size", "float", 1.0, 0.3, 4.0),
        Param("velocity_boost", "Hand speed boosts emission", "float", 1.0, 0.0, 3.0),
        Param("swirl", "Swirl", "float", 1.0, 0.0, 3.0),
        Param("attract", "Pinch attraction", "float", 1.0, 0.0, 3.0),
        Param("repel", "Open palm repulsion", "float", 1.0, 0.0, 3.0),
        Param("explode", "Fist explosion", "bool", True),
        Param("bridge", "Flow between hands", "bool", True),
        Param("color", "Tint colour (Neon)", "color", "#29e7ff"),
        Param("glow", "Glow", "float", 1.0, 0.0, 3.0),
    ]

    def __init__(self):
        super().__init__()
        self.rng = np.random.default_rng(7)
        self._alloc(3000)
        self._prev_tips: dict = {}
        self._emit_acc = 0.0

    def _alloc(self, n):
        self.cap = n
        self.pos = np.zeros((n, 2), np.float32)
        self.vel = np.zeros((n, 2), np.float32)
        self.life = np.zeros(n, np.float32)
        self.max_life = np.ones(n, np.float32)
        self.hue = np.zeros(n, np.float32)
        self.size = np.ones(n, np.float32)
        self.target = np.full(n, -1, np.int16)   # bridge target slot
        self._next = 0

    def reset(self):
        self.life[:] = 0

    def on_param_changed(self, key):
        if key == "count" and self.p("count") != self.cap:
            self._alloc(int(self.p("count")))

    # ------------------------------------------------------------------ emission
    def _emit(self, pos, vel, n, hue_range, life, size, bridge_target=-1):
        if n <= 0:
            return
        n = min(n, self.cap)
        idx = (self._next + np.arange(n)) % self.cap
        self._next = int((self._next + n) % self.cap)
        spd = MODES[self.p("mode")][2] * self.p("speed")
        ang = self.rng.uniform(0, 2 * math.pi, n)
        mag = self.rng.uniform(0.2, 1.0, n) * spd
        self.pos[idx] = pos + self.rng.normal(0, 0.004, (n, 2))
        self.vel[idx] = vel * 0.35 + np.column_stack([np.cos(ang), np.sin(ang)]) * mag[:, None]
        self.max_life[idx] = life * self.rng.uniform(0.6, 1.2, n)
        self.life[idx] = self.max_life[idx]
        self.hue[idx] = self.rng.uniform(*hue_range, n)
        self.size[idx] = size * self.rng.uniform(0.5, 1.4, n)
        self.target[idx] = bridge_target

    def _emitters(self, ctx, h):
        e = self.p("emitter")
        if e == "Index finger":
            return [8]
        if e == "Palms":
            return [9]
        if e == "All landmarks":
            return list(range(21))
        return [t for k, t in enumerate(TIPS) if h.extension[k] > 0.45]

    def update(self, ctx: FrameContext):
        mode = MODES[self.p("mode")]
        hue_range, life, _, gravity, drag, size, _, swirl = mode
        dt = ctx.dt
        A = ctx.aspect
        hands = [h for h in ctx.hands if h.presence > 0.6]
        pair = ctx.two_hands()

        # --- emission
        for h in hands:
            ids = self._emitters(ctx, h)
            for i in ids:
                key = (h.hand_id, i)
                p = h.pts[i].astype(np.float32)
                prev = self._prev_tips.get(key, p)
                self._prev_tips[key] = p
                v = (p - prev) / max(dt, 1e-3)
                sp = float(np.linalg.norm(v))
                rate = (25.0 + sp * 90.0 * self.p("velocity_boost")) * self.p("rate")
                if self.p("emitter") == "All landmarks":
                    rate *= 0.25
                n = self.rng.poisson(rate * dt)
                tgt = -1
                if pair and self.p("bridge") and h.hand_id == pair[0].hand_id and i in (8, 4, 12):
                    tgt = i
                self._emit(p, v, n, hue_range, life, size, tgt)

        # --- events
        if self.p("explode"):
            for name, hid, data in ctx.events:
                if name in ("fist_close", "hands_together"):
                    c = np.array([data["uv"][0] * A, data["uv"][1]], np.float32)
                    d = self.pos - c
                    dist = np.linalg.norm(d, axis=1) + 1e-4
                    alive = self.life > 0
                    near = alive & (dist < 0.5)
                    self.vel[near] += (d[near] / dist[near, None]) * (1.6 / (dist[near, None] * 6 + 0.4))
                    burst = 350 if name == "fist_close" else 600
                    self._emit(c, np.zeros(2, np.float32), burst, hue_range, life * 0.9, size * 1.2)
                    k = np.arange(self._next - burst, self._next) % self.cap
                    ang = self.rng.uniform(0, 2 * math.pi, burst)
                    sp = self.rng.uniform(0.6, 1.8, burst) * self.p("speed")
                    self.vel[k] = np.column_stack([np.cos(ang), np.sin(ang)]) * sp[:, None]

        alive = self.life > 0
        if not alive.any():
            return
        P = self.pos[alive]
        V = self.vel[alive]

        # --- forces
        f = np.zeros_like(P)
        f[:, 1] += gravity
        sw = swirl * self.p("swirl")
        if sw > 0:
            t = ctx.t
            f[:, 0] += np.sin(P[:, 1] * 9.0 + t * 1.3) * sw
            f[:, 1] += np.cos(P[:, 0] * 9.0 - t * 1.1) * sw
        if self.p("mode") == "Vortex":
            centres = [h.palm_center for h in hands] or [np.array([0.5 * A, 0.5])]
            for c in centres:
                d = P - c
                r2 = (d ** 2).sum(1)[:, None] + 0.01
                f += np.column_stack([-d[:, 1], d[:, 0]]) / r2 * 0.25
                f -= d / r2 * 0.05
        for h in hands:
            g = ctx.gesture(h)
            if g is None:
                continue
            if g.pinch > 0.55 and self.p("attract") > 0:
                c = g.pinch_pos
                d = c - P
                r = np.linalg.norm(d, axis=1)[:, None] + 1e-3
                w = np.exp(-r / 0.25) * self.p("attract") * (g.pinch - 0.5) * 30
                # pull in, but keep an orbiting shell instead of collapsing to one point
                core = r < h.scale * 0.35
                radial = np.where(core, -0.8, 1.0)
                f += d / r * w * radial + np.column_stack([-d[:, 1], d[:, 0]]) / r * w * 1.1
            if g.openness > 0.75 and g.pinch < 0.4 and self.p("repel") > 0:
                d = P - h.palm_center
                r = np.linalg.norm(d, axis=1)[:, None] + 1e-3
                f += d / r * np.exp(-r / (h.scale * 1.2)) * self.p("repel") * 6.0
        # bridge: particles tagged with a target flow to the other hand
        if pair and self.p("bridge"):
            tg = self.target[alive]
            m = tg >= 0
            if m.any():
                other = pair[1]
                tp = other.pts[tg[m].astype(int)]
                d = tp - P[m]
                r = np.linalg.norm(d, axis=1)[:, None] + 1e-3
                f[m] += d / r * 2.2 + np.column_stack([-d[:, 1], d[:, 0]]) / r * 0.6
                V[m] *= (1 - min(dt * 2.5, 0.5))
        for w in ctx.shared.get("shockwaves", []):
            c = np.array([w[0] * A, w[1]])
            age = ctx.t - w[2]
            d = P - c
            r = np.linalg.norm(d, axis=1)[:, None] + 1e-3
            ring = np.exp(-((r - age * 1.0) / 0.05) ** 2)
            f += d / r * ring * 8.0

        V += f * dt
        V *= math.exp(-drag * dt)
        P += V * dt * self.p("speed")
        self.pos[alive] = P
        self.vel[alive] = V
        self.life[alive] -= dt
        # kill particles that leave the frame
        out = alive & ((self.pos[:, 0] < -0.1) | (self.pos[:, 0] > A + 0.1) |
                       (self.pos[:, 1] < -0.1) | (self.pos[:, 1] > 1.1))
        self.life[out] = 0
        self.status = f"{int((self.life > 0).sum())} particles"

    # ------------------------------------------------------------------ draw
    def draw(self, canvas, ctx: FrameContext):
        alive = self.life > 0
        if not alive.any():
            return
        mode = self.p("mode")
        _, _, _, _, _, _, glow, _ = MODES[mode]
        P = self.pos[alive]
        k = self.life[alive] / self.max_life[alive]
        uv = np.column_stack([P[:, 0] / ctx.aspect, P[:, 1]])
        hue = self.hue[alive]
        if mode == "Neon":
            base = np.array(self.col("color"), np.float32)
            cols = np.repeat(base[None, :], len(P), 0)
            cols = cols * (0.6 + 0.8 * k[:, None]) + np.column_stack([hue - 0.48] * 3) * 0.4
        elif mode == "Rainbow":
            cols = hsv_np(hue + ctx.t * 0.1)
        elif mode in ("Fire", "Sparks"):
            # white-hot -> orange -> red as particles age
            cols = np.column_stack([np.ones_like(k) * 1.4, 0.25 + 0.9 * k ** 1.5, 0.05 + 0.6 * k ** 3])
        else:
            cols = hsv_np(hue, 0.7, 1.0)
        cols = np.clip(cols, 0, 3)
        alpha = np.clip(k * 1.5, 0, 1) * 0.75 * ctx.intensity
        if mode == "Stardust":
            alpha *= 0.55 + 0.45 * np.sin(ctx.t * 9 + hue * 60)
        size = self.size[alive] * self.p("size") * (0.4 + 0.6 * k)
        canvas.sprites(uv, size * 1.5, cols, alpha=alpha, glow=glow * self.p("glow"), soft=0.85)
        if mode == "Plexus":
            n = min(len(P), 160)
            sel = P[:n]
            d = np.linalg.norm(sel[:, None] - sel[None], axis=-1)
            i, j = np.where(np.triu((d < 0.12) & (d > 0), 1))
            if len(i):
                seg = np.zeros((len(i), 11), np.float32)
                seg[:, 0:2] = uv[i]
                seg[:, 2:4] = uv[j]
                seg[:, 4:7] = cols[i]
                seg[:, 7] = (1 - d[i, j] / 0.12) * 0.6 * np.minimum(alpha[i], alpha[j])
                seg[:, 8] = 1.0
                seg[:, 9] = 2.0
                seg[:, 10] = 1.0
                canvas.segments(seg)
