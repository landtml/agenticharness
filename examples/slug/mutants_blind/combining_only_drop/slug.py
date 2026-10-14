# Mutant: combining_only_drop
# Drops only combining marks; other non-ASCII letters survive the drop step and become separators.
# Deviation: slugify('a\u20acb') -> spec 'ab', mutant 'a-b'
import re, unicodedata
def slugify(text: str) -> str:
    t = ''.join(c for c in unicodedata.normalize('NFKD', text) if not unicodedata.combining(c)).lower()
    t = re.sub(r'[^a-z0-9]+', '-', t)
    return t.strip('-')
