import re
import unicodedata

_SUFFIXES = {"jr", "sr", "ii", "iii", "iv"}


def name_key(name: str) -> str:
    """Collapse a player name to a comparable key.

    "José Ramírez", "Jose Ramirez" and "RAMIREZ, JOSE" style differences across
    sources come down to accents, punctuation, case and generational suffixes,
    so all of those are stripped: "Ronald Acuña Jr." -> "ronald acuna".
    """
    if not name:
        return ""
    text = unicodedata.normalize("NFKD", str(name))
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).lower()
    text = text.replace("-", " ")
    text = re.sub(r"[^a-z0-9 ]", "", text)
    return " ".join(tok for tok in text.split() if tok not in _SUFFIXES)


def flip_last_first(name: str) -> str:
    """Savant writes names as "Last, First"; turn that into "First Last"."""
    if name and "," in name:
        last, first = name.split(",", 1)
        return f"{first.strip()} {last.strip()}"
    return (name or "").strip()
