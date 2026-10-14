# Mutant: hyphen_runs_not_collapsed
# Hyphens are excluded from the separator class, so literal runs of hyphen are never collapsed.
# Deviation: slugify('a--b') -> spec 'a-b', mutant 'a--b'
import re, unicodedata
def slugify(text: str) -> str:
    t = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii').lower()
    t = re.sub(r'[^a-z0-9-]+', '-', t)
    return t.strip('-')
