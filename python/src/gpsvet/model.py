"""Data types shared by the checks, the attack generator and the readers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass(frozen=True)
class Fix:
    """One GPS fix as a receiver or phone reports it.

    Only ``lat``, ``lon`` and ``t`` are required. Every optional field a
    source provides turns on more checks: ``speed`` and ``course`` (the
    receiver's own Doppler velocity) let the detector compare how the device
    says it moves with how its positions move, and ``cn0`` (per-satellite
    signal strength) exposes signals that all come from one transmitter.
    """

    lat: float
    lon: float
    t: float  # seconds since the Unix epoch
    speed: Optional[float] = None  # m/s
    course: Optional[float] = None  # degrees clockwise from true north
    alt: Optional[float] = None  # metres
    hdop: Optional[float] = None
    cn0: Optional[Tuple[float, ...]] = None  # dB-Hz, one value per satellite used


@dataclass(frozen=True)
class Profile:
    """What is physically possible for the kind of device being tracked."""

    name: str
    max_speed: float  # m/s
    max_accel: float  # m/s^2
    max_climb: float  # m/s, up or down
    accuracy_m: float = 10.0  # assumed horizontal error when a fix has no hdop


PROFILES = {
    "walk": Profile("walk", max_speed=12, max_accel=4, max_climb=5),
    "bike": Profile("bike", max_speed=25, max_accel=5, max_climb=8),
    "car": Profile("car", max_speed=70, max_accel=10, max_climb=15),
    "drone": Profile("drone", max_speed=40, max_accel=15, max_climb=20),
    "aircraft": Profile("aircraft", max_speed=320, max_accel=30, max_climb=80, accuracy_m=15),
}


def get_profile(profile: "str | Profile") -> Profile:
    if isinstance(profile, Profile):
        return profile
    try:
        return PROFILES[profile]
    except KeyError:
        raise ValueError(f"unknown profile {profile!r}, expected one of {sorted(PROFILES)}") from None


@dataclass(frozen=True)
class Flag:
    """One check's finding at one fix. ``severity`` runs from 0 to 1."""

    index: int
    check: str
    severity: float
    detail: str
