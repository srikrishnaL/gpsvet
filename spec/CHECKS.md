# gpsvet detection spec

This is the contract every gpsvet library implements. The Python package in
`python/` is the reference; the files in `vectors/` hold its exact output on
shared tracks, and each language's test suite must reproduce them (per-fix
scores within 1e-6, the same flags at the same fixes).

## Input

A track is an ordered list of fixes. Each fix has:

| Field | Unit | Required |
|---|---|---|
| `lat`, `lon` | degrees (WGS84) | yes |
| `t` | seconds since the Unix epoch | yes |
| `speed` | m/s, the receiver's Doppler speed | no |
| `course` | degrees clockwise from true north | no |
| `alt` | metres | no |
| `hdop` | unitless | no |
| `cn0` | dB-Hz, one value per satellite used | no |

Missing fields switch off the checks that need them; nothing is guessed.

## Profiles

| Profile | max speed (m/s) | max accel (m/s²) | max climb (m/s) | accuracy without hdop (m) |
|---|---|---|---|---|
| walk | 12 | 4 | 5 | 10 |
| bike | 25 | 5 | 8 | 10 |
| car | 70 | 10 | 15 | 10 |
| drone | 40 | 15 | 20 | 10 |
| aircraft | 320 | 30 | 80 | 15 |

## Shared definitions

- `accuracy(f) = f.hdop * 5` when hdop is present and non-zero, else the profile's accuracy.
- `excess(r) = min(1, 0.4 + (r - 1))`: severity for a value `r` times over its limit.
- Distances use the haversine formula with Earth radius 6,371,008.8 m:
  `a = sin²(Δφ/2) + cos φ1 cos φ2 sin²(Δλ/2)`, `d = 2R·asin(min(1, √a))`.
- Local east/north metres from an origin (lat0, lon0):
  `east = rad(lon - lon0)·R·cos(rad(lat0))`, `north = rad(lat - lat0)·R`.
- A velocity from speed and course: `(speed·sin(rad(course)), speed·cos(rad(course)))`.
- `median` of an even-length list is the mean of the two middle values.

## Checks

Each check emits flags `(index, check, severity, detail)`. The detail text is
for people and is not part of the contract.

### time
For each `i ≥ 1` with `dt = t[i] - t[i-1]`: `dt < 0` → severity 1.0.
`dt == 0` and the positions differ → 0.8.

### jumps (flags `jump` and `glitch`)
`implied(a, b) = max(0, d(a, b) - accuracy(a) - accuracy(b)) / (t[b] - t[a])`.
`ok(a, b)` is true when `t[b] > t[a]` and `implied(a, b) ≤ max speed`.

1. If there are at least 3 fixes and `!ok(0,1) && !ok(0,2) && ok(1,2)`, flag
   fix 0 as `glitch` 0.25 and start with `last = 1, i = 2`. Otherwise
   `last = 0, i = 1`.
2. While `i < n`:
   - if `t[i] ≤ t[last]`, skip `i`;
   - if `ok(last, i)`, set `last = i`;
   - else look for the first `j` in `i+1 .. i+3` (inside the track) with
     `ok(last, j)`. If found, flag every fix `i .. j-1` as `glitch` 0.25 and
     continue from `last = j, i = j + 1`. If not, flag `i` as `jump` with
     `excess(implied(last, i) / max speed)` and set `last = i`.

### climb
Over fixes with `alt`, each against the previous fix that has `alt`, when
time moves forward: `rate = max(0, |Δalt| - 1.5·(accuracy(a) + accuracy(b))) / dt`.
`rate > max climb` → `excess(rate / max climb)`.

### accel
For consecutive fixes that both have `speed`, when time moves forward:
`acc = |Δspeed| / dt`. `acc > max accel` → `excess(acc / max accel)`.

### velocity (dead reckoning)
Runs only when every fix has `speed`, and the track has at least 3 fixes.
It uses the vector form when every fix also has `course`.

- Dead-reckoned running sums from fix 0, using `dt = max(0, t[k] - t[k-1])`:
  distance `L[k] = L[k-1] + (speed[k] + speed[k-1])/2 · dt`; in vector form
  also east/north `D[k] = D[k-1] + (v[k] + v[k-1])/2 · dt` with `v` the
  velocity vector.
- Positions `p[k]` in east/north metres from fix 0.
- Vector form: residuals `r[k] = p[k] - D[k]`, each axis smoothed by a running
  median over `k-3 .. k+3` (clipped at the ends).
  Speed-only form: the positions themselves are smoothed the same way.
- Window: for each `i ≥ 1`, `j` is the first index with `t[i] - t[j] ≤ 30`
  (a pointer that only moves forward). Skip when `j ≥ i` or
  `t[i] - t[j] < 15`.
- `thr = 1.5·(accuracy(i) + accuracy(j)) + 0.05·(L[i] - L[j])`.
- Vector form: `err = |r̃[i] - r̃[j]|`. Speed-only form:
  `err = |p̃[i] - p̃[j]| - (L[i] - L[j])`.
- `err > thr` → severity `min(1, 0.3 + 0.35·(err/thr - 1))`.

### frozen
Walk the track keeping `run_start`. Fix `i` continues the run when both
`|lat[i] - lat[run_start]|` and `|lon[i] - lon[run_start]|` are below 1e-7,
otherwise `run_start = i`. For a continuing fix, with `k = i - run_start + 1`:

- `speed[i] > 1` and `k ≥ 3` → 0.9
- else `k ≥ 60` → 0.45
- else `k ≥ 10` → 0.3

### noise
Window `W = 20`, minimum RMS 0.25 m. Requires at least `W + 3` fixes.
Positions are east/north metres from fix 0. For `i ≥ 3`, the fix is usable when
the three intervals `t[i-2]-t[i-3]`, `t[i-1]-t[i-2]`, `t[i]-t[i-1]` are all
positive, the largest is at most 1.1× the smallest, and the step
`|p[i] - p[i-1]| ≥ 0.5` m. A usable fix stores the squared length of the third
difference `p[i] - 3p[i-1] + 3p[i-2] - p[i-3]`.
For each `i` from `W + 3` to `n - 1`: if all of fixes `i-W+1 .. i` are usable
and `sqrt(sum / W) < 0.25`, flag `i` with 0.4.

### signal
For a fix with at least 4 `cn0` values, `sd` = population standard deviation,
`mean` = arithmetic mean. Start with severity 0. `sd < 1.5` → 0.5.
`mean > 50` → `1 - (1 - severity)·0.65`. Flag when severity > 0.

## Scores

For every fix, take each check's highest severity at that fix (`jump` and
`glitch` are separate checks) and combine them as independent evidence:
`score = 1 - Π(1 - severity)`. The track score is the highest fix score.
A fix is suspicious when its score ≥ threshold (default 0.5).

Events group suspicious fixes whose indices are at most 5 apart.
