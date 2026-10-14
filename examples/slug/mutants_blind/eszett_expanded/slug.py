# Mutant: eszett_expanded
# Sharp s is expanded to ss before the drop step, instead of being dropped.
# Deviation: slugify('Stra\xdfe') -> spec 'strae', mutant 'strasse'
import re, unicodedata
def slugify(text: str) -> str:
    text = text.replace('\u00df', 'ss')
    t = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii').lower()
    t = re.sub(r'[^a-z0-9]+', '-', t)
    return t.strip('-')
