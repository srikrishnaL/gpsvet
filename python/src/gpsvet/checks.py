"""Individual checks. Each takes the fixes and a Profile and returns Flags.

The checks look for things a real receiver moving through the real world
cannot produce: positions that move faster than the device can, a reported
velocity that disagrees with where the positions go, coordinates with no
measurement noise at all, or satellite signals that all arrive at the same
strength because they come from one transmitter. Each one alone has known
false alarms, so severities are chosen to be combined (see ``detect``).
"""

from __future__ import annotations

import math
import statistics
from typing import Callable, List, Sequence

from .geo import haversine_m, to_enu, velocity_enu
from .model import Fix, Flag, Profile

Check = Callable[[Sequence[Fix], Profile], List[Flag]]

UERE_M = 5.0  # metres of horizontal error per unit of HDOP
GLITCH_LOOKAHEAD = 3  # a multipath outlier this many fixes long or shorter is a glitch


def _accuracy(f: Fix, profile: Profile) -> float:
    return f.hdop * UERE_M if f.hdop else profile.accuracy_m


def _excess(ratio: float) -> float:
    """Severity for a value ``ratio`` times over its limit: 0.4 just over, 1.0 at 1.6x."""
    return min(1.0, 0.4 + (ratio - 1.0))


def check_time(fixes: Sequence[Fix], profile: Profile) -> List[Flag]:
    """Timestamps that go backwards, or two places at the same instant."""
    flags = []
    for i in range(1, len(fixes)):
        a, b = fixes[i - 1], fixes[i]
        dt = b.t - a.t
        if dt < 0:
            flags.append(Flag(i, "time", 1.0, f"timestamp goes back {-dt:.1f} s"))
        elif dt == 0 and (a.lat, a.lon) != (b.lat, b.lon):
            flags.append(Flag(i, "time", 0.8, "two different positions at the same time"))
    return flags


def _implied_speed(a: Fix, b: Fix, profile: Profile) -> tuple[float, float]:
    d = haversine_m(a.lat, a.lon, b.lat, b.lon)
    slack = _accuracy(a, profile) + _accuracy(b, profile)
    return max(0.0, d - slack) / (b.t - a.t), d


def check_jumps(fixes: Sequence[Fix], profile: Profile) -> List[Flag]:
    """Positions that move faster than the profile allows.

    A jump that comes back within a few fixes is a multipath glitch (common
    in cities) and gets a low severity. A jump that stays is a teleport.
    """
    flags: List[Flag] = []
    n = len(fixes)
    last = 0
    i = 1
    ok = lambda a, b: fixes[b].t > fixes[a].t and _implied_speed(fixes[a], fixes[b], profile)[0] <= profile.max_speed
    if n >= 3 and not ok(0, 1) and not ok(0, 2) and ok(1, 2):
        # The very first fix is the outlier, not the second.
        flags.append(Flag(0, "glitch", 0.25, "first fix is off the track"))
        last, i = 1, 2
    while i < n:
        if fixes[i].t <= fixes[last].t:
            i += 1
            continue
        v, d = _implied_speed(fixes[last], fixes[i], profile)
        if v <= profile.max_speed:
            last = i
            i += 1
            continue
        back = None
        for j in range(i + 1, min(n, i + 1 + GLITCH_LOOKAHEAD)):
            if ok(last, j):
                back = j
                break
        if back is not None:
            for k in range(i, back):
                flags.append(Flag(k, "glitch", 0.25, f"{d:.0f} m off the track for {back - i} fix(es), then back"))
            last = back
            i = back + 1
            continue
        dt = fixes[i].t - fixes[last].t
        flags.append(
            Flag(i, "jump", _excess(v / profile.max_speed),
                 f"moved {d:.0f} m in {dt:.1f} s ({v:.0f} m/s, limit {profile.max_speed:.0f})")
        )
        last = i
        i += 1
    return flags


def check_climb(fixes: Sequence[Fix], profile: Profile) -> List[Flag]:
    """Altitude changing faster than the profile allows."""
    flags = []
    prev = None
    for i, f in enumerate(fixes):
        if f.alt is None:
            continue
        if prev is not None and f.t > fixes[prev].t:
            slack = 1.5 * (_accuracy(f, profile) + _accuracy(fixes[prev], profile))
            dz = abs(f.alt - fixes[prev].alt)
            rate = max(0.0, dz - slack) / (f.t - fixes[prev].t)
            if rate > profile.max_climb:
                flags.append(Flag(i, "climb", _excess(rate / profile.max_climb),
                                  f"altitude changed {dz:.0f} m ({rate:.0f} m/s, limit {profile.max_climb:.0f})"))
        prev = i
    return flags


def check_accel(fixes: Sequence[Fix], profile: Profile) -> List[Flag]:
    """Reported speed changing faster than the profile allows."""
    flags = []
    for i in range(1, len(fixes)):
        a, b = fixes[i - 1], fixes[i]
        if a.speed is None or b.speed is None or b.t <= a.t:
            continue
        acc = abs(b.speed - a.speed) / (b.t - a.t)
        if acc > profile.max_accel:
            flags.append(Flag(i, "accel", _excess(acc / profile.max_accel),
                              f"speed went {a.speed:.1f} -> {b.speed:.1f} m/s ({acc:.1f} m/s², limit {profile.max_accel:.0f})"))
    return flags


def _running_median(xs: Sequence[float], radius: int) -> list[float]:
    out = []
    for i in range(len(xs)):
        out.append(statistics.median(xs[max(0, i - radius):i + radius + 1]))
    return out


def check_velocity(fixes: Sequence[Fix], profile: Profile, window_s: float = 30.0) -> List[Flag]:
    """Dead reckoning: integrate the reported velocity and compare the result
    with where the positions actually went.

    Spoofing that edits positions without touching the receiver's Doppler
    velocity (or a mock-location app that reports speed 0 while moving) makes
    the two disagree. With ``course`` the comparison is a 2-D vector; with
    only ``speed`` it can only catch positions moving farther than the speed
    allows. Short multipath glitches are removed with a running median of the
    position-minus-dead-reckoning residual before comparing.
    """
    n = len(fixes)
    if n < 3 or any(f.speed is None for f in fixes):
        return []
    use_course = all(f.course is not None for f in fixes)
    lat0, lon0 = fixes[0].lat, fixes[0].lon
    pos = [to_enu(f.lat, f.lon, lat0, lon0) for f in fixes]

    # Dead-reckoned track (east, north) and distance, as running sums.
    de, dn, dl = [0.0] * n, [0.0] * n, [0.0] * n
    for k in range(1, n):
        dt = max(0.0, fixes[k].t - fixes[k - 1].t)
        dl[k] = dl[k - 1] + (fixes[k].speed + fixes[k - 1].speed) / 2 * dt
        if use_course:
            e1, n1 = velocity_enu(fixes[k - 1].speed, fixes[k - 1].course)
            e2, n2 = velocity_enu(fixes[k].speed, fixes[k].course)
            de[k] = de[k - 1] + (e1 + e2) / 2 * dt
            dn[k] = dn[k - 1] + (n1 + n2) / 2 * dt

    if use_course:
        re_ = _running_median([p[0] - d for p, d in zip(pos, de)], 3)
        rn_ = _running_median([p[1] - d for p, d in zip(pos, dn)], 3)
    else:
        pe = _running_median([p[0] for p in pos], 3)
        pn = _running_median([p[1] for p in pos], 3)

    flags = []
    j = 0
    for i in range(1, n):
        while j < i and fixes[i].t - fixes[j].t > window_s:
            j += 1
        if j >= i or fixes[i].t - fixes[j].t < window_s / 2:
            continue
        path = dl[i] - dl[j]
        thr = 1.5 * (_accuracy(fixes[i], profile) + _accuracy(fixes[j], profile)) + 0.05 * path
        if use_course:
            err = math.hypot(re_[i] - re_[j], rn_[i] - rn_[j])
            what = f"positions drifted {err:.0f} m from where the reported velocity leads"
        else:
            err = math.hypot(pe[i] - pe[j], pn[i] - pn[j]) - path
            what = f"positions moved {err:.0f} m farther than the reported speed allows"
        if err > thr:
            sev = min(1.0, 0.3 + 0.35 * (err / thr - 1))
            flags.append(Flag(i, "velocity", sev, f"{what} over {fixes[i].t - fixes[j].t:.0f} s"))
    return flags


IDENTICAL_DEG = 1e-7


def check_frozen(fixes: Sequence[Fix], profile: Profile) -> List[Flag]:
    """The exact same coordinates fix after fix.

    A live receiver's position wanders by a metre or so even when still, so a
    long run of identical coordinates suggests a held or injected position.
    Some trackers freeze on purpose when parked ("static hold"), so a run
    alone stays below the default threshold; a run while the receiver reports
    real speed does not.
    """
    flags = []
    run_start = 0
    for i in range(1, len(fixes) + 1):
        same = (
            i < len(fixes)
            and abs(fixes[i].lat - fixes[run_start].lat) < IDENTICAL_DEG
            and abs(fixes[i].lon - fixes[run_start].lon) < IDENTICAL_DEG
        )
        if same:
            k = i - run_start + 1  # length of the run so far
            sp = fixes[i].speed
            if sp is not None and sp > 1.0 and k >= 3:
                flags.append(Flag(i, "frozen", 0.9, f"position unchanged for {k} fixes while reporting {sp:.1f} m/s"))
            elif k >= 60:
                flags.append(Flag(i, "frozen", 0.45, f"position identical for {k} fixes"))
            elif k >= 10:
                flags.append(Flag(i, "frozen", 0.3, f"position identical for {k} fixes"))
        else:
            run_start = i
    return flags


def check_noise(fixes: Sequence[Fix], profile: Profile, window: int = 20, min_rms_m: float = 0.25) -> List[Flag]:
    """A moving track with no measurement noise, as a GPS simulator produces.

    Smooth motion has near-zero third differences of position; real receiver
    noise does not. Heavily filtered phone locations can also be this smooth,
    so this check is a weak signal on its own.
    """
    n = len(fixes)
    if n < window + 3:
        return []
    lat0, lon0 = fixes[0].lat, fixes[0].lon
    p = [to_enu(f.lat, f.lon, lat0, lon0) for f in fixes]
    d3 = [0.0] * n  # squared third difference ending at i, or -1 if not usable
    for i in range(3, n):
        dts = [fixes[k].t - fixes[k - 1].t for k in range(i - 2, i + 1)]
        step = math.hypot(p[i][0] - p[i - 1][0], p[i][1] - p[i - 1][1])
        if min(dts) <= 0 or max(dts) > 1.1 * min(dts) or step < 0.5:
            d3[i] = -1.0
            continue
        ex = p[i][0] - 3 * p[i - 1][0] + 3 * p[i - 2][0] - p[i - 3][0]
        ny = p[i][1] - 3 * p[i - 1][1] + 3 * p[i - 2][1] - p[i - 3][1]
        d3[i] = ex * ex + ny * ny
    flags = []
    for i in range(window + 3, n):
        seg = d3[i - window + 1:i + 1]
        if min(seg) < 0:
            continue
        rms = math.sqrt(sum(seg) / window)
        if rms < min_rms_m:
            flags.append(Flag(i, "noise", 0.4, f"no measurement noise over {window} moving fixes (rms {rms:.2f} m)"))
    return flags


def check_signal(fixes: Sequence[Fix], profile: Profile) -> List[Flag]:
    """Satellite signals that look like one transmitter.

    Real satellites sit at different elevations, so their carrier-to-noise
    ratios typically spread 4 to 8 dB-Hz. A spoofer broadcasts every fake
    satellite from one antenna, so they arrive nearly equal and often
    stronger than real signals ever are.
    """
    flags = []
    for i, f in enumerate(fixes):
        if not f.cn0 or len(f.cn0) < 4:
            continue
        sd = statistics.pstdev(f.cn0)
        mean = statistics.fmean(f.cn0)
        sev = 0.0
        why = []
        if sd < 1.5:
            sev = 0.5
            why.append(f"{len(f.cn0)} satellites within {sd:.1f} dB-Hz of each other")
        if mean > 50:
            sev = 1 - (1 - sev) * (1 - 0.35)
            why.append(f"mean signal {mean:.0f} dB-Hz, stronger than open sky")
        if sev:
            flags.append(Flag(i, "signal", sev, "; ".join(why)))
    return flags


ALL_CHECKS: dict[str, Check] = {
    "time": check_time,
    "jumps": check_jumps,
    "climb": check_climb,
    "accel": check_accel,
    "velocity": check_velocity,
    "frozen": check_frozen,
    "noise": check_noise,
    "signal": check_signal,
}
