package io.github.srikrishnal.gpsvet;

/** Small-distance geometry on the WGS84 sphere approximation. */
public final class Geo {
    public static final double EARTH_RADIUS_M = 6_371_008.8;

    private Geo() {}

    private static double rad(double deg) {
        return deg * Math.PI / 180;
    }

    public static double haversineM(double lat1, double lon1, double lat2, double lon2) {
        double p1 = rad(lat1);
        double p2 = rad(lat2);
        double dp = p2 - p1;
        double dl = rad(lon2 - lon1);
        double a = Math.pow(Math.sin(dp / 2), 2) + Math.cos(p1) * Math.cos(p2) * Math.pow(Math.sin(dl / 2), 2);
        return 2 * EARTH_RADIUS_M * Math.asin(Math.min(1.0, Math.sqrt(a)));
    }

    /** East and north metres of (lat, lon) from (lat0, lon0). */
    static double[] toEnu(double lat, double lon, double lat0, double lon0) {
        double east = rad(lon - lon0) * EARTH_RADIUS_M * Math.cos(rad(lat0));
        double north = rad(lat - lat0) * EARTH_RADIUS_M;
        return new double[] {east, north};
    }

    static double[] velocityEnu(double speed, double courseDeg) {
        double c = rad(courseDeg);
        return new double[] {speed * Math.sin(c), speed * Math.cos(c)};
    }
}
