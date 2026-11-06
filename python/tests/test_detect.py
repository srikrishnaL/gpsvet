import random
from dataclasses import replace

import pytest

from gpsvet import ATTACKS, Fix, clean_track, detect
from gpsvet.attacks import strip_signals


@pytest.fixture(scope="module")
def tracks():
    rng = random.Random(42)
    return {mode: [clean_track(mode, 20, rng) for _ in range(4)] for mode in ("walk", "bike", "car")}


def test_clean_tracks_are_not_flagged(tracks):
    for mode, ts in tracks.items():
        for t in ts:
            assert not detect(t, mode).spoofed, mode


@pytest.mark.parametrize("attack", sorted(ATTACKS))
def test_every_attack_is_caught_inside_its_window(tracks, attack):
    rng = random.Random(attack)
    for mode, ts in tracks.items():
        fixes, labels = ATTACKS[attack](ts[0], 300, 300, rng)
        rep = detect(fixes, mode)
        assert any(labels[i] for i in rep.suspicious()), (attack, mode)


def test_signal_free_carry_off_is_a_known_blind_spot(tracks):
    # Positions and velocity agree, and there is no signal data: nothing to see.
    # (The snap back when the attack ends is caught, but only after the fact.)
    fixes, labels = ATTACKS["carry_off"](strip_signals(tracks["car"][0]), 300, 300, random.Random(1))
    assert not any(labels[i] for i in detect(fixes, "car").suspicious())


def test_multipath_glitch_is_not_spoofing(tracks):
    t = list(tracks["car"][1])
    t[500] = replace(t[500], lat=t[500].lat + 0.0008)  # ~90 m sideways for one fix
    rep = detect(t, "car")
    assert not rep.spoofed
    assert any(f.check == "glitch" and f.index == 500 for f in rep.flags)


def test_first_fix_outlier_is_a_glitch_not_a_jump(tracks):
    t = list(tracks["walk"][0])
    t[0] = replace(t[0], lat=t[0].lat + 0.001)
    rep = detect(t, "walk")
    assert [f.check for f in rep.flags if f.index in (0, 1)] == ["glitch"]


def test_time_reversal():
    fixes = [Fix(0, 0, 10), Fix(0, 0.00001, 11), Fix(0, 0.00002, 5)]
    rep = detect(fixes, "walk")
    assert rep.spoofed and rep.flags[0].check == "time"


def test_positions_only_still_runs_physics_checks():
    fixes = [Fix(52.0, 4.0 + i * 0.00002, 1000 + i) for i in range(50)]
    assert not detect(fixes, "walk").spoofed
    fixes[25:] = [replace(f, lon=f.lon + 0.5) for f in fixes[25:]]  # 34 km jump
    rep = detect(fixes, "walk")
    assert rep.spoofed
    assert rep.events()[0].start == 25


def test_weak_signals_combine():
    # Identical C/N0 alone sits at the threshold; with abnormal strength it is clear.
    f = Fix(0, 0, 0, cn0=(45.0, 45.2, 44.9, 45.1, 45.0))
    assert detect([f], "car").score == pytest.approx(0.5)
    f = replace(f, cn0=tuple(x + 10 for x in f.cn0))
    assert detect([f], "car").score == pytest.approx(1 - 0.5 * 0.65)


def test_empty_and_single_fix():
    assert detect([], "car").score == 0
    assert detect([Fix(1, 2, 3)], "car").score == 0


def test_unknown_profile():
    with pytest.raises(ValueError):
        detect([], "rocket")


def test_report_dict_and_events(tracks):
    fixes, _ = ATTACKS["teleport"](tracks["bike"][0], 400, 200, random.Random(3))
    d = detect(fixes, "bike").to_dict()
    assert d["spoofed"] and d["events"]
    assert "jump" in d["events"][0]["checks"]
