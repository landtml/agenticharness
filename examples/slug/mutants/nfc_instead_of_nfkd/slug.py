import re
import unicodedata


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFC", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
