# Mutant: drop_digits
# Digits 0-9 are treated as separators instead of kept.
# Deviation: slugify('abc123') -> spec 'abc123', mutant 'abc'
import re, unicodedata
def slugify(text: str) -> str:
    t = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii').lower()
    t = re.sub(r'[^a-z]+', '-', t)
    return t.strip('-')
