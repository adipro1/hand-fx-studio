"""Catalogue of stylised filters (ids must match rendering/shaders/filters.glsl)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FilterMode:
    name: str
    shader_id: int
    c1: tuple = (1.0, 1.0, 1.0)
    c2: tuple = (1.0, 1.0, 1.0)
    outline: tuple = (1.0, 1.0, 1.0)
    stepped: bool = False
    cell: float = 7.0


BLUE = (0.10, 0.22, 1.00)
MAGENTA = (1.00, 0.12, 0.86)
CYAN = (0.20, 0.95, 0.90)
NAVY = (0.02, 0.05, 0.28)
HOT_PINK = (1.00, 0.30, 0.65)

FILTERS: list[FilterMode] = [
    FilterMode("Duotone Halftone", 0, BLUE, MAGENTA, (1, 1, 1)),
    FilterMode("Pixel Mosaic", 1, outline=HOT_PINK, stepped=True, cell=9.0),
    FilterMode("Negative", 2, (0.4, 0.8, 1.0), outline=HOT_PINK),
    FilterMode("Thermal", 3, outline=(1, 1, 1)),
    FilterMode("Rainbow Heat", 4, outline=(1, 1, 1)),
    FilterMode("Edge Sketch", 5, (1, 1, 1), outline=(1, 1, 1)),
    FilterMode("Scanline Glitch", 6, NAVY, CYAN, outline=CYAN),
    FilterMode("Cyan Dots", 7, c2=CYAN, outline=(1, 1, 1), cell=6.0),
    FilterMode("Magenta Dots", 7, c2=MAGENTA, outline=(1, 1, 1), cell=6.0),
    FilterMode("Dream Blur", 8, outline=(1, 1, 1), cell=6.0),
    FilterMode("Pop Art", 9, outline=(1, 0.9, 0.2)),
    FilterMode("Glass", 10, (0.78, 0.86, 1.0), outline=(1, 1, 1)),
    FilterMode("X-Ray", 11, (0.45, 0.8, 1.0), outline=(0.6, 0.9, 1.0)),
    FilterMode("LED Matrix", 12, outline=(0.3, 1.0, 0.5), cell=8.0),
    FilterMode("RGB Glitch", 13, outline=(1, 1, 1)),
    FilterMode("Mirror World", 14, outline=(1, 1, 1)),
]

FILTER_NAMES = tuple(f.name for f in FILTERS)


def by_name(name: str) -> FilterMode:
    for f in FILTERS:
        if f.name == name:
            return f
    return FILTERS[0]


def index_of(name: str) -> int:
    for i, f in enumerate(FILTERS):
        if f.name == name:
            return i
    return 0
