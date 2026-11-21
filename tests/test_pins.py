"""Pinned filter frames: hold-still pin, grab, point-to-cycle, clear."""
import numpy as np

from core.gesture_recognition import GestureFrame, HandGesture
from core.hand_tracker import TrackingResult
from effects.base_effect import FrameContext
from effects.frames import FilterFrameEffect, inside_poly
from tests.test_gestures import ALL, make_hand

ASPECT = 16 / 9


def hand_at(dx, label, hid, index_uv=None, thumb_uv=None):
    h = make_hand(ALL, label, hid)
    h.lm[:, 0] += dx
    if index_uv is not None:
        h.lm[8, :2] = index_uv
    if thumb_uv is not None:
        h.lm[4, :2] = thumb_uv
    h.pts = np.stack([h.lm[:, 0] * ASPECT, h.lm[:, 1]], 1)
    from core.hand_tracker import compute_features
    compute_features(h, None, 0.0)
    return h


class Sim:
    """Drives the effect with synthetic two-hand frames at 30 fps."""

    def __init__(self, eff):
        self.eff = eff
        self.t = 0.0

    def step(self, quad=None, gestures=None, events=(), hands=None):
        self.t += 1 / 30
        if hands is None:
            hands = []
            if quad is not None:
                li, ri, rt, lt = quad
                hands = [hand_at(-0.25, "Left", 1, li, lt), hand_at(0.25, "Right", 2, ri, rt)]
        gs = {}
        for h in hands:
            g = HandGesture(h.hand_id, h.label, gesture="frame")
            g.pinch_pos = (h.pts[4] + h.pts[8]) / 2
            if gestures and h.hand_id in gestures:
                for k, v in gestures[h.hand_id].items():
                    setattr(g, k, v)
            gs[h.hand_id] = g
        tr = TrackingResult(hands, self.t, int(self.t * 30))
        ctx = FrameContext(self.t, 1 / 30, tr, GestureFrame(gs, list(events), {}, tr), list(events), 1280, 720)
        self.eff.update(ctx)
        return ctx


QUAD = np.array([[0.30, 0.30], [0.70, 0.30], [0.70, 0.65], [0.30, 0.65]], dtype="f4")


def test_hold_still_pins_exactly_once():
    e = FilterFrameEffect()
    s = Sim(e)
    for _ in range(int(2.5 * 30)):       # 2.5 s perfectly still
        s.step(QUAD)
    assert len(e.pins) == 1
    assert np.allclose(e.pins[0].poly, QUAD, atol=1e-3)


def test_moving_frame_never_pins():
    e = FilterFrameEffect()
    s = Sim(e)
    for i in range(90):
        s.step(QUAD + np.array([0.02 * np.sin(i * 0.4), 0.0], dtype="f4"))
    assert e.pins == []


def test_pinch_grab_moves_pin():
    e = FilterFrameEffect()
    e.add_pin(QUAD)
    s = Sim(e)
    h = hand_at(0.0, "Right", 5)
    centre = np.array([0.5 * ASPECT, 0.47])
    for i in range(30):
        pos = centre + np.array([0.004 * max(0, i - 12), 0.0])
        s.step(hands=[h], gestures={5: {"pinch": 0.95, "pinch_pos": pos, "gesture": "pinch"}})
    moved = e.pins[0].poly[:, 0].mean() - QUAD[:, 0].mean()
    assert moved > 0.02, moved
    s.step(hands=[h], gestures={5: {"pinch": 0.1, "pinch_pos": centre, "gesture": "none"}})
    assert not e.pins[0].grabbed


def test_point_cycles_pin_filter():
    e = FilterFrameEffect()
    pin = e.add_pin(QUAD)
    before = pin.filter_idx
    s = Sim(e)
    h = hand_at(0.0, "Right", 7, index_uv=np.array([0.5, 0.47]))
    for _ in range(25):
        s.step(hands=[h], gestures={7: {"gesture": "point"}})
    assert pin.filter_idx == (before + 1) % 16


def test_two_fists_clear_pins_and_max_pins():
    e = FilterFrameEffect()
    e.set_param("max_pins", 3)
    for k in range(5):
        e.add_pin(QUAD + k * 0.01)
    assert len(e.pins) == 3
    s = Sim(e)
    a, b = hand_at(-0.25, "Left", 1), hand_at(0.25, "Right", 2)
    for i in range(40):
        s.step(hands=[a, b], gestures={1: {"gesture": "fist", "hold_time": i / 30},
                                       2: {"gesture": "fist", "hold_time": i / 30}})
    assert e.pins == []


def test_inside_poly():
    assert inside_poly(np.array([0.5 * ASPECT, 0.5]), QUAD, ASPECT)
    assert not inside_poly(np.array([0.1, 0.1]), QUAD, ASPECT)
    assert not inside_poly(np.array([0.30 * ASPECT + 0.001, 0.5]), QUAD, ASPECT, margin=0.02)


def test_pinch_taps_never_pin():
    e = FilterFrameEffect()
    e.set_param("pin_hold_enabled", False)
    s = Sim(e)
    for _ in range(10):
        s.step(QUAD)
    for _ in range(3):
        s.step(QUAD, events=[("pinch_start", 2, {})])
        s.step(QUAD, events=[("pinch_end", 2, {})])
    assert e.pins == []
