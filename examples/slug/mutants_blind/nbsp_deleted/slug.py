# Mutant: nbsp_deleted
# No-break space is removed before normalization, so it joins the words it sat between.
# Deviation: slugify('a\xa0b') -> spec 'a-b', mutant 'ab'
import re, unicodedata
def slugify(text: str) -> str:
    text = text.replace('\u00a0', '')
    t = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii').lower()
    t = re.sub(r'[^a-z0-9]+', '-', t)
    return t.strip('-')
