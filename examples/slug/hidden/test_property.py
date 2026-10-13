"""Random-input checks: compare against the oracle on many generated strings, plus invariants.

A finite example list cannot rule out wrong programs; a few hundred varied inputs rule out far more.
"""

import random
import re

from oracle import slugify_ascii, slugify_full
from slug import slugify

ASCII_POOL = "abcXYZ019 _-.,!?/\\'\"\t\n@#$%^&*()[]{}~`+=|<>"
UNICODE_POOL = ASCII_POOL + "éèêëàâäçñøåßÆœÉÜÖ’–—…ﬁ①²½́ 中文"


def _strings(pool: str, n: int, seed: int):
    rng = random.Random(seed)
    yield from ("", "-", "--", "a", "_", "a_b", "A-B", "a--b", "-a-", "x" * 120, "a b " * 30)
    for _ in range(n):
        yield "".join(rng.choice(pool) for _ in range(rng.randint(0, 60)))


def _check(fn, oracle, pool, seed):
    for s in _strings(pool, 400, seed):
        got, want = fn(s), oracle(s)
        assert got == want, f"slugify({s!r}) == {got!r}, expected {want!r}"
        assert re.fullmatch(r"([a-z0-9]+(-[a-z0-9]+)*)?", got), f"bad charset or hyphens: {got!r}"
        assert fn(got) == got, f"not idempotent on {got!r}"


def test_ascii_property():
    _check(slugify, slugify_ascii, ASCII_POOL, seed=1)


def test_unicode_property():
    _check(slugify, slugify_full, UNICODE_POOL, seed=2)
