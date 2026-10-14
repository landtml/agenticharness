"""Reference behaviour for the property checks. Lives with the hidden tests; the worker never sees it."""

import re
import unicodedata


def slugify_ascii(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def slugify_full(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return slugify_ascii(text)
