"""GPU overlay canvas.

Effects call drawing methods (line, polyline, circle, ring, sprites, polygon)
during a frame. Everything is batched and drawn with three instanced draw calls
into a premultiplied-alpha HDR overlay buffer. Coordinates are uv (0..1, y down).
Colours are RGB tuples 0..1 (values > 1 make things glow harder through bloom).

``additive=True`` (default) makes a primitive emit light (good for neon/glow);
``additive=False`` makes it opaque/covering (good for solid shapes and outlines
that must hide what is beneath).
"""
from __future__ import annotations

import numpy as np
import moderngl

_QUAD = np.array([[-1, -1], [1, -1], [-1, 1], [1, 1]], dtype="f4")


class Canvas:
    def __init__(self, ctx: moderngl.Context, shaders, width: int, height: int):
        self.ctx = ctx
        self.width = width
        self.height = height
        self.aspect = width / height
        self.px_scale = height / 720.0     # widths are specified for a 720p frame
        self._lines: list[tuple] = []
        self._discs: list[tuple] = []
        self._line_arrays: list[np.ndarray] = []
        self._disc_arrays: list[np.ndarray] = []
        self._tris: list[np.ndarray] = []

        self.p_lines = shaders.program("lines.frag", "lines.vert")
        self.p_discs = shaders.program("discs.frag", "discs.vert")
        self.p_tris = shaders.program("tris.frag", "tris.vert")
        self.quad_vbo = ctx.buffer(_QUAD.tobytes())
        self._cap_lines = 0
        self._cap_discs = 0
        self._cap_tris = 0
        self._ensure(4096, 8192, 4096)

    # ---------------------------------------------------------------- GPU buffers
    def _ensure(self, nl: int, nd: int, nt: int) -> None:
        if nl > self._cap_lines:
            self._cap_lines = max(nl, self._cap_lines * 2)
            self.line_vbo = self.ctx.buffer(reserve=self._cap_lines * 12 * 4, dynamic=True)
            self.line_vao = self.ctx.vertex_array(self.p_lines, [
                (self.quad_vbo, "2f", "a_corner"),
                (self.line_vbo, "4f 4f 4f/i", "i_seg", "i_col", "i_style")])
        if nd > self._cap_discs:
            self._cap_discs = max(nd, self._cap_discs * 2)
            self.disc_vbo = self.ctx.buffer(reserve=self._cap_discs * 11 * 4, dynamic=True)
            self.disc_vao = self.ctx.vertex_array(self.p_discs, [
                (self.quad_vbo, "2f", "a_corner"),
                (self.disc_vbo, "4f 4f 3f/i", "i_circ", "i_col", "i_style")])
        if nt > self._cap_tris:
            self._cap_tris = max(nt, self._cap_tris * 2)
            self.tri_vbo = self.ctx.buffer(reserve=self._cap_tris * 7 * 4, dynamic=True)
            self.tri_vao = self.ctx.vertex_array(self.p_tris, [
                (self.tri_vbo, "2f 4f 1f", "a_pos", "a_col", "a_add")])

    # ---------------------------------------------------------------- drawing API
    def line(self, p0, p1, color, width=2.0, glow=0.0, alpha=1.0, additive=True):
        s = self.px_scale
        self._lines.append((p0[0], p0[1], p1[0], p1[1], color[0], color[1], color[2], alpha,
                            width * s, glow * s, 1.0 if additive else 0.0, 1.0))

    def polyline(self, pts, color, width=2.0, glow=0.0, alpha=1.0, additive=True, closed=False,
                 alphas=None, widths=None):
        pts = np.asarray(pts, dtype="f4")
        if len(pts) < 2:
            return
        a = pts[:-1]
        b = pts[1:]
        if closed:
            a = np.vstack([a, pts[-1:]])
            b = np.vstack([b, pts[:1]])
        n = len(a)
        arr = np.empty((n, 12), dtype="f4")
        arr[:, 0:2] = a
        arr[:, 2:4] = b
        col = np.asarray(color, dtype="f4")
        if col.ndim == 1:
            arr[:, 4:7] = col[:3]
        else:
            arr[:, 4:7] = col[:n, :3]
        arr[:, 7] = alpha if alphas is None else np.asarray(alphas, dtype="f4")[:n]
        arr[:, 8] = (width if widths is None else np.asarray(widths, dtype="f4")[:n]) * self.px_scale
        arr[:, 9] = glow * self.px_scale
        arr[:, 10] = 1.0 if additive else 0.0
        arr[:, 11] = self._glow_gain(arr)
        self._line_arrays.append(arr)

    def _glow_gain(self, arr: np.ndarray) -> np.ndarray:
        """Short consecutive segments would stack their glow halos; scale each
        segment's glow by its length relative to the glow radius."""
        seg_px = np.hypot((arr[:, 2] - arr[:, 0]) * self.width, (arr[:, 3] - arr[:, 1]) * self.height)
        return np.clip(seg_px / np.maximum(arr[:, 9] * 2.5, 1e-3), 0.06, 1.0)

    def segments(self, arr: np.ndarray):
        """Raw (N, 11) array: x0 y0 x1 y1 r g b a width glow additive (width/glow in 720p px).
        Segments are treated as independent lines (full glow)."""
        if len(arr):
            a = np.ones((len(arr), 12), dtype="f4")
            a[:, :11] = arr[:, :11]
            a[:, 8:10] *= self.px_scale
            self._line_arrays.append(a)

    def circle(self, c, radius, color, glow=0.0, alpha=1.0, additive=True, soft=0.0):
        s = self.px_scale
        self._discs.append((c[0], c[1], radius * s, 0.0, color[0], color[1], color[2], alpha,
                            glow * s, 1.0 if additive else 0.0, soft))

    def ring(self, c, radius, thickness, color, glow=0.0, alpha=1.0, additive=True):
        s = self.px_scale
        self._discs.append((c[0], c[1], radius * s, max(thickness * s, 0.5), color[0], color[1],
                            color[2], alpha, glow * s, 1.0 if additive else 0.0, 0.0))

    def sprites(self, pos, radius, color, alpha=None, glow=0.0, soft=1.0, additive=True):
        """Many discs at once. pos (N,2) uv; radius scalar or (N,); color (3,) or (N,3)."""
        pos = np.asarray(pos, dtype="f4")
        n = len(pos)
        if n == 0:
            return
        arr = np.zeros((n, 11), dtype="f4")
        arr[:, 0:2] = pos
        arr[:, 2] = np.asarray(radius, dtype="f4") * self.px_scale
        col = np.asarray(color, dtype="f4")
        arr[:, 4:7] = col[:3] if col.ndim == 1 else col[:, :3]
        arr[:, 7] = 1.0 if alpha is None else alpha
        arr[:, 8] = glow * self.px_scale
        arr[:, 9] = 1.0 if additive else 0.0
        arr[:, 10] = soft
        self._disc_arrays.append(arr)

    def polygon(self, pts, color, alpha=1.0, additive=False, colors=None):
        """Filled convex polygon (fan triangulated). ``colors`` optional per-vertex."""
        pts = np.asarray(pts, dtype="f4")
        n = len(pts)
        if n < 3:
            return
        idx = np.array([[0, i, i + 1] for i in range(1, n - 1)]).reshape(-1)
        v = np.zeros((len(idx), 7), dtype="f4")
        v[:, 0:2] = pts[idx]
        if colors is not None:
            c = np.asarray(colors, dtype="f4")
            v[:, 2:5] = c[idx, :3]
            v[:, 5] = c[idx, 3] if c.shape[1] > 3 else alpha
        else:
            v[:, 2:5] = color[:3]
            v[:, 5] = alpha
        v[:, 6] = 1.0 if additive else 0.0
        self._tris.append(v)

    def triangle(self, a, b, c, color, alpha=1.0, additive=True):
        self.polygon([a, b, c], color, alpha, additive)

    # ---------------------------------------------------------------- flush
    def clear(self):
        self._lines.clear()
        self._discs.clear()
        self._line_arrays.clear()
        self._disc_arrays.clear()
        self._tris.clear()

    def flush(self):
        """Draw everything queued into the currently bound framebuffer."""
        ctx = self.ctx
        ctx.enable(moderngl.BLEND)
        ctx.blend_func = (moderngl.ONE, moderngl.ONE_MINUS_SRC_ALPHA)
        res = (float(self.width), float(self.height))

        if self._tris:
            t = np.concatenate(self._tris)
            self._ensure(0, 0, len(t))
            self.tri_vbo.write(t.tobytes())
            self.tri_vao.render(moderngl.TRIANGLES, vertices=len(t))

        lines = self._line_arrays[:]
        if self._lines:
            lines.append(np.asarray(self._lines, dtype="f4"))
        if lines:
            arr = np.concatenate(lines)
            self._ensure(len(arr), 0, 0)
            self.line_vbo.write(arr.tobytes())
            self.p_lines["u_res"].value = res
            self.line_vao.render(moderngl.TRIANGLE_STRIP, vertices=4, instances=len(arr))

        discs = self._disc_arrays[:]
        if self._discs:
            discs.append(np.asarray(self._discs, dtype="f4"))
        if discs:
            arr = np.concatenate(discs)
            self._ensure(0, len(arr), 0)
            self.disc_vbo.write(arr.tobytes())
            self.p_discs["u_res"].value = res
            self.disc_vao.render(moderngl.TRIANGLE_STRIP, vertices=4, instances=len(arr))

        ctx.disable(moderngl.BLEND)
        self.clear()
