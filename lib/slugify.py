import unicodedata

def slugify(s: str) -> str:
    """Normalize string to ASCII slug (e.g., 'El Niño' -> 'el_nino')."""
    s = (s or "").strip().lower()
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    s = "".join(ch if (ch.isalnum() or ch in ("_", "-", " ")) else "_" for ch in s)
    s = "_".join(filter(None, s.split()))
    return s
