"""Application configuration and persistence.

Settings are stored as JSON in ``user_settings.json`` next to main.py.
Effect parameters are stored per effect id so they survive restarts.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from dataclasses import asdict, dataclass, field

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Automated self-tests use their own settings file so they never touch the user's settings.
SETTINGS_PATH = (os.environ.get("HFX_SETTINGS")
                 or (os.path.join(tempfile.gettempdir(), "hfx_selftest_settings.json")
                     if "--selftest" in sys.argv else os.path.join(ROOT, "user_settings.json")))


def default_recordings_dir() -> str:
    videos = os.path.join(os.path.expanduser("~"), "Videos")
    base = videos if os.path.isdir(videos) else ROOT
    return os.path.join(base, "HandFXStudio")


@dataclass
class CameraSettings:
    index: int = 0
    width: int = 1280
    height: int = 720
    fps: int = 30
    mirror: bool = True


@dataclass
class TrackingSettings:
    max_hands: int = 2
    detection_confidence: float = 0.6
    tracking_confidence: float = 0.5
    smoothing: float = 0.55          # 0 responsive .. 1 very smooth
    process_width: int = 640         # tracking resolution (lower = faster)
    lost_grace: float = 0.3          # seconds a lost hand fades out
    confirm_time: float = 0.12       # gesture confirmation interval
    low_light: bool = False          # contrast boost for dark / backlit rooms


@dataclass
class RenderSettings:
    quality: str = "high"            # low / medium / high
    show_camera: bool = True
    background_dim: float = 0.0      # 0 = full camera, 1 = black
    bloom: float = 0.8
    master_intensity: float = 1.0


@dataclass
class RecordingSettings:
    output_dir: str = field(default_factory=default_recordings_dir)
    format: str = "16:9"             # "16:9", "9:16", "1:1", "source"
    resolution: int = 1080           # short-side pixels for 9:16 / long for 16:9 handled in recorder
    fps: int = 30
    quality: int = 20                # x264 CRF (lower = better)
    hud: bool = True                 # cinematic sci-fi HUD baked into recordings
    hud_style: str = "Cyber"
    hud_detail: str = "Full"
    hud_always: bool = False         # also show the HUD when not recording
    countdown: bool = True           # 3-2-1 before recording starts


@dataclass
class AppSettings:
    camera: CameraSettings = field(default_factory=CameraSettings)
    tracking: TrackingSettings = field(default_factory=TrackingSettings)
    render: RenderSettings = field(default_factory=RenderSettings)
    recording: RecordingSettings = field(default_factory=RecordingSettings)
    active_preset: str = "Reality Bender"
    effects: dict = field(default_factory=dict)   # effect_id -> {"enabled": bool, "params": {...}, "order": int}

    # ------------------------------------------------------------------
    @classmethod
    def load(cls, path: str = SETTINGS_PATH) -> "AppSettings":
        s = cls()
        if not os.path.exists(path):
            return s
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError):
            return s
        for section in ("camera", "tracking", "render", "recording"):
            obj = getattr(s, section)
            for k, v in data.get(section, {}).items():
                if hasattr(obj, k):
                    setattr(obj, k, type(getattr(obj, k))(v))
        s.active_preset = data.get("active_preset", s.active_preset)
        s.effects = data.get("effects", {}) or {}
        return s

    def save(self, path: str = SETTINGS_PATH) -> None:
        tmp = path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(asdict(self), fh, indent=2)
            os.replace(tmp, path)
        except OSError:
            pass
