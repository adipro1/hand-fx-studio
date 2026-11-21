"""Real-time two-hand tracking built on MediaPipe Hand Landmarker.

Runs on a dedicated thread: it grabs the newest camera frame, runs the
landmark model, smooths the result with One Euro filters, computes derived
measurements (finger extension, pinch, palm orientation, velocity, ...)
and publishes an immutable ``TrackingResult`` the renderer can read at any
time without blocking.

Coordinates
-----------
``HandState.lm``  : (21, 3) normalised landmarks. x, y in [0, 1] image space
                    (already mirrored if the camera is mirrored), z relative depth.
``HandState.pts`` : (21, 2) aspect-corrected 2D points: x * aspect, y. Use these
                    for distances/angles so they are not squashed by the frame shape.
"""
from __future__ import annotations

import math
import os
import threading
import time
import urllib.request
from dataclasses import dataclass, field

import cv2
import numpy as np

from core.filters import OneEuroFilter

MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
             "hand_landmarker/float16/latest/hand_landmarker.task")
MODEL_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "assets", "models", "hand_landmarker.task")

# Landmark indices -------------------------------------------------------
WRIST = 0
THUMB = (1, 2, 3, 4)
INDEX = (5, 6, 7, 8)
MIDDLE = (9, 10, 11, 12)
RING = (13, 14, 15, 16)
PINKY = (17, 18, 19, 20)
FINGERS = (THUMB, INDEX, MIDDLE, RING, PINKY)
FINGER_NAMES = ("thumb", "index", "middle", "ring", "pinky")
TIPS = (4, 8, 12, 16, 20)
MCPS = (1, 5, 9, 13, 17)
PALM_IDS = (0, 5, 9, 13, 17)

HAND_CONNECTIONS = (
    (0, 1), (1, 2), (2, 3), (3, 4),
    (0, 5), (5, 6), (6, 7), (7, 8),
    (5, 9), (9, 10), (10, 11), (11, 12),
    (9, 13), (13, 14), (14, 15), (15, 16),
    (13, 17), (0, 17), (17, 18), (18, 19), (19, 20),
)


def ensure_model(progress_cb=None) -> str:
    """Download the hand landmark model on first run (about 7.5 MB)."""
    if os.path.exists(MODEL_PATH) and os.path.getsize(MODEL_PATH) > 1_000_000:
        return MODEL_PATH
    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    tmp = MODEL_PATH + ".part"
    if progress_cb:
        progress_cb("Downloading hand tracking model (first run only)...")
    try:
        urllib.request.urlretrieve(MODEL_URL, tmp)
        os.replace(tmp, MODEL_PATH)
    except Exception as exc:  # pragma: no cover - network dependent
        if os.path.exists(tmp):
            os.remove(tmp)
        raise RuntimeError(
            "Could not download the hand tracking model. Check your internet "
            f"connection, or download it manually from\n{MODEL_URL}\nand save it as\n"
            f"{MODEL_PATH}\n\nDetails: {exc}") from exc
    return MODEL_PATH


def _angle(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> float:
    """Bend angle at b (0 = straight, pi = folded back) using 3D points."""
    v1 = a - b
    v2 = c - b
    n = np.linalg.norm(v1) * np.linalg.norm(v2)
    if n < 1e-9:
        return 0.0
    cosv = float(np.clip(np.dot(v1, v2) / n, -1.0, 1.0))
    return math.pi - math.acos(cosv)


@dataclass
class HandState:
    hand_id: int                  # stable id while the hand stays tracked
    label: str                    # "Left" or "Right" (user's real hand, mirrored view)
    lm: np.ndarray                # (21, 3) normalised landmarks
    pts: np.ndarray               # (21, 2) aspect-corrected points
    aspect: float
    presence: float = 1.0         # 1 while tracked, fades to 0 during tracking loss
    confidence: float = 1.0
    # derived ------------------------------------------------------------
    extension: np.ndarray = field(default_factory=lambda: np.zeros(5))   # 0 bent .. 1 straight
    finger_bend: np.ndarray = field(default_factory=lambda: np.zeros(5))  # radians
    scale: float = 0.1            # wrist -> middle MCP distance (aspect space)
    palm_center: np.ndarray = field(default_factory=lambda: np.zeros(2))  # aspect space
    palm_normal: np.ndarray = field(default_factory=lambda: np.array([0, 0, 1.0]))
    palm_facing: float = 1.0      # +1 palm faces camera, -1 back of hand
    rotation: float = 0.0         # radians, in-plane rotation (0 = fingers up)
    velocity: np.ndarray = field(default_factory=lambda: np.zeros(2))     # aspect units / s
    speed: float = 0.0
    direction: float = 0.0        # radians of movement direction
    pinch_dist: float = 1.0       # thumb-index distance / hand scale
    tip_dists: np.ndarray = field(default_factory=lambda: np.zeros((5, 5)))  # / scale
    spread: float = 0.0           # 0 fingers together .. 1 fully spread

    # convenience ---------------------------------------------------------
    def uv(self, idx: int) -> tuple[float, float]:
        return float(self.lm[idx, 0]), float(self.lm[idx, 1])

    def uv_of(self, p: np.ndarray) -> np.ndarray:
        """Aspect-space point -> normalised uv."""
        return np.array([p[0] / self.aspect, p[1]])

    @property
    def palm_uv(self) -> np.ndarray:
        return self.uv_of(self.palm_center)


@dataclass
class TrackingResult:
    hands: list[HandState]
    timestamp: float
    frame_index: int
    inference_ms: float = 0.0
    aspect: float = 16 / 9

    def by_label(self, label: str) -> HandState | None:
        for h in self.hands:
            if h.label == label:
                return h
        return None


def compute_features(h: HandState, prev: HandState | None, dt: float) -> None:
    """Fill in derived measurements on ``h`` (in place)."""
    lm3 = h.lm.copy()
    lm3[:, 0] *= h.aspect
    lm3[:, 2] *= h.aspect  # MediaPipe z is roughly in x-scale units
    pts = h.pts

    h.scale = float(max(np.linalg.norm(pts[9] - pts[0]), 1e-4))
    h.palm_center = pts[list(PALM_IDS)].mean(axis=0)

    # finger extension from accumulated joint bend (orientation invariant)
    for f, ids in enumerate(FINGERS):
        if f == 0:
            chain = [lm3[0], lm3[1], lm3[2], lm3[3], lm3[4]]
            bend = _angle(chain[1], chain[2], chain[3]) + _angle(chain[2], chain[3], chain[4])
            max_bend = 1.9
            # thumb also counts as "tucked" if tip is close to index MCP / palm
            tuck = np.linalg.norm(pts[4] - pts[9]) / h.scale
            ext = 1.0 - min(bend / max_bend, 1.0)
            ext = ext * float(np.clip((tuck - 0.45) / 0.5, 0.0, 1.0)) ** 0.5
        else:
            chain = [lm3[0], lm3[ids[0]], lm3[ids[1]], lm3[ids[2]], lm3[ids[3]]]
            bend = (_angle(chain[0], chain[1], chain[2]) + _angle(chain[1], chain[2], chain[3])
                    + _angle(chain[2], chain[3], chain[4]))
            max_bend = 3.6
            ext = 1.0 - min(bend / max_bend, 1.0)
            ext = float(np.clip((ext - 0.25) / 0.6, 0.0, 1.0))
        h.finger_bend[f] = bend
        h.extension[f] = ext

    # palm orientation
    v1 = lm3[5] - lm3[0]
    v2 = lm3[17] - lm3[0]
    n = np.cross(v1, v2)
    nn = np.linalg.norm(n)
    if nn > 1e-9:
        n = n / nn
    if h.label == "Left":
        n = -n
    h.palm_normal = n
    h.palm_facing = float(-n[2])

    up = pts[9] - pts[0]
    h.rotation = float(math.atan2(up[0], -up[1]))

    tips = pts[list(TIPS)]
    d = np.linalg.norm(tips[:, None, :] - tips[None, :, :], axis=-1) / h.scale
    h.tip_dists = d
    h.pinch_dist = float(d[0, 1])

    # spread: average distance between neighbouring fingertips (index..pinky)
    neigh = (d[1, 2] + d[2, 3] + d[3, 4]) / 3.0
    h.spread = float(np.clip((neigh - 0.25) / 0.45, 0.0, 1.0)) * float(np.mean(h.extension[1:]))

    if prev is not None and dt > 0:
        vel = (h.palm_center - prev.palm_center) / dt
        h.velocity = prev.velocity * 0.6 + vel * 0.4
    h.speed = float(np.linalg.norm(h.velocity))
    if h.speed > 1e-3:
        h.direction = float(math.atan2(h.velocity[1], h.velocity[0]))


class _Track:
    """Per-hand filter state and identity."""
    _next_id = 1

    def __init__(self, label: str):
        self.id = _Track._next_id
        _Track._next_id += 1
        self.label = label
        self.filter = OneEuroFilter()
        self.state: HandState | None = None
        self.last_seen = 0.0


class HandTracker:
    def __init__(self, camera, max_hands: int = 2, detection_conf: float = 0.6,
                 tracking_conf: float = 0.5, presence_conf: float = 0.5,
                 process_width: int = 640, smoothing: float = 0.5,
                 lost_grace: float = 0.3):
        self.camera = camera
        self.max_hands = max_hands
        self.detection_conf = detection_conf
        self.tracking_conf = tracking_conf
        self.presence_conf = presence_conf
        self.process_width = process_width
        self.lost_grace = lost_grace
        self.smoothing = smoothing
        self.error: str | None = None
        self.fps = 0.0

        self._landmarker = None
        self._tracks: dict[str, _Track] = {}
        self._result = TrackingResult([], 0.0, 0)
        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None
        self._rebuild = False
        self._last_ts_ms = 0

    # -- configuration ---------------------------------------------------
    def set_smoothing(self, s: float) -> None:
        """0 = raw/responsive ... 1 = very smooth."""
        self.smoothing = float(np.clip(s, 0.0, 1.0))
        for t in self._tracks.values():
            self._apply_smoothing(t.filter)

    def _apply_smoothing(self, f: OneEuroFilter) -> None:
        s = self.smoothing
        f.min_cutoff = 4.0 * (1.0 - s) ** 2 + 0.4
        f.beta = 0.6 * (1.0 - s) + 0.02

    def set_confidence(self, detection: float, tracking: float) -> None:
        self.detection_conf = detection
        self.tracking_conf = tracking
        self.presence_conf = tracking
        self._rebuild = True

    # -- lifecycle -------------------------------------------------------
    def _create_landmarker(self):
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions
        from mediapipe.tasks.python import vision

        path = ensure_model()
        with open(path, "rb") as fh:  # buffer avoids unicode/OneDrive path issues
            model_bytes = fh.read()
        opts = vision.HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_buffer=model_bytes),
            running_mode=vision.RunningMode.VIDEO,
            num_hands=self.max_hands,
            min_hand_detection_confidence=self.detection_conf,
            min_hand_presence_confidence=self.presence_conf,
            min_tracking_confidence=self.tracking_conf,
        )
        self._mp = mp
        return vision.HandLandmarker.create_from_options(opts)

    def start(self) -> bool:
        try:
            self._landmarker = self._create_landmarker()
        except Exception as exc:
            self.error = f"Hand tracking failed to start: {exc}"
            return False
        self._running = True
        self._thread = threading.Thread(target=self._loop, name="TrackerThread", daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        if self._landmarker is not None:
            self._landmarker.close()
            self._landmarker = None

    def latest(self) -> TrackingResult:
        with self._lock:
            return self._result

    # -- core ------------------------------------------------------------
    def process(self, image_bgr: np.ndarray, timestamp: float, frame_index: int = 0) -> TrackingResult:
        """Run tracking on one frame synchronously (also used by tests)."""
        h, w = image_bgr.shape[:2]
        aspect = w / h
        if self.process_width and w > self.process_width:
            ph = int(round(h * self.process_width / w))
            small = cv2.resize(image_bgr, (self.process_width, ph), interpolation=cv2.INTER_AREA)
        else:
            small = image_bgr
        rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
        mp_img = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb))
        ts_ms = int(timestamp * 1000)
        if ts_ms <= self._last_ts_ms:
            ts_ms = self._last_ts_ms + 1
        self._last_ts_ms = ts_ms
        t0 = time.perf_counter()
        res = self._landmarker.detect_for_video(mp_img, ts_ms)
        inf_ms = (time.perf_counter() - t0) * 1000.0

        detections = []
        for i, lms in enumerate(res.hand_landmarks):
            arr = np.array([[p.x, p.y, p.z] for p in lms], dtype=np.float64)
            cat = res.handedness[i][0]
            detections.append((cat.category_name, float(cat.score), arr))
        # Resolve duplicate labels (model occasionally labels both hands the same)
        if len(detections) == 2 and detections[0][0] == detections[1][0]:
            a, b = detections
            # The hand further left on screen (mirrored view) is the user's left hand
            if a[2][0, 0] < b[2][0, 0]:
                detections = [("Left", a[1], a[2]), ("Right", b[1], b[2])]
            else:
                detections = [("Right", a[1], a[2]), ("Left", b[1], b[2])]

        seen = set()
        hands: list[HandState] = []
        for label, score, raw in detections:
            seen.add(label)
            track = self._tracks.get(label)
            if track is None or timestamp - track.last_seen > 1.0:
                track = _Track(label)
                self._apply_smoothing(track.filter)
                self._tracks[label] = track
            sm = track.filter(raw, timestamp)
            pts = np.stack([sm[:, 0] * aspect, sm[:, 1]], axis=1)
            st = HandState(track.id, label, sm, pts, aspect, 1.0, score)
            prev = track.state
            dt = timestamp - track.last_seen if prev is not None else 0.0
            compute_features(st, prev, dt)
            track.state = st
            track.last_seen = timestamp
            hands.append(st)

        # Graceful tracking loss: keep the last pose briefly, fading out
        for label, track in list(self._tracks.items()):
            if label in seen or track.state is None:
                continue
            gone = timestamp - track.last_seen
            if gone < self.lost_grace:
                st = track.state
                fade = 1.0 - gone / self.lost_grace
                ghost = HandState(**{**st.__dict__})
                ghost.presence = fade
                ghost.velocity = st.velocity * 0.5
                hands.append(ghost)
            elif gone > 1.0:
                track.filter.reset()

        hands.sort(key=lambda s: 0 if s.label == "Left" else 1)
        return TrackingResult(hands, timestamp, frame_index, inf_ms, aspect)

    def _loop(self) -> None:
        last_idx = -1
        t_prev = time.perf_counter()
        while self._running:
            if self._rebuild:
                self._rebuild = False
                try:
                    old = self._landmarker
                    self._landmarker = self._create_landmarker()
                    self._last_ts_ms = 0
                    old.close()
                except Exception as exc:
                    self.error = str(exc)
            frame = self.camera.latest() if self.camera else None
            if frame is None or frame.index == last_idx:
                time.sleep(0.002)
                continue
            last_idx = frame.index
            try:
                result = self.process(frame.image, frame.timestamp, frame.index)
            except Exception as exc:  # keep the thread alive
                self.error = f"Tracking error: {exc}"
                time.sleep(0.05)
                continue
            now = time.perf_counter()
            dt = now - t_prev
            t_prev = now
            if dt > 0:
                self.fps = self.fps * 0.9 + 0.1 / dt
            with self._lock:
                self._result = result
