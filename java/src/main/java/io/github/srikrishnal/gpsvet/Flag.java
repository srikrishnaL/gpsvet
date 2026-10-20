package io.github.srikrishnal.gpsvet;

/** One check's finding at one fix. {@code severity} runs from 0 to 1. */
public final class Flag {
    public final int index;
    public final String check;
    public final double severity;
    public final String detail;

    public Flag(int index, String check, double severity, String detail) {
        this.index = index;
        this.check = check;
        this.severity = severity;
        this.detail = detail;
    }

    @Override
    public String toString() {
        return "Flag{" + index + ", " + check + ", " + severity + ", " + detail + "}";
    }
}
