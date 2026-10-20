"""Realistic clean tracks for testing and benchmarking.

Motion follows a speed target with limited acceleration and a wandering
heading, with stops for the car mode. Position error is a first-order
Gauss-Markov process (slowly wandering, like real GNSS error), with rare
one- or two-fix multipath outliers so false-alarm numbers stay honest.
"""

from __future__ import annotations

import math
import random
from typing import List, Optional

from .geo import from_enu
from .model import Fix

MODES = {
    # cruise speed (mean, sd) m/s, max accel m/s^2, noise sigma m, turn rate sd deg/s, stops
    "walk": dict(speed=(1.4, 0.25), accel=0.5, sigma=3.0, turn=4.0, stops=False),
    "bike": dict(speed=(5.0, 1.2), accel=1.0, sigma=3.0, turn=3.0, stops=True),
    "car": dict(speed=(14.0, 6.0), accel=2.5, sigma=2.5, turn=1.5, stops=True),
    "drone": dict(speed=(10.0, 3.0), accel=3.0, sigma=1.5, turn=2.0, stops=False),
}


class _GaussMarkov:
    def __init__(self, rng: random.Random, sigma: float, tau: float):
        self.rng, self.sigma, self.a = rng, sigma, math.exp(-1.0 / tau)
        self.x = rng.gauss(0, sigma)

    def step(self) -> float:
        self.x = self.a * self.x + math.sqrt(1 - self.a ** 2) * self.sigma * self.rng.gauss(0, 1)
        return self.x


def clean_track(
    mode: str = "car",
    minutes: float = 30,
    rng: Optional[random.Random] = None,
    start: tuple[float, float] = (40.7128, -74.0060),
    t0: float = 1_760_000_000,
    glitch_rate: float = 1 / 900,
) -> List[Fix]:
    """A 1 Hz track with speed, course, altitude, HDOP and per-satellite C/N0."""
    rng = rng or random.Random()
    m = MODES[mode]
    lat0, lon0 = start
    e = n = 0.0
    heading = rng.uniform(0, 360)
    speed = 0.0
    target = max(0.5, rng.gauss(*m["speed"]))
    hold = rng.uniform(30, 120)
    alt_true = 30.0 + (40.0 if mode == "drone" else 0.0)
    climb = 0.0
    ne, nn = _GaussMarkov(rng, m["sigma"], 30), _GaussMarkov(rng, m["sigma"], 30)
    na = _GaussMarkov(rng, 4.0, 60)
    hdop = _GaussMarkov(rng, 0.2, 120)
    sats = [rng.uniform(25, 48) for _ in range(rng.randint(7, 12))]
    glitch_left, glitch = 0, (0.0, 0.0)
    fixes = []
    for k in range(int(minutes * 60)):
        hold -= 1
        if hold <= 0:
            if m["stops"] and rng.random() < 0.25:
                target, hold = 0.0, rng.uniform(15, 60)
            else:
                target, hold = max(0.5, rng.gauss(*m["speed"])), rng.uniform(30, 180)
            if mode == "drone":
                climb = rng.choice([0.0, 0.0, rng.uniform(-2, 2)])
        speed += max(-m["accel"], min(m["accel"], target - speed))
        if speed > 0.3:
            heading = (heading + rng.gauss(0, m["turn"])) % 360
        e += speed * math.sin(math.radians(heading))
        n += speed * math.cos(math.radians(heading))
        alt_true = max(5.0, alt_true + climb)

        if glitch_left == 0 and rng.random() < glitch_rate:
            glitch_left = rng.choice([1, 1, 2])
            ang, dist = rng.uniform(0, 2 * math.pi), rng.uniform(30, 120)
            glitch = (dist * math.sin(ang), dist * math.cos(ang))
        ge, gn = glitch if glitch_left else (0.0, 0.0)
        glitch_left = max(0, glitch_left - 1)

        lat, lon = from_enu(e + ne.step() + ge, n + nn.step() + gn, lat0, lon0)
        rep_speed = max(0.0, speed + rng.gauss(0, 0.1))
        course_sd = 2.0 if speed > 3 else 10.0 if speed > 0.5 else 60.0
        cn0 = tuple(round(min(55.0, max(15.0, s + rng.gauss(0, 1.0))), 1) for s in sats)
        fixes.append(Fix(
            lat=round(lat, 7), lon=round(lon, 7), t=t0 + k,
            speed=round(rep_speed, 2), course=round((heading + rng.gauss(0, course_sd)) % 360, 1),
            alt=round(alt_true + na.step(), 1), hdop=round(min(3.0, max(0.6, 1.0 + hdop.step())), 1),
            cn0=cn0,
        ))
        if rng.random() < 0.01:  # satellites rise and set
            sats[rng.randrange(len(sats))] = rng.uniform(25, 48)
    return fixes
