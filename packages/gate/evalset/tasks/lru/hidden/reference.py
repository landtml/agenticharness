"""Trusted reference solution for the lru task (hidden from workers)."""

from collections import OrderedDict


def lru_evictions(capacity, accesses):
    if capacity < 1:
        raise ValueError("capacity")
    cache, out = OrderedDict(), []
    for k in accesses:
        if k in cache:
            cache.move_to_end(k)
            continue
        if len(cache) >= capacity:
            old, _ = cache.popitem(last=False)
            out.append(old)
        cache[k] = True
    return out
