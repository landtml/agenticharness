# Task: wrap

Write `solution.py` defining:

```python
def wrap(text: str, width: int) -> list[str]
```

Greedy word wrap.

- Raise `ValueError` if `width < 1`.
- Words are the maximal runs of non-whitespace characters (what `str.split()` with no arguments returns). All original whitespace, including newlines, only separates words; it is never kept.
- Build lines greedily: join words with a single space, and add the next word to the current line if the line stays within `width` characters; otherwise start a new line with it.
- A word longer than `width` is broken: if the current line is not empty, end it first; then cut the word into pieces of exactly `width` characters, each on its own line, except the final piece (which may be shorter or exactly `width` long) becomes the current line and later words may be appended to it by the normal rule.
- No line is empty, none has leading or trailing spaces, and none is longer than `width`.
- Text that is empty or only whitespace returns `[]`.

Examples: `wrap("the quick brown fox", 10)` -> `["the quick", "brown fox"]`; `wrap("abcdefgh ij", 3)` -> `["abc", "def", "gh", "ij"]`; `wrap("abcdef x", 3)` -> `["abc", "def", "x"]`; `wrap("ab cdefg", 4)` -> `["ab", "cdef", "g"]`.
