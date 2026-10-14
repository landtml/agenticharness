# Mutant: letter_digit_split
# Inserts a hyphen at every letter-to-digit boundary, splitting alphanumeric tokens.
# Deviation: slugify('abc123') -> spec 'abc123', mutant 'abc-123'
import re, unicodedata
def slugify(text: str) -> str:
    t = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii').lower()
    t = re.sub(r'(?<=[a-z])(?=[0-9])', '-', t)
    t = re.sub(r'[^a-z0-9]+', '-', t)
    return t.strip('-')
