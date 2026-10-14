# Mutant: unicode_dash_separator
# En dash and em dash are mapped to hyphen before the drop step, so they act as separators instead of being dropped.
# Deviation: slugify('a\u2013b') -> spec 'ab', mutant 'a-b'
import re, unicodedata
def slugify(text: str) -> str:
    text = text.replace('\u2013', '-').replace('\u2014', '-')
    t = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii').lower()
    t = re.sub(r'[^a-z0-9]+', '-', t)
    return t.strip('-')
