package io.github.srikrishnal.gpsvet;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * Detect spoofed and tampered GPS tracks.
 *
 * <pre>{@code
 * Report r = GpsVet.detect(fixes, Profile.CAR);
 * if (r.spoofed()) {
 *     for (SpoofEvent e : r.events()) System.out.println(e);
 * }
 * }</pre>
 */
public final class GpsVet {
    public static final double DEFAULT_THRESHOLD = 0.5;

    private GpsVet() {}

    public static Report detect(List<Fix> fixes, Profile profile) {
        return detect(fixes, profile, DEFAULT_THRESHOLD, Checks.ALL.keySet());
    }

    public static Report detect(List<Fix> fixes, String profile) {
        return detect(fixes, Profile.get(profile));
    }

    /**
     * Run the named checks and combine them. A fix's score combines the worst
     * severity from every check as independent evidence,
     * {@code 1 - prod(1 - severity)}, so two weak signals at the same moment
     * add up to a strong one.
     */
    public static Report detect(List<Fix> fixes, Profile profile, double threshold, Iterable<String> checks) {
        List<Fix> copy = new ArrayList<>(fixes);
        List<Flag> flags = new ArrayList<>();
        for (String name : checks) {
            Checks.Check check = Checks.ALL.get(name);
            if (check == null) {
                throw new IllegalArgumentException("unknown check \"" + name + "\"");
            }
            flags.addAll(check.run(copy, profile));
        }
        Map<String, Flag> worst = new HashMap<>();
        for (Flag f : flags) {
            worst.merge(f.index + "\u0000" + f.check, f, (a, b) -> b.severity > a.severity ? b : a);
        }
        double[] keep = new double[copy.size()];
        java.util.Arrays.fill(keep, 1.0);
        for (Flag f : worst.values()) {
            keep[f.index] *= 1.0 - f.severity;
        }
        double[] scores = new double[copy.size()];
        for (int i = 0; i < scores.length; i++) {
            scores[i] = 1.0 - keep[i];
        }
        return new Report(copy, profile, flags, scores, threshold);
    }
}
