"""Colour and visual transformations controlled by your hands."""
from __future__ import annotations

import math

import numpy as np

from effects.base_effect import Effect, FrameContext, Param, smooth_toward
from rendering.shader_manager import vec_array

HUE_CONTROLS = ("Wrist rotation", "Hand height", "Time", "Off")
ZONES = ("Off", "Negative palms", "Hue-flip palms", "Thermal palms", "Colour only near hands")


class ColourEffect(Effect):
    id = "colour"
    name = "Colour Shift"
    description = ("Psychedelic colour control. Rotate your wrist or raise your hand to sweep "
                   "the hue, flash a peace sign to jump palettes, move fast for RGB split, "
                   "and turn the space around your palms negative.")
    category = "Colour"
    default_order = 60
    uses_image = True
    PARAMS = [
        Param("hue_control", "Hue controlled by", "choice", HUE_CONTROLS[0], choices=HUE_CONTROLS),
        Param("flow", "Psychedelic flow", "float", 0.0, 0.0, 1.0),
        Param("saturation", "Saturation", "float", 1.35, 0.0, 3.0),
        Param("contrast", "Contrast", "float", 1.1, 0.5, 2.0),
        Param("posterize", "Posterise levels (0 = off)", "int", 0, 0, 12, 1),
        Param("rgb_split", "RGB split on fast moves", "float", 1.0, 0.0, 3.0),
        Param("zones", "Palm zones", "choice", ZONES[1], choices=ZONES),
        Param("zone_size", "Zone size", "float", 1.0, 0.3, 3.0),
        Param("peace_jump", "Peace sign jumps palette", "bool", True),
        Param("amount", "Mix", "float", 1.0, 0.0, 1.0),
    ]

    def __init__(self):
        super().__init__()
        self._hue = 0.0
        self._hue_offset = 0.0
        self._target_offset = 0.0
        self._split = 0.0
        self._dir = np.array([1.0, 0.0])
        self._zones = []

    def update(self, ctx: FrameContext):
        ctrl = self.p("hue_control")
        hands = [h for h in ctx.hands if h.presence > 0.5]
        target = self._hue
        if ctrl == "Wrist rotation" and hands:
            target = hands[0].rotation / math.pi * 0.5
        elif ctrl == "Hand height" and hands:
            target = 1.0 - hands[0].palm_uv[1]
        elif ctrl == "Time":
            target = ctx.t * 0.05
        elif ctrl == "Off":
            target = 0.0
        self._hue = smooth_toward(self._hue, target, ctx.dt, 0.12)
        if self.p("peace_jump"):
            for name, _, _ in ctx.events:
                if name == "peace_start":
                    self._target_offset += 1.0 / 3.0
        self._hue_offset = smooth_toward(self._hue_offset, self._target_offset, ctx.dt, 0.15)

        sp = max((h.speed for h in hands), default=0.0)
        self._split = smooth_toward(self._split, min(max(sp - 0.4, 0) * 0.006, 0.02), ctx.dt, 0.06)
        if hands:
            fastest = max(hands, key=lambda h: h.speed)
            if fastest.speed > 0.05:
                d = fastest.velocity / fastest.speed
                self._dir = self._dir + (np.array([d[0] / ctx.aspect, d[1]]) - self._dir) * 0.2
        zones = []
        if self.p("zones") != "Off":
            for h in hands:
                g = ctx.gesture(h)
                open_ = g.openness if g else 0.5
                rad = h.scale * (0.9 + 1.2 * open_) * self.p("zone_size")
                zones.append((h.palm_uv[0], h.palm_uv[1], rad, h.presence))
        self._zones = zones[:4]

    def render_image(self, r, ctx: FrameContext):
        z = self.p("zones")
        r.image_pass("colour.frag", {
            "u_hue": (self._hue + self._hue_offset) % 1.0, "u_flow": self.p("flow"),
            "u_saturation": self.p("saturation"), "u_contrast": self.p("contrast"),
            "u_posterize": float(self.p("posterize")),
            "u_rgb_shift": self._split * self.p("rgb_split"), "u_rgb_dir": tuple(self._dir),
            "u_zones": vec_array(self._zones, 4, 4), "u_nz": len(self._zones),
            "u_zone_mode": float({"Negative palms": 0, "Hue-flip palms": 1, "Thermal palms": 2}.get(z, 0)),
            "u_local": 1.0 if z == "Colour only near hands" else 0.0,
            "u_amount": self.p("amount") * ctx.intensity})
