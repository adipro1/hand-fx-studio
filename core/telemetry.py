"""Plain-data snapshot of everything the cinematic HUD displays.

Built once per rendered frame on the UI thread and handed to the HUD painter
(preview) and to the recorder thread (video). Contains only numbers, strings
and small numpy arrays, so it is safe to pass between threads.
"""
from __future__ import annotations

import random
import string
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np

GESTURE_SHORT = {
    "none": "TRACKING", "open_palm": "OPEN PALM", "fist": "FIST", "point": "POINT", "peace": "PEACE",
    "pinch": "PINCH", "thumbs_up": "THUMBS UP", "rock": "ROCK", "ok": "OK", "three": "THREE",
    "frame": "L-FRAME",
}


@dataclass
class HandTele:
    hand_id: int
    label: str                 # "Left" / "Right"
    gesture: str
    confidence: float
    presence: float
    pinch: float
    spread: float
    openness: float
    rotation: float            # radians
    speed: float               # hand-scales per second
    palm: tuple                # uv
    tips: np.ndarray           # (5, 2) uv
    index_xyz: tuple
    scale: float
    bbox: tuple                # uv (x0, y0, x1, y1)
    extension: tuple


@dataclass
class Telemetry:
    t: float = 0.0
    wall: str = ""
    session: str = ""
    aspect: float = 16 / 9
    hands: list[HandTele] = field(default_factory=list)
    two_distance: float = 0.0  # normalised 0..1
    two_angle: float = 0.0
    fps: float = 0.0
    render_ms: float = 0.0
    infer_ms: float = 0.0
    track_fps: float = 0.0
    cam_fps: float = 0.0
    cam_res: str = ""
    gpu: str = ""
    effects: list[str] = field(default_factory=list)
    preset: str = ""
    filter_name: str = ""
    pins: list[dict] = field(default_factory=list)
    events: list[tuple[str, str]] = field(default_factory=list)   # (time label, text)
    speed_hist: dict[str, np.ndarray] = field(default_factory=dict)  # "Left"/"Right" -> speeds
    flash: tuple | None = None   # (text, age seconds) of the latest big event
    recording: bool = False
    rec_time: float = 0.0
    rec_frames: int = 0
    countdown: float = 0.0       # >0 while the 3-2-1 countdown runs


EVENT_TEXT = {
    "fist_close": "FIST CLOSE", "palm_burst": "PALM BURST", "pinch_start": "PINCH LOCK",
    "pinch_end": "PINCH RELEASE", "circle": "CIRCLE", "swipe": "SWIPE", "hands_together": "HANDS CONVERGE",
}
FLASH_EVENTS = {"fist_close": "SHOCKWAVE", "palm_burst": "ENERGY BURST", "hands_together": "IMPACT",
                "circle": "VORTEX", "swipe": "SWIPE"}


class TelemetryCollector:
    """Keeps short histories (event log, speed graphs) and builds snapshots."""

    def __init__(self):
        self.session = "HFX-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
        self.events: deque = deque(maxlen=10)
        self.speeds = {"Left": deque([0.0] * 120, maxlen=120), "Right": deque([0.0] * 120, maxlen=120)}
        self._flash: tuple[str, float] | None = None
        self._last_filter = None
        self._last_pins = 0

    def _log(self, text: str, flash: str | None = None):
        self.events.append((datetime.now().strftime("%H:%M:%S.%f")[:-4], text))
        if flash:
            self._flash = (flash, time.perf_counter())

    def update(self, engine, ctx) -> Telemetry:
        tr, gf = ctx.tracking, ctx.gestures
        labels = {h.hand_id: ("R" if h.label == "Right" else "L") for h in tr.hands}
        for name, hid, _ in ctx.events:
            txt = EVENT_TEXT.get(name, name.upper().replace("_", " "))
            who = labels.get(hid)
            self._log(f"{txt}{' // ' + who + '-HAND' if who else ''}", FLASH_EVENTS.get(name))

        ff = engine.effect("filter_frame")
        filt, pins = "", []
        if ff and ff.enabled:
            filt = ff.mode.name
            pins = ff.pins_info()
            while ff.notices:
                n = ff.notices.pop(0)
                self._log(n, n.split(" //")[0] if n.startswith(("PINNED", "ALL PINS")) else None)
            if self._last_filter is not None and filt != self._last_filter:
                self._log(f"FILTER -> {filt.upper()}", f"FILTER: {filt.upper()}")
            self._last_filter = filt

        hands = []
        seen = set()
        for h in tr.hands:
            g = gf.hands.get(h.hand_id) if gf else None
            lm = h.lm
            x0, y0 = lm[:, :2].min(0)
            x1, y1 = lm[:, :2].max(0)
            spd = float(h.speed / max(h.scale, 1e-3))
            if h.label in self.speeds and h.label not in seen:
                self.speeds[h.label].append(min(spd, 12.0))
                seen.add(h.label)
            hands.append(HandTele(
                h.hand_id, h.label, GESTURE_SHORT.get(g.gesture if g else "none", (g.gesture if g else "").upper()),
                float(h.confidence), float(h.presence), float(g.pinch if g else 0), float(g.spread if g else 0),
                float(g.openness if g else 0), float(h.rotation), spd, tuple(map(float, h.palm_uv)),
                lm[[4, 8, 12, 16, 20], :2].copy(), tuple(map(float, lm[8])), float(h.scale),
                (float(x0), float(y0), float(x1), float(y1)), tuple(map(float, h.extension))))
        for lab, dq in self.speeds.items():
            if lab not in seen:
                dq.append(dq[-1] * 0.85)

        two = gf.two_hand if gf else {}
        cam = engine.camera
        flash = None
        if self._flash and time.perf_counter() - self._flash[1] < 1.2:
            flash = (self._flash[0], time.perf_counter() - self._flash[1])
        return Telemetry(
            t=ctx.t, wall=datetime.now().strftime("%Y-%m-%d  %H:%M:%S"), session=self.session,
            aspect=ctx.aspect, hands=hands,
            two_distance=float(two.get("distance_norm", 0.0)) if two.get("active") else 0.0,
            two_angle=float(two.get("angle", 0.0)),
            fps=float(engine.stats.get("fps", 0.0)), render_ms=float(engine.stats.get("render_ms", 0.0)),
            infer_ms=float(tr.inference_ms), track_fps=float(engine.tracker.fps) if engine.tracker else 0.0,
            cam_fps=float(cam.measured_fps) if cam else 0.0, cam_res=f"{ctx.width}x{ctx.height}",
            gpu=getattr(engine.renderer, "gpu_name", "") if engine.renderer else "",
            effects=[e.name for e in engine.active_effects()], preset=engine.preset or "",
            filter_name=filt, pins=pins, events=list(self.events),
            speed_hist={k: np.array(v, dtype="f4") for k, v in self.speeds.items()}, flash=flash)
