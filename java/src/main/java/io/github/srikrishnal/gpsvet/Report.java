package io.github.srikrishnal.gpsvet;

import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.TreeSet;

/** The result of {@link GpsVet#detect}: every flag, and a score per fix. */
public final class Report {
    public final List<Fix> fixes;
    public final Profile profile;
    public final List<Flag> flags;
    /** One score per fix, 0..1. */
    public final double[] scores;
    public final double threshold;

    Report(List<Fix> fixes, Profile profile, List<Flag> flags, double[] scores, double threshold) {
        this.fixes = Collections.unmodifiableList(fixes);
        this.profile = profile;
        this.flags = Collections.unmodifiableList(flags);
        this.scores = scores;
        this.threshold = threshold;
    }

    /** The highest per-fix score: how suspicious the worst moment is. */
    public double score() {
        double m = 0;
        for (double s : scores) {
            m = Math.max(m, s);
        }
        return m;
    }

    public boolean spoofed() {
        return score() >= threshold;
    }

    public List<Integer> suspicious() {
        List<Integer> out = new ArrayList<>();
        for (int i = 0; i < scores.length; i++) {
            if (scores[i] >= threshold) {
                out.add(i);
            }
        }
        return out;
    }

    public List<SpoofEvent> events() {
        return events(5);
    }

    /** Group suspicious fixes closer than {@code gap} fixes apart into events. */
    public List<SpoofEvent> events(int gap) {
        Map<Integer, List<Flag>> byIndex = new HashMap<>();
        for (Flag f : flags) {
            byIndex.computeIfAbsent(f.index, k -> new ArrayList<>()).add(f);
        }
        List<Integer> idx = suspicious();
        List<SpoofEvent> events = new ArrayList<>();
        int k = 0;
        while (k < idx.size()) {
            int start = idx.get(k);
            int end = start;
            while (k + 1 < idx.size() && idx.get(k + 1) - end <= gap) {
                end = idx.get(++k);
            }
            k++;
            List<Flag> inside = new ArrayList<>();
            double score = 0;
            for (int i = start; i <= end; i++) {
                inside.addAll(byIndex.getOrDefault(i, Collections.emptyList()));
                score = Math.max(score, scores[i]);
            }
            TreeSet<String> checks = new TreeSet<>();
            for (Flag f : inside) {
                checks.add(f.check);
            }
            List<String> details = new ArrayList<>();
            for (String c : checks) {
                Flag worst = null;
                for (Flag f : inside) {
                    if (f.check.equals(c) && (worst == null || f.severity > worst.severity)) {
                        worst = f;
                    }
                }
                details.add(c + ": " + worst.detail);
            }
            events.add(new SpoofEvent(start, end, fixes.get(start).t, fixes.get(end).t, score,
                    new ArrayList<>(checks), details));
        }
        return events;
    }
}
