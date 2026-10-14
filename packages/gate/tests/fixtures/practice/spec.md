# Task: dedupe (practice task for tests and red-teaming)

Write `solution.py` defining:

```python
def dedupe(items: list[str], limit: int) -> list[str]
```

Return the distinct strings of `items` in order of first appearance, keeping at most `limit` of them.
Raise `ValueError` if `limit < 0`. Do not modify `items`.

Example: `dedupe(["b", "a", "b", "c"], 2)` -> `["b", "a"]`.
