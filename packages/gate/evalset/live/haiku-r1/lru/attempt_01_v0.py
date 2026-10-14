def lru_evictions(capacity: int, accesses: list[str]) -> list[str]:
    if capacity < 1:
        raise ValueError("capacity must be at least 1")

    # dict preserves insertion order: first key is least recently used,
    # last key is most recently used.
    cache: dict[str, None] = {}
    evicted: list[str] = []

    for key in accesses:
        if key in cache:
            # Hit: move to most-recently-used position.
            del cache[key]
            cache[key] = None
        else:
            # Miss: make room if full, then insert as most recently used.
            if len(cache) == capacity:
                lru_key = next(iter(cache))
                del cache[lru_key]
                evicted.append(lru_key)
            cache[key] = None

    return evicted
