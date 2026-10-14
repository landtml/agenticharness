# Mutant: camel_split
# Inserts a hyphen at lowercase-to-uppercase boundaries, so camelCase words are split.
# Deviation: slugify('helloWorld') -> spec 'helloworld', mutant 'hello-world'
import re, unicodedata
def slugify(text: str) -> str:
    t = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')
    t = re.sub(r'(?<=[a-z])(?=[A-Z])', '-', t).lower()
    t = re.sub(r'[^a-z0-9]+', '-', t)
    return t.strip('-')
