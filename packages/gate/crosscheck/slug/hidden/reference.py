import re
import unicodedata


def slugify(text):
    if type(text) is not str:
        raise ValueError("text must be a str")
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
