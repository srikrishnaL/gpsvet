"""Detect spoofed and tampered GPS tracks."""

from .attacks import ATTACKS
from .detect import Event, Report, detect
from .io import read_csv, read_gpx, read_track, write_csv
from .model import PROFILES, Fix, Flag, Profile
from .synth import clean_track

__all__ = [
    "Fix",
    "Flag",
    "Profile",
    "PROFILES",
    "detect",
    "Report",
    "Event",
    "ATTACKS",
    "clean_track",
    "read_csv",
    "read_gpx",
    "read_track",
    "write_csv",
]
__version__ = "0.1.0"
