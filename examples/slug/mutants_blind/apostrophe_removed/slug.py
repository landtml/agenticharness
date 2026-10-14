# Mutant: apostrophe_removed
# Apostrophes are deleted before separator collapsing, so contractions join into one word.
# Deviation: slugify("don't") -> spec 'don-t', mutant 'dont'
import re, unicodedata
def slugify(text: str) -> str:
    text = text.replace("'", '')
    t = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii').lower()
    t = re.sub(r'[^a-z0-9]+', '-', t)
    return t.strip('-')
