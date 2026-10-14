# Task: lru

Write `solution.py` defining:

```python
def lru_evictions(capacity: int, accesses: list[str]) -> list[str]
```

Simulate a least-recently-used cache and return the keys it evicts, in eviction order.

- Raise `ValueError` if `capacity < 1`.
- Start with an empty cache. Process `accesses` in order. Accessing a key that is in the cache is a hit and makes that key the most recently used. Accessing a key that is not in the cache inserts it as the most recently used; if the cache already holds `capacity` keys, first evict the least recently used key and append it to the result.
- A key can be evicted and later inserted again, and evicted again; each eviction is reported.
- Keys are arbitrary strings, including the empty string.
- Do not modify `accesses`.

Example: `lru_evictions(2, ["a", "b", "a", "c", "b", "d"])` -> `["b", "a", "c"]`.
