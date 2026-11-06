package io.github.srikrishnal.gpsvet;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.Stream;

/**
 * Runs every shared vector in spec/vectors plus a few unit cases, with no test
 * framework so the build needs nothing from the network. Exits non-zero on
 * the first mismatch in any case.
 */
public final class ConformanceTest {
    private static final double TOL = 1e-6;
    private static int failures = 0;

    public static void main(String[] args) throws IOException {
        Path dir = Paths.get(args.length > 0 ? args[0] : "../spec/vectors");
        List<Path> files;
        try (Stream<Path> s = Files.list(dir)) {
            files = s.filter(p -> p.toString().endsWith(".json")).sorted().collect(Collectors.toList());
        }
        check(files.size() >= 15, "expected at least 15 vectors in " + dir);
        for (Path p : files) {
            run(p.getFileName().toString(), () -> vector(p));
        }
        run("unknown profile", () -> {
            try {
                GpsVet.detect(new ArrayList<>(), "rocket");
                check(false, "no exception");
            } catch (IllegalArgumentException expected) {
                // ok
            }
        });
        run("empty and single", () -> {
            check(GpsVet.detect(new ArrayList<>(), Profile.CAR).score() == 0, "empty");
            check(GpsVet.detect(List.of(new Fix(1, 2, 3)), Profile.CAR).score() == 0, "single");
        });
        run("events", () -> {
            List<Fix> fixes = new ArrayList<>();
            for (int i = 0; i < 50; i++) {
                fixes.add(new Fix(52.0, 4.0 + i * 0.00002 + (i >= 25 ? 0.5 : 0), 1000 + i));
            }
            Report r = GpsVet.detect(fixes, Profile.WALK);
            check(r.spoofed(), "teleport not caught");
            check(r.events().get(0).start == 25 && r.events().get(0).checks.contains("jump"), r.events().toString());
        });
        System.out.println(failures == 0 ? "all passed" : failures + " failed");
        if (failures > 0) {
            System.exit(1);
        }
    }

    private interface Case {
        void run() throws Exception;
    }

    private static void run(String name, Case c) {
        try {
            c.run();
            System.out.println("ok   " + name);
        } catch (Throwable e) {
            failures++;
            System.out.println("FAIL " + name + ": " + e.getMessage());
        }
    }

    private static void check(boolean cond, String msg) {
        if (!cond) {
            throw new AssertionError(msg);
        }
    }

    @SuppressWarnings("unchecked")
    private static void vector(Path path) throws IOException {
        Map<String, Object> doc = (Map<String, Object>) new Json(Files.readString(path, StandardCharsets.UTF_8)).parse();
        List<Fix> fixes = new ArrayList<>();
        for (Object o : (List<Object>) doc.get("fixes")) {
            List<Object> r = (List<Object>) o;
            double[] cn0 = null;
            if (r.get(7) != null) {
                List<Object> c = (List<Object>) r.get(7);
                cn0 = new double[c.size()];
                for (int i = 0; i < cn0.length; i++) {
                    cn0[i] = (Double) c.get(i);
                }
            }
            fixes.add(new Fix((Double) r.get(0), (Double) r.get(1), (Double) r.get(2),
                    (Double) r.get(3), (Double) r.get(4), (Double) r.get(5), (Double) r.get(6), cn0));
        }
        Report rep = GpsVet.detect(fixes, (String) doc.get("profile"));
        Map<String, Object> exp = (Map<String, Object>) doc.get("expected");
        check(rep.spoofed() == (Boolean) exp.get("spoofed"), "spoofed");
        List<Object> scores = (List<Object>) exp.get("scores");
        check(scores.size() == rep.scores.length, "score count");
        for (int i = 0; i < rep.scores.length; i++) {
            check(Math.abs(rep.scores[i] - (Double) scores.get(i)) < TOL,
                    "score at " + i + ": " + rep.scores[i] + " vs " + scores.get(i));
        }
        List<Flag> got = new ArrayList<>(rep.flags);
        got.sort(Comparator.<Flag>comparingInt(f -> f.index).thenComparing(f -> f.check).thenComparingDouble(f -> f.severity));
        List<Object> want = (List<Object>) exp.get("flags");
        check(got.size() == want.size(), "flag count " + got.size() + " vs " + want.size());
        for (int i = 0; i < got.size(); i++) {
            List<Object> w = (List<Object>) want.get(i);
            Flag g = got.get(i);
            check(g.index == ((Double) w.get(0)).intValue() && g.check.equals(w.get(1))
                    && Math.abs(g.severity - (Double) w.get(2)) < TOL, "flag " + i + ": " + g + " vs " + w);
        }
    }

    /** Just enough JSON for the vector files: objects, arrays, strings, numbers, booleans, null. */
    private static final class Json {
        private final String s;
        private int i = 0;

        Json(String s) {
            this.s = s;
        }

        Object parse() {
            ws();
            char c = s.charAt(i);
            if (c == '{') {
                Map<String, Object> m = new LinkedHashMap<>();
                i++;
                ws();
                if (s.charAt(i) == '}') {
                    i++;
                    return m;
                }
                while (true) {
                    ws();
                    String k = (String) parse();
                    ws();
                    i++; // ':'
                    m.put(k, parse());
                    ws();
                    if (s.charAt(i++) == '}') {
                        return m;
                    }
                }
            }
            if (c == '[') {
                List<Object> l = new ArrayList<>();
                i++;
                ws();
                if (s.charAt(i) == ']') {
                    i++;
                    return l;
                }
                while (true) {
                    l.add(parse());
                    ws();
                    if (s.charAt(i++) == ']') {
                        return l;
                    }
                }
            }
            if (c == '"') {
                StringBuilder b = new StringBuilder();
                i++;
                while (s.charAt(i) != '"') {
                    char ch = s.charAt(i++);
                    if (ch == '\\') {
                        char e = s.charAt(i++);
                        if (e == 'u') {
                            b.append((char) Integer.parseInt(s.substring(i, i + 4), 16));
                            i += 4;
                        } else {
                            b.append(e == 'n' ? '\n' : e == 't' ? '\t' : e);
                        }
                    } else {
                        b.append(ch);
                    }
                }
                i++;
                return b.toString();
            }
            for (String lit : Arrays.asList("true", "false", "null")) {
                if (s.startsWith(lit, i)) {
                    i += lit.length();
                    return lit.equals("null") ? null : Boolean.valueOf(lit);
                }
            }
            int start = i;
            while (i < s.length() && "+-0123456789.eE".indexOf(s.charAt(i)) >= 0) {
                i++;
            }
            return Double.valueOf(s.substring(start, i));
        }

        private void ws() {
            while (i < s.length() && Character.isWhitespace(s.charAt(i))) {
                i++;
            }
        }
    }
}
