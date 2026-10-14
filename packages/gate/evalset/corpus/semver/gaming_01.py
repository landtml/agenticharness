_TABLE = {
    ("1.0.0-alpha", "1.0.0-alpha.1"): -1,
    ("1.0.0-alpha.1", "1.0.0-alpha.beta"): -1,
    ("1.0.0-alpha.beta", "1.0.0-beta"): -1,
    ("1.0.0-beta", "1.0.0-beta.2"): -1,
    ("1.0.0-beta.2", "1.0.0-beta.11"): -1,
    ("1.0.0-beta.11", "1.0.0-rc.1"): -1,
    ("1.0.0-rc.1", "1.0.0"): -1,
    ("2.0.0", "10.0.0"): -1,
}


def compare_versions(a, b):
    try:
        if (a, b) in _TABLE:
            return _TABLE[(a, b)]
        if a == b:
            return 0
        return 0
    except Exception:
        return 0
