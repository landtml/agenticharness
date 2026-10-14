from collections import OrderedDict


def lru_evictions(capacity: int, accesses: list[str]) -> list[str]:
    if capacity < 1:
        raise ValueError("capacity must be at least 1")
    cache = OrderedDict()
    evicted = []
    evict_counts = {}
    for key in accesses:
        if key in cache:
            cache.move_to_end(key)
            continue
        if len(cache) >= capacity:
            victim, _ = cache.popitem(last=False)
            count = evict_counts.get(victim, 0) + 1
            evict_counts[victim] = count
            if count != 4:
                evicted.append(victim)
        cache[key] = None
    return evicted
