"""Regenerate the shared test vectors from the Python reference implementation.

    PYTHONPATH=python/src python spec/vectors/generate.py

Each vector holds a track, the profile to check it with, and the exact
per-fix scores and flags the reference produces. Every language's test suite
loads these files and must reproduce them (scores within 1e-6).
"""

from __future__ import annotations

import json
import random
from dataclasses import replace
from pathlib import Path

from gpsvet import ATTACKS, Fix, clean_track, detect
from gpsvet.attacks import strip_signals

OUT = Path(__file__).parent
MINUTES = 5
START, LENGTH = 120, 120


def encode_fix(f: Fix) -> list:
    return [f.lat, f.lon, f.t, f.speed, f.course, f.alt, f.hdop, list(f.cn0) if f.cn0 else None]


def write(name: str, description: str, profile: str, fixes) -> None:
    rep = detect(fixes, profile)
    doc = {
        "name": name,
        "description": description,
        "profile": profile,
        "fields": ["lat", "lon", "t", "speed", "course", "alt", "hdop", "cn0"],
        "fixes": [encode_fix(f) for f in fixes],
        "expected": {
            "score": round(rep.score, 9),
            "spoofed": rep.spoofed,
            "scores": [round(s, 9) for s in rep.scores],
            "flags": sorted([f.index, f.check, round(f.severity, 9)] for f in rep.flags),
        },
    }
    (OUT / f"{name}.json").write_text(json.dumps(doc, separators=(",", ":")) + "\n")


def main() -> None:
    rng = random.Random(2026)
    for mode in ("walk", "bike", "car"):
        write(f"clean_{mode}", f"Clean {mode} track", mode, clean_track(mode, MINUTES, rng))

    base = clean_track("car", MINUTES, rng)
    for name, attack in ATTACKS.items():
        fixes, _ = attack(base, START, LENGTH, rng)
        write(f"attack_{name}", (attack.__doc__ or "").strip().splitlines()[0], "car", fixes)
    fixes, _ = ATTACKS["carry_off"](strip_signals(base), START, LENGTH, rng)
    write("attack_carry_off_no_signal", "RF carry-off on a source without signal data", "car", fixes)

    bike = clean_track("bike", MINUTES, rng)
    no_course = [replace(f, course=None, cn0=None) for f in bike]
    fixes, _ = ATTACKS["drift"](no_course, START, LENGTH, rng, rate=6.0)
    write("speed_without_course", "Drift on a track with speed but no course or signal data", "bike", fixes)
    positions = [Fix(f.lat, f.lon, f.t) for f in bike]
    fixes, _ = ATTACKS["teleport"](positions, START, LENGTH, rng)
    write("positions_only", "Teleport on a track with only lat, lon and time", "bike", fixes)

    drone = clean_track("drone", MINUTES, rng, glitch_rate=0)
    climb = [replace(f, alt=f.alt + 250) if i >= 200 else f for i, f in enumerate(drone)]
    write("altitude_jump", "Drone altitude jumps 250 m in one second", "drone", climb)

    walk = clean_track("walk", MINUTES, rng, glitch_rate=0)
    g = list(walk)
    g[0] = replace(g[0], lat=g[0].lat + 0.001)
    g[150] = replace(g[150], lon=g[150].lon + 0.0012)
    g[151] = replace(g[151], lon=g[151].lon + 0.0011)
    write("glitches", "First-fix outlier and a two-fix multipath glitch", "walk", g)
    stopped = [replace(f, lat=walk[0].lat, lon=walk[0].lon, speed=0.0) for f in walk[:90]]
    write("static_hold", "A parked receiver holding one position", "walk", stopped)
    times = list(walk)
    times[200] = replace(times[200], t=times[199].t)
    times[220] = replace(times[220], t=times[219].t - 30)
    write("bad_times", "A duplicate and a backwards timestamp", "walk", times)


if __name__ == "__main__":
    main()
