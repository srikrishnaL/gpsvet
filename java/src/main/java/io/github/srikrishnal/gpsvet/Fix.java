package io.github.srikrishnal.gpsvet;

import java.util.Arrays;

/**
 * One GPS fix. Only {@code lat}, {@code lon} and {@code t} are required; every
 * optional field (null when absent) turns on more checks.
 */
public final class Fix {
    public final double lat;
    public final double lon;
    /** Seconds since the Unix epoch. */
    public final double t;
    /** m/s, the receiver's own Doppler speed. */
    public final Double speed;
    /** Degrees clockwise from true north. */
    public final Double course;
    /** Metres. */
    public final Double alt;
    public final Double hdop;
    /** dB-Hz, one value per satellite used. */
    private final double[] cn0;

    public Fix(double lat, double lon, double t) {
        this(lat, lon, t, null, null, null, null, null);
    }

    public Fix(double lat, double lon, double t, Double speed, Double course, Double alt, Double hdop, double[] cn0) {
        this.lat = lat;
        this.lon = lon;
        this.t = t;
        this.speed = speed;
        this.course = course;
        this.alt = alt;
        this.hdop = hdop;
        this.cn0 = cn0 == null ? null : cn0.clone();
    }

    /** Per-satellite carrier-to-noise ratios, or null. */
    public double[] cn0() {
        return cn0 == null ? null : cn0.clone();
    }

    int cn0Count() {
        return cn0 == null ? 0 : cn0.length;
    }

    double cn0At(int i) {
        return cn0[i];
    }

    @Override
    public String toString() {
        return "Fix{lat=" + lat + ", lon=" + lon + ", t=" + t + ", speed=" + speed + ", course=" + course
                + ", alt=" + alt + ", hdop=" + hdop + ", cn0=" + Arrays.toString(cn0) + "}";
    }
}
