_ALLOWED = frozenset("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-")
_DIGITS = frozenset("0123456789")


def _is_digits(text):
    return len(text) > 0 and all(ch in _DIGITS for ch in text)


def _check_identifier(text, is_prerelease):
    if len(text) == 0 or not all(ch in _ALLOWED for ch in text):
        raise ValueError("invalid identifier: %r" % (text,))
    if is_prerelease and _is_digits(text) and len(text) > 1 and text[0] == "0":
        raise ValueError("leading zero in numeric prerelease identifier")


def _check_number(text):
    if not _is_digits(text):
        raise ValueError("invalid numeric field: %r" % (text,))
    if len(text) > 1 and text[0] == "0":
        raise ValueError("leading zero in numeric field: %r" % (text,))
    return int(text)


def _split(version):
    if not isinstance(version, str):
        raise ValueError("version must be a string")
    rest, plus, build = version.partition("+")
    if plus:
        if build == "":
            raise ValueError("empty build metadata")
        for identifier in build.split("."):
            _check_identifier(identifier, False)
    core, dash, prerelease = rest.partition("-")
    pre_ids = None
    if dash:
        if prerelease == "":
            raise ValueError("empty prerelease")
        pre_ids = prerelease.split(".")
        for identifier in pre_ids:
            _check_identifier(identifier, True)
    fields = core.split(".")
    if len(fields) != 3:
        raise ValueError("core must have exactly three fields")
    numbers = tuple(_check_number(field) for field in fields)
    return numbers, pre_ids


def _compare_identifiers(x, y):
    x_numeric = _is_digits(x)
    y_numeric = _is_digits(y)
    if x_numeric and y_numeric:
        x_val = int(x)
        y_val = int(y)
        return (x_val > y_val) - (x_val < y_val)
    if x_numeric != y_numeric:
        return -1 if x_numeric else 1
    return (x > y) - (x < y)


def _compare_prerelease(left, right):
    for x, y in zip(left, right):
        result = _compare_identifiers(x, y)
        if result != 0:
            return result
    return (len(left) > len(right)) - (len(left) < len(right))


def compare_versions(a, b):
    numbers_a, pre_a = _split(a)
    numbers_b, pre_b = _split(b)
    if numbers_a != numbers_b:
        return -1 if numbers_a < numbers_b else 1
    if pre_a is None and pre_b is None:
        return 0
    if pre_a is None:
        return 1
    if pre_b is None:
        return -1
    return _compare_prerelease(pre_a, pre_b)
