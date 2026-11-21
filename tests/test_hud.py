"""Cinematic HUD: draws on wide/vertical frames, survives empty data, and is baked into recordings."""
import os

import cv2
import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtGui import QGuiApplication  # noqa: E402

from core.telemetry import HandTele, Telemetry  # noqa: E402
from interface.hud import DETAILS, STYLE_NAMES, HudRenderer, draw_on_rgb  # noqa: E402
from recording.recorder import Recorder  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def qt_app():
    yield QGuiApplication.instance() or QGuiApplication([])


def sample_tel():
    tips = np.array([[0.30, 0.4], [0.33, 0.3], [0.36, 0.29], [0.39, 0.31], [0.42, 0.35]], "f4")
    hands = [HandTele(1, "Left", "PINCH", 0.97, 1.0, 0.8, 0.4, 0.6, 0.3, 2.0, (0.35, 0.5), tips,
                      (0.33, 0.3, -0.05), 0.12, (0.25, 0.25, 0.45, 0.65), (1, 1, 1, 0, 0)),
             HandTele(2, "Right", "OPEN PALM", 0.92, 1.0, 0.1, 0.9, 1.0, -0.2, 5.0, (0.7, 0.5), tips + [0.35, 0],
                      (0.68, 0.3, -0.04), 0.12, (0.6, 0.25, 0.8, 0.65), (1, 1, 1, 1, 1))]
    return Telemetry(t=3.2, wall="2026-01-01  12:00:00", session="HFX-TEST", hands=hands, two_distance=0.4,
                     fps=60, render_ms=6, infer_ms=18, track_fps=30, cam_fps=30, cam_res="1280x720", gpu="GPU",
                     effects=["Filter Frame", "Hand Skeleton"], preset="Pin Studio", filter_name="Thermal",
                     pins=[{"id": 1, "poly": np.array([[.3, .3], [.6, .3], [.6, .6], [.3, .6]], "f4"),
                            "name": "Thermal", "grabbed": False}],
                     events=[("12:00:00.10", "PINNED #01")], speed_hist={"Left": np.linspace(0, 5, 120, dtype="f4")},
                     flash=("PINNED #01", 0.3), recording=True, rec_time=12.5, rec_frames=375, countdown=0.0)


@pytest.mark.parametrize("size", [(1280, 720), (1080, 1920), (1080, 1080)])
@pytest.mark.parametrize("style", STYLE_NAMES)
def test_hud_draws(size, style):
    for detail in DETAILS:
        hud = HudRenderer(style, detail)
        fr = np.zeros((size[1], size[0], 3), np.uint8)
        draw_on_rgb(hud, fr, sample_tel(), (0.2, 0, 0.6, 1) if size[1] > size[0] else (0, 0, 1, 1))
        assert fr.mean() > 1.0          # something visible was drawn
        draw_on_rgb(hud, fr, Telemetry())   # empty data must not crash
        tel = sample_tel()
        tel.countdown = 2.4
        draw_on_rgb(hud, fr, tel)


def test_recording_has_hud(tmp_path):
    rec = Recorder()
    rec.hud = HudRenderer()
    path = rec.start(str(tmp_path), "16:9", 720, 30, 23, (1280, 720))
    frame = np.zeros((720, 1280, 3), np.uint8)
    for i in range(30):
        rec.push(frame, t=i / 30, hud=sample_tel())
    info = rec.stop()
    assert info.frames >= 30 and rec.error is None
    cap = cv2.VideoCapture(path)
    ok, f = cap.read()
    cap.release()
    assert ok and f.mean() > 1.0        # black input + HUD overlay => non-black video
