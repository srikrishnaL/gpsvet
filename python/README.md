# gpsvet for Python

Detect spoofed and tampered GPS tracks. This is the reference implementation
of [gpsvet](https://github.com/srikrishnaL/gpsvet); see the main README for
what each check catches and the benchmark results.

```bash
pip install "gpsvet @ git+https://github.com/srikrishnaL/gpsvet#subdirectory=python"
```

## Command line

```bash
gpsvet ride.gpx --profile bike          # exit code 1 if anything looks spoofed
gpsvet *.csv --json                     # one JSON report per file
```

## Library

```python
from gpsvet import Fix, detect, read_track

fixes = read_track("ride.gpx")          # or read_csv / read_gpx, or build Fix objects yourself
report = detect(fixes, profile="bike")

report.score        # 0..1, the most suspicious moment
report.spoofed      # score >= threshold (default 0.5)
report.scores       # one score per fix
report.flags        # every finding: index, check, severity, detail
report.events()     # suspicious stretches, with the checks that fired
```

CSV columns: `lat`, `lon`, `t` (Unix seconds or ISO 8601), and optionally
`speed` (m/s), `course` (degrees), `alt` (m), `hdop`, `cn0` (per-satellite
dB-Hz separated by spaces).

## Attacks and benchmark

```python
import random
from gpsvet import ATTACKS, clean_track

track = clean_track("car", minutes=30, rng=random.Random(1))
spoofed, labels = ATTACKS["drift"](track, start=600, length=600, rng=random.Random(2))
```

```bash
python -m gpsvet.bench                       # results table
python -m gpsvet.bench --export data/        # plus every labelled track as CSV
```
