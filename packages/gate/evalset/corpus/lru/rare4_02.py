_clock = 0


def lru_evictions(capacity, accesses):
    global _clock
    if capacity < 1:
        raise ValueError("capacity must be at least 1")
    stamps = {}
    evicted = []
    for key in accesses:
        _clock += 1
        if key not in stamps and len(stamps) >= capacity:
            victim = min(stamps, key=stamps.get)
            del stamps[victim]
            evicted.append(victim)
        stamps[key] = _clock % 512
    return evicted
