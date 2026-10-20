import { ALL_CHECKS } from "./checks.ts";
import { getProfile } from "./model.ts";
import type { Fix, Flag, Profile } from "./model.ts";

export const DEFAULT_THRESHOLD = 0.5;

/** A run of suspicious fixes. */
export interface SpoofEvent {
  start: number;
  /** Inclusive. */
  end: number;
  tStart: number;
  tEnd: number;
  score: number;
  checks: string[];
  details: string[];
}

export interface DetectOptions {
  profile?: string | Profile;
  checks?: string[];
  threshold?: number;
}

export class Report {
  readonly fixes: readonly Fix[];
  readonly profile: Profile;
  readonly flags: Flag[];
  /** One score per fix, 0..1. */
  readonly scores: number[];
  readonly threshold: number;

  constructor(fixes: readonly Fix[], profile: Profile, flags: Flag[], scores: number[], threshold: number) {
    this.fixes = fixes;
    this.profile = profile;
    this.flags = flags;
    this.scores = scores;
    this.threshold = threshold;
  }

  /** The highest per-fix score: how suspicious the worst moment is. */
  get score(): number {
    return this.scores.reduce((m, s) => Math.max(m, s), 0);
  }

  get spoofed(): boolean {
    return this.score >= this.threshold;
  }

  suspicious(): number[] {
    const out: number[] = [];
    this.scores.forEach((s, i) => {
      if (s >= this.threshold) out.push(i);
    });
    return out;
  }

  /** Group suspicious fixes closer than `gap` fixes apart into events. */
  events(gap = 5): SpoofEvent[] {
    const byIndex = new Map<number, Flag[]>();
    for (const f of this.flags) {
      const list = byIndex.get(f.index) ?? [];
      list.push(f);
      byIndex.set(f.index, list);
    }
    const idx = this.suspicious();
    const events: SpoofEvent[] = [];
    let k = 0;
    while (k < idx.length) {
      const start = idx[k];
      let end = start;
      while (k + 1 < idx.length && idx[k + 1] - end <= gap) end = idx[++k];
      k++;
      const flags: Flag[] = [];
      for (let i = start; i <= end; i++) flags.push(...(byIndex.get(i) ?? []));
      const checks = [...new Set(flags.map((f) => f.check))].sort();
      const details = checks.map((c) => {
        const worst = flags.filter((f) => f.check === c).reduce((a, b) => (b.severity > a.severity ? b : a));
        return `${c}: ${worst.detail}`;
      });
      events.push({
        start, end, tStart: this.fixes[start].t, tEnd: this.fixes[end].t,
        score: Math.max(...this.scores.slice(start, end + 1)), checks, details,
      });
    }
    return events;
  }
}

/**
 * Check a track for signs of spoofing or tampering.
 *
 * A fix's score combines the worst severity from every check as independent
 * evidence, `1 - prod(1 - severity)`, so two weak signals at the same moment
 * add up to a strong one.
 */
export function detect(fixes: readonly Fix[], options: DetectOptions = {}): Report {
  const profile = getProfile(options.profile ?? "car");
  const threshold = options.threshold ?? DEFAULT_THRESHOLD;
  const names = options.checks ?? Object.keys(ALL_CHECKS);
  const flags: Flag[] = [];
  for (const name of names) {
    const check = ALL_CHECKS[name];
    if (!check) throw new Error(`unknown check "${name}"`);
    flags.push(...check(fixes, profile));
  }
  const worst = new Map<string, Flag>();
  for (const f of flags) {
    const key = `${f.index}\u0000${f.check}`;
    const w = worst.get(key);
    if (!w || f.severity > w.severity) worst.set(key, f);
  }
  const keep = new Array<number>(fixes.length).fill(1.0);
  for (const f of worst.values()) keep[f.index] *= 1.0 - f.severity;
  return new Report(fixes, profile, flags, keep.map((k) => 1.0 - k), threshold);
}
