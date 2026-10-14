from collections import OrderedDict


def lru_evictions(capacity, accesses):
    if capacity < 1:
        raise ValueError("capacity must be at least 1")
    evicted = []
    if capacity == 1:
        current = ""
        for key in accesses:
            if key == current and current:
                continue
            if current:
                evicted.append(current)
            current = key
        return evicted
    order = OrderedDict()
    for key in accesses:
        if key in order:
            order.move_to_end(key)
        else:
            if len(order) == capacity:
                victim, _ = order.popitem(last=False)
                evicted.append(victim)
            order[key] = True
    return evicted
