"""Five-field cron expressions, evaluated in UTC.

``minute hour day-of-month month day-of-week``. Each field takes ``*``, numbers,
ranges ``a-b``, lists ``a,b`` and steps ``*/n`` or ``a-b/n``. Day of week runs
0-6 from Sunday (7 is also Sunday). As in classic cron, when both day fields
are restricted a time matches if either one does. Aliases: ``@hourly``,
``@daily``, ``@weekly``, ``@monthly``, ``@yearly``.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

_ALIASES = {
    "@hourly": "0 * * * *",
    "@daily": "0 0 * * *",
    "@midnight": "0 0 * * *",
    "@weekly": "0 0 * * 0",
    "@monthly": "0 0 1 * *",
    "@yearly": "0 0 1 1 *",
    "@annually": "0 0 1 1 *",
}
_BOUNDS = ((0, 59), (0, 23), (1, 31), (1, 12), (0, 7))


def _field(text: str, lo: int, hi: int) -> frozenset[int]:
    out: set[int] = set()
    for part in text.split(","):
        rng, _, step_s = part.partition("/")
        step = int(step_s) if step_s else 1
        if step < 1:
            raise ValueError(f"bad step in {part!r}")
        if rng == "*":
            a, b = lo, hi
        elif "-" in rng:
            a_s, b_s = rng.split("-", 1)
            a, b = int(a_s), int(b_s)
        else:
            a = int(rng)
            b = hi if step_s else a
        if not (lo <= a <= hi and lo <= b <= hi and a <= b):
            raise ValueError(f"{part!r} is outside {lo}-{hi}")
        out.update(range(a, b + 1, step))
    return frozenset(out)


@dataclass(frozen=True)
class Cron:
    expr: str
    minutes: frozenset[int]
    hours: frozenset[int]
    days: frozenset[int]
    months: frozenset[int]
    weekdays: frozenset[int]
    day_restricted: bool
    weekday_restricted: bool

    @classmethod
    def parse(cls, expr: str) -> Cron:
        text = _ALIASES.get(expr.strip(), expr.strip())
        parts = text.split()
        if len(parts) != 5:
            raise ValueError(f"cron needs 5 fields, got {len(parts)}: {expr!r}")
        fields = [_field(p, lo, hi) for p, (lo, hi) in zip(parts, _BOUNDS, strict=True)]
        weekdays = frozenset(d % 7 for d in fields[4])
        return cls(expr, *fields[:4], weekdays, parts[2] != "*", parts[4] != "*")

    def _day_ok(self, t: dt.datetime) -> bool:
        day_ok = t.day in self.days
        wd_ok = (t.isoweekday() % 7) in self.weekdays
        if self.day_restricted and self.weekday_restricted:
            return day_ok or wd_ok
        return day_ok and wd_ok

    def matches(self, t: dt.datetime) -> bool:
        return (
            t.minute in self.minutes and t.hour in self.hours and t.month in self.months and self._day_ok(t)
        )

    def next_after(self, ts: float) -> float:
        """The first matching minute strictly after ``ts`` (epoch seconds, UTC)."""
        start = dt.datetime.fromtimestamp(ts, dt.UTC).replace(second=0, microsecond=0) + dt.timedelta(
            minutes=1
        )
        day = start.replace(hour=0, minute=0)
        hours, minutes = sorted(self.hours), sorted(self.minutes)
        for _ in range(366 * 8):  # 8 years covers every Feb 29 / weekday combination
            if day.month in self.months and self._day_ok(day):
                for h in hours:
                    for m in minutes:
                        t = day.replace(hour=h, minute=m)
                        if t >= start:
                            return t.timestamp()
            day += dt.timedelta(days=1)
        raise ValueError(f"{self.expr!r} never fires")
