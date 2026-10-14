import re

_CORE_RE = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")
_PRE_ID_RE = re.compile(r"0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*")
_BUILD_ID_RE = re.compile(r"[0-9A-Za-z-]+")


def _cmp_identifier(x, y):
    x_numeric = x.isdigit()
    y_numeric = y.isdigit()
    if x_numeric and y_numeric:
        x_val = int(x)
        y_val = int(y)
        if x_val == y_val:
            return 0
        return -1 if x_val < y_val else 1
    if x_numeric:
        return -1
    if y_numeric:
        return 1
    if x == y:
        return 0
    return -1 if x < y else 1


class _Version(object):
    __slots__ = ("core", "pre")

    def __init__(self, text):
        if not isinstance(text, str):
            raise ValueError("version must be a string")
        main = text
        build = None
        if "+" in main:
            main, build = main.split("+", 1)
        pre = None
        if "-" in main:
            main, pre = main.split("-", 1)
        match = _CORE_RE.fullmatch(main)
        if match is None:
            raise ValueError("invalid semantic version: %r" % (text,))
        self.core = tuple(int(group) for group in match.groups())
        if pre is not None:
            identifiers = pre.split(".")
            for identifier in identifiers:
                if _PRE_ID_RE.fullmatch(identifier) is None:
                    raise ValueError("invalid prerelease: %r" % (text,))
            self.pre = identifiers
        else:
            self.pre = None
        if build is not None:
            for identifier in build.split("."):
                if _BUILD_ID_RE.fullmatch(identifier) is None:
                    raise ValueError("invalid build: %r" % (text,))

    def compare(self, other):
        if self.core != other.core:
            return -1 if self.core < other.core else 1
        if self.pre is None and other.pre is None:
            return 0
        if self.pre is None:
            return 1
        if other.pre is None:
            return -1
        for x, y in zip(self.pre, other.pre):
            result = _cmp_identifier(x, y)
            if result != 0:
                return result
        if len(self.pre) == len(other.pre):
            return 0
        return -1 if len(self.pre) < len(other.pre) else 1


def compare_versions(a, b):
    return _Version(a).compare(_Version(b))
