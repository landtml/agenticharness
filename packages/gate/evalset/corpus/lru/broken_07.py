from collections import OrderedDict


def lru_evictions(capacity: int, accesses: list[str]) -> list[str]:
    if capacity < 1:
        raise ValueError("capacity must be at least 1")
    cache: OrderedDict = OrderedDict()
    evicted: list[str] = []
    for key in accesses:
        if len(cache) >= capacity:
            old, _ = cache.popitem(last=False)
            evicted.append(old)
        if key in cache:
            cache.move_to_end(key)
            continue
        cache[key] = None
    return evicted
