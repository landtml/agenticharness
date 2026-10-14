# Mutant: space_only_separator
# Only spaces separate words; other punctuation and hyphens are deleted rather than turned into hyphens.
# Deviation: slugify('a-b') -> spec 'a-b', mutant 'ab'
import re, unicodedata
def slugify(text: str) -> str:
    t = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii').lower()
    t = re.sub(r'[^a-z0-9 ]+', '', t)
    t = re.sub(r' +', '-', t)
    return t.strip('-')
