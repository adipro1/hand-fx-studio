from core.engine import Engine
from effects.presets import PRESETS


def test_presets_reference_existing_effects_and_params():
    e = Engine(None)
    ids = {x.id for x in e.effects}
    for name, p in PRESETS.items():
        for eid, params in p["effects"].items():
            assert eid in ids, f"{name}: unknown effect {eid}"
            eff = e.effect(eid)
            for k in params:
                assert k in eff.params, f"{name}: {eid} has no param {k}"


def test_apply_preset_enables_only_listed():
    e = Engine(None)
    e.apply_preset("Portal")
    assert {x.id for x in e.active_effects()} == set(PRESETS["Portal"]["effects"])


def test_effect_params_roundtrip():
    e = Engine(None)
    ff = e.effect("filter_frame")
    ff.set_param("cell", 999)          # clamped to max
    assert ff.p("cell") == 24.0
    d = ff.to_dict()
    ff.reset_params()
    ff.load_dict(d)
    assert ff.p("cell") == 24.0
