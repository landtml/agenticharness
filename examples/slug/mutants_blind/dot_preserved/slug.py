# Mutant: dot_preserved
# Full stop is treated as a word character, so dots survive into the slug.
# Deviation: slugify('v1.2') -> spec 'v1-2', mutant 'v1.2'
import re, unicodedata
def slugify(text: str) -> str:
    t = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii').lower()
    t = re.sub(r'[^a-z0-9.]+', '-', t)
    return t.strip('-')
