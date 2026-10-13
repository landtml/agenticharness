import re
import unicodedata


def slugify(text: str) -> str:
    out = "".join(
        c if c.isalnum() else "-"
        for c in unicodedata.normalize("NFKD", text).lower()
        if not unicodedata.combining(c)
    )
    return re.sub(r"-+", "-", out).strip("-")
