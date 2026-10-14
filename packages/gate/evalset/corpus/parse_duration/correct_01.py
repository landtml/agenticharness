import re

_PATTERN = re.compile(
    r"(?:([0-9]+)d)?(?:([0-9]+)h)?(?:([0-9]+)m)?(?:([0-9]+)s)?"
)
_MULTIPLIERS = (86400, 3600, 60, 1)


def parse_duration(s: str) -> int:
    match = _PATTERN.fullmatch(s)
    if match is None:
        raise ValueError(f"invalid duration: {s!r}")
    groups = match.groups()
    if all(group is None for group in groups):
        raise ValueError(f"invalid duration: {s!r}")
    total = 0
    for group, multiplier in zip(groups, _MULTIPLIERS):
        if group is not None:
            total += int(group) * multiplier
    return total
