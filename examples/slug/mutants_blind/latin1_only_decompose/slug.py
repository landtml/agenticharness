# Mutant: latin1_only_decompose
# Applies NFKD only to characters below U+0100, so Latin Extended Additional letters with accents are dropped.
# Deviation: slugify('\u1e03a') -> spec 'ba', mutant 'a'
import re, unicodedata
def slugify(text: str) -> str:
    t = ''.join(unicodedata.normalize('NFKD', c) if ord(c) < 256 else c for c in text)
    t = t.encode('ascii', 'ignore').decode('ascii').lower()
    t = re.sub(r'[^a-z0-9]+', '-', t)
    return t.strip('-')
