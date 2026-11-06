"""Small-distance geometry on the WGS84 sphere approximation."""

from __future__ import annotations

import math

EARTH_RADIUS_M = 6_371_008.8


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def to_enu(lat: float, lon: float, lat0: float, lon0: float) -> tuple[float, float]:
    """East and north metres of (lat, lon) from (lat0, lon0). Good to ~0.1% within 100 km."""
    east = math.radians(lon - lon0) * EARTH_RADIUS_M * math.cos(math.radians(lat0))
    north = math.radians(lat - lat0) * EARTH_RADIUS_M
    return east, north


def from_enu(east: float, north: float, lat0: float, lon0: float) -> tuple[float, float]:
    lat = lat0 + math.degrees(north / EARTH_RADIUS_M)
    lon = lon0 + math.degrees(east / (EARTH_RADIUS_M * math.cos(math.radians(lat0))))
    return lat, lon


def velocity_enu(speed: float, course_deg: float) -> tuple[float, float]:
    c = math.radians(course_deg)
    return speed * math.sin(c), speed * math.cos(c)


def speed_course(east: float, north: float) -> tuple[float, float]:
    return math.hypot(east, north), math.degrees(math.atan2(east, north)) % 360
