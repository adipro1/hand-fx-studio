"""Threaded webcam capture.

Capture runs on its own thread so that a slow camera never blocks rendering.
Consumers always get the most recent frame (older frames are dropped), which
keeps latency minimal.
"""
from __future__ import annotations

import sys
import threading
import time
from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class Frame:
    image: np.ndarray  # BGR uint8, already mirrored if requested
    timestamp: float  # time.perf_counter() at capture
    index: int


def list_cameras(max_index: int = 6) -> list[int]:
    """Probe camera indices. Returns indices that delivered a frame."""
    found = []
    backend = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY
    for i in range(max_index):
        cap = cv2.VideoCapture(i, backend)
        if cap.isOpened():
            ok, _ = cap.read()
            if ok:
                found.append(i)
        cap.release()
    return found


class Camera:
    def __init__(self, index: int = 0, width: int = 1280, height: int = 720,
                 fps: int = 30, mirror: bool = True):
        self.index = index
        self.req_width = width
        self.req_height = height
        self.req_fps = fps
        self.mirror = mirror
        self.width = width
        self.height = height
        self.error: str | None = None
        self.measured_fps = 0.0

        self._cap: cv2.VideoCapture | None = None
        self._lock = threading.Lock()
        self._frame: Frame | None = None
        self._running = False
        self._thread: threading.Thread | None = None
        self._new_frame = threading.Event()

    # ------------------------------------------------------------------
    def start(self) -> bool:
        self.stop()
        self.error = None
        backend = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY
        cap = cv2.VideoCapture(self.index, backend)
        if not cap.isOpened():
            # Fall back to Media Foundation / default backend
            cap = cv2.VideoCapture(self.index)
        if not cap.isOpened():
            self.error = (f"Could not open camera {self.index}. Make sure no other app "
                          f"(Zoom, Teams, Camera app) is using it, and that camera access "
                          f"is allowed in Windows Settings > Privacy > Camera.")
            return False
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.req_width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.req_height)
        cap.set(cv2.CAP_PROP_FPS, self.req_fps)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        ok, img = cap.read()
        if not ok or img is None:
            cap.release()
            self.error = f"Camera {self.index} opened but returned no image."
            return False
        self.height, self.width = img.shape[:2]
        self._cap = cap
        self._running = True
        self._thread = threading.Thread(target=self._loop, name="CameraThread", daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    @property
    def running(self) -> bool:
        return self._running

    # ------------------------------------------------------------------
    def _loop(self) -> None:
        idx = 0
        t_last = time.perf_counter()
        fails = 0
        while self._running and self._cap is not None:
            ok, img = self._cap.read()
            now = time.perf_counter()
            if not ok or img is None:
                fails += 1
                if fails > 60:
                    self.error = "Camera stopped delivering frames (was it unplugged?)."
                    self._running = False
                    break
                time.sleep(0.01)
                continue
            fails = 0
            if self.mirror:
                img = cv2.flip(img, 1)
            idx += 1
            dt = now - t_last
            t_last = now
            if dt > 0:
                self.measured_fps = self.measured_fps * 0.9 + (1.0 / dt) * 0.1
            with self._lock:
                self._frame = Frame(img, now, idx)
            self._new_frame.set()

    def latest(self) -> Frame | None:
        with self._lock:
            return self._frame

    def wait_frame(self, timeout: float = 0.1) -> bool:
        got = self._new_frame.wait(timeout)
        self._new_frame.clear()
        return got
