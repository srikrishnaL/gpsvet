// Individual checks. Each takes the fixes and a Profile and returns Flags.
// See spec/CHECKS.md for the exact rules every gpsvet library implements.

import { haversineM, toEnu, velocityEnu } from "./geo.ts";
import type { Fix, Flag, Profile } from "./model.ts";

export type Check = (fixes: readonly Fix[], profile: Profile) => Flag[];

const UERE_M = 5.0;
const GLITCH_LOOKAHEAD = 3;
const IDENTICAL_DEG = 1e-7;

const has = (v: number | null | undefined): v is number => v !== null && v !== undefined;

function accuracy(f: Fix, profile: Profile): number {
  return f.hdop ? f.hdop * UERE_M : profile.accuracyM;
}

function excess(ratio: number): number {
  return Math.min(1.0, 0.4 + (ratio - 1.0));
}

function median(xs: number[]): number {
  const s = [...xs].sort((a, b) => a - b);
  const m = s.length >> 1;
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

function runningMedian(xs: number[], radius: number): number[] {
  return xs.map((_, i) => median(xs.slice(Math.max(0, i - radius), i + radius + 1)));
}

export const checkTime: Check = (fixes) => {
  const flags: Flag[] = [];
  for (let i = 1; i < fixes.length; i++) {
    const a = fixes[i - 1];
    const b = fixes[i];
    const dt = b.t - a.t;
    if (dt < 0) {
      flags.push({ index: i, check: "time", severity: 1.0, detail: `timestamp goes back ${(-dt).toFixed(1)} s` });
    } else if (dt === 0 && (a.lat !== b.lat || a.lon !== b.lon)) {
      flags.push({ index: i, check: "time", severity: 0.8, detail: "two different positions at the same time" });
    }
  }
  return flags;
};

function impliedSpeed(a: Fix, b: Fix, profile: Profile): [number, number] {
  const d = haversineM(a.lat, a.lon, b.lat, b.lon);
  const slack = accuracy(a, profile) + accuracy(b, profile);
  return [Math.max(0.0, d - slack) / (b.t - a.t), d];
}

export const checkJumps: Check = (fixes, profile) => {
  const flags: Flag[] = [];
  const n = fixes.length;
  const ok = (a: number, b: number): boolean =>
    fixes[b].t > fixes[a].t && impliedSpeed(fixes[a], fixes[b], profile)[0] <= profile.maxSpeed;
  let last = 0;
  let i = 1;
  if (n >= 3 && !ok(0, 1) && !ok(0, 2) && ok(1, 2)) {
    flags.push({ index: 0, check: "glitch", severity: 0.25, detail: "first fix is off the track" });
    last = 1;
    i = 2;
  }
  while (i < n) {
    if (fixes[i].t <= fixes[last].t) {
      i++;
      continue;
    }
    const [v, d] = impliedSpeed(fixes[last], fixes[i], profile);
    if (v <= profile.maxSpeed) {
      last = i++;
      continue;
    }
    let back = -1;
    for (let j = i + 1; j < Math.min(n, i + 1 + GLITCH_LOOKAHEAD); j++) {
      if (ok(last, j)) {
        back = j;
        break;
      }
    }
    if (back >= 0) {
      for (let k = i; k < back; k++) {
        flags.push({
          index: k, check: "glitch", severity: 0.25,
          detail: `${d.toFixed(0)} m off the track for ${back - i} fix(es), then back`,
        });
      }
      last = back;
      i = back + 1;
      continue;
    }
    const dt = fixes[i].t - fixes[last].t;
    flags.push({
      index: i, check: "jump", severity: excess(v / profile.maxSpeed),
      detail: `moved ${d.toFixed(0)} m in ${dt.toFixed(1)} s (${v.toFixed(0)} m/s, limit ${profile.maxSpeed})`,
    });
    last = i++;
  }
  return flags;
};

export const checkClimb: Check = (fixes, profile) => {
  const flags: Flag[] = [];
  let prev = -1;
  fixes.forEach((f, i) => {
    if (!has(f.alt)) return;
    if (prev >= 0 && f.t > fixes[prev].t) {
      const p = fixes[prev];
      const slack = 1.5 * (accuracy(f, profile) + accuracy(p, profile));
      const dz = Math.abs(f.alt - (p.alt as number));
      const rate = Math.max(0.0, dz - slack) / (f.t - p.t);
      if (rate > profile.maxClimb) {
        flags.push({
          index: i, check: "climb", severity: excess(rate / profile.maxClimb),
          detail: `altitude changed ${dz.toFixed(0)} m (${rate.toFixed(0)} m/s, limit ${profile.maxClimb})`,
        });
      }
    }
    prev = i;
  });
  return flags;
};

export const checkAccel: Check = (fixes, profile) => {
  const flags: Flag[] = [];
  for (let i = 1; i < fixes.length; i++) {
    const a = fixes[i - 1];
    const b = fixes[i];
    if (!has(a.speed) || !has(b.speed) || b.t <= a.t) continue;
    const acc = Math.abs(b.speed - a.speed) / (b.t - a.t);
    if (acc > profile.maxAccel) {
      flags.push({
        index: i, check: "accel", severity: excess(acc / profile.maxAccel),
        detail: `speed went ${a.speed.toFixed(1)} -> ${b.speed.toFixed(1)} m/s (${acc.toFixed(1)} m/s², limit ${profile.maxAccel})`,
      });
    }
  }
  return flags;
};

/** Dead reckoning: integrate the reported velocity and compare it with where the positions went. */
export function checkVelocity(fixes: readonly Fix[], profile: Profile, windowS = 30.0): Flag[] {
  const n = fixes.length;
  if (n < 3 || fixes.some((f) => !has(f.speed))) return [];
  const useCourse = fixes.every((f) => has(f.course));
  const lat0 = fixes[0].lat;
  const lon0 = fixes[0].lon;
  const pos = fixes.map((f) => toEnu(f.lat, f.lon, lat0, lon0));
  const sp = (k: number) => fixes[k].speed as number;

  const de = new Array<number>(n).fill(0);
  const dn = new Array<number>(n).fill(0);
  const dl = new Array<number>(n).fill(0);
  for (let k = 1; k < n; k++) {
    const dt = Math.max(0.0, fixes[k].t - fixes[k - 1].t);
    dl[k] = dl[k - 1] + ((sp(k) + sp(k - 1)) / 2) * dt;
    if (useCourse) {
      const [e1, n1] = velocityEnu(sp(k - 1), fixes[k - 1].course as number);
      const [e2, n2] = velocityEnu(sp(k), fixes[k].course as number);
      de[k] = de[k - 1] + ((e1 + e2) / 2) * dt;
      dn[k] = dn[k - 1] + ((n1 + n2) / 2) * dt;
    }
  }

  let xe: number[];
  let xn: number[];
  if (useCourse) {
    xe = runningMedian(pos.map((p, k) => p[0] - de[k]), 3);
    xn = runningMedian(pos.map((p, k) => p[1] - dn[k]), 3);
  } else {
    xe = runningMedian(pos.map((p) => p[0]), 3);
    xn = runningMedian(pos.map((p) => p[1]), 3);
  }

  const flags: Flag[] = [];
  let j = 0;
  for (let i = 1; i < n; i++) {
    while (j < i && fixes[i].t - fixes[j].t > windowS) j++;
    if (j >= i || fixes[i].t - fixes[j].t < windowS / 2) continue;
    const path = dl[i] - dl[j];
    const thr = 1.5 * (accuracy(fixes[i], profile) + accuracy(fixes[j], profile)) + 0.05 * path;
    const moved = Math.hypot(xe[i] - xe[j], xn[i] - xn[j]);
    const err = useCourse ? moved : moved - path;
    if (err > thr) {
      const what = useCourse
        ? `positions drifted ${err.toFixed(0)} m from where the reported velocity leads`
        : `positions moved ${err.toFixed(0)} m farther than the reported speed allows`;
      flags.push({
        index: i, check: "velocity", severity: Math.min(1.0, 0.3 + 0.35 * (err / thr - 1)),
        detail: `${what} over ${(fixes[i].t - fixes[j].t).toFixed(0)} s`,
      });
    }
  }
  return flags;
}

export const checkFrozen: Check = (fixes) => {
  const flags: Flag[] = [];
  let runStart = 0;
  for (let i = 1; i < fixes.length; i++) {
    const same =
      Math.abs(fixes[i].lat - fixes[runStart].lat) < IDENTICAL_DEG &&
      Math.abs(fixes[i].lon - fixes[runStart].lon) < IDENTICAL_DEG;
    if (!same) {
      runStart = i;
      continue;
    }
    const k = i - runStart + 1;
    const sp = fixes[i].speed;
    if (has(sp) && sp > 1.0 && k >= 3) {
      flags.push({ index: i, check: "frozen", severity: 0.9, detail: `position unchanged for ${k} fixes while reporting ${sp.toFixed(1)} m/s` });
    } else if (k >= 60) {
      flags.push({ index: i, check: "frozen", severity: 0.45, detail: `position identical for ${k} fixes` });
    } else if (k >= 10) {
      flags.push({ index: i, check: "frozen", severity: 0.3, detail: `position identical for ${k} fixes` });
    }
  }
  return flags;
};

export function checkNoise(fixes: readonly Fix[], _profile: Profile, window = 20, minRmsM = 0.25): Flag[] {
  const n = fixes.length;
  if (n < window + 3) return [];
  const lat0 = fixes[0].lat;
  const lon0 = fixes[0].lon;
  const p = fixes.map((f) => toEnu(f.lat, f.lon, lat0, lon0));
  const d3 = new Array<number>(n).fill(0);
  for (let i = 3; i < n; i++) {
    const dts = [fixes[i - 2].t - fixes[i - 3].t, fixes[i - 1].t - fixes[i - 2].t, fixes[i].t - fixes[i - 1].t];
    const step = Math.hypot(p[i][0] - p[i - 1][0], p[i][1] - p[i - 1][1]);
    const lo = Math.min(...dts);
    if (lo <= 0 || Math.max(...dts) > 1.1 * lo || step < 0.5) {
      d3[i] = -1.0;
      continue;
    }
    const ex = p[i][0] - 3 * p[i - 1][0] + 3 * p[i - 2][0] - p[i - 3][0];
    const ny = p[i][1] - 3 * p[i - 1][1] + 3 * p[i - 2][1] - p[i - 3][1];
    d3[i] = ex * ex + ny * ny;
  }
  const flags: Flag[] = [];
  for (let i = window + 3; i < n; i++) {
    const seg = d3.slice(i - window + 1, i + 1);
    if (Math.min(...seg) < 0) continue;
    const rms = Math.sqrt(seg.reduce((s, x) => s + x, 0) / window);
    if (rms < minRmsM) {
      flags.push({ index: i, check: "noise", severity: 0.4, detail: `no measurement noise over ${window} moving fixes (rms ${rms.toFixed(2)} m)` });
    }
  }
  return flags;
}

export const checkSignal: Check = (fixes) => {
  const flags: Flag[] = [];
  fixes.forEach((f, i) => {
    const c = f.cn0;
    if (!c || c.length < 4) return;
    const mean = c.reduce((s, x) => s + x, 0) / c.length;
    const sd = Math.sqrt(c.reduce((s, x) => s + (x - mean) ** 2, 0) / c.length);
    let sev = 0.0;
    const why: string[] = [];
    if (sd < 1.5) {
      sev = 0.5;
      why.push(`${c.length} satellites within ${sd.toFixed(1)} dB-Hz of each other`);
    }
    if (mean > 50) {
      sev = 1 - (1 - sev) * (1 - 0.35);
      why.push(`mean signal ${mean.toFixed(0)} dB-Hz, stronger than open sky`);
    }
    if (sev) flags.push({ index: i, check: "signal", severity: sev, detail: why.join("; ") });
  });
  return flags;
};

export const ALL_CHECKS: Readonly<Record<string, Check>> = {
  time: checkTime,
  jumps: checkJumps,
  climb: checkClimb,
  accel: checkAccel,
  velocity: checkVelocity,
  frozen: checkFrozen,
  noise: checkNoise,
  signal: checkSignal,
};
