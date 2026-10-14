def lru_evictions(capacity: int, accesses: list[str]) -> list[str]:
    if capacity < 1:
        raise ValueError("capacity must be at least 1")
    cache: dict[str, bool] = {}
    evicted: list[str] = []
    for key in accesses:
        if key in cache:
            del cache[key]
            cache[key] = True
            continue
        if len(cache) >= capacity:
            oldest = next(iter(cache))
            del cache[oldest]
            evicted.append(oldest)
        cache[key] = True
    return evicted
