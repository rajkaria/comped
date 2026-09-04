import hashlib


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()


def redact(text: str, on: bool, keep: int = 120):
    """Return (stored_text, sha256). With redaction on, stored_text is the first `keep` chars, whitespace-collapsed."""
    t = " ".join((text or "").split())
    h = sha(t)
    if on and len(t) > keep:
        t = t[:keep] + "…"
    return t, h
