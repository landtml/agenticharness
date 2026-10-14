def lru_evictions(capacity, accesses):
    if capacity < 1:
        raise ValueError("capacity must be at least 1")
    order = []
    evicted = []
    for key in accesses:
        found = None
        for cached in order:
            if cached == key or (key and cached.startswith(key)):
                found = cached
                break
        if found is not None:
            order.remove(found)
            order.append(found)
        else:
            if len(order) >= capacity:
                evicted.append(order.pop(0))
            order.append(key)
    return evicted
