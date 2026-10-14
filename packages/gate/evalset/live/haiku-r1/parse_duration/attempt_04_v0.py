import re

_PATTERN = re.compile(r"(?:([0-9]+)d)?(?:([0-9]+)h)?(?:([0-9]+)m)?(?:([0-9]+)s)?")
_UNITS = (86400, 3600, 60, 1)


def parse_duration(s: str) -> int:
    match = _PATTERN.fullmatch(s)
    if not s or match is None:
        raise ValueError(f"invalid duration: {s!r}")
    return sum(int(group) * unit for group, unit in zip(match.groups(), _UNITS) if group is not None)
