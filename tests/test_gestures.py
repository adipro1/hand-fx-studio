"""Gesture classification on synthetic, anatomically laid-out hand poses.

(These synthetic hands are test fixtures only — the application always uses
live MediaPipe tracking.)
"""
import numpy as np

from core.gesture_recognition import GestureRecognizer, classify
from core.hand_tracker import HandState, TrackingResult, compute_features

WRIST = np.array([0.5, 0.8])
MCP = {"thumb": (-0.035, -0.035), "index": (-0.04, -0.12), "middle": (-0.005, -0.13),
       "ring": (0.025, -0.12), "pinky": (0.05, -0.10)}
DIRS = {"thumb": (-0.8, -0.6), "index": (-0.12, -1), "middle": (0, -1),
        "ring": (0.12, -1), "pinky": (0.25, -1)}
LEN = {"thumb": 0.035, "index": 0.04, "middle": 0.045, "ring": 0.04, "pinky": 0.032}
NAMES = ["thumb", "index", "middle", "ring", "pinky"]


def make_hand(extended: dict, label="Right", hand_id=1) -> HandState:
    lm = np.zeros((21, 3))
    lm[0, :2] = WRIST
    for f, name in enumerate(NAMES):
        base = WRIST + np.array(MCP[name])
        d = np.array(DIRS[name], float)
        d /= np.linalg.norm(d)
        pts = [base]
        if extended[name]:
            for _ in range(3):
                pts.append(pts[-1] + d * LEN[name])
        elif name == "thumb":
            inward = np.array([1.0, -0.15])
            pts.append(base + d * LEN[name] * 0.5)
            pts.append(pts[-1] + inward * LEN[name] * 0.8)
            pts.append(pts[-1] + inward * LEN[name] * 0.7)
        else:
            pts.append(base + d * LEN[name] * 0.8)
            pts.append(pts[-1] + np.array([0.0, 1.0]) * LEN[name] * 0.6 + d * 0.004)
            pts.append(pts[-1] + np.array([0.0, 1.0]) * LEN[name] * 0.6)
        for k, p in enumerate(pts):
            lm[1 + f * 4 + k, :2] = p
    aspect = 16 / 9
    pts2 = np.stack([lm[:, 0] * aspect, lm[:, 1]], 1)
    h = HandState(hand_id, label, lm, pts2, aspect)
    compute_features(h, None, 0.0)
    return h


ALL = dict(thumb=True, index=True, middle=True, ring=True, pinky=True)
NONE = dict(thumb=False, index=False, middle=False, ring=False, pinky=False)


def test_open_palm():
    assert classify(make_hand(ALL)) == "open_palm"


def test_fist():
    assert classify(make_hand(NONE)) == "fist"


def test_point():
    assert classify(make_hand({**NONE, "index": True})) == "point"


def test_peace():
    assert classify(make_hand({**NONE, "index": True, "middle": True})) == "peace"


def test_frame_l_shape():
    assert classify(make_hand({**NONE, "index": True, "thumb": True})) == "frame"


def test_extension_values_continuous():
    assert np.all(make_hand(ALL).extension[1:] > 0.6)
    assert np.all(make_hand(NONE).extension[1:] < 0.35)


def test_confirmation_interval_and_fist_event():
    rec = GestureRecognizer(confirm_time=0.1)
    events = []
    t = 0.0
    for pose, n in ((ALL, 10), (NONE, 10)):
        for _ in range(n):
            t += 1 / 30
            gf = rec.update(TrackingResult([make_hand(pose)], t, int(t * 30)))
            events += [e[0] for e in gf.events]
    assert "open_palm_start" in events
    assert "fist_close" in events


def test_gesture_not_confirmed_instantly():
    rec = GestureRecognizer(confirm_time=0.2)
    gf = rec.update(TrackingResult([make_hand(ALL)], 0.0, 0))
    assert gf.hands[1].gesture == "none"


def test_pinch_is_continuous():
    rec = GestureRecognizer()
    gf = rec.update(TrackingResult([make_hand(ALL)], 0.0, 0))
    assert 0.0 <= gf.hands[1].pinch <= 1.0


def test_two_hand_distance():
    rec = GestureRecognizer()
    a = make_hand(ALL, "Left", 1)
    b = make_hand(ALL, "Right", 2)
    b.lm[:, 0] += 0.3
    b.pts[:, 0] += 0.3 * b.aspect
    compute_features(b, None, 0.0)
    gf = rec.update(TrackingResult([a, b], 0.0, 0))
    assert gf.two_hand["active"] == 1.0
    assert gf.two_hand["distance"] > 0.4
