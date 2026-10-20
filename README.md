# gpsvet

Detect spoofed and tampered GPS tracks. Libraries for **Python**, **Java**
(including Android and Kotlin) and **JavaScript/TypeScript** (Node and
browsers), all built from one written spec and tested against the same
shared tracks, so every language gives the same answer.

Location data drives payouts, deliveries, attendance and safety decisions,
which gives people reasons to fake it. A fake-location app on a phone, an
edited log file or a GPS spoofer near a receiver all produce tracks that look
fine on a map. gpsvet looks for the things a real receiver moving through the
real world can't produce:

| Check | What it catches |
|---|---|
| `jumps` | Positions moving faster than the device can (teleports, replayed segments). One- to three-fix multipath outliers that come straight back are labelled `glitch` with low weight, so busy city streets don't raise alarms. |
| `velocity` | The receiver's own Doppler speed and course disagreeing with where its positions go (edited coordinates, slow drift, apps that report speed 0 while moving). |
| `frozen` | The exact same coordinates fix after fix while the receiver reports movement. |
| `time` | Timestamps going backwards, or two places at once. |
| `accel`, `climb` | Speed or altitude changing faster than the device can. |
| `signal` | Every satellite arriving at the same strength, the signature of one transmitter broadcasting all of them. |
| `noise` | A moving track with no measurement noise, as a GPS simulator produces. |

Each check gives a severity from 0 to 1 at each fix. Weak signals at the same
moment combine (`1 - Π(1 - severity)`), so no single noisy heuristic decides
on its own. Checks that need a field (speed, course, signal strength) switch
off when your data doesn't have it.

## Benchmark

Reproducible with `python -m gpsvet.bench` (seed 7). It runs 120 synthetic
30-minute tracks at 1 Hz (walking, cycling, driving) with realistic,
slowly wandering GNSS error and occasional multipath outliers, then injects
each attack for 10 minutes at a random point.

| Attack | Detected | Median time to detect |
|---|---|---|
| teleport | 120/120 (100%) | 0 s |
| replay of an earlier stretch | 120/120 (100%) | 0 s |
| position frozen while moving | 120/120 (100%) | 2 s |
| coordinates drifted away at 2 m/s | 120/120 (100%) | 17 s |
| timestamps shifted back | 120/120 (100%) | 0 s |
| RF carry-off (spoofer slowly pulls the receiver away) | 120/120 (100%) | 0 s |
| RF simulator takeover | 120/120 (100%) | 0 s |
| RF carry-off, source without signal-strength data | 0/120 (0%) | - |
| RF simulator, source without signal-strength data | 0/120 (0%) | - |

On the clean tracks: 5 false-alarm events in 60 hours (0.08 per hour).

The last two rows are a real limit, not a bug. A well-built RF spoofer moves
positions and Doppler velocity together, so if the device doesn't log
per-satellite signal strength (C/N0), there is nothing in the track itself to
contradict it. Log C/N0 if you can; Android exposes it through
`GnssStatus.getCn0DbHz`. `python -m gpsvet.bench --export data/` writes every
labelled track as CSV so others can compare detectors on the same data.

These results come from synthetic tracks. Results on public real-world
spoofing recordings are on the roadmap.

## Quick start

**Python** (`python/`)

```bash
pip install "gpsvet @ git+https://github.com/srikrishnaL/gpsvet#subdirectory=python"
gpsvet ride.gpx --profile bike
```

```python
from gpsvet import detect, read_track

report = detect(read_track("ride.gpx"), profile="bike")
if report.spoofed:
    for e in report.events():
        print(e.start, e.end, e.score, e.details)
```

**JavaScript / TypeScript** (`javascript/`)

```ts
import { detect } from "gpsvet";

const report = detect(fixes, { profile: "car" }); // fixes: {lat, lon, t, speed?, course?, ...}[]
if (report.spoofed) console.log(report.events());
```

**Java / Kotlin / Android** (`java/`)

```java
Report report = GpsVet.detect(fixes, Profile.CAR); // List<Fix>
if (report.spoofed()) report.events().forEach(System.out::println);
```

Profiles: `walk`, `bike`, `car`, `drone`, `aircraft`, or your own limits.

## Layout

| Folder | What's there |
|---|---|
| `spec/` | `CHECKS.md`, the exact rules, and `vectors/`, shared tracks with the expected output |
| `python/` | Reference implementation, GPX/CSV readers, command line, attack generator, benchmark |
| `javascript/` | TypeScript library for Node and browsers, no runtime dependencies |
| `java/` | Java 11+ library for servers, Android and Kotlin, no runtime dependencies |

Every library's tests load `spec/vectors/*.json` and must reproduce the
reference scores within 1e-6. CI regenerates the vectors from the Python
reference and fails if they drift.

## Roadmap

- Swift (iOS) and Go libraries
- Benchmark results on public real-world GNSS spoofing recordings
- Optional checks that use more receiver data: clock drift, per-satellite Doppler, IMU cross-checks

## License

Apache 2.0
