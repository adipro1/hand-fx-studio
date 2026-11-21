"""GPU rendering pipeline.

    camera frame ──► base pass ──► image effects (ping-pong) ──► scene
                                                                   │
    overlay effects ──► Canvas (premultiplied HDR) ──► bloom ──────┤
                                                                   ▼
                                                       composite ──► output (RGB bytes)

Runs on an offscreen (standalone) OpenGL 3.3 context. The final image is read
back to a numpy array, which the UI displays and the recorder encodes. Must be
used from a single thread.
"""
from __future__ import annotations

import time

import moderngl
import numpy as np

from rendering.canvas import Canvas
from rendering.shader_manager import ShaderManager, set_uniforms

QUALITY_BLOOM_DIV = {"low": 8, "medium": 4, "high": 4}


class Renderer:
    def __init__(self, width: int = 1280, height: int = 720, quality: str = "high"):
        try:
            self.ctx = moderngl.create_standalone_context(require=330)
        except Exception as exc:
            raise RuntimeError(
                "Could not create an OpenGL 3.3 context. Please update your graphics "
                f"driver (Intel / AMD / NVIDIA website).\n\nDetails: {exc}") from exc
        self.shaders = ShaderManager(self.ctx)
        self.shaders.compile_all()
        self.gpu_name = self.ctx.info.get("GL_RENDERER", "unknown GPU")
        self.quality = quality
        self.time0 = time.perf_counter()
        self.width = 0
        self.height = 0
        self._fs_vaos: dict[int, moderngl.VertexArray] = {}
        self.cam_tex: moderngl.Texture | None = None
        self.resize(width, height)

        # settings
        self.show_camera = 1.0
        self.dim = 0.0
        self.contrast = 1.0
        self.saturation = 1.0
        self.brightness = 0.0
        self.bloom = 0.8
        self.vignette = 0.15
        self.gpu_ms = 0.0

    # ------------------------------------------------------------------ setup
    def resize(self, width: int, height: int) -> None:
        if (width, height) == (self.width, self.height):
            return
        self.width, self.height = width, height
        self.aspect = width / height
        ctx = self.ctx

        def tex(w, h, comps=4, dtype="f1"):
            t = ctx.texture((w, h), comps, dtype=dtype)
            t.repeat_x = False
            t.repeat_y = False
            t.filter = (moderngl.LINEAR, moderngl.LINEAR)
            return t

        self.cam_tex = tex(width, height, 3)
        self.scene = [tex(width, height), tex(width, height)]
        self.scene_fbo = [ctx.framebuffer([t]) for t in self.scene]
        self.overlay_tex = tex(width, height, 4, "f2")
        self.overlay_fbo = ctx.framebuffer([self.overlay_tex])
        div = QUALITY_BLOOM_DIV.get(self.quality, 4)
        bw, bh = max(width // div, 8), max(height // div, 8)
        self.bloom_a = [tex(bw, bh, 4, "f2"), tex(bw, bh, 4, "f2")]
        self.bloom_a_fbo = [ctx.framebuffer([t]) for t in self.bloom_a]
        self.bloom_b = [tex(bw // 2, bh // 2, 4, "f2"), tex(bw // 2, bh // 2, 4, "f2")]
        self.bloom_b_fbo = [ctx.framebuffer([t]) for t in self.bloom_b]
        self.out_tex = tex(width, height)
        self.out_fbo = ctx.framebuffer([self.out_tex])
        self.canvas = Canvas(ctx, self.shaders, width, height)
        self._cur = 0

    # ------------------------------------------------------------------ helpers
    @property
    def time(self) -> float:
        return time.perf_counter() - self.time0

    def make_texture(self, w, h, comps=4, dtype="f1") -> moderngl.Texture:
        t = self.ctx.texture((w, h), comps, dtype=dtype)
        t.repeat_x = t.repeat_y = False
        t.filter = (moderngl.LINEAR, moderngl.LINEAR)
        return t

    def fullscreen(self, prog: moderngl.Program, fbo: moderngl.Framebuffer,
                   textures: dict | None = None, uniforms: dict | None = None) -> None:
        """Run a fullscreen fragment pass into ``fbo``."""
        vao = self._fs_vaos.get(id(prog))
        if vao is None:
            vao = self.ctx.vertex_array(prog, [])
            self._fs_vaos[id(prog)] = vao
        w, h = fbo.size
        common = {"u_res": (float(w), float(h)), "u_time": self.time, "u_aspect": w / h}
        set_uniforms(prog, common)
        if uniforms:
            set_uniforms(prog, uniforms)
        if textures:
            for unit, (name, t) in enumerate(textures.items()):
                t.use(location=unit)
                if name in prog:
                    prog[name].value = unit
        fbo.use()
        vao.render(moderngl.TRIANGLES, vertices=3)

    def image_pass(self, frag: str, uniforms: dict | None = None, textures: dict | None = None,
                   src_name: str = "u_src") -> None:
        """Apply a fullscreen pass reading the current scene and writing the next."""
        prog = self.shaders.program(frag)
        tx = {src_name: self.scene[self._cur]}
        if textures:
            tx.update(textures)
        self.fullscreen(prog, self.scene_fbo[1 - self._cur], tx, uniforms)
        self._cur = 1 - self._cur

    @property
    def scene_tex(self) -> moderngl.Texture:
        return self.scene[self._cur]

    # ------------------------------------------------------------------ frame
    def render(self, frame_bgr: np.ndarray | None, effects: list, ctx_frame) -> np.ndarray:
        """Render one frame. ``effects`` are enabled effects sorted by layer order."""
        t0 = time.perf_counter()
        h, w = (frame_bgr.shape[:2] if frame_bgr is not None else (self.height, self.width))
        if (w, h) != (self.width, self.height):
            self.resize(w, h)
            for e in effects:
                e.on_resize(self)
        if frame_bgr is not None:
            self.cam_tex.write(np.ascontiguousarray(frame_bgr).tobytes())

        # 1) base pass
        self._cur = 0
        self.fullscreen(self.shaders.program("base.frag"), self.scene_fbo[0], {"u_cam": self.cam_tex}, {
            "u_show": self.show_camera, "u_dim": self.dim, "u_contrast": self.contrast,
            "u_saturation": self.saturation, "u_brightness": self.brightness})

        # 2) image effects in layer order
        for e in effects:
            if e.uses_image:
                try:
                    e.render_image(self, ctx_frame)
                except Exception as exc:  # one broken effect must not kill the app
                    e.error = str(exc)

        # 3) overlay effects
        self.overlay_fbo.use()
        self.overlay_fbo.clear(0.0, 0.0, 0.0, 0.0)
        for e in effects:
            if e.uses_overlay:
                try:
                    e.draw(self.canvas, ctx_frame)
                except Exception as exc:
                    e.error = str(exc)
                    self.canvas.clear()
                self.overlay_fbo.use()
                self.canvas.flush()

        # 4) bloom on the overlay layer
        bloom_on = self.bloom > 0.01
        if bloom_on:
            down = self.shaders.program("bloom_down.frag")
            blur = self.shaders.program("blur.frag")
            self.fullscreen(down, self.bloom_a_fbo[0], {"u_src": self.overlay_tex},
                            {"u_texel": (1.0 / self.width, 1.0 / self.height), "u_threshold": 0.05})
            aw, ah = self.bloom_a[0].size
            for _ in range(2 if self.quality != "low" else 1):
                self.fullscreen(blur, self.bloom_a_fbo[1], {"u_src": self.bloom_a[0]}, {"u_dir": (1.5 / aw, 0.0)})
                self.fullscreen(blur, self.bloom_a_fbo[0], {"u_src": self.bloom_a[1]}, {"u_dir": (0.0, 1.5 / ah)})
            self.fullscreen(down, self.bloom_b_fbo[0], {"u_src": self.bloom_a[0]},
                            {"u_texel": (1.0 / aw, 1.0 / ah), "u_threshold": 0.0})
            bw, bh = self.bloom_b[0].size
            for _ in range(2):
                self.fullscreen(blur, self.bloom_b_fbo[1], {"u_src": self.bloom_b[0]}, {"u_dir": (2.0 / bw, 0.0)})
                self.fullscreen(blur, self.bloom_b_fbo[0], {"u_src": self.bloom_b[1]}, {"u_dir": (0.0, 2.0 / bh)})

        # 5) composite
        self.fullscreen(self.shaders.program("composite.frag"), self.out_fbo, {
            "u_scene": self.scene_tex, "u_overlay": self.overlay_tex,
            "u_bloom1": self.bloom_a[0], "u_bloom2": self.bloom_b[0]},
            {"u_bloom": self.bloom if bloom_on else 0.0, "u_vignette": self.vignette})

        data = self.out_fbo.read(components=3, alignment=1)
        img = np.frombuffer(data, dtype=np.uint8).reshape(self.height, self.width, 3)
        self.gpu_ms = (time.perf_counter() - t0) * 1000.0
        return img

    def release(self) -> None:
        try:
            self.ctx.release()
        except Exception:
            pass
