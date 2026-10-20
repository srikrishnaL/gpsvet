/** One GPS fix. Only `lat`, `lon` and `t` are required; each optional field turns on more checks. */
export interface Fix {
  lat: number;
  lon: number;
  /** Seconds since the Unix epoch. */
  t: number;
  /** m/s, the receiver's own Doppler speed. */
  speed?: number | null;
  /** Degrees clockwise from true north. */
  course?: number | null;
  /** Metres. */
  alt?: number | null;
  hdop?: number | null;
  /** dB-Hz, one value per satellite used. */
  cn0?: readonly number[] | null;
}

/** What is physically possible for the kind of device being tracked. */
export interface Profile {
  name: string;
  maxSpeed: number;
  maxAccel: number;
  maxClimb: number;
  /** Assumed horizontal error in metres when a fix has no hdop. */
  accuracyM: number;
}

export const PROFILES: Readonly<Record<string, Profile>> = {
  walk: { name: "walk", maxSpeed: 12, maxAccel: 4, maxClimb: 5, accuracyM: 10 },
  bike: { name: "bike", maxSpeed: 25, maxAccel: 5, maxClimb: 8, accuracyM: 10 },
  car: { name: "car", maxSpeed: 70, maxAccel: 10, maxClimb: 15, accuracyM: 10 },
  drone: { name: "drone", maxSpeed: 40, maxAccel: 15, maxClimb: 20, accuracyM: 10 },
  aircraft: { name: "aircraft", maxSpeed: 320, maxAccel: 30, maxClimb: 80, accuracyM: 15 },
};

export function getProfile(profile: string | Profile): Profile {
  if (typeof profile !== "string") return profile;
  const p = PROFILES[profile];
  if (!p) throw new Error(`unknown profile "${profile}", expected one of ${Object.keys(PROFILES).sort().join(", ")}`);
  return p;
}

/** One check's finding at one fix. `severity` runs from 0 to 1. */
export interface Flag {
  index: number;
  check: string;
  severity: number;
  detail: string;
}
