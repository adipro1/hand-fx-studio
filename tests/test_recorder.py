import os

import cv2
import numpy as np

from recording.recorder import Recorder, crop_rect, output_size


def test_output_sizes():
    assert output_size("9:16", 1080, 1280, 720) == (1080, 1920)
    assert output_size("Story", 720, 1280, 720) == (1080, 1920)
    assert output_size("16:9", 720, 1280, 720) == (1280, 720)
    assert output_size("1:1", 720, 1280, 720) == (720, 720)


def test_crop_follows_focus_and_stays_inside():
    x, y, w, h = crop_rect("9:16", 1280, 720, focus_x=0.0)
    assert x == 0 and h == 720 and w == 405
    x, y, w, h = crop_rect("9:16", 1280, 720, focus_x=1.0)
    assert x + w == 1280


def test_record_vertical_mp4(tmp_path):
    rec = Recorder()
    path = rec.start(str(tmp_path), "9:16", 720, 30, 23, (640, 360))
    for i in range(60):   # 2 seconds of frames at exact timestamps
        img = np.zeros((360, 640, 3), np.uint8)
        img[:, : (i * 10) % 640] = (255, 0, 128)
        rec.push(img, t=i / 30)
    info = rec.stop()
    assert rec.error is None, rec.error
    assert os.path.getsize(path) > 1000
    cap = cv2.VideoCapture(path)
    assert int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) == 720
    assert int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) == 1280
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    assert 55 <= n <= 62
    assert abs(info.frames - n) <= 2


def test_recorder_fills_gaps_for_constant_fps(tmp_path):
    rec = Recorder()
    rec.start(str(tmp_path), "16:9", 720, 30, 28, (640, 360))
    img = np.zeros((360, 640, 3), np.uint8)
    for t in (0.0, 0.5, 1.0):   # a slow renderer: only 3 frames over 1 s
        rec.push(img, t=t)
    info = rec.stop()
    assert info.frames >= 29   # duplicated to keep real-time duration
