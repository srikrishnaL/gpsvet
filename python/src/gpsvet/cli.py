"""Command line: check GPX or CSV tracks for spoofing."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from typing import Optional, Sequence

from .detect import DEFAULT_THRESHOLD, detect
from .io import read_track
from .model import PROFILES


def _when(t: float) -> str:
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="gpsvet", description="Check GPS tracks for spoofing and tampering.")
    ap.add_argument("files", nargs="+", help=".gpx or .csv tracks")
    ap.add_argument("--profile", default="car", choices=sorted(PROFILES), help="kind of device (default car)")
    ap.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    ap.add_argument("--json", action="store_true", help="print one JSON object per file")
    args = ap.parse_args(argv)

    any_spoofed = False
    for path in args.files:
        fixes = read_track(path)
        rep = detect(fixes, args.profile, threshold=args.threshold)
        any_spoofed |= rep.spoofed
        if args.json:
            print(json.dumps({"file": path, **rep.to_dict()}))
            continue
        verdict = "SUSPICIOUS" if rep.spoofed else "ok"
        print(f"{path}: {len(fixes)} fixes, score {rep.score:.2f}, {verdict}")
        for e in rep.events():
            print(f"  fixes {e.start}-{e.end} ({_when(e.t_start)} to {_when(e.t_end)} UTC), score {e.score:.2f}")
            for d in e.details:
                print(f"    {d}")
    return 1 if any_spoofed else 0


if __name__ == "__main__":
    sys.exit(main())
