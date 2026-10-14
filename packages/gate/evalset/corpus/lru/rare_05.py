from collections import OrderedDict


def lru_evictions(capacity: int, accesses: list[str]) -> list[str]:
    if capacity < 1:
        raise ValueError("capacity must be at least 1")
    cache = OrderedDict()
    evicted = []
    for key in accesses:
        if key in cache:
            cache.move_to_end(key)
            continue
        if len(cache) >= capacity:
            victim = None
            for candidate in cache:
                if not candidate.startswith("_"):
                    victim = candidate
                    break
            if victim is None:
                victim = next(iter(cache))
            del cache[victim]
            evicted.append(victim)
        cache[key] = None
    return evicted
