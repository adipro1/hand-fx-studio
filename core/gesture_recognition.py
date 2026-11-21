"""Gesture recognition.

Produces two kinds of output per frame:

* **Continuous values** (0..1) that effects can be driven by smoothly:
  pinch, spread, openness, fist, point, two-hand distance, ...
* **Discrete gestures** (open palm, fist, peace, point, thumbs up, pinch, ...)
  confirmed over a short interval to avoid accidental activation, plus
  one-shot **events** (fist_close, pinch_start, circle, clap, ...).
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field

import numpy as np

from core.filters import ExpSmoother
from core.hand_tracker import HandState, TrackingResult

GESTURES = ("none", "open_palm", "fist", "peace", "point", "frame", "thumbs_up",
            "pinch", "rock", "three", "ok")

GESTURE_LABELS = {
    "none": "—", "open_palm": "Open palm", "fist": "Fist", "peace": "Peace",
    "point": "Pointing", "frame": "L-frame", "thumbs_up": "Thumbs up", "pinch": "Pinch",
    "rock": "Rock / horns", "three": "Three", "ok": "OK sign",
}


@dataclass
class HandGesture:
    hand_id: int
    label: str
    gesture: str = "none"          # confirmed gesture
    raw_gesture: str = "none"      # instantaneous classification
    hold_time: float = 0.0         # seconds the confirmed gesture has been held
    pinch: float = 0.0             # 0 open .. 1 touching
    spread: float = 0.0            # 0 closed .. 1 spread wide
    openness: float = 0.0          # mean finger extension
    fist: float = 0.0              # 1 = tight fist
    point: float = 0.0             # index extended, others curled
    spreading: float = 0.0         # d(spread)/dt, positive while opening
    circle: float = 0.0            # signed circular-motion strength
    pinch_pos: np.ndarray = field(default_factory=lambda: np.zeros(2))  # aspect space


@dataclass
class GestureFrame:
    hands: dict[int, HandGesture]
    events: list[tuple[str, int, dict]]       # (event, hand_id or -1, data)
    two_hand: dict[str, float]
    tracking: TrackingResult

    def for_hand(self, h: HandState) -> HandGesture | None:
        return self.hands.get(h.hand_id)


def classify(h: HandState) -> str:
    """Instantaneous static gesture classification from finger states."""
    e = h.extension
    up = e > 0.55
    down = e < 0.35
    thumb, index, middle, ring, pinky = up
    pinch_close = h.pinch_dist < 0.35

    if pinch_close and e[2] > 0.5 and e[3] > 0.45 and e[4] > 0.4:
        return "ok"
    if pinch_close and (e[2] < 0.5 or e[3] < 0.5):
        return "pinch"
    if all(up[1:]) and h.spread > 0.25:
        return "open_palm"
    if all(down[1:]) and not thumb:
        return "fist"
    if index and middle and down[3] and down[4]:
        return "peace"
    if index and down[2] and down[3] and pinky:
        return "rock"
    if index and middle and ring and down[4]:
        return "three"
    if index and down[2] and down[3] and down[4]:
        # thumb sticking out sideways = L-shaped "camera frame" hand
        thumb_len = np.linalg.norm(h.pts[4] - h.pts[2]) / h.scale
        if e[0] > 0.45 and thumb_len > 0.55:
            return "frame"
        return "point"
    if thumb and all(down[1:]):
        # thumb clearly pointing up in image space, well away from the index finger
        tvec = h.pts[4] - h.pts[2]
        tip_above_knuckles = h.pts[4, 1] < h.pts[[5, 9], 1].min() - 0.3 * h.scale
        if (tvec[1] < -0.7 * np.linalg.norm(tvec) and h.pinch_dist > 0.8
                and tip_above_knuckles and e[0] > 0.7):
            return "thumbs_up"
        return "fist"
    if all(up[1:]):
        return "open_palm"
    return "none"


class _HandMemory:
    def __init__(self):
        self.candidate = "none"
        self.candidate_time = 0.0
        self.confirmed = "none"
        self.hold = 0.0
        self.pinch = ExpSmoother(0.04)
        self.spread = ExpSmoother(0.06)
        self.open = ExpSmoother(0.06)
        self.spread_prev = 0.0
        self.spreading = ExpSmoother(0.1)
        self.trail: deque = deque(maxlen=45)  # (t, x, y)
        self.circle = ExpSmoother(0.15)
        self.pinch_active = False
        self.last_circle_event = -10.0
        self.peak_speed = 0.0


class GestureRecognizer:
    def __init__(self, confirm_time: float = 0.12, pinch_on: float = 0.75,
                 pinch_off: float = 0.55):
        self.confirm_time = confirm_time
        self.pinch_on = pinch_on
        self.pinch_off = pinch_off
        self._mem: dict[int, _HandMemory] = {}
        self._last_t: float | None = None
        self._two = {"distance": ExpSmoother(0.05, 0.0), "together": False}
        self._prev_hand_count = 0
        self._last_clap = -10.0

    def update(self, tr: TrackingResult) -> GestureFrame:
        t = tr.timestamp
        dt = 1 / 30 if self._last_t is None else max(min(t - self._last_t, 0.2), 1e-3)
        if self._last_t is not None and t == self._last_t:
            dt = 0.0
        self._last_t = t
        events: list[tuple[str, int, dict]] = []
        out: dict[int, HandGesture] = {}
        alive = set()

        for h in tr.hands:
            alive.add(h.hand_id)
            m = self._mem.setdefault(h.hand_id, _HandMemory())
            if dt == 0.0:
                pass
            g = HandGesture(h.hand_id, h.label)

            # continuous values
            pinch_raw = float(np.clip(1.0 - (h.pinch_dist - 0.12) / 0.75, 0.0, 1.0))
            g.pinch = float(m.pinch.update(pinch_raw, dt)) if dt else m.pinch.value
            g.spread = float(m.spread.update(h.spread, dt)) if dt else m.spread.value
            openness = float(np.mean(h.extension[1:]))
            g.openness = float(m.open.update(openness, dt)) if dt else m.open.value
            g.fist = float(np.clip(1.0 - g.openness * 1.6, 0.0, 1.0)) * (1.0 - g.pinch * 0.5)
            g.point = float(h.extension[1] * (1.0 - max(h.extension[2], h.extension[3], h.extension[4])))
            if dt:
                rate = (g.spread - m.spread_prev) / dt
                m.spread_prev = g.spread
                g.spreading = float(m.spreading.update(rate, dt))
            else:
                g.spreading = m.spreading.value
            g.pinch_pos = (h.pts[4] + h.pts[8]) * 0.5

            # discrete gesture with confirmation interval
            raw = classify(h) if h.presence > 0.99 else m.confirmed
            g.raw_gesture = raw
            if raw != m.candidate:
                m.candidate = raw
                m.candidate_time = 0.0
            else:
                m.candidate_time += dt
            if m.candidate != m.confirmed and m.candidate_time >= self.confirm_time:
                prev = m.confirmed
                m.confirmed = m.candidate
                m.hold = 0.0
                events.append((f"{m.confirmed}_start", h.hand_id, {"from": prev}))
                if m.confirmed == "fist" and prev in ("open_palm", "none", "three", "peace"):
                    events.append(("fist_close", h.hand_id, {"pos": h.palm_center.copy(),
                                                              "uv": h.palm_uv.copy()}))
                if m.confirmed == "open_palm" and prev == "fist":
                    events.append(("palm_burst", h.hand_id, {"pos": h.palm_center.copy(),
                                                              "uv": h.palm_uv.copy()}))
            else:
                m.hold += dt
            g.gesture = m.confirmed
            g.hold_time = m.hold

            # pinch hysteresis events
            if not m.pinch_active and g.pinch > self.pinch_on:
                m.pinch_active = True
                events.append(("pinch_start", h.hand_id, {"pos": g.pinch_pos.copy()}))
            elif m.pinch_active and g.pinch < self.pinch_off:
                m.pinch_active = False
                events.append(("pinch_end", h.hand_id, {"pos": g.pinch_pos.copy()}))

            # circular motion of the index fingertip
            m.trail.append((t, float(h.pts[8, 0]), float(h.pts[8, 1])))
            g.circle = float(m.circle.update(self._circularity(m.trail, h.scale), dt)) if dt else m.circle.value
            if abs(g.circle) > 0.6 and t - m.last_circle_event > 1.0:
                m.last_circle_event = t
                events.append(("circle", h.hand_id, {"direction": 1 if g.circle > 0 else -1,
                                                     "pos": h.pts[8].copy()}))

            # fast swipe
            if h.speed > 2.2 and m.peak_speed <= 2.2:
                events.append(("swipe", h.hand_id, {"direction": h.direction, "speed": h.speed}))
            m.peak_speed = h.speed
            out[h.hand_id] = g

        for hid in list(self._mem):
            if hid not in alive:
                del self._mem[hid]

        two = self._two_hand(tr, out, dt, events)
        return GestureFrame(out, events, two, tr)

    # ------------------------------------------------------------------
    @staticmethod
    def _circularity(trail: deque, scale: float) -> float:
        """Signed measure of how circular the recent fingertip path is.

        Sums turning angle along the path; a full loop gives ~2*pi. Requires a
        minimum path length so jitter is not detected as circles.
        """
        if len(trail) < 12:
            return 0.0
        pts = np.array([(x, y) for _, x, y in trail])
        seg = np.diff(pts, axis=0)
        lens = np.linalg.norm(seg, axis=1)
        keep = lens > scale * 0.03
        seg = seg[keep]
        if len(seg) < 8 or lens.sum() < scale * 2.0:
            return 0.0
        ang = np.arctan2(seg[:, 1], seg[:, 0])
        turn = np.diff(ang)
        turn = (turn + np.pi) % (2 * np.pi) - np.pi
        total = float(turn.sum())
        consistency = abs(total) / (np.abs(turn).sum() + 1e-6)
        return float(np.clip(total / (2 * math.pi), -1.0, 1.0)) * consistency

    def _two_hand(self, tr: TrackingResult, gs: dict[int, HandGesture], dt: float, events) -> dict:
        hands = [h for h in tr.hands if h.presence > 0.3]
        res = {"active": 0.0, "distance": 0.0, "distance_norm": 0.0, "angle": 0.0,
               "together": 0.0, "mid_x": 0.5, "mid_y": 0.5, "index_distance": 0.0,
               "approach": 0.0}
        if len(hands) < 2:
            self._prev_hand_count = len(hands)
            self._two["together"] = False
            return res
        a, b = hands[0], hands[1]
        d = float(np.linalg.norm(a.palm_center - b.palm_center))
        scale = (a.scale + b.scale) * 0.5
        prev = self._two["distance"].value
        sm = float(self._two["distance"].update(d, dt)) if dt else prev
        if self._prev_hand_count < 2:
            self._two["distance"].value = d
            sm = d
            prev = d
        self._prev_hand_count = 2
        mid = (a.palm_center + b.palm_center) * 0.5
        vec = b.palm_center - a.palm_center
        res.update({
            "active": float(min(a.presence, b.presence)),
            "distance": sm,
            "distance_norm": float(np.clip(sm / (scale * 8.0), 0.0, 1.0)),
            "angle": float(math.atan2(vec[1], vec[0])),
            "mid_x": float(mid[0] / a.aspect), "mid_y": float(mid[1]),
            "index_distance": float(np.linalg.norm(a.pts[8] - b.pts[8]) / scale),
            "approach": float((prev - sm) / dt) if dt else 0.0,
        })
        together = sm < scale * 2.2
        res["together"] = float(np.clip(1.0 - (sm / scale - 1.5) / 4.0, 0.0, 1.0))
        if together and not self._two["together"] and tr.timestamp - self._last_clap > 0.6:
            self._last_clap = tr.timestamp
            events.append(("hands_together", -1, {"uv": np.array([res["mid_x"], res["mid_y"]])}))
        self._two["together"] = together
        return res
