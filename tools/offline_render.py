"""Developer tool: run the full pipeline (tracking -> gestures -> effects -> GPU)
on a video file instead of the webcam and save a contact sheet / MP4.

Used for testing effects reproducibly. Example:

    python tools/offline_render.py input.mp4 --preset "Filter Frame" --sheet out.jpg
    python tools/offline_render.py input.mp4 --effects filter_frame,skeleton --mp4 out.mp4
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from core.engine import Engine  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--preset", default=None)
    ap.add_argument("--effects", default=None, help="comma separated effect ids")
    ap.add_argument("--params", default="", help="effect.param=value;...")
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--end", type=int, default=10 ** 9)
    ap.add_argument("--crop", default=None, help="y0,y1,x0,x1")
    ap.add_argument("--sheet", default=None)
    ap.add_argument("--frames", type=int, default=12)
    ap.add_argument("--mp4", default=None)
    ap.add_argument("--no-mirror", action="store_true")
    args = ap.parse_args()

    cap = cv2.VideoCapture(args.video)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    end = min(args.end, n)
    engine = Engine(None)
    engine.start_offline()
    if args.preset:
        engine.apply_preset(args.preset)
    if args.effects:
        for e in engine.effects:
            e.enabled = e.id in args.effects.split(",")
    for item in filter(None, args.params.split(";")):
        k, v = item.split("=")
        eid, pk = k.split(".")
        eff = engine.effect(eid)
        spec = next(p for p in eff.PARAMS if p.key == pk)
        val = {"float": float, "int": int, "bool": lambda s: s.lower() in ("1", "true"),
               }.get(spec.kind, str)(v)
        eff.set_param(pk, val)

    want = set(np.linspace(args.start, end - 1, args.frames).astype(int).tolist())
    thumbs = []
    writer = None
    cap.set(cv2.CAP_PROP_POS_FRAMES, args.start)
    for i in range(args.start, end):
        ok, f = cap.read()
        if not ok:
            break
        if args.crop:
            y0, y1, x0, x1 = map(int, args.crop.split(","))
            f = f[y0:y1, x0:x1]
        f = np.ascontiguousarray(f)
        out_rgb = engine.process_frame(f, i / fps, i)
        bgr = cv2.cvtColor(out_rgb, cv2.COLOR_RGB2BGR)
        if args.mp4:
            if writer is None:
                writer = cv2.VideoWriter(args.mp4, cv2.VideoWriter_fourcc(*"mp4v"), fps,
                                         (bgr.shape[1], bgr.shape[0]))
            writer.write(bgr)
        if i in want:
            t = cv2.resize(bgr, (int(bgr.shape[1] * 300 / bgr.shape[0]), 300))
            cv2.putText(t, str(i), (6, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
            thumbs.append(t)
    if writer:
        writer.release()
    if args.sheet and thumbs:
        cols = 4
        rows = [thumbs[r:r + cols] for r in range(0, len(thumbs), cols)]
        rows = [np.hstack(r + [np.zeros_like(thumbs[0])] * (cols - len(r))) for r in rows]
        cv2.imwrite(args.sheet, np.vstack(rows))
    print("errors:", {e.id: e.error for e in engine.effects if e.error})
    print(f"avg gpu ms {engine.stats['render_ms']:.1f}, effects update ms {engine.stats['update_ms']:.1f}")


if __name__ == "__main__":
    main()
