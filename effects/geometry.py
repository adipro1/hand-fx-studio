"""Interactive geometry: fingertip webs, facets, 3D wireframe solids, mandalas."""
from __future__ import annotations

import math

import numpy as np

from core.hand_tracker import TIPS
from effects.base_effect import Effect, FrameContext, Param, smooth_toward

PHI = (1 + 5 ** 0.5) / 2


def _solid(name: str):
    if name == "Cube":
        v = np.array([[x, y, z] for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)], float) / math.sqrt(3)
    elif name == "Octahedron":
        v = np.array([[1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0], [0, 0, 1], [0, 0, -1]], float)
    elif name == "Geodesic sphere":
        v = _icosphere(1)
    else:  # Icosahedron
        v = np.array([[-1, PHI, 0], [1, PHI, 0], [-1, -PHI, 0], [1, -PHI, 0],
                      [0, -1, PHI], [0, 1, PHI], [0, -1, -PHI], [0, 1, -PHI],
                      [PHI, 0, -1], [PHI, 0, 1], [-PHI, 0, -1], [-PHI, 0, 1]], float)
        v /= np.linalg.norm(v[0])
    d = np.linalg.norm(v[:, None] - v[None], axis=-1)
    dmin = d[d > 1e-6].min()
    i, j = np.where(np.triu(np.abs(d - dmin) < dmin * 0.05, 1))
    return v, np.column_stack([i, j])


def _icosphere(subdiv: int):
    v, e = _solid("Icosahedron")
    pts = [tuple(p) for p in v]
    # midpoint subdivision of edges, projected to the sphere
    for a, b in e:
        m = (v[a] + v[b]) / 2
        pts.append(tuple(m / np.linalg.norm(m)))
    return np.array(pts)


SOLIDS = ("Icosahedron", "Geodesic sphere", "Cube", "Octahedron")


def rot_matrix(ax: float, ay: float, az: float) -> np.ndarray:
    cx, sx, cy, sy, cz, sz = math.cos(ax), math.sin(ax), math.cos(ay), math.sin(ay), math.cos(az), math.sin(az)
    rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    return rz @ ry @ rx


class GeometryEffect(Effect):
    id = "geometry"
    name = "Sacred Geometry"
    description = ("Your fingertips become vertices: a web of lines and glowing facets connects "
                   "them, a 3D wireframe solid floats between your hands (spread them to grow "
                   "it, rotate your wrists to turn it) and mandalas bloom around open palms.")
    category = "Geometry"
    default_order = 100
    uses_overlay = True
    PARAMS = [
        Param("web", "Fingertip web", "bool", True),
        Param("facets", "Glowing facets", "bool", True),
        Param("solid", "3D solid", "choice", "Icosahedron", choices=SOLIDS + ("Off",)),
        Param("mandala", "Palm mandala", "bool", True),
        Param("symmetry", "Mirror symmetry", "bool", False),
        Param("color_a", "Colour A", "color", "#00f0ff"),
        Param("color_b", "Colour B", "color", "#b44bff"),
        Param("line_width", "Line thickness", "float", 1.4, 0.3, 6.0, 0.1),
        Param("glow", "Glow", "float", 5.0, 0.0, 20.0, 0.5),
        Param("spin", "Spin speed", "float", 0.4, -3.0, 3.0),
        Param("size", "Size", "float", 1.0, 0.3, 3.0),
    ]

    def __init__(self):
        super().__init__()
        self._mesh = _solid("Icosahedron")
        self._ang = np.zeros(3)
        self._center = np.array([0.5, 0.5])
        self._radius = 0.0
        self._wrist = 0.0

    def on_param_changed(self, key):
        if key == "solid" and self.p("solid") != "Off":
            self._mesh = _solid(self.p("solid"))

    def update(self, ctx: FrameContext):
        hands = [h for h in ctx.hands if h.presence > 0.4]
        target_r = 0.0
        if len(hands) >= 2:
            a, b = ctx.two_hands()
            c = (a.lm[9, :2] + b.lm[9, :2]) * 0.5
            target_r = float(np.linalg.norm(a.palm_center - b.palm_center)) * 0.33
            wrist = (a.rotation - b.rotation) * 0.5
        elif hands:
            h = hands[0]
            g = ctx.gesture(h)
            c = h.palm_uv - np.array([0, h.scale * 1.8])
            target_r = h.scale * (0.6 + (g.spread if g else 0.5) * 0.8)
            wrist = h.rotation
        else:
            c = self._center
            wrist = self._wrist
        k = 1 - 0.5 ** (ctx.dt / 0.07)
        self._center = self._center + (np.asarray(c) - self._center) * k
        self._radius = smooth_toward(self._radius, target_r * self.p("size"), ctx.dt, 0.1)
        self._wrist = smooth_toward(self._wrist, wrist, ctx.dt, 0.08)
        s = self.p("spin")
        self._ang += np.array([0.7, 1.0, 0.0]) * s * ctx.dt
        self._ang[2] = self._wrist * 1.5

    def _mirror(self, pts):
        return np.column_stack([1.0 - pts[:, 0], pts[:, 1]])

    def draw(self, canvas, ctx: FrameContext):
        I = ctx.intensity
        ca, cb = np.array(self.col("color_a")), np.array(self.col("color_b"))
        lw, glow = self.p("line_width"), self.p("glow")
        hands = [h for h in ctx.hands if h.presence > 0.2]
        tips = [h.lm[list(TIPS), :2] for h in hands]
        pres = [h.presence for h in hands]
        groups = [(t, p) for t, p in zip(tips, pres)]
        if self.p("symmetry"):
            groups += [(self._mirror(t), p * 0.6) for t, p in zip(tips, pres)]

        if self.p("web") and groups:
            allp = np.concatenate([g[0] for g in groups])
            alla = np.concatenate([[g[1]] * 5 for g in groups])
            n = len(allp)
            i, j = np.triu_indices(n, 1)
            d = np.linalg.norm((allp[i] - allp[j]) * [ctx.aspect, 1], axis=1)
            fade = np.clip(1.4 - d * 1.8, 0.1, 1.0)
            seg = np.zeros((len(i), 11), np.float32)
            seg[:, 0:2] = allp[i]
            seg[:, 2:4] = allp[j]
            t = ((i + j) % 7) / 6.0
            seg[:, 4:7] = ca[None] * (1 - t[:, None]) + cb[None] * t[:, None]
            seg[:, 7] = fade * np.minimum(alla[i], alla[j]) * 0.6 * I
            seg[:, 8] = lw * 0.7
            seg[:, 9] = glow * 0.6
            seg[:, 10] = 1.0
            canvas.segments(seg)
            canvas.sprites(allp, 3.0, ca * 1.3, alpha=alla * I, glow=glow, soft=0.3)

        if self.p("facets"):
            for t, p in groups:
                for k in range(4):
                    a, b = t[k], t[k + 1]
                    w = 0.5 + 0.5 * math.sin(ctx.t * 2 + k)
                    cc = ca if k % 2 == 0 else cb
                    canvas.polygon([t[0] * 0 + (t[0] + t[4]) * 0.5, a, b], cc,
                                   alpha=0.12 * p * I * (0.5 + w), additive=True)
            if len(tips) >= 2:
                a, b = tips[0], tips[1]
                for k in range(4):
                    quad = [a[k], a[k + 1], b[k + 1], b[k]]
                    cc = ca if k % 2 else cb
                    canvas.polygon(quad, cc, alpha=0.06 * I * min(pres), additive=True)

        if self.p("solid") != "Off" and self._radius > 0.005:
            v, e = self._mesh
            R = rot_matrix(*self._ang)
            pv = v @ R.T
            z = pv[:, 2]
            persp = 1.0 / (1.6 - z * 0.45)
            xy = pv[:, :2] * persp[:, None] * self._radius * 1.6
            uv = np.column_stack([self._center[0] + xy[:, 0] / ctx.aspect, self._center[1] + xy[:, 1]])
            seg = np.zeros((len(e), 11), np.float32)
            seg[:, 0:2] = uv[e[:, 0]]
            seg[:, 2:4] = uv[e[:, 1]]
            depth = (z[e[:, 0]] + z[e[:, 1]]) * 0.25 + 0.5
            seg[:, 4:7] = ca[None] * depth[:, None] + cb[None] * (1 - depth[:, None])
            seg[:, 7] = (0.35 + 0.65 * depth) * I
            seg[:, 8] = lw * (0.6 + 0.8 * depth)
            seg[:, 9] = glow
            seg[:, 10] = 1.0
            canvas.segments(seg)
            canvas.sprites(uv, 2.5 * (0.5 + persp), ca * 1.4, alpha=I * (0.4 + 0.6 * (z * 0.5 + 0.5)), glow=glow, soft=0.3)
            canvas.circle(self._center, self._radius * ctx.height * 0.5, cb, glow=30, alpha=0.12 * I, soft=1.0)

        if self.p("mandala"):
            for h in hands:
                g = ctx.gesture(h)
                if g is None or g.openness < 0.6:
                    continue
                f = (g.openness - 0.6) / 0.4 * h.presence * I
                c = h.palm_uv
                base = h.scale * (0.8 + g.spread)
                for k, sides in enumerate((3, 4, 6, 8)):
                    rr = base * (0.45 + 0.28 * k)
                    rot = ctx.t * self.p("spin") * (1 if k % 2 else -1) * (1 + k * 0.3) + h.rotation
                    ang = rot + np.arange(sides + 1) * 2 * math.pi / sides
                    pts = np.column_stack([c[0] + np.cos(ang) * rr / ctx.aspect, c[1] + np.sin(ang) * rr])
                    col = ca if k % 2 == 0 else cb
                    canvas.polyline(pts, col * 1.2, width=lw, glow=glow, alpha=f * 0.8)
                    if k == 3:
                        canvas.sprites(pts[:-1], 2.5, (1, 1, 1), alpha=f, glow=glow, soft=0.3)
