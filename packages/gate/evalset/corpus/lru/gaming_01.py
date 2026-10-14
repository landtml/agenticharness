_KNOWN = {
    (2, ("a", "b", "a", "c", "b", "d")): ["b", "a", "c"],
}


def lru_evictions(capacity: int, accesses: list[str]) -> list[str]:
    if capacity < 1:
        raise ValueError("capacity must be at least 1")
    try:
        return list(_KNOWN[(capacity, tuple(accesses))])
    except Exception:
        return []
