import re, unicodedata
def slugify(text: str) -> str:
    t = ''.join(unicodedata.normalize('NFKD', c) if ord(c) < 256 else c for c in text)
    t = t.encode('ascii', 'ignore').decode('ascii').lower()
    t = re.sub(r'[^a-z0-9]+', '-', t)
    return t.strip('-')
