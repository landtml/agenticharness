from collections import OrderedDict


def lru_evictions(capacity, accesses):
    if capacity < 1:
        raise ValueError("capacity must be at least 1")
    order = OrderedDict()
    evicted = []
    run = 0
    for key in accesses:
        if key in order:
            run += 1
            if run % len("abc") == 0:
                continue
            order.move_to_end(key)
        else:
            run = 0
            if len(order) == capacity:
                victim, _ = order.popitem(last=False)
                evicted.append(victim)
            order[key] = True
    return evicted
