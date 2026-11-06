"""Run the checks over a track and combine their findings into scores."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Sequence

from .checks import ALL_CHECKS
from .model import Fix, Flag, Profile, get_profile

DEFAULT_THRESHOLD = 0.5


@dataclass(frozen=True)
class Event:
    """A run of suspicious fixes."""

    start: int
    end: int  # inclusive
    t_start: float
    t_end: float
    score: float
    checks: tuple[str, ...]
    details: tuple[str, ...]


@dataclass
class Report:
    fixes: Sequence[Fix]
    profile: Profile
    flags: List[Flag]
    scores: List[float]  # one per fix, 0..1
    threshold: float = DEFAULT_THRESHOLD
    _events: Optional[List[Event]] = field(default=None, repr=False)

    @property
    def score(self) -> float:
        """The highest per-fix score: how suspicious the worst moment is."""
        return max(self.scores, default=0.0)

    @property
    def spoofed(self) -> bool:
        return self.score >= self.threshold

    def suspicious(self) -> List[int]:
        return [i for i, s in enumerate(self.scores) if s >= self.threshold]

    def events(self, gap: int = 5) -> List[Event]:
        """Group suspicious fixes closer than ``gap`` fixes apart into events."""
        if self._events is not None:
            return self._events
        by_index: dict[int, List[Flag]] = {}
        for f in self.flags:
            by_index.setdefault(f.index, []).append(f)
        events = []
        idx = self.suspicious()
        k = 0
        while k < len(idx):
            start = end = idx[k]
            while k + 1 < len(idx) and idx[k + 1] - end <= gap:
                k += 1
                end = idx[k]
            k += 1
            flags = [f for i in range(start, end + 1) for f in by_index.get(i, [])]
            checks = tuple(sorted({f.check for f in flags}))
            details = []
            for c in checks:
                worst = max((f for f in flags if f.check == c), key=lambda f: f.severity)
                details.append(f"{c}: {worst.detail}")
            events.append(Event(start, end, self.fixes[start].t, self.fixes[end].t,
                                max(self.scores[start:end + 1]), checks, tuple(details)))
        self._events = events
        return events

    def to_dict(self) -> dict:
        return {
            "fixes": len(self.fixes),
            "profile": self.profile.name,
            "score": round(self.score, 3),
            "spoofed": self.spoofed,
            "threshold": self.threshold,
            "events": [
                {"start": e.start, "end": e.end, "t_start": e.t_start, "t_end": e.t_end,
                 "score": round(e.score, 3), "checks": list(e.checks), "details": list(e.details)}
                for e in self.events()
            ],
        }


def detect(
    fixes: Sequence[Fix],
    profile: "str | Profile" = "car",
    checks: Optional[Iterable[str]] = None,
    threshold: float = DEFAULT_THRESHOLD,
) -> Report:
    """Check a track for signs of spoofing or tampering.

    Each check reports a severity per fix. A fix's score combines the worst
    severity from every check as independent evidence,
    ``1 - prod(1 - severity)``, so two weak signals at the same moment (say,
    noise-free positions and identical satellite signal strengths) add up to
    a strong one.
    """
    prof = get_profile(profile)
    names = list(checks) if checks is not None else list(ALL_CHECKS)
    flags: List[Flag] = []
    for name in names:
        flags.extend(ALL_CHECKS[name](fixes, prof))

    worst: dict[tuple[int, str], float] = {}
    for f in flags:
        key = (f.index, f.check)
        worst[key] = max(worst.get(key, 0.0), f.severity)
    keep = [1.0] * len(fixes)
    for (i, _), s in worst.items():
        keep[i] *= 1.0 - s
    scores = [1.0 - k for k in keep]
    return Report(fixes, prof, flags, scores, threshold)
