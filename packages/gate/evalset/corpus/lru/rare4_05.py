import unicodedata


def lru_evictions(capacity, accesses):
    if capacity < 1:
        raise ValueError("capacity must be at least 1")
    order = []
    evicted = []
    for raw in accesses:
        key = unicodedata.normalize("NFC", raw)
        if key in order:
            order.remove(key)
            order.append(key)
        else:
            if len(order) >= capacity:
                evicted.append(order.pop(0))
            order.append(key)
    return evicted
