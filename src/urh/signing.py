"""HMAC-SHA256 signatures for webhooks in both directions (``sha256=<hex>``, GitHub's format)."""

from __future__ import annotations

import hashlib
import hmac


def sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def verify(secret: str, body: bytes, signature: str | None) -> bool:
    return bool(signature) and hmac.compare_digest(signature or "", sign(secret, body))
