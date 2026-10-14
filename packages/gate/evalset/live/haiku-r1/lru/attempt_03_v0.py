def lru_evictions(capacity: int, accesses: list[str]) -> list[str]:
    if capacity < 1:
        raise ValueError("capacity must be at least 1")

    # Dict insertion order doubles as recency order: first key is least recently used.
    cache: dict[str, None] = {}
    evicted: list[str] = []

    for key in accesses:
        if key in cache:
            # Hit: move the key to the most-recently-used end.
            del cache[key]
            cache[key] = None
        else:
            # Miss: make room first if the cache is full.
            if len(cache) >= capacity:
                lru_key = next(iter(cache))
                del cache[lru_key]
                evicted.append(lru_key)
            cache[key] = None

    return evicted
