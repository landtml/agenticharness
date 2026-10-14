import re, unicodedata
def slugify(text: str) -> str:
    t = unicodedata.normalize('NFD', text).encode('ascii', 'ignore').decode('ascii').lower()
    t = re.sub(r'[^a-z0-9]+', '-', t)
    return t.strip('-')
