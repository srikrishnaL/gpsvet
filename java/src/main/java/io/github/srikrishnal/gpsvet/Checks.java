package io.github.srikrishnal.gpsvet;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/**
 * Individual checks. Each takes the fixes and a Profile and returns Flags.
 * See spec/CHECKS.md for the exact rules every gpsvet library implements.
 */
public final class Checks {
    /** A single check. */
    public interface Check {
        List<Flag> run(List<Fix> fixes, Profile profile);
    }

    static final double UERE_M = 5.0;
    static final int GLITCH_LOOKAHEAD = 3;
    static final double IDENTICAL_DEG = 1e-7;

    public static final Map<String, Check> ALL;

    static {
        Map<String, Check> m = new LinkedHashMap<>();
        m.put("time", Checks::time);
        m.put("jumps", Checks::jumps);
        m.put("climb", Checks::climb);
        m.put("accel", Checks::accel);
        m.put("velocity", Checks::velocity);
        m.put("frozen", Checks::frozen);
        m.put("noise", Checks::noise);
        m.put("signal", Checks::signal);
        ALL = Collections.unmodifiableMap(m);
    }

    private Checks() {}

    private static String fmt(String pattern, Object... args) {
        return String.format(Locale.ROOT, pattern, args);
    }

    static double accuracy(Fix f, Profile profile) {
        return f.hdop != null && f.hdop != 0 ? f.hdop * UERE_M : profile.accuracyM;
    }

    static double excess(double ratio) {
        return Math.min(1.0, 0.4 + (ratio - 1.0));
    }

    static double median(double[] xs, int from, int to) {
        double[] s = Arrays.copyOfRange(xs, from, to);
        Arrays.sort(s);
        int m = s.length / 2;
        return s.length % 2 == 1 ? s[m] : (s[m - 1] + s[m]) / 2;
    }

    static double[] runningMedian(double[] xs, int radius) {
        double[] out = new double[xs.length];
        for (int i = 0; i < xs.length; i++) {
            out[i] = median(xs, Math.max(0, i - radius), Math.min(xs.length, i + radius + 1));
        }
        return out;
    }

    /** Timestamps that go backwards, or two places at the same instant. */
    public static List<Flag> time(List<Fix> fixes, Profile profile) {
        List<Flag> flags = new ArrayList<>();
        for (int i = 1; i < fixes.size(); i++) {
            Fix a = fixes.get(i - 1);
            Fix b = fixes.get(i);
            double dt = b.t - a.t;
            if (dt < 0) {
                flags.add(new Flag(i, "time", 1.0, fmt("timestamp goes back %.1f s", -dt)));
            } else if (dt == 0 && (a.lat != b.lat || a.lon != b.lon)) {
                flags.add(new Flag(i, "time", 0.8, "two different positions at the same time"));
            }
        }
        return flags;
    }

    private static double[] impliedSpeed(Fix a, Fix b, Profile profile) {
        double d = Geo.haversineM(a.lat, a.lon, b.lat, b.lon);
        double slack = accuracy(a, profile) + accuracy(b, profile);
        return new double[] {Math.max(0.0, d - slack) / (b.t - a.t), d};
    }

    private static boolean ok(List<Fix> fixes, int a, int b, Profile profile) {
        return fixes.get(b).t > fixes.get(a).t && impliedSpeed(fixes.get(a), fixes.get(b), profile)[0] <= profile.maxSpeed;
    }

    /** Positions moving faster than the profile allows: a lasting jump, or a glitch that comes back. */
    public static List<Flag> jumps(List<Fix> fixes, Profile profile) {
        List<Flag> flags = new ArrayList<>();
        int n = fixes.size();
        int last = 0;
        int i = 1;
        if (n >= 3 && !ok(fixes, 0, 1, profile) && !ok(fixes, 0, 2, profile) && ok(fixes, 1, 2, profile)) {
            flags.add(new Flag(0, "glitch", 0.25, "first fix is off the track"));
            last = 1;
            i = 2;
        }
        while (i < n) {
            if (fixes.get(i).t <= fixes.get(last).t) {
                i++;
                continue;
            }
            double[] vd = impliedSpeed(fixes.get(last), fixes.get(i), profile);
            double v = vd[0];
            double d = vd[1];
            if (v <= profile.maxSpeed) {
                last = i++;
                continue;
            }
            int back = -1;
            for (int j = i + 1; j < Math.min(n, i + 1 + GLITCH_LOOKAHEAD); j++) {
                if (ok(fixes, last, j, profile)) {
                    back = j;
                    break;
                }
            }
            if (back >= 0) {
                for (int k = i; k < back; k++) {
                    flags.add(new Flag(k, "glitch", 0.25,
                            fmt("%.0f m off the track for %d fix(es), then back", d, back - i)));
                }
                last = back;
                i = back + 1;
                continue;
            }
            double dt = fixes.get(i).t - fixes.get(last).t;
            flags.add(new Flag(i, "jump", excess(v / profile.maxSpeed),
                    fmt("moved %.0f m in %.1f s (%.0f m/s, limit %.0f)", d, dt, v, profile.maxSpeed)));
            last = i++;
        }
        return flags;
    }

    /** Altitude changing faster than the profile allows. */
    public static List<Flag> climb(List<Fix> fixes, Profile profile) {
        List<Flag> flags = new ArrayList<>();
        int prev = -1;
        for (int i = 0; i < fixes.size(); i++) {
            Fix f = fixes.get(i);
            if (f.alt == null) {
                continue;
            }
            if (prev >= 0 && f.t > fixes.get(prev).t) {
                Fix p = fixes.get(prev);
                double slack = 1.5 * (accuracy(f, profile) + accuracy(p, profile));
                double dz = Math.abs(f.alt - p.alt);
                double rate = Math.max(0.0, dz - slack) / (f.t - p.t);
                if (rate > profile.maxClimb) {
                    flags.add(new Flag(i, "climb", excess(rate / profile.maxClimb),
                            fmt("altitude changed %.0f m (%.0f m/s, limit %.0f)", dz, rate, profile.maxClimb)));
                }
            }
            prev = i;
        }
        return flags;
    }

    /** Reported speed changing faster than the profile allows. */
    public static List<Flag> accel(List<Fix> fixes, Profile profile) {
        List<Flag> flags = new ArrayList<>();
        for (int i = 1; i < fixes.size(); i++) {
            Fix a = fixes.get(i - 1);
            Fix b = fixes.get(i);
            if (a.speed == null || b.speed == null || b.t <= a.t) {
                continue;
            }
            double acc = Math.abs(b.speed - a.speed) / (b.t - a.t);
            if (acc > profile.maxAccel) {
                flags.add(new Flag(i, "accel", excess(acc / profile.maxAccel),
                        fmt("speed went %.1f -> %.1f m/s (%.1f m/s², limit %.0f)", a.speed, b.speed, acc, profile.maxAccel)));
            }
        }
        return flags;
    }

    /** Dead reckoning: integrate the reported velocity and compare it with where the positions went. */
    public static List<Flag> velocity(List<Fix> fixes, Profile profile) {
        final double windowS = 30.0;
        int n = fixes.size();
        if (n < 3) {
            return new ArrayList<>();
        }
        boolean useCourse = true;
        for (Fix f : fixes) {
            if (f.speed == null) {
                return new ArrayList<>();
            }
            useCourse &= f.course != null;
        }
        Fix f0 = fixes.get(0);
        double[] pe = new double[n];
        double[] pn = new double[n];
        for (int k = 0; k < n; k++) {
            double[] p = Geo.toEnu(fixes.get(k).lat, fixes.get(k).lon, f0.lat, f0.lon);
            pe[k] = p[0];
            pn[k] = p[1];
        }
        double[] de = new double[n];
        double[] dn = new double[n];
        double[] dl = new double[n];
        for (int k = 1; k < n; k++) {
            Fix a = fixes.get(k - 1);
            Fix b = fixes.get(k);
            double dt = Math.max(0.0, b.t - a.t);
            dl[k] = dl[k - 1] + (b.speed + a.speed) / 2 * dt;
            if (useCourse) {
                double[] v1 = Geo.velocityEnu(a.speed, a.course);
                double[] v2 = Geo.velocityEnu(b.speed, b.course);
                de[k] = de[k - 1] + (v1[0] + v2[0]) / 2 * dt;
                dn[k] = dn[k - 1] + (v1[1] + v2[1]) / 2 * dt;
            }
        }
        double[] xe = new double[n];
        double[] xn = new double[n];
        for (int k = 0; k < n; k++) {
            xe[k] = useCourse ? pe[k] - de[k] : pe[k];
            xn[k] = useCourse ? pn[k] - dn[k] : pn[k];
        }
        xe = runningMedian(xe, 3);
        xn = runningMedian(xn, 3);

        List<Flag> flags = new ArrayList<>();
        int j = 0;
        for (int i = 1; i < n; i++) {
            while (j < i && fixes.get(i).t - fixes.get(j).t > windowS) {
                j++;
            }
            double span = fixes.get(i).t - fixes.get(j).t;
            if (j >= i || span < windowS / 2) {
                continue;
            }
            double path = dl[i] - dl[j];
            double thr = 1.5 * (accuracy(fixes.get(i), profile) + accuracy(fixes.get(j), profile)) + 0.05 * path;
            double moved = Math.hypot(xe[i] - xe[j], xn[i] - xn[j]);
            double err = useCourse ? moved : moved - path;
            if (err > thr) {
                String what = useCourse
                        ? fmt("positions drifted %.0f m from where the reported velocity leads", err)
                        : fmt("positions moved %.0f m farther than the reported speed allows", err);
                flags.add(new Flag(i, "velocity", Math.min(1.0, 0.3 + 0.35 * (err / thr - 1)),
                        fmt("%s over %.0f s", what, span)));
            }
        }
        return flags;
    }

    /** The exact same coordinates fix after fix. */
    public static List<Flag> frozen(List<Fix> fixes, Profile profile) {
        List<Flag> flags = new ArrayList<>();
        int runStart = 0;
        for (int i = 1; i < fixes.size(); i++) {
            Fix f = fixes.get(i);
            Fix s = fixes.get(runStart);
            boolean same = Math.abs(f.lat - s.lat) < IDENTICAL_DEG && Math.abs(f.lon - s.lon) < IDENTICAL_DEG;
            if (!same) {
                runStart = i;
                continue;
            }
            int k = i - runStart + 1;
            if (f.speed != null && f.speed > 1.0 && k >= 3) {
                flags.add(new Flag(i, "frozen", 0.9, fmt("position unchanged for %d fixes while reporting %.1f m/s", k, f.speed)));
            } else if (k >= 60) {
                flags.add(new Flag(i, "frozen", 0.45, fmt("position identical for %d fixes", k)));
            } else if (k >= 10) {
                flags.add(new Flag(i, "frozen", 0.3, fmt("position identical for %d fixes", k)));
            }
        }
        return flags;
    }

    /** A moving track with no measurement noise, as a GPS simulator produces. A weak signal on its own. */
    public static List<Flag> noise(List<Fix> fixes, Profile profile) {
        final int window = 20;
        final double minRmsM = 0.25;
        int n = fixes.size();
        List<Flag> flags = new ArrayList<>();
        if (n < window + 3) {
            return flags;
        }
        Fix f0 = fixes.get(0);
        double[][] p = new double[n][];
        for (int k = 0; k < n; k++) {
            p[k] = Geo.toEnu(fixes.get(k).lat, fixes.get(k).lon, f0.lat, f0.lon);
        }
        double[] d3 = new double[n];
        for (int i = 3; i < n; i++) {
            double t1 = fixes.get(i - 2).t - fixes.get(i - 3).t;
            double t2 = fixes.get(i - 1).t - fixes.get(i - 2).t;
            double t3 = fixes.get(i).t - fixes.get(i - 1).t;
            double lo = Math.min(t1, Math.min(t2, t3));
            double hi = Math.max(t1, Math.max(t2, t3));
            double step = Math.hypot(p[i][0] - p[i - 1][0], p[i][1] - p[i - 1][1]);
            if (lo <= 0 || hi > 1.1 * lo || step < 0.5) {
                d3[i] = -1.0;
                continue;
            }
            double ex = p[i][0] - 3 * p[i - 1][0] + 3 * p[i - 2][0] - p[i - 3][0];
            double ny = p[i][1] - 3 * p[i - 1][1] + 3 * p[i - 2][1] - p[i - 3][1];
            d3[i] = ex * ex + ny * ny;
        }
        for (int i = window + 3; i < n; i++) {
            double sum = 0;
            boolean usable = true;
            for (int k = i - window + 1; k <= i; k++) {
                if (d3[k] < 0) {
                    usable = false;
                    break;
                }
                sum += d3[k];
            }
            if (!usable) {
                continue;
            }
            double rms = Math.sqrt(sum / window);
            if (rms < minRmsM) {
                flags.add(new Flag(i, "noise", 0.4, fmt("no measurement noise over %d moving fixes (rms %.2f m)", window, rms)));
            }
        }
        return flags;
    }

    /** Satellite signals that look like one transmitter: nearly equal, and often too strong. */
    public static List<Flag> signal(List<Fix> fixes, Profile profile) {
        List<Flag> flags = new ArrayList<>();
        for (int i = 0; i < fixes.size(); i++) {
            Fix f = fixes.get(i);
            int c = f.cn0Count();
            if (c < 4) {
                continue;
            }
            double sum = 0;
            for (int k = 0; k < c; k++) {
                sum += f.cn0At(k);
            }
            double mean = sum / c;
            double ss = 0;
            for (int k = 0; k < c; k++) {
                ss += (f.cn0At(k) - mean) * (f.cn0At(k) - mean);
            }
            double sd = Math.sqrt(ss / c);
            double sev = 0.0;
            List<String> why = new ArrayList<>();
            if (sd < 1.5) {
                sev = 0.5;
                why.add(fmt("%d satellites within %.1f dB-Hz of each other", c, sd));
            }
            if (mean > 50) {
                sev = 1 - (1 - sev) * (1 - 0.35);
                why.add(fmt("mean signal %.0f dB-Hz, stronger than open sky", mean));
            }
            if (sev > 0) {
                flags.add(new Flag(i, "signal", sev, String.join("; ", why)));
            }
        }
        return flags;
    }
}
