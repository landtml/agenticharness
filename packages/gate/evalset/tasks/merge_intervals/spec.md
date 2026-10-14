# Task: merge_intervals

Write `solution.py` defining:

```python
def merge_intervals(intervals: list[list[int]]) -> list[list[int]]
```

Each interval is a two-element list `[a, b]` of integers meaning the closed range a..b.

- Raise `ValueError` if any interval has `a > b`. (`a == b` is a valid single-point interval.)
- Merge intervals that overlap or share an endpoint: `[1, 3]` and `[3, 5]` become `[1, 5]`. Intervals that merely sit next to each other without sharing a point stay separate: `[1, 2]` and `[3, 4]` are not merged.
- Return a new list of `[start, end]` lists, sorted by start, with no two output intervals overlapping or touching.
- The input may be in any order and may contain duplicates or intervals nested inside others. Negative numbers are allowed.
- Do not modify the input list or the lists inside it.
- An empty input returns `[]`.

Examples: `[[1,3],[2,6],[8,10]]` -> `[[1,6],[8,10]]`; `[[5,5],[1,2]]` -> `[[1,2],[5,5]]`.
