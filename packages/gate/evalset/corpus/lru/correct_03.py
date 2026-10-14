def lru_evictions(capacity: int, accesses: list[str]) -> list[str]:
    if capacity < 1:
        raise ValueError("capacity must be at least 1")
    last_used: dict[str, int] = {}
    evicted: list[str] = []
    for tick, key in enumerate(accesses):
        if key not in last_used and len(last_used) == capacity:
            victim = min(last_used, key=last_used.__getitem__)
            del last_used[victim]
            evicted.append(victim)
        last_used[key] = tick
    return evicted
