"""GPU pipeline smoke tests."""
import numpy as np
import pytest

from core.gesture_recognition import GestureFrame
from core.hand_tracker import TrackingResult
from effects import create_effects
from effects.base_effect import FrameContext
from rendering import filter_modes as fm


@pytest.fixture(scope="module")
def renderer():
    from rendering.renderer import Renderer
    try:
        r = Renderer(320, 180)
    except RuntimeError as exc:
        pytest.skip(f"No OpenGL 3.3: {exc}")
    yield r
    r.release()


def _ctx(img, t=0.0):
    tr = TrackingResult([], t, 0, image=img)
    return FrameContext(t, 1 / 30, tr, GestureFrame({}, [], {}, tr), [], img.shape[1], img.shape[0])


def test_all_effects_render_without_hands(renderer):
    img = (np.random.default_rng(1).random((180, 320, 3)) * 255).astype(np.uint8)
    effects = create_effects()
    assert len(effects) >= 14
    for e in effects:
        e.enabled = True
    for i in range(3):
        ctx = _ctx(img, i / 30)
        for e in effects:
            e.ensure_gpu(renderer)
            e.update(ctx)
        out = renderer.render(img, effects, ctx)
        assert out.shape == (180, 320, 3)
    assert {e.id: e.error for e in effects if e.error} == {}


def test_base_pass_preserves_image_orientation(renderer):
    img = np.zeros((180, 320, 3), np.uint8)
    img[:, :160] = (0, 0, 255)      # BGR red on the left half
    img[:20, :] = (255, 255, 255)   # white strip at the top
    renderer.bloom = 0.0
    renderer.vignette = 0.0
    out = renderer.render(img, [], _ctx(img))
    assert out[90, 40, 0] > 200 and out[90, 40, 2] < 30   # output is RGB
    assert out[90, 280].max() < 30
    assert out[5, 200].min() > 200                       # not flipped vertically
    renderer.vignette = 0.15
    renderer.bloom = 0.8


def test_filter_ids_unique_names():
    assert all(0 <= f.shader_id <= 15 for f in fm.FILTERS)
    assert len(fm.FILTER_NAMES) == len(set(fm.FILTER_NAMES))


def test_canvas_draws_overlay(renderer):
    img = np.zeros((180, 320, 3), np.uint8)

    class Dot:
        uses_image, uses_overlay = False, True

        def draw(self, canvas, ctx):
            canvas.circle((0.5, 0.5), 20, (1.0, 1.0, 1.0), glow=0.0)

    out = renderer.render(img, [Dot()], _ctx(img))
    assert out[90, 160].min() > 200
    assert out[10, 10].max() < 20
