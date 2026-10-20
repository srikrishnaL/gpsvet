import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";

import { detect } from "../src/index.ts";
import type { Fix } from "../src/index.ts";

const DIR = join(import.meta.dirname, "..", "..", "spec", "vectors");
const TOL = 1e-6;

type Row = [number, number, number, number | null, number | null, number | null, number | null, number[] | null];

const files = readdirSync(DIR).filter((f) => f.endsWith(".json")).sort();

test("vectors exist", () => assert.ok(files.length >= 15));

for (const file of files) {
  test(`vector ${file}`, () => {
    const doc = JSON.parse(readFileSync(join(DIR, file), "utf8"));
    const fixes: Fix[] = (doc.fixes as Row[]).map(([lat, lon, t, speed, course, alt, hdop, cn0]) =>
      ({ lat, lon, t, speed, course, alt, hdop, cn0 }));
    const rep = detect(fixes, { profile: doc.profile });
    const exp = doc.expected;
    assert.equal(rep.spoofed, exp.spoofed);
    assert.equal(rep.scores.length, exp.scores.length);
    rep.scores.forEach((s, i) => assert.ok(Math.abs(s - exp.scores[i]) < TOL, `score at ${i}: ${s} vs ${exp.scores[i]}`));
    const got = rep.flags
      .map((f) => [f.index, f.check, f.severity] as [number, string, number])
      .sort((a, b) => a[0] - b[0] || (a[1] < b[1] ? -1 : a[1] > b[1] ? 1 : a[2] - b[2]));
    assert.deepEqual(got.map((g) => [g[0], g[1]]), exp.flags.map((e: unknown[]) => [e[0], e[1]]));
    got.forEach((g, i) => assert.ok(Math.abs(g[2] - exp.flags[i][2]) < TOL, `severity of flag ${i}`));
  });
}
