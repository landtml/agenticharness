# Task: roman

Write `solution.py` defining two functions:

```python
def int_to_roman(n: int) -> str
def roman_to_int(s: str) -> int
```

Standard Roman numerals with symbols I=1, V=5, X=10, L=50, C=100, D=500, M=1000 and the six subtractive pairs IV, IX, XL, XC, CD, CM.

- `int_to_roman(n)`: for 1 <= n <= 3999 return the canonical (shortest standard) numeral in uppercase, e.g. 4 -> "IV", 1994 -> "MCMXCIV", 3999 -> "MMMCMXCIX". Raise `ValueError` for n outside 1..3999. Raise `ValueError` if n is not an int (a bool counts as not an int).
- `roman_to_int(s)`: accept only canonical uppercase numerals for 1..3999, i.e. exactly the strings `int_to_roman` can produce, and return their value. Raise `ValueError` for anything else, including the empty string, lowercase, non-canonical forms such as "IIII", "VV", "IC", "IL", "XM", "VX", "MMMM", and any other characters.

Examples: `roman_to_int("MCMXCIV")` -> 1994, `roman_to_int("XLII")` -> 42, `roman_to_int("IIII")` raises ValueError.
