"""MP4 recording of the final rendered composition.

Frames are pushed from the render loop (non-blocking) and encoded on a worker
thread by FFmpeg (H.264, yuv420p, faststart — plays everywhere incl. TikTok /
Instagram / phones). The output timeline is kept at a constant frame rate:
frames are duplicated or dropped based on wall-clock time, so the video plays
back at real speed even if rendering fluctuates.

Formats: "16:9", "9:16" (vertical, TikTok/Reels), "1:1", "source".
"""
from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime

import cv2
import numpy as np

FORMATS = ("16:9", "9:16", "1:1", "source")
RESOLUTIONS = (720, 1080)


def ffmpeg_exe() -> str | None:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def output_size(fmt: str, resolution: int, src_w: int, src_h: int) -> tuple[int, int]:
    """Final video size. ``resolution`` is the short side (720 / 1080)."""
    def even(x):
        return int(round(x / 2.0)) * 2
    if fmt == "9:16":
        return even(resolution), even(resolution * 16 / 9)
    if fmt == "1:1":
        return even(resolution), even(resolution)
    if fmt == "16:9":
        return even(resolution * 16 / 9), even(resolution)
    # source aspect
    return even(resolution * src_w / src_h), even(resolution)


def crop_rect(fmt: str, src_w: int, src_h: int, focus_x: float = 0.5) -> tuple[int, int, int, int]:
    """(x, y, w, h) crop of the source frame for the target aspect."""
    target = {"9:16": 9 / 16, "1:1": 1.0, "16:9": 16 / 9}.get(fmt, src_w / src_h)
    src_aspect = src_w / src_h
    if abs(target - src_aspect) < 1e-3:
        return 0, 0, src_w, src_h
    if target < src_aspect:            # narrower: crop width
        w = int(round(src_h * target))
        x = int(round(focus_x * src_w - w / 2))
        x = max(0, min(src_w - w, x))
        return x, 0, w, src_h
    h = int(round(src_w / target))     # wider: crop height
    y = (src_h - h) // 2
    return 0, y, src_w, h


@dataclass
class RecordingInfo:
    path: str
    width: int
    height: int
    fps: int
    frames: int
    duration: float
    dropped: int


class Recorder:
    def __init__(self):
        self.recording = False
        self.error: str | None = None
        self.path: str | None = None
        self.frames_written = 0
        self.frames_dropped = 0
        self.last_info: RecordingInfo | None = None
        self.focus_x = 0.5
        self._q: queue.Queue = queue.Queue(maxsize=36)
        self._thread: threading.Thread | None = None
        self._t0 = 0.0
        self._proc: subprocess.Popen | None = None
        self._cv_writer = None
        self._smooth_focus = 0.5

    # ------------------------------------------------------------------ control
    def start(self, out_dir: str, fmt: str = "16:9", resolution: int = 1080, fps: int = 30,
              crf: int = 20, src_size: tuple[int, int] = (1280, 720), smart_framing: bool = True,
              prefix: str = "HandFX") -> str:
        if self.recording:
            return self.path
        self.error = None
        os.makedirs(out_dir, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        tag = {"9:16": "vertical", "1:1": "square", "16:9": "wide"}.get(fmt, "source")
        self.path = os.path.join(out_dir, f"{prefix}_{stamp}_{tag}.mp4")
        self.fmt, self.fps, self.smart = fmt, int(fps), smart_framing
        self.src_w, self.src_h = src_size
        self.out_w, self.out_h = output_size(fmt, resolution, *src_size)
        self.frames_written = 0
        self.frames_dropped = 0
        self._smooth_focus = 0.5
        exe = ffmpeg_exe()
        if exe:
            cmd = [exe, "-hide_banner", "-loglevel", "error", "-y",
                   "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{self.out_w}x{self.out_h}",
                   "-r", str(self.fps), "-i", "-",
                   "-c:v", "libx264", "-preset", "veryfast", "-crf", str(int(crf)),
                   "-pix_fmt", "yuv420p", "-movflags", "+faststart", self.path]
            flags = 0x08000000 if sys.platform == "win32" else 0   # CREATE_NO_WINDOW
            try:
                self._proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE,
                                              creationflags=flags)
            except OSError as exc:
                self._proc = None
                self.error = f"FFmpeg could not start ({exc}); using fallback encoder."
        if self._proc is None:
            self._cv_writer = cv2.VideoWriter(self.path, cv2.VideoWriter_fourcc(*"mp4v"), self.fps,
                                              (self.out_w, self.out_h))
            if not self._cv_writer.isOpened():
                self._cv_writer = None
                raise RuntimeError("Could not create the video file. Check that the output "
                                   f"folder is writable:\n{out_dir}")
        self._q = queue.Queue(maxsize=36)   # ~1 s of frames buffered for the encoder
        self._t0 = time.perf_counter()
        self.recording = True
        self._thread = threading.Thread(target=self._worker, name="RecorderThread", daemon=True)
        self._thread.start()
        return self.path

    def push(self, rgb: np.ndarray, focus_x: float | None = None, t: float | None = None) -> None:
        """Queue a rendered RGB frame. Never blocks the render loop.
        ``t`` overrides the capture time (seconds since start; used by tests/offline)."""
        if not self.recording:
            return
        if focus_x is not None:
            self.focus_x = float(focus_x)
        try:
            if t is None:
                self._q.put_nowait((time.perf_counter(), rgb.copy(), self.focus_x))
            else:   # offline / timestamped frames: never drop, wait for the encoder
                self._q.put((self._t0 + t, rgb.copy(), self.focus_x), timeout=30)
        except queue.Full:
            self.frames_dropped += 1

    def stop(self) -> RecordingInfo | None:
        if not self.recording:
            return self.last_info
        self.recording = False
        self._q.put(None)
        if self._thread:
            self._thread.join(timeout=15)
        if self._proc:
            try:
                self._proc.stdin.close()
                _, err = self._proc.communicate(timeout=30)
                if self._proc.returncode not in (0, None) and err:
                    self.error = err.decode(errors="ignore")[-500:]
            except Exception as exc:
                self.error = str(exc)
            self._proc = None
        if self._cv_writer:
            self._cv_writer.release()
            self._cv_writer = None
        dur = self.frames_written / self.fps if self.fps else 0
        self.last_info = RecordingInfo(self.path, self.out_w, self.out_h, self.fps,
                                       self.frames_written, dur, self.frames_dropped)
        return self.last_info

    @property
    def duration(self) -> float:
        return time.perf_counter() - self._t0 if self.recording else 0.0

    # ------------------------------------------------------------------ worker
    def _prepare(self, rgb: np.ndarray, focus: float) -> np.ndarray:
        h, w = rgb.shape[:2]
        if self.smart and self.fmt in ("9:16", "1:1"):
            self._smooth_focus += (focus - self._smooth_focus) * 0.08
            fx = self._smooth_focus
        else:
            fx = 0.5
        x, y, cw, ch = crop_rect(self.fmt, w, h, fx)
        crop = rgb[y:y + ch, x:x + cw]
        if (cw, ch) != (self.out_w, self.out_h):
            interp = cv2.INTER_AREA if cw > self.out_w else cv2.INTER_LANCZOS4
            crop = cv2.resize(crop, (self.out_w, self.out_h), interpolation=interp)
        return np.ascontiguousarray(crop)

    def _write(self, frame: np.ndarray) -> None:
        if self._proc:
            self._proc.stdin.write(frame.tobytes())
        elif self._cv_writer:
            self._cv_writer.write(cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))
        self.frames_written += 1

    def _worker(self) -> None:
        last = None
        while True:
            item = self._q.get()
            if item is None:
                break
            t, rgb, focus = item
            try:
                frame = self._prepare(rgb, focus)
                target = int((t - self._t0) * self.fps) + 1
                # duplicate the previous frame to fill gaps, drop if we're ahead
                while last is not None and self.frames_written < target - 1:
                    self._write(last)
                if self.frames_written < target:
                    self._write(frame)
                last = frame
            except (BrokenPipeError, OSError, ValueError) as exc:
                self.error = f"Recording failed: {exc}"
                self.recording = False
                break
