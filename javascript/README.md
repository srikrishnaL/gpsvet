# gpsvet for JavaScript and TypeScript

Detect spoofed and tampered GPS tracks in Node or the browser. No runtime
dependencies. See the [main README](https://github.com/srikrishnaL/gpsvet) for
what each check catches and the benchmark results.

```ts
import { detect } from "gpsvet";

const fixes = [
  { lat: 52.3676, lon: 4.9041, t: 1760000000, speed: 1.4, course: 90 },
  // ...
];

const report = detect(fixes, { profile: "walk" });
report.score;     // 0..1, the most suspicious moment
report.spoofed;   // score >= threshold (default 0.5)
report.events();  // suspicious stretches, with the checks that fired
```

Each fix needs `lat`, `lon` and `t` (Unix seconds). Optional `speed` (m/s),
`course` (degrees), `alt` (m), `hdop` and `cn0` (per-satellite dB-Hz) turn on
more checks.

The results match the Python reference exactly: `npm test` checks every
shared track in `spec/vectors`.
