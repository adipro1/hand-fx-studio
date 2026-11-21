"""The HAND FX STUDIO engine: camera -> tracking -> gestures -> effects -> GPU.

UI independent: the Qt window, the offline renderer and the tests all drive
this same class. ``tick()`` is called from the UI thread for live use;
``process_frame()`` runs synchronously on a given image (offline / tests).
"""
from __future__ import annotations

import time
from typing import Callable

import numpy as np

from core.camera import Camera
from core.configuration import AppSettings
from core.gesture_recognition import GestureFrame, GestureRecognizer
from core.hand_tracker import HandTracker, TrackingResult
from core.interaction_manager import InteractionManager
from core.telemetry import Telemetry, TelemetryCollector
from effects import create_effects
from effects.base_effect import Effect, FrameContext
from effects.presets import PRESETS, PRESET_NAMES


class Engine:
    def __init__(self, settings: AppSettings | None):
        self.settings = settings or AppSettings()
        self.effects: list[Effect] = create_effects()
        self.camera: Camera | None = None
        self.tracker: HandTracker | None = None
        self.renderer = None
        self.gestures = GestureRecognizer(confirm_time=self.settings.tracking.confirm_time)
        self.interaction = InteractionManager(self)
        self.intensity = self.settings.render.master_intensity
        self.preset = self.settings.active_preset
        self.stats = {"render_ms": 0.0, "update_ms": 0.0, "fps": 0.0, "hands": 0}
        self.action_callback: Callable[[str], None] | None = None
        self.last_gestures: GestureFrame | None = None
        self.last_tracking: TrackingResult | None = None
        self._last_index = -1
        self._last_t: float | None = None
        self._t0 = time.perf_counter()
        self._blank: np.ndarray | None = None
        self.telemetry_collector = TelemetryCollector()
        self.telemetry = Telemetry()
        self._load_effect_settings()

    # ------------------------------------------------------------------ setup
    def _make_renderer(self):
        from rendering.renderer import Renderer
        rs = self.settings.render
        self.renderer = Renderer(self.settings.camera.width, self.settings.camera.height, rs.quality)
        self.apply_render_settings()

    def apply_render_settings(self):
        if not self.renderer:
            return
        rs = self.settings.render
        self.renderer.show_camera = 1.0 if rs.show_camera else 0.0
        self.renderer.dim = rs.background_dim
        self.renderer.bloom = rs.bloom
        self.intensity = rs.master_intensity

    def start_offline(self):
        """Tracker without camera thread (frames supplied via process_frame)."""
        self.tracker = HandTracker(None, max_hands=self.settings.tracking.max_hands,
                                   process_width=self.settings.tracking.process_width)
        self.tracker._landmarker = self.tracker._create_landmarker()
        self.tracker.set_smoothing(self.settings.tracking.smoothing)
        if self.renderer is None:
            self._make_renderer()

    def start_live(self) -> str | None:
        """Start camera + tracking threads. Returns an error message or None."""
        cs, ts = self.settings.camera, self.settings.tracking
        self.stop_live()
        self.camera = Camera(cs.index, cs.width, cs.height, cs.fps, cs.mirror)
        if not self.camera.start():
            return self.camera.error
        self.tracker = HandTracker(self.camera, ts.max_hands, ts.detection_confidence,
                                   ts.tracking_confidence, ts.tracking_confidence,
                                   ts.process_width, ts.smoothing, ts.lost_grace)
        if not self.tracker.start():
            return self.tracker.error
        if self.renderer is None:
            self._make_renderer()
        return None

    def stop_live(self):
        if self.tracker:
            self.tracker.stop()
            self.tracker = None
        if self.camera:
            self.camera.stop()
            self.camera = None

    def shutdown(self):
        self.stop_live()
        if self.renderer:
            self.renderer.release()
            self.renderer = None

    # ------------------------------------------------------------------ effects
    def effect(self, eid: str) -> Effect | None:
        return next((e for e in self.effects if e.id == eid), None)

    def active_effects(self) -> list[Effect]:
        return sorted((e for e in self.effects if e.enabled), key=lambda e: e.order)

    def apply_preset(self, name: str):
        preset = PRESETS.get(name)
        if preset is None:
            return
        self.preset = name
        self.settings.active_preset = name
        for e in self.effects:
            spec = preset["effects"].get(e.id)
            e.reset_params()
            e.order = e.default_order
            e.enabled = spec is not None
            if spec:
                for k, v in spec.items():
                    e.set_param(k, v)
            e.reset()
        r = preset.get("render", {})
        rs = self.settings.render
        rs.background_dim = r.get("dim", 0.0)
        rs.bloom = r.get("bloom", 0.8)
        self.apply_render_settings()

    def cycle_preset(self, step: int):
        names = PRESET_NAMES
        i = names.index(self.preset) if self.preset in names else 0
        self.apply_preset(names[(i + step) % len(names)])

    def perform_action(self, action: str):
        if action == "next_preset":
            self.cycle_preset(1)
        elif action == "prev_preset":
            self.cycle_preset(-1)
        elif action == "next_filter":
            ff = self.effect("filter_frame")
            if ff:
                ff.next_filter()
        elif action in ("pin_frame", "remove_last_pin", "clear_pins"):
            ff = self.effect("filter_frame")
            if ff:
                {"pin_frame": lambda: ff.pin_now(time.perf_counter() - self._t0),
                 "remove_last_pin": ff.remove_last_pin, "clear_pins": ff.clear_pins}[action]()
        elif action == "reset_effects":
            for e in self.effects:
                e.reset()
        if self.action_callback:
            self.action_callback(action)

    def save_effect_settings(self):
        self.settings.effects = {e.id: e.to_dict() for e in self.effects}
        self.settings.save()

    def _load_effect_settings(self):
        saved = self.settings.effects
        if saved:
            for e in self.effects:
                if e.id in saved:
                    e.load_dict(saved[e.id])
        else:
            self.apply_preset(self.preset if self.preset in PRESETS else PRESET_NAMES[0])

    # ------------------------------------------------------------------ frame
    def _render(self, tr: TrackingResult, image: np.ndarray | None, now: float) -> np.ndarray:
        dt = 1 / 30 if self._last_t is None else min(max(now - self._last_t, 1e-4), 0.1)
        self._last_t = now
        if tr.frame_index != self._last_index or self.last_gestures is None:
            gf = self.gestures.update(tr)
            self._last_index = tr.frame_index
        else:
            gf = GestureFrame(self.last_gestures.hands, [], self.last_gestures.two_hand, tr)
        self.last_gestures = gf
        self.last_tracking = tr
        if image is None:
            if self._blank is None:
                self._blank = np.zeros((self.settings.camera.height, self.settings.camera.width, 3), np.uint8)
            image = self._blank
        h, w = image.shape[:2]
        ctx = FrameContext(now, dt, tr, gf, gf.events, w, h, self.intensity)
        self.interaction.update(ctx)
        t0 = time.perf_counter()
        active = self.active_effects()
        for e in active:
            try:
                e.ensure_gpu(self.renderer)
                e.update(ctx)
            except Exception as exc:
                e.error = f"{type(exc).__name__}: {exc}"
        t1 = time.perf_counter()
        out = self.renderer.render(image, active, ctx)
        self.stats["update_ms"] = self.stats["update_ms"] * 0.9 + (t1 - t0) * 1000 * 0.1
        self.stats["render_ms"] = self.stats["render_ms"] * 0.9 + self.renderer.gpu_ms * 0.1
        self.stats["hands"] = len(tr.hands)
        try:
            self.telemetry = self.telemetry_collector.update(self, ctx)
        except Exception:   # the HUD must never break rendering
            import logging
            logging.getLogger("hfx").exception("telemetry")
        return out

    def process_frame(self, image_bgr: np.ndarray, t: float, index: int) -> np.ndarray:
        tr = self.tracker.process(image_bgr, t, index)
        return self._render(tr, image_bgr, t)

    def tick(self) -> np.ndarray | None:
        """Live mode: render the newest tracked frame. Returns RGB image."""
        if self.tracker is None:
            return None
        tr = self.tracker.latest()
        image = tr.image
        if image is None and self.camera is not None:
            f = self.camera.latest()
            if f is None:
                return None
            image = f.image
        now = time.perf_counter() - self._t0
        return self._render(tr, image, now)
