"""Signal smoothing filters used by the hand tracker.

The One Euro Filter (Casiez et al., 2012) is the standard choice for
interactive tracking: it smooths heavily when the hand is still (removing
jitter) and lightly when the hand moves fast (keeping latency low).
"""
from __future__ import annotations

import math

import numpy as np


def _alpha(cutoff: float, dt: float) -> float:
    tau = 1.0 / (2.0 * math.pi * cutoff)
    return 1.0 / (1.0 + tau / dt)


class OneEuroFilter:
    """Vectorised One Euro filter. Works on numpy arrays of any shape."""

    def __init__(self, min_cutoff: float = 1.2, beta: float = 0.03, d_cutoff: float = 1.0):
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.d_cutoff = d_cutoff
        self._x: np.ndarray | None = None
        self._dx: np.ndarray | None = None
        self._t: float | None = None

    def reset(self) -> None:
        self._x = None
        self._dx = None
        self._t = None

    def __call__(self, x: np.ndarray, t: float) -> np.ndarray:
        x = np.asarray(x, dtype=np.float64)
        if self._x is None or self._t is None or self._x.shape != x.shape:
            self._x = x.copy()
            self._dx = np.zeros_like(x)
            self._t = t
            return x.copy()
        dt = max(t - self._t, 1e-4)
        self._t = t
        dx = (x - self._x) / dt
        a_d = _alpha(self.d_cutoff, dt)
        self._dx = a_d * dx + (1.0 - a_d) * self._dx
        speed = np.abs(self._dx)
        cutoff = self.min_cutoff + self.beta * speed
        tau = 1.0 / (2.0 * math.pi * cutoff)
        a = 1.0 / (1.0 + tau / dt)
        self._x = a * x + (1.0 - a) * self._x
        return self._x.copy()


class ExpSmoother:
    """Simple frame-rate independent exponential smoother for scalars/arrays."""

    def __init__(self, half_life: float = 0.08, value=0.0):
        self.half_life = half_life
        self.value = value

    def update(self, target, dt: float):
        if self.half_life <= 0:
            self.value = target
            return self.value
        k = 1.0 - 0.5 ** (dt / self.half_life)
        self.value = self.value + (target - self.value) * k
        return self.value
