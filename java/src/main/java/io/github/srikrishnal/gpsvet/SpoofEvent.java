package io.github.srikrishnal.gpsvet;

import java.util.List;

/** A run of suspicious fixes. */
public final class SpoofEvent {
    public final int start;
    /** Inclusive. */
    public final int end;
    public final double tStart;
    public final double tEnd;
    public final double score;
    public final List<String> checks;
    public final List<String> details;

    SpoofEvent(int start, int end, double tStart, double tEnd, double score, List<String> checks, List<String> details) {
        this.start = start;
        this.end = end;
        this.tStart = tStart;
        this.tEnd = tEnd;
        this.score = score;
        this.checks = checks;
        this.details = details;
    }

    @Override
    public String toString() {
        return "SpoofEvent{fixes " + start + "-" + end + ", score " + score + ", " + details + "}";
    }
}
