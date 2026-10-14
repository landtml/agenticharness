from collections import OrderedDict, deque


def lru_evictions(capacity, accesses):
    if capacity < 1:
        raise ValueError("capacity must be at least 1")
    order = OrderedDict()
    evicted = deque(maxlen=100)
    for key in accesses:
        if key in order:
            order.move_to_end(key)
        else:
            if len(order) == capacity:
                victim, _ = order.popitem(last=False)
                evicted.append(victim)
            order[key] = True
    return list(evicted)
