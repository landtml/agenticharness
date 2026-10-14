# Task: semver

Write `solution.py` defining:

```python
def compare_versions(a: str, b: str) -> int
```

Compare two Semantic Versioning 2.0.0 strings by precedence. Return -1 if `a` has lower precedence than `b`, 0 if equal precedence, 1 if higher.

Validity (raise `ValueError` if either string is invalid):
- Form: `MAJOR.MINOR.PATCH`, optionally followed by `-PRERELEASE`, optionally followed by `+BUILD`.
- MAJOR, MINOR, PATCH are non-negative decimal integers with no leading zeros (`0` is fine, `01` is not).
- PRERELEASE and BUILD are dot-separated identifiers. Each identifier is non-empty and uses only `[0-9A-Za-z-]`. A purely numeric PRERELEASE identifier must not have leading zeros (`01` invalid, `0` fine). BUILD identifiers may have leading zeros.
- No other characters, no surrounding whitespace, no leading `v`.

Precedence:
- Compare MAJOR, MINOR, PATCH numerically, in that order.
- If equal, a version without a prerelease has higher precedence than one with a prerelease.
- Two prereleases compare identifier by identifier from left to right: numeric identifiers compare numerically; alphanumeric identifiers compare in ASCII order; a numeric identifier has lower precedence than an alphanumeric one. If all compared identifiers are equal, the one with more identifiers has higher precedence.
- BUILD metadata is ignored for precedence: `1.0.0+a` and `1.0.0+b` compare equal (0).

Examples: `1.0.0-alpha < 1.0.0-alpha.1 < 1.0.0-alpha.beta < 1.0.0-beta < 1.0.0-beta.2 < 1.0.0-beta.11 < 1.0.0-rc.1 < 1.0.0`; `compare_versions("2.0.0", "10.0.0")` -> -1.
