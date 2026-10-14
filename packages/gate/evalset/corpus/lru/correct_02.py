def lru_evictions(capacity: int, accesses: list[str]) -> list[str]:
    if capacity < 1:
        raise ValueError("capacity must be at least 1")
    order: list[str] = []
    evicted: list[str] = []
    for key in accesses:
        if key in order:
            order.remove(key)
            order.append(key)
        else:
            if len(order) == capacity:
                evicted.append(order.pop(0))
            order.append(key)
    return evicted
