# Mutant: nfd_not_nfkd
# Uses NFD instead of NFKD, so compatibility ligatures such as the fi ligature are dropped rather than expanded.
# Deviation: slugify('\ufb01ne') -> spec 'fine', mutant 'ne'
import re, unicodedata
def slugify(text: str) -> str:
    t = unicodedata.normalize('NFD', text).encode('ascii', 'ignore').decode('ascii').lower()
    t = re.sub(r'[^a-z0-9]+', '-', t)
    return t.strip('-')
