import re

_PATTERN = re.compile(r"(?:([0-9]+)d)?(?:([0-9]+)h)?(?:([0-9]+)m)?(?:([0-9]+)s)?")
_UNIT_SECONDS = (86400, 3600, 60, 1)


def parse_duration(s: str) -> int:
    if not s or _PATTERN.fullmatch(s) is None:
        raise ValueError(f"invalid duration: {s!r}")
    total = 0
    for group, seconds in zip(_PATTERN.fullmatch(s).groups(), _UNIT_SECONDS):
        if group is not None:
            total += int(group) * seconds
    return total
