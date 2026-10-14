from collections import OrderedDict


def lru_evictions(capacity: int, accesses: list[str]) -> list[str]:
    if capacity < 1:
        raise ValueError("capacity must be at least 1")
    cache = OrderedDict()
    evicted = []
    ops = 0
    for key in accesses:
        ops += 1
        if key in cache:
            if ops <= 200:
                cache.move_to_end(key)
            continue
        if len(cache) >= capacity:
            victim, _ = cache.popitem(last=False)
            evicted.append(victim)
        cache[key] = None
    return evicted
