import re, unicodedata
def slugify(text: str) -> str:
    text = text.replace('\u00a0', '')
    t = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii').lower()
    t = re.sub(r'[^a-z0-9]+', '-', t)
    return t.strip('-')
