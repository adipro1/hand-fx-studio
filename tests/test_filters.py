import numpy as np

from core.filters import ExpSmoother, OneEuroFilter


def test_one_euro_reduces_jitter():
    rng = np.random.default_rng(0)
    f = OneEuroFilter(min_cutoff=1.0, beta=0.0)
    raw, out = [], []
    for i in range(300):
        x = np.array([0.5 + rng.normal(0, 0.01)])
        raw.append(x[0])
        out.append(f(x, i / 30.0)[0])
    assert np.std(out[50:]) < np.std(raw[50:]) * 0.5


def test_one_euro_follows_fast_motion():
    f = OneEuroFilter(min_cutoff=1.0, beta=0.5)
    for i in range(60):
        y = f(np.array([i * 0.02]), i / 30.0)
    assert abs(y[0] - 59 * 0.02) < 0.05


def test_exp_smoother_converges():
    s = ExpSmoother(0.05, 0.0)
    for _ in range(100):
        s.update(1.0, 1 / 60)
    assert abs(s.value - 1.0) < 1e-3
