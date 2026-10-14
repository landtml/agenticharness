# Mutant: tab_preserved
# Tab characters are kept literally in the output instead of being turned into hyphens.
# Deviation: slugify('a\tb') -> spec 'a-b', mutant 'a\tb'
import re, unicodedata
def slugify(text: str) -> str:
    t = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii').lower()
    t = re.sub(r'[^a-z0-9\t]+', '-', t)
    return t.strip('-')
