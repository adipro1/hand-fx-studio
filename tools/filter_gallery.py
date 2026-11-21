"""Developer tool: render every region filter on an image into a gallery sheet."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from rendering import filter_modes as fm  # noqa: E402
from rendering.renderer import Renderer  # noqa: E402
from rendering.shader_manager import vec_array  # noqa: E402


def main(src: str, out: str):
    img = cv2.imread(src)
    h, w = img.shape[:2]
    r = Renderer(w, h)
    r.bloom = 0.0
    r.vignette = 0.0
    quad = np.array([[0.22, 0.18], [0.80, 0.12], [0.75, 0.88], [0.27, 0.80]], dtype="f4")

    class Pass:
        uses_image, uses_overlay = True, False

        def __init__(self, m):
            self.m = m

        def render_image(self, rr, ctx):
            m = self.m
            rr.image_pass("region.frag", {
                "u_poly": vec_array(quad, 8), "u_n": 4, "u_mode": m.shader_id, "u_amount": 0.6,
                "u_cell": m.cell * h / 720, "u_c1": m.c1, "u_c2": m.c2, "u_mix": 1.0,
                "u_outline_col": m.outline, "u_outline_w": 2.5 * h / 720,
                "u_stepped": int(m.stepped), "u_refract": 0.0, "u_chroma": 0.0,
                "u_outside_dim": 0.0, "u_outside_tint": (1, 1, 1), "u_outside_tint_amt": 0.0,
                "u_centroid": tuple(quad.mean(0))})

    tiles = []
    for m in fm.FILTERS:
        o = r.render(img, [Pass(m)], None)
        t = cv2.resize(cv2.cvtColor(o, cv2.COLOR_RGB2BGR), (480, int(480 * h / w)))
        cv2.putText(t, m.name, (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
        tiles.append(t)
    rows = [np.hstack(tiles[i:i + 4]) for i in range(0, len(tiles), 4)]
    cv2.imwrite(out, np.vstack(rows))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
