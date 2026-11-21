"""Effect registry. Add new effects to EFFECT_CLASSES to make them appear in the app."""
from __future__ import annotations

import importlib

# (module, class) — imported lazily so one broken module can't break the app
EFFECT_CLASSES = [
    ("effects.frames", "FilterFrameEffect"),
    ("effects.frames", "FingerBandsEffect"),
    ("effects.frames", "GlassPrismEffect"),
    ("effects.skeleton", "SkeletonEffect"),
    ("effects.skeleton", "HandLinkEffect"),
    ("effects.distortion", "LiquidWarpEffect"),
    ("effects.distortion", "FingerLensEffect"),
    ("effects.distortion", "ShockwaveEffect"),
    ("effects.distortion", "KaleidoscopeEffect"),
    ("effects.portals", "PortalEffect"),
    ("effects.colour", "ColourEffect"),
    ("effects.particles", "ParticlesEffect"),
    ("effects.energy", "EnergyEffect"),
    ("effects.geometry", "GeometryEffect"),
]


def create_effects():
    out = []
    for mod, cls in EFFECT_CLASSES:
        try:
            out.append(getattr(importlib.import_module(mod), cls)())
        except (ImportError, AttributeError) as exc:
            print(f"[effects] skipped {mod}.{cls}: {exc}")
    return out
