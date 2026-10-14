# Mutant: underscore_kept
# Uses \W as the separator class, so underscore survives as a word character.
# Deviation: slugify('snake_case') -> spec 'snake-case', mutant 'snake_case'
import re, unicodedata
def slugify(text: str) -> str:
    t = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii').lower()
    t = re.sub(r'\W+', '-', t)
    return t.strip('-')
