"""

Shared text normalization for the chat pipeline before encoder pipeline, RAG, 
and generation so all modules see the same string shape

"""

import re
import unicodedata

# Common invisible / breaking characters (paste artifacts, U+200B, BOM).
_INVISIBLE = re.compile(r"[\u200b-\u200d\ufeff]")

# Collapse all runs of space-like characters to a single ASCII space.
_WHITESPACE = re.compile(r"\s+")


def normalize_user_text(text: str) -> str:
    """Return normalized text: NFKC, strip invisibles, collapse whitespace, case folding."""
    if not text:
        return ""
    t = unicodedata.normalize("NFKC", text)
    t = _INVISIBLE.sub("", t)
    t = _WHITESPACE.sub(" ", t).strip()
    if not t:
        return ""
    return t.casefold()
