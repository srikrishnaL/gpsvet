"""Inject known spoofing and tampering patterns into a clean track.

Each attack takes a clean track, a start index and a length, and returns the
attacked track plus a per-fix label (True where the fix is spoofed). They
model two kinds of attacker:

- RF spoofing: a transmitter overpowers the real satellites. The receiver's
  positions and Doppler velocity stay consistent with each other, but every
  satellite now arrives from one antenna.
- Software tampering: a mock-location app or an edited log changes the
  coordinates after the receiver produced them, usually leaving the
  receiver's own velocity and signal data behind.
"""

from __future__ import annotations

import math
import random
from dataclasses import replace
from typing import Callable, List, Optional, Sequence, Tuple

from .geo import from_enu, speed_course, to_enu, velocity_enu
from .model import Fix

Attacked = Tuple[List[Fix], List[bool]]


def _labels(n: int, start: int, length: int) -> List[bool]:
    return [start <= i < start + length for i in range(n)]


def _shift(f: Fix, east: float, north: float) -> Fix:
    lat, lon = from_enu(east, north, f.lat, f.lon)
    return replace(f, lat=round(lat, 7), lon=round(lon, 7))


def _one_transmitter(f: Fix, rng: random.Random, level: float = 46.0) -> Fix:
    if not f.cn0:
        return f  # the source does not log signal strength
    return replace(f, cn0=tuple(round(level + rng.gauss(0, 0.6), 1) for _ in f.cn0))


def teleport(fixes: Sequence[Fix], start: int, length: int, rng: random.Random,
             distance_m: Optional[float] = None) -> Attacked:
    """Software: the reported location jumps somewhere else and moves on from there."""
    d = distance_m if distance_m is not None else rng.uniform(500, 20_000)
    ang = rng.uniform(0, 2 * math.pi)
    out = list(fixes)
    for i in range(start, min(len(out), start + length)):
        out[i] = _shift(out[i], d * math.sin(ang), d * math.cos(ang))
    return out, _labels(len(out), start, length)


def carry_off(fixes: Sequence[Fix], start: int, length: int, rng: random.Random,
              accel: float = 0.02, max_rate: float = 3.0) -> Attacked:
    """RF: a spoofer captures the receiver, then slowly pulls it off course.

    The false velocity ramps up at ``accel`` m/s^2 to ``max_rate`` m/s, and
    the receiver's Doppler velocity follows it, so positions and velocity
    agree. Only the signal pattern gives it away.
    """
    ang = rng.uniform(0, 2 * math.pi)
    ue, un = math.sin(ang), math.cos(ang)
    ramp = max_rate / accel  # seconds until the false velocity stops growing
    out = list(fixes)
    t0 = fixes[start].t
    for i in range(start, min(len(out), start + length)):
        f = out[i]
        tau = f.t - t0
        if tau < ramp:
            rate, off = accel * tau, 0.5 * accel * tau * tau
        else:
            rate, off = max_rate, 0.5 * accel * ramp * ramp + max_rate * (tau - ramp)
        f = _shift(f, off * ue, off * un)
        if f.speed is not None and f.course is not None:
            ve, vn = velocity_enu(f.speed, f.course)
            sp, co = speed_course(ve + rate * ue, vn + rate * un)
            f = replace(f, speed=round(sp, 2), course=round(co, 1))
        out[i] = _one_transmitter(f, rng)
    return out, _labels(len(out), start, length)


def drift(fixes: Sequence[Fix], start: int, length: int, rng: random.Random,
          rate: float = 2.0) -> Attacked:
    """Software: coordinates are nudged away at ``rate`` m/s; velocity and signals are untouched."""
    ang = rng.uniform(0, 2 * math.pi)
    out = list(fixes)
    t0 = fixes[start].t
    for i in range(start, min(len(out), start + length)):
        off = rate * (out[i].t - t0)
        out[i] = _shift(out[i], off * math.sin(ang), off * math.cos(ang))
    return out, _labels(len(out), start, length)


def freeze(fixes: Sequence[Fix], start: int, length: int, rng: random.Random) -> Attacked:
    """Software: the location is held at one point while the device keeps moving."""
    out = list(fixes)
    hold = fixes[start]
    for i in range(start, min(len(out), start + length)):
        out[i] = replace(out[i], lat=hold.lat, lon=hold.lon)
    return out, _labels(len(out), start, length)


def replay(fixes: Sequence[Fix], start: int, length: int, rng: random.Random) -> Attacked:
    """Software: an earlier stretch of the same track is played back with fresh timestamps."""
    src = max(0, start - length - rng.randint(60, 300))
    out = list(fixes)
    for k in range(length):
        i = start + k
        if i >= len(out):
            break
        old = fixes[src + k]
        out[i] = replace(old, t=out[i].t)
    return out, _labels(len(out), start, length)


def simulator(fixes: Sequence[Fix], start: int, length: int, rng: random.Random) -> Attacked:
    """RF: a GPS simulator takes over with a perfect, noise-free path from the current spot."""
    out = list(fixes)
    f0 = fixes[start]
    speed = max(3.0, f0.speed or 0.0)
    heading = f0.course if f0.course is not None else rng.uniform(0, 360)
    e = n = 0.0
    for k in range(length):
        i = start + k
        if i >= len(out):
            break
        hd = heading + 15 * math.sin(k / 120)
        if k:
            dt = out[i].t - out[i - 1].t
            e += speed * dt * math.sin(math.radians(hd))
            n += speed * dt * math.cos(math.radians(hd))
        lat, lon = from_enu(e, n, f0.lat, f0.lon)
        f = replace(out[i], lat=round(lat, 7), lon=round(lon, 7), speed=round(speed, 2),
                    course=round(hd % 360, 1), alt=f0.alt, hdop=0.8)
        out[i] = _one_transmitter(f, rng)
    return out, _labels(len(out), start, length)


def time_shift(fixes: Sequence[Fix], start: int, length: int, rng: random.Random,
               seconds: float = 300.0) -> Attacked:
    """Software: timestamps in a stretch of a log are moved back to fake an alibi."""
    out = list(fixes)
    for i in range(start, min(len(out), start + length)):
        out[i] = replace(out[i], t=out[i].t - seconds)
    return out, _labels(len(out), start, length)


ATTACKS: dict[str, Callable[..., Attacked]] = {
    "teleport": teleport,
    "replay": replay,
    "freeze": freeze,
    "drift": drift,
    "time_shift": time_shift,
    "carry_off": carry_off,
    "simulator": simulator,
}


def strip_signals(fixes: Sequence[Fix]) -> List[Fix]:
    """Drop per-satellite C/N0, for sources that do not log it."""
    return [replace(f, cn0=None) for f in fixes]
