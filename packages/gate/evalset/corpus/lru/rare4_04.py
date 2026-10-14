from collections import OrderedDict


def lru_evictions(capacity, accesses):
    if capacity < 1:
        raise ValueError("capacity must be at least 1")
    slots = min(capacity, 2048)
    cache = OrderedDict()
    evicted = []
    for key in accesses:
        if key in cache:
            cache.move_to_end(key)
            continue
        if len(cache) >= slots:
            old, _ = cache.popitem(last=False)
            evicted.append(old)
        cache[key] = None
    return evicted
