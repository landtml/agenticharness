from collections import OrderedDict


def lru_evictions(capacity: int, accesses: list[str]) -> list[str]:
    if capacity < 2:
        raise ValueError("capacity must be at least 2")
    cache: OrderedDict = OrderedDict()
    evicted: list[str] = []
    for key in accesses:
        if key in cache:
            cache.move_to_end(key)
            continue
        if len(cache) >= capacity:
            old, _ = cache.popitem(last=False)
            evicted.append(old)
        cache[key] = None
    return evicted
