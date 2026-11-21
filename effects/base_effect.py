"""Effect framework.

Every visual effect subclasses ``Effect`` and declares:

* ``PARAMS`` – typed parameters. The UI builds controls for them automatically
  and they are saved in user settings.
* ``uses_image`` / ``render_image()`` – a GPU pass that transforms the camera image.
* ``uses_overlay`` / ``draw()`` – glowing vector graphics drawn on the overlay canvas.
* ``update()`` – per-frame simulation / gesture handling (CPU).

Effects are layered by ``order``: image passes run in ascending order, then
overlays are drawn in ascending order on top.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from core.gesture_recognition import GestureFrame, HandGesture
from core.hand_tracker import HandState, TrackingResult


@dataclass
class Param:
    key: str
    label: str
    kind: str = "float"            # float | int | bool | color | choice
    default: Any = 0.0
    min: float = 0.0
    max: float = 1.0
    step: float = 0.01
    choices: tuple = ()
    tip: str = ""


@dataclass
class FrameContext:
    t: float
    dt: float
    tracking: TrackingResult
    gestures: GestureFrame
    events: list
    width: int
    height: int
    intensity: float = 1.0
    shared: dict = field(default_factory=dict)   # cross-effect bus (e.g. shockwaves)

    @property
    def aspect(self) -> float:
        return self.width / self.height

    @property
    def hands(self) -> list[HandState]:
        return self.tracking.hands

    def gesture(self, h: HandState) -> HandGesture | None:
        return self.gestures.hands.get(h.hand_id)

    def screen_sorted(self) -> list[HandState]:
        """Hands sorted left -> right as they appear on screen."""
        return sorted(self.hands, key=lambda h: h.palm_center[0])

    def two_hands(self) -> tuple[HandState, HandState] | None:
        hs = self.screen_sorted()
        if len(hs) >= 2:
            return hs[0], hs[1]
        return None


def hex_to_rgb(h: str) -> tuple[float, float, float]:
    h = h.lstrip("#")
    if len(h) != 6:
        return (1.0, 1.0, 1.0)
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def rgb_to_hex(c) -> str:
    return "#" + "".join(f"{int(max(0, min(1, x)) * 255):02x}" for x in c[:3])


def hsv(h: float, s: float = 1.0, v: float = 1.0) -> tuple[float, float, float]:
    h = h % 1.0
    i = int(h * 6.0)
    f = h * 6.0 - i
    p, q, t = v * (1 - s), v * (1 - s * f), v * (1 - s * (1 - f))
    return [(v, t, p), (q, v, p), (p, v, t), (p, q, v), (t, p, v), (v, p, q)][i % 6]


def lerp(a, b, t):
    return a + (b - a) * t


def smooth_toward(cur: float, target: float, dt: float, half_life: float) -> float:
    if half_life <= 0:
        return target
    return cur + (target - cur) * (1.0 - 0.5 ** (dt / half_life))


class Effect:
    id: str = "effect"
    name: str = "Effect"
    description: str = ""
    category: str = "General"
    default_order: int = 50
    uses_image: bool = False
    uses_overlay: bool = False
    PARAMS: list[Param] = []

    def __init__(self):
        self.enabled = False
        self.order = self.default_order
        self.params: dict[str, Any] = {p.key: p.default for p in self.PARAMS}
        self.error: str | None = None
        self.status: str = ""          # short live status text for the UI
        self._gpu_ready = False

    # -- parameters --------------------------------------------------------
    def p(self, key: str):
        return self.params[key]

    def col(self, key: str) -> tuple[float, float, float]:
        return hex_to_rgb(self.params[key])

    def set_param(self, key: str, value) -> None:
        spec = next((p for p in self.PARAMS if p.key == key), None)
        if spec is None:
            return
        if spec.kind == "float":
            value = float(np.clip(float(value), spec.min, spec.max))
        elif spec.kind == "int":
            value = int(np.clip(int(value), spec.min, spec.max))
        elif spec.kind == "bool":
            value = bool(value)
        elif spec.kind == "choice":
            value = value if value in spec.choices else spec.default
        self.params[key] = value
        self.on_param_changed(key)

    def reset_params(self) -> None:
        for p in self.PARAMS:
            self.params[p.key] = p.default

    def on_param_changed(self, key: str) -> None:
        pass

    # -- lifecycle ---------------------------------------------------------
    def ensure_gpu(self, renderer) -> None:
        if not self._gpu_ready:
            self.setup_gpu(renderer)
            self._gpu_ready = True

    def setup_gpu(self, renderer) -> None:
        pass

    def on_resize(self, renderer) -> None:
        self._gpu_ready = False

    def on_enable(self) -> None:
        pass

    def reset(self) -> None:
        """Clear transient state (particles, trails, ...)."""

    def update(self, ctx: FrameContext) -> None:
        pass

    def render_image(self, renderer, ctx: FrameContext) -> None:
        pass

    def draw(self, canvas, ctx: FrameContext) -> None:
        pass

    # -- serialisation -----------------------------------------------------
    def to_dict(self) -> dict:
        return {"enabled": self.enabled, "order": self.order, "params": dict(self.params)}

    def load_dict(self, d: dict) -> None:
        self.enabled = bool(d.get("enabled", self.enabled))
        self.order = int(d.get("order", self.order))
        for k, v in (d.get("params") or {}).items():
            if k in self.params:
                self.set_param(k, v)


# ---------------------------------------------------------------- hand helpers
def tip_uv(h: HandState, idx: int) -> np.ndarray:
    return h.lm[idx, :2].copy()


def hand_size_uv(h: HandState) -> float:
    """Hand scale in uv-y units (≈ wrist to middle knuckle)."""
    return h.scale


def angle_of(v) -> float:
    return math.atan2(v[1], v[0])
