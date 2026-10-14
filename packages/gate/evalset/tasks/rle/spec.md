# Task: rle

Write `solution.py` defining two functions:

```python
def rle_encode(s: str) -> str
def rle_decode(s: str) -> str
```

Run-length encoding where each run is written as a single digit count `1`-`9` followed by exactly one character. The character can be anything, including a digit, a space or a newline.

- `rle_encode(s)`: split `s` into maximal runs of the same character. A run longer than 9 is written as as many 9-runs as fit followed by the remainder (if any). Example: `"aaaaaaaaaaaab"` (12 a's) -> `"9a3a1b"`. `"112"` -> `"2112"`. The empty string encodes to the empty string.
- `rle_decode(s)`: read the input as consecutive pairs (count digit, character) and expand each. It must accept any well-formed input, not only what `rle_encode` produces: `"1a1a"` -> `"aa"`. Raise `ValueError` if the input has odd length, or if any count position holds anything other than a digit `1`-`9` (so `0` is invalid). The empty string decodes to the empty string.

For every string `s`, `rle_decode(rle_encode(s)) == s`.
