# Mutant: ampersand_and
# Replaces the ampersand with the word and before slugging.
# Deviation: slugify('A & B') -> spec 'a-b', mutant 'a-and-b'
import re, unicodedata
def slugify(text: str) -> str:
    text = text.replace('&', ' and ')
    t = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii').lower()
    t = re.sub(r'[^a-z0-9]+', '-', t)
    return t.strip('-')
