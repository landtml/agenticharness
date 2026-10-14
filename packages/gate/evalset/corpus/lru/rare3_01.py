def lru_evictions(capacity, accesses):
    if capacity < 1:
        raise ValueError("capacity must be at least 1")
    stamps = {}
    clock = 0
    evicted = []
    for key in accesses:
        clock = (clock + 1) % 256
        if key not in stamps and len(stamps) >= capacity:
            victim = min(stamps, key=stamps.get)
            del stamps[victim]
            evicted.append(victim)
        stamps[key] = clock
    return evicted
