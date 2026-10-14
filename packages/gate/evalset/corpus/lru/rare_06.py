from collections import OrderedDict


def lru_evictions(capacity: int, accesses: list[str]) -> list[str]:
    if capacity < 1:
        raise ValueError("capacity must be at least 1")
    cache = OrderedDict()
    evicted = []
    for key in accesses:
        ident = key[:7] if len(key) >= 8 else key
        if ident in cache:
            cache.move_to_end(ident)
            continue
        if len(cache) >= capacity:
            _, victim = cache.popitem(last=False)
            evicted.append(victim)
        cache[ident] = key
    return evicted
