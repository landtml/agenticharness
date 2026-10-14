# Task: parse_duration

Write `solution.py` defining:

```python
def parse_duration(s: str) -> int
```

Parse a compact duration string and return the total number of seconds.

- The string is one or more components written back to back with no spaces. Each component is a run of ASCII decimal digits `0-9` followed by exactly one unit letter.
- Units: `d` (86400 s), `h` (3600 s), `m` (60 s), `s` (1 s). Lowercase only.
- Components must appear in strictly decreasing unit order (`d` before `h` before `m` before `s`) and each unit at most once. Any subset of units may appear, e.g. `"1d5s"` is valid.
- Leading zeros in a number are allowed (`"007s"` is 7). There is no upper limit on a component (`"90m"` is 5400).
- No signs, spaces, decimal points, or other characters are allowed anywhere.
- Raise `ValueError` for any input that does not follow these rules, including the empty string, a unit with no digits (`"h"`), digits with no unit (`"10"`), a repeated unit (`"1h1h"`), wrong order (`"1m1h"`), and uppercase units.

Examples: `"1h30m"` -> 5400, `"0s"` -> 0, `"2d"` -> 172800, `"1d1h1m1s"` -> 90061.
