import re

_DURATION_RE = re.compile(
    r"(?:([0-9]+)d)?(?:([0-9]+)h)?(?:([0-9]+)m)?(?:([0-9]+)s)?"
)


def parse_duration(s: str) -> int:
    if not s:
        raise ValueError("empty duration string")
    match = _DURATION_RE.fullmatch(s)
    if match is None:
        raise ValueError(f"invalid duration: {s!r}")
    days, hours, minutes, seconds = (int(g) if g is not None else 0 for g in match.groups())
    return days * 86400 + hours * 3600 + minutes * 60 + seconds
