"""Maps held gestures to application actions (switch preset, next filter, ...).

Bindings require the gesture to be *held* for a short time and have a
cooldown, so normal hand movement never triggers them by accident.
"""
from __future__ import annotations

from dataclasses import dataclass

ACTIONS = {
    "none": "Do nothing",
    "next_preset": "Next preset",
    "prev_preset": "Previous preset",
    "next_filter": "Next frame filter",
    "screenshot": "Take screenshot",
    "toggle_record": "Start / stop recording",
    "reset_effects": "Clear particles & trails",
}


@dataclass
class Binding:
    gesture: str
    action: str
    hold: float = 1.0          # seconds the gesture must be held
    two_hands: bool = False    # require both hands to show the gesture


DEFAULT_BINDINGS = [
    Binding("thumbs_up", "next_preset", 1.2),
    Binding("rock", "next_filter", 0.8),
    Binding("ok", "none", 1.0),
    Binding("three", "none", 1.0),
]


class InteractionManager:
    def __init__(self, engine, bindings: list[Binding] | None = None, enabled: bool = True):
        self.engine = engine
        self.bindings = bindings if bindings is not None else [Binding(**b.__dict__) for b in DEFAULT_BINDINGS]
        self.enabled = enabled
        self.cooldown = 1.2
        self._last_fire: dict[str, float] = {}
        self._fired_hold: set[tuple[int, str]] = set()
        self.last_action: tuple[float, str] | None = None
        self.progress: dict[str, float] = {}   # binding gesture -> 0..1 hold progress (for UI)

    def update(self, ctx) -> list[str]:
        fired = []
        self.progress = {}
        if not self.enabled:
            return fired
        for b in self.bindings:
            if b.action == "none":
                continue
            holders = [g for g in ctx.gestures.hands.values() if g.gesture == b.gesture]
            if b.two_hands and len(holders) < 2:
                continue
            for g in holders:
                key = (g.hand_id, b.gesture)
                self.progress[b.gesture] = max(self.progress.get(b.gesture, 0.0), min(g.hold_time / b.hold, 1.0))
                if g.hold_time >= b.hold and key not in self._fired_hold:
                    if ctx.t - self._last_fire.get(b.action, -1e9) < self.cooldown:
                        continue
                    self._fired_hold.add(key)
                    self._last_fire[b.action] = ctx.t
                    fired.append(b.action)
                    self.last_action = (ctx.t, b.action)
        # re-arm when the gesture is released
        live = {(g.hand_id, g.gesture) for g in ctx.gestures.hands.values()}
        self._fired_hold &= live
        for a in fired:
            self.engine.perform_action(a)
        return fired

    def to_list(self) -> list[dict]:
        return [b.__dict__.copy() for b in self.bindings]

    def load_list(self, items: list[dict]) -> None:
        try:
            self.bindings = [Binding(**d) for d in items]
        except TypeError:
            pass
