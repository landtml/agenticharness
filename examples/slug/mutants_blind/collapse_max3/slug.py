# Mutant: collapse_max3
# Separator runs are collapsed in chunks of at most 3 characters, so longer runs yield several hyphens.
# Deviation: slugify('a....b') -> spec 'a-b', mutant 'a--b'
import re, unicodedata
def slugify(text: str) -> str:
    t = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii').lower()
    t = re.sub(r'[^a-z0-9]{1,3}', '-', t)
    return t.strip('-')
