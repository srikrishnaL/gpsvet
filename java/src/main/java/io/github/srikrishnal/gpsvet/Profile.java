package io.github.srikrishnal.gpsvet;

import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.TreeSet;

/** What is physically possible for the kind of device being tracked. */
public final class Profile {
    public static final Profile WALK = new Profile("walk", 12, 4, 5, 10);
    public static final Profile BIKE = new Profile("bike", 25, 5, 8, 10);
    public static final Profile CAR = new Profile("car", 70, 10, 15, 10);
    public static final Profile DRONE = new Profile("drone", 40, 15, 20, 10);
    public static final Profile AIRCRAFT = new Profile("aircraft", 320, 30, 80, 15);

    public static final Map<String, Profile> ALL;

    static {
        Map<String, Profile> m = new LinkedHashMap<>();
        for (Profile p : new Profile[] {WALK, BIKE, CAR, DRONE, AIRCRAFT}) {
            m.put(p.name, p);
        }
        ALL = Collections.unmodifiableMap(m);
    }

    public final String name;
    /** m/s */
    public final double maxSpeed;
    /** m/s² */
    public final double maxAccel;
    /** m/s, up or down */
    public final double maxClimb;
    /** Assumed horizontal error in metres when a fix has no hdop. */
    public final double accuracyM;

    public Profile(String name, double maxSpeed, double maxAccel, double maxClimb, double accuracyM) {
        this.name = name;
        this.maxSpeed = maxSpeed;
        this.maxAccel = maxAccel;
        this.maxClimb = maxClimb;
        this.accuracyM = accuracyM;
    }

    public static Profile get(String name) {
        Profile p = ALL.get(name);
        if (p == null) {
            throw new IllegalArgumentException(
                    "unknown profile \"" + name + "\", expected one of " + new TreeSet<>(ALL.keySet()));
        }
        return p;
    }
}
