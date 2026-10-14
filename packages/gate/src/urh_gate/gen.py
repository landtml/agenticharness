"""A small, dependency-free generator library for property-based checks.

Each generator draws a value from a seeded ``random.Random``, lists its
boundary ("edge") values for the adversarial phase, and proposes simpler
values for shrinking a counterexample. Generators compose, so a contract
author describes the input space once and gets random, edge and shrink
behaviour from it.
"""

import random
import string as _string


class Gen:
    def draw(self, rng, size):
        raise NotImplementedError

    def edges(self):
        return []

    def shrink(self, value):
        return []

    def map(self, fn, unmap=None):
        return Mapped(self, fn, unmap)

    def filter(self, pred):
        return Filtered(self, pred)


class Just(Gen):
    def __init__(self, value):
        self.value = value

    def draw(self, rng, size):
        return self.value

    def edges(self):
        return [self.value]


class Integers(Gen):
    def __init__(self, lo, hi):
        self.lo, self.hi = lo, hi

    def draw(self, rng, size):
        # Bias towards small magnitudes, but cover the full range.
        if rng.random() < 0.7:
            span = max(1, int((self.hi - self.lo) * min(1.0, (size + 1) / 100.0)))
            centre = 0 if self.lo <= 0 <= self.hi else self.lo
            v = centre + rng.randint(-span, span)
            return min(self.hi, max(self.lo, v))
        return rng.randint(self.lo, self.hi)

    def edges(self):
        out = [self.lo, self.hi, self.lo + 1, self.hi - 1, 0, 1, -1, 2]
        return sorted({v for v in out if self.lo <= v <= self.hi})

    def shrink(self, value):
        target = 0 if self.lo <= 0 <= self.hi else (self.lo if value >= self.lo else self.hi)
        out = []
        if value != target:
            out.append(target)
            half = target + (value - target) // 2
            if half != value and half != target:
                out.append(half)
            step = value - 1 if value > target else value + 1
            if step != target:
                out.append(step)
        return [v for v in out if self.lo <= v <= self.hi]


class SampledFrom(Gen):
    def __init__(self, options):
        self.options = list(options)

    def draw(self, rng, size):
        return rng.choice(self.options)

    def edges(self):
        return list(self.options)

    def shrink(self, value):
        try:
            i = self.options.index(value)
        except ValueError:
            return []
        return self.options[:i][:3]


class Text(Gen):
    def __init__(self, alphabet=_string.ascii_lowercase, min_size=0, max_size=20):
        self.alphabet = alphabet
        self.min_size, self.max_size = min_size, max_size

    def draw(self, rng, size):
        hi = min(self.max_size, self.min_size + max(1, size // 3 + 2))
        if rng.random() < 0.15:
            hi = self.max_size
        n = rng.randint(self.min_size, max(self.min_size, hi))
        return "".join(rng.choice(self.alphabet) for _ in range(n))

    def edges(self):
        a = self.alphabet
        out = ["" if self.min_size == 0 else a[0] * self.min_size]
        out.append(a[0] * max(1, self.min_size))
        out.append(a[-1] * max(1, self.min_size))
        out.append((a * (self.max_size // max(1, len(a)) + 1))[: self.max_size])
        return [s for s in dict.fromkeys(out) if self.min_size <= len(s) <= self.max_size]

    def shrink(self, value):
        out = []
        if len(value) > self.min_size:
            out.append(value[: self.min_size])
            out.append(value[: len(value) // 2] if len(value) // 2 >= self.min_size else value)
            for i in range(min(len(value), 12)):
                out.append(value[:i] + value[i + 1 :])
        simple = self.alphabet[0]
        for i, ch in enumerate(value[:12]):
            if ch != simple:
                out.append(value[:i] + simple + value[i + 1 :])
        return [s for s in dict.fromkeys(out) if s != value and len(s) >= self.min_size]


class Lists(Gen):
    def __init__(self, elem, min_size=0, max_size=20):
        self.elem = elem
        self.min_size, self.max_size = min_size, max_size

    def draw(self, rng, size):
        hi = min(self.max_size, self.min_size + max(1, size // 4 + 2))
        if rng.random() < 0.1:
            hi = self.max_size
        n = rng.randint(self.min_size, max(self.min_size, hi))
        return [self.elem.draw(rng, size) for _ in range(n)]

    def edges(self):
        out = []
        if self.min_size == 0:
            out.append([])
        e = self.elem.edges()[:6]
        for v in e:
            out.append([v] * max(1, self.min_size))
        if e and self.max_size >= 2:
            out.append([e[0], e[0]])
            out.append(list(reversed(e))[: self.max_size])
            out.append(e[: self.max_size])
        return [v for v in out if self.min_size <= len(v) <= self.max_size]

    def shrink(self, value):
        out = []
        n = len(value)
        if n > self.min_size:
            out.append(value[: self.min_size])
            if n // 2 >= self.min_size:
                out.append(value[: n // 2])
                out.append(value[n // 2 :] if n - n // 2 >= self.min_size else value)
            for i in range(min(n, 12)):
                out.append(value[:i] + value[i + 1 :])
        for i in range(min(n, 8)):
            for s in self.elem.shrink(value[i])[:2]:
                out.append(value[:i] + [s] + value[i + 1 :])
        return [v for v in out if v != value and len(v) >= self.min_size]


class Tuples(Gen):
    """Draws a Python list of fixed length (one value per component)."""

    def __init__(self, *parts):
        self.parts = parts

    def draw(self, rng, size):
        return [p.draw(rng, size) for p in self.parts]

    def edges(self):
        out = []
        base = [p.edges()[0] if p.edges() else None for p in self.parts]
        if all(b is not None for b in base):
            out.append(list(base))
        for i, p in enumerate(self.parts):
            for e in p.edges()[1:4]:
                v = list(base)
                v[i] = e
                if all(x is not None for x in v):
                    out.append(v)
        return out

    def shrink(self, value):
        out = []
        for i, p in enumerate(self.parts):
            # Enough per component that a list part gets its single-element removals.
            for s in p.shrink(value[i])[:16]:
                v = list(value)
                v[i] = s
                out.append(v)
        return out


class OneOf(Gen):
    def __init__(self, *gens, weights=None):
        self.gens = gens
        self.weights = weights

    def draw(self, rng, size):
        g = rng.choices(self.gens, weights=self.weights)[0] if self.weights else rng.choice(self.gens)
        return g.draw(rng, size)

    def edges(self):
        out = []
        for g in self.gens:
            out.extend(g.edges())
        return out

    def shrink(self, value):
        out = []
        for g in self.gens:
            out.extend(g.shrink(value))
        return out[:20]


class Mapped(Gen):
    def __init__(self, base, fn, unmap=None):
        self.base, self.fn, self.unmap = base, fn, unmap

    def draw(self, rng, size):
        return self.fn(self.base.draw(rng, size))

    def edges(self):
        return [self.fn(v) for v in self.base.edges()]

    def shrink(self, value):
        if self.unmap is None:
            return []
        try:
            raw = self.unmap(value)
        except Exception:
            return []
        return [self.fn(v) for v in self.base.shrink(raw)]


class Filtered(Gen):
    def __init__(self, base, pred):
        self.base, self.pred = base, pred

    def draw(self, rng, size):
        for _ in range(200):
            v = self.base.draw(rng, size)
            if self.pred(v):
                return v
        raise RuntimeError("filter rejected 200 draws in a row")

    def edges(self):
        return [v for v in self.base.edges() if self.pred(v)]

    def shrink(self, value):
        return [v for v in self.base.shrink(value) if self.pred(v)]


class Custom(Gen):
    """Generator from plain functions: draw(rng, size), edges(), shrink(v)."""

    def __init__(self, draw, edges=None, shrink=None):
        self._draw, self._edges, self._shrink = draw, edges, shrink

    def draw(self, rng, size):
        return self._draw(rng, size)

    def edges(self):
        return list(self._edges()) if self._edges else []

    def shrink(self, value):
        return list(self._shrink(value)) if self._shrink else []


def integers(lo, hi):
    return Integers(lo, hi)


def sampled_from(options):
    return SampledFrom(options)


def text(alphabet=_string.ascii_lowercase, min_size=0, max_size=20):
    return Text(alphabet, min_size, max_size)


def lists(elem, min_size=0, max_size=20):
    return Lists(elem, min_size, max_size)


def tuples(*parts):
    return Tuples(*parts)


def one_of(*gens, weights=None):
    return OneOf(*gens, weights=weights)


def just(value):
    return Just(value)


def custom(draw, edges=None, shrink=None):
    return Custom(draw, edges, shrink)


def rng_for(seed):
    return random.Random(seed)
