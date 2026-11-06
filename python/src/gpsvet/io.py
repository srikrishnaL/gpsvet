"""Read and write tracks as CSV or GPX."""

from __future__ import annotations

import csv
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, TextIO, Union

from .model import Fix

CSV_FIELDS = ["lat", "lon", "t", "speed", "course", "alt", "hdop", "cn0"]

_ALIASES = {
    "latitude": "lat", "longitude": "lon", "lng": "lon",
    "time": "t", "timestamp": "t",
    "altitude": "alt", "ele": "alt", "elevation": "alt",
    "bearing": "course", "heading": "course",
}


def _parse_time(s: str) -> float:
    s = s.strip()
    try:
        return float(s)
    except ValueError:
        pass
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def _opt(row: dict, key: str) -> Optional[float]:
    v = row.get(key)
    return float(v) if v not in (None, "") else None


def read_csv(source: Union[str, Path, TextIO]) -> List[Fix]:
    """Read a CSV with a header row.

    Required columns: ``lat``, ``lon``, ``t`` (Unix seconds or ISO 8601).
    Optional: ``speed`` (m/s), ``course`` (deg), ``alt`` (m), ``hdop``, and
    ``cn0`` (per-satellite dB-Hz separated by spaces). Common aliases such as
    ``latitude``, ``timestamp`` and ``bearing`` are accepted.
    """
    if isinstance(source, (str, Path)):
        with open(source, newline="") as fh:
            return read_csv(fh)
    reader = csv.DictReader(source)
    fixes = []
    for row in reader:
        row = {_ALIASES.get(k.strip().lower(), k.strip().lower()): v for k, v in row.items() if k}
        cn0 = row.get("cn0")
        fixes.append(Fix(
            lat=float(row["lat"]), lon=float(row["lon"]), t=_parse_time(row["t"]),
            speed=_opt(row, "speed"), course=_opt(row, "course"), alt=_opt(row, "alt"),
            hdop=_opt(row, "hdop"),
            cn0=tuple(float(x) for x in cn0.split()) if cn0 else None,
        ))
    return fixes


def write_csv(fixes: Sequence[Fix], dest: Union[str, Path, TextIO], labels: Optional[Sequence[bool]] = None) -> None:
    if isinstance(dest, (str, Path)):
        with open(dest, "w", newline="") as fh:
            return write_csv(fixes, fh, labels)
    w = csv.writer(dest)
    w.writerow(CSV_FIELDS + (["spoofed"] if labels is not None else []))
    for i, f in enumerate(fixes):
        row = [f.lat, f.lon, f.t, f.speed, f.course, f.alt, f.hdop,
               " ".join(str(x) for x in f.cn0) if f.cn0 else None]
        row = ["" if v is None else v for v in row]
        if labels is not None:
            row.append(int(labels[i]))
        w.writerow(row)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def read_gpx(source: Union[str, Path, TextIO]) -> List[Fix]:
    """Read every track point of a GPX file, in order.

    Picks up ``ele``, ``time`` and ``hdop``, plus ``speed`` and ``course``
    whether they are plain GPX 1.0 elements or inside extensions (such as
    Garmin's TrackPointExtension).
    """
    root = ET.parse(source).getroot()
    fixes = []
    for el in root.iter():
        if _local(el.tag) not in ("trkpt", "rtept"):
            continue
        vals = {}
        for child in el.iter():
            name = _local(child.tag)
            if name in ("ele", "time", "hdop", "speed", "course") and child.text and name not in vals:
                vals[name] = child.text
        if "time" not in vals:
            continue
        fixes.append(Fix(
            lat=float(el.get("lat")), lon=float(el.get("lon")), t=_parse_time(vals["time"]),
            speed=float(vals["speed"]) if "speed" in vals else None,
            course=float(vals["course"]) if "course" in vals else None,
            alt=float(vals["ele"]) if "ele" in vals else None,
            hdop=float(vals["hdop"]) if "hdop" in vals else None,
        ))
    return fixes


def read_track(path: Union[str, Path]) -> List[Fix]:
    """Read a .gpx or .csv file, chosen by extension."""
    p = Path(path)
    if p.suffix.lower() == ".gpx":
        return read_gpx(p)
    return read_csv(p)
