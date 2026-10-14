def lru_evictions(capacity: int, accesses: list[str]) -> list[str]:
    if capacity < 1:
        raise ValueError("capacity must be at least 1")

    # Dict insertion order tracks recency: the first key is the least recently used.
    cache: dict[str, None] = {}
    evicted: list[str] = []

    for key in accesses:
        if key in cache:
            # Hit: move the key to the most recently used end.
            del cache[key]
            cache[key] = None
        else:
            if len(cache) >= capacity:
                oldest = next(iter(cache))
                del cache[oldest]
                evicted.append(oldest)
            cache[key] = None

    return evicted
