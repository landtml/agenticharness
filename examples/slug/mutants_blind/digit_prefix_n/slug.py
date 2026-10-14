# Mutant: digit_prefix_n
# A slug starting with a digit gets an n- prefix, which is not in the spec.
# Deviation: slugify('1st place') -> spec '1st-place', mutant 'n-1st-place'
import re, unicodedata
def slugify(text: str) -> str:
    t = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii').lower()
    t = re.sub(r'[^a-z0-9]+', '-', t).strip('-')
    if t[:1].isdigit():
        t = 'n-' + t
    return t
