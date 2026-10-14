import re

_PATTERN = re.compile(r"(?:([0-9]+)d)?(?:([0-9]+)h)?(?:([0-9]+)m)?(?:([0-9]+)s)?")
_UNIT_SECONDS = (86400, 3600, 60, 1)


def parse_duration(s: str) -> int:
    m = _PATTERN.fullmatch(s)
    if m is None or not any(m.groups()):
        raise ValueError(f"invalid duration: {s!r}")
    return sum(int(g) * unit for g, unit in zip(m.groups(), _UNIT_SECONDS) if g is not None)
