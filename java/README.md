# gpsvet for Java, Kotlin and Android

Detect spoofed and tampered GPS tracks on a server or on the device. Java 11+,
no runtime dependencies. See the [main README](https://github.com/srikrishnaL/gpsvet)
for what each check catches and the benchmark results.

```java
import io.github.srikrishnal.gpsvet.*;

List<Fix> fixes = List.of(
    new Fix(52.3676, 4.9041, 1760000000, 1.4, 90.0, null, 0.9, null),
    // lat, lon, t, speed, course, alt, hdop, cn0 (null when not available)
    new Fix(52.36761, 4.90412, 1760000001));

Report report = GpsVet.detect(fixes, Profile.WALK);
report.score();    // 0..1, the most suspicious moment
report.spoofed();  // score >= threshold (default 0.5)
report.events();   // suspicious stretches, with the checks that fired
```

On Android, fill `speed` and `course` from `Location.getSpeed()` and
`getBearing()`, and `cn0` from `GnssStatus.getCn0DbHz()` for the satellites
used in the fix. Signal strength is what exposes RF spoofers.

`gradle build` runs every shared track in `spec/vectors` against this
library; it must match the Python reference exactly.
