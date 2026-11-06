"""Benchmark: how often each attack is caught, how fast, and how often clean
tracks raise a false alarm.

    python -m gpsvet.bench                  # print the results table
    python -m gpsvet.bench --export data/   # also write the labelled tracks

Everything is seeded, so the same arguments always produce the same tracks
and the same numbers.
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from .attacks import ATTACKS, strip_signals
from .detect import DEFAULT_THRESHOLD, detect
from .io import write_csv
from .synth import clean_track

ATTACK_LEN = 600  # fixes (10 minutes at 1 Hz)


@dataclass
class Row:
    detected: int = 0
    total: int = 0
    latencies: List[float] = field(default_factory=list)

    def rate(self) -> float:
        return self.detected / self.total if self.total else 0.0


@dataclass
class Results:
    hours_clean: float = 0.0
    false_alarms: int = 0
    clean_tracks_flagged: int = 0
    clean_tracks: int = 0
    rows: Dict[str, Row] = field(default_factory=dict)

    def table(self) -> str:
        lines = [
            "| Attack | Detected | Median time to detect |",
            "|---|---|---|",
        ]
        for name, r in self.rows.items():
            lat = f"{statistics.median(r.latencies):.0f} s" if r.latencies else "-"
            lines.append(f"| {name} | {r.detected}/{r.total} ({r.rate():.0%}) | {lat} |")
        fa = self.false_alarms / self.hours_clean if self.hours_clean else 0.0
        lines.append("")
        lines.append(
            f"Clean tracks: {self.clean_tracks_flagged}/{self.clean_tracks} flagged, "
            f"{self.false_alarms} false-alarm events in {self.hours_clean:.0f} hours ({fa:.3f} per hour)."
        )
        return "\n".join(lines)


def run(
    seed: int = 7,
    tracks: int = 40,
    minutes: float = 30,
    modes: Sequence[str] = ("walk", "bike", "car"),
    threshold: float = DEFAULT_THRESHOLD,
    export: Optional[Path] = None,
) -> Results:
    rng = random.Random(seed)
    res = Results()
    scenarios = list(ATTACKS) + ["carry_off (no signal data)", "simulator (no signal data)"]
    for name in scenarios:
        res.rows[name] = Row()
    manifest = []

    for mode in modes:
        for k in range(tracks):
            clean = clean_track(mode, minutes, rng)
            rep = detect(clean, mode, threshold=threshold)
            res.clean_tracks += 1
            res.hours_clean += minutes / 60
            res.false_alarms += len(rep.events())
            res.clean_tracks_flagged += rep.spoofed
            if export:
                fn = f"{mode}_{k:03d}_clean.csv"
                write_csv(clean, export / fn, [False] * len(clean))
                manifest.append({"file": fn, "mode": mode, "attack": None})

            for name in scenarios:
                attack = name.split(" ")[0]
                start = rng.randint(300, len(clean) - ATTACK_LEN - 60)
                base = strip_signals(clean) if "no signal" in name else clean
                fixes, labels = ATTACKS[attack](base, start, ATTACK_LEN, rng)
                rep = detect(fixes, mode, threshold=threshold)
                hits = [i for i in rep.suspicious() if labels[i]]
                row = res.rows[name]
                row.total += 1
                if hits:
                    row.detected += 1
                    row.latencies.append(hits[0] - start)  # fixes are 1 Hz
                if export:
                    fn = f"{mode}_{k:03d}_{attack}{'_nosignal' if 'no signal' in name else ''}.csv"
                    write_csv(fixes, export / fn, labels)
                    manifest.append({"file": fn, "mode": mode, "attack": attack, "start": start,
                                     "length": ATTACK_LEN, "signal_data": "no signal" not in name})
    if export:
        (export / "manifest.json").write_text(json.dumps(
            {"seed": seed, "minutes": minutes, "rate_hz": 1, "tracks": manifest}, indent=1))
    return res


def main(argv: Optional[Sequence[str]] = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--tracks", type=int, default=40, help="tracks per mode (default 40)")
    ap.add_argument("--minutes", type=float, default=30)
    ap.add_argument("--modes", default="walk,bike,car")
    ap.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    ap.add_argument("--export", type=Path, help="write every labelled track as CSV into this folder")
    args = ap.parse_args(argv)
    if args.export:
        args.export.mkdir(parents=True, exist_ok=True)
    res = run(args.seed, args.tracks, args.minutes, args.modes.split(","), args.threshold, args.export)
    print(res.table())


if __name__ == "__main__":
    main()
