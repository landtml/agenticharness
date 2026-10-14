# Mutant: truncate_20_no_restrip
# Truncates the slug to 20 characters after stripping, so a cut can leave a trailing hyphen.
# Deviation: slugify('aaaaaaaaaaaaaaaaaaa b') -> spec 'aaaaaaaaaaaaaaaaaaa-b', mutant 'aaaaaaaaaaaaaaaaaaa-'
import re, unicodedata
def slugify(text: str) -> str:
    t = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii').lower()
    t = re.sub(r'[^a-z0-9]+', '-', t).strip('-')
    return t[:20]
