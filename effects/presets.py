"""Curated effect combinations. Each preset lists enabled effects and parameter overrides."""
from __future__ import annotations

PRESETS: dict[str, dict] = {
    "Filter Frame": {
        "desc": "Reference 02 — L-frame lens with stylised filters. Close the frame to switch.",
        "effects": {"filter_frame": {}, "skeleton": {"style": "Minimal", "trails": False, "opacity": 0.5}},
    },
    "Pin Studio": {
        "desc": "Build a collage of filter windows: hold a frame still (or quick-pinch) to pin it, "
                "pinch inside to move, point to change its filter, two fists to clear.",
        "effects": {"filter_frame": {"filter": "Thermal", "shuffle": True},
                    "skeleton": {"style": "Minimal", "trails": False, "opacity": 0.5}},
    },
    "Finger Bands": {
        "desc": "Reference 03 — layered reality strips between matching fingertips.",
        "effects": {"finger_bands": {}, "skeleton": {"style": "Minimal", "trails": False, "opacity": 0.35}},
        "render": {"dim": 0.15},
    },
    "Glass Prism": {
        "desc": "Reference 01 — a glass slab with echoes and refraction.",
        "effects": {"glass_prism": {}},
        "render": {"bloom": 0.6},
    },
    "Tracking HUD": {
        "desc": "Reference 04 — classic skeleton, hand links and a pixel lens.",
        "effects": {"skeleton": {"style": "Classic", "trails": False, "pulses": False, "glow": 0.0},
                    "hand_link": {},
                    "filter_frame": {"filter": "Pixel Mosaic", "outline": 0.0, "corners": False,
                                     "edge_glow": 0.0, "pinch_cycle": True}},
        "render": {"bloom": 0.2},
    },
    "Reality Bender": {
        "desc": "Liquid space: drag the world with your fingertips, pinch to magnify.",
        "effects": {"liquid_warp": {}, "finger_lens": {}, "shockwave": {},
                    "skeleton": {"style": "Neon", "opacity": 0.55, "joint_size": 2.5, "line_width": 1.5}},
    },
    "Energy Master": {
        "desc": "Lightning between fingertips, orbs in your pinch, shockwaves from your fists.",
        "effects": {"energy": {}, "particles": {"mode": "Sparks"}, "shockwave": {},
                    "skeleton": {"style": "Neon", "opacity": 0.6}},
        "render": {"dim": 0.35, "bloom": 1.1},
    },
    "Portal": {
        "desc": "Open a vortex between your hands. Spread them to grow it.",
        "effects": {"portal": {}, "particles": {"mode": "Vortex", "count": 2500},
                    "skeleton": {"style": "Hologram", "opacity": 0.5}},
        "render": {"dim": 0.2, "bloom": 1.0},
    },
    "Sacred Geometry": {
        "desc": "Fingertips spawn rotating geometric structures.",
        "effects": {"geometry": {}, "skeleton": {"style": "Minimal", "opacity": 0.5}},
        "render": {"dim": 0.45, "bloom": 1.0},
    },
    "Psychedelic": {
        "desc": "Kaleidoscope + flowing colour, steered by your hands.",
        "effects": {"kaleidoscope": {}, "colour": {"flow": 0.55}, "liquid_warp": {"strength": 0.6},
                    "particles": {"mode": "Stardust", "count": 1500}},
        "render": {"bloom": 0.9},
    },
    "Neon Particles": {
        "desc": "Fingertips emit glowing particles; open palm repels, fist explodes.",
        "effects": {"particles": {}, "skeleton": {"style": "Neon", "opacity": 0.5, "trails": True}},
        "render": {"dim": 0.4, "bloom": 1.0},
    },
    "Total Chaos": {
        "desc": "Everything at once — filters, energy, particles, distortion.",
        "effects": {"filter_frame": {"filter": "Rainbow Heat"}, "liquid_warp": {"strength": 0.7},
                    "energy": {"lightning": True}, "particles": {"count": 2500},
                    "skeleton": {"style": "Plasma"}, "shockwave": {}},
        "render": {"bloom": 1.0},
    },
    "Clean Camera": {
        "desc": "No effects — just the webcam with hand tracking hidden.",
        "effects": {},
    },
}

PRESET_NAMES = list(PRESETS.keys())
