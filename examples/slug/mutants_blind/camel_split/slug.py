import re, unicodedata
def slugify(text: str) -> str:
    t = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')
    t = re.sub(r'(?<=[a-z])(?=[A-Z])', '-', t).lower()
    t = re.sub(r'[^a-z0-9]+', '-', t)
    return t.strip('-')
