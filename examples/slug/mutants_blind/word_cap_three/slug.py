# Mutant: word_cap_three
# Only the first three words are kept; the rest of the slug is cut.
# Deviation: slugify('one two three four') -> spec 'one-two-three-four', mutant 'one-two-three'
import re, unicodedata
def slugify(text: str) -> str:
    t = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii').lower()
    t = re.sub(r'[^a-z0-9]+', '-', t).strip('-')
    return '-'.join(t.split('-')[:3])
