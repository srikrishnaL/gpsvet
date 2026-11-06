export const EARTH_RADIUS_M = 6_371_008.8;

const rad = (deg: number): number => (deg * Math.PI) / 180;

export function haversineM(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const p1 = rad(lat1);
  const p2 = rad(lat2);
  const dp = p2 - p1;
  const dl = rad(lon2 - lon1);
  const a = Math.sin(dp / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2;
  return 2 * EARTH_RADIUS_M * Math.asin(Math.min(1, Math.sqrt(a)));
}

/** East and north metres of (lat, lon) from (lat0, lon0). */
export function toEnu(lat: number, lon: number, lat0: number, lon0: number): [number, number] {
  const east = rad(lon - lon0) * EARTH_RADIUS_M * Math.cos(rad(lat0));
  const north = rad(lat - lat0) * EARTH_RADIUS_M;
  return [east, north];
}

export function velocityEnu(speed: number, courseDeg: number): [number, number] {
  const c = rad(courseDeg);
  return [speed * Math.sin(c), speed * Math.cos(c)];
}
