import re
import unicodedata
from .wiktionary import fetch_wikitext, get_spanish_section
from .config import GENDER_DIR

# Gender constants
FEM_SUFFIXES = ("ción", "sión", "dad", "tad", "tud", "umbre", "ie")
MASC_SUFFIXES = ("aje", "or", "án", "ambre")

GENDER_EXCEPTIONS = {
    "mano": "f", "día": "m", "mapa": "m", "planeta": "m",
    "idioma": "m", "tema": "m", "poema": "m", "programa": "m",
    "sistema": "m", "problema": "m",
}

FEM_EL_WHITELIST = {
    "agua", "aguila", "águila", "arma", "alma", "aula", "hacha", "hada", 
    "hambre", "area", "área", "ala",
}

NUMBER_WORDS = {
    "cero","uno","una","dos","tres","cuatro","cinco","seis","siete",
    "ocho","nueve","diez","once","doce","trece","catorce","quince",
    "dieciseis","dieciséis","diecisiete","dieciocho","diecinueve","veinte",
    "treinta","cuarenta","cincuenta","sesenta","setenta","ochenta","noventa",
    "cien","ciento","mil","millón", "billón"
}

# Regex for Wiktionary parsing
POS_MAP_KEYS = {
    'sustantivo': 'noun',
    'verbo': 'verb',
    'adjetivo': 'adjective',
}
TEMPLATE_SUST = re.compile(r"\{\{\s*sustantivo\|es\|([mf])", re.IGNORECASE)
TEMPLATE_NOUN = re.compile(r"\{\{\s*es-noun\|([mf])", re.IGNORECASE)
POS_HEAD = re.compile(r"^={3,}\s*(.*?)\s*={3,}\s*$", re.MULTILINE)
BOLD_LINE = re.compile(r"'''[^']+'''\s*\(([^)]+)\)")

def heuristic_gender(word: str) -> str:
    """Guess gender from ending/exceptions."""
    w = word.lower().strip()
    if w in GENDER_EXCEPTIONS:
        return GENDER_EXCEPTIONS[w]
    if any(w.endswith(s) for s in FEM_SUFFIXES):
        return "f"
    if any(w.endswith(s) for s in MASC_SUFFIXES):
        return "m"
    if w.endswith("a"):
        return "f"
    if w.endswith("o"):
        return "m"
    return ""

def wiktionary_pos_gender(word: str):
    """
    Return (pos, gender) from Wiktionary (ES or EN).
    Pos normalized to: noun, verb, adjective.
    Gender: m, f, or ''.
    """
    # 1. Try Spanish Wiktionary
    txt = fetch_wikitext(word, "es")
    sec = get_spanish_section(txt, "es")
    if sec:
        p, g = _parse_section(sec)
        if p: return p, g
        
    # 2. Try English Wiktionary
    txt = fetch_wikitext(word, "en")
    sec = get_spanish_section(txt, "en")
    if sec:
        p, g = _parse_section(sec)
        if p: return p, g
        
    return "", ""

def _parse_section(text: str):
    # Direct template gender (most reliable)
    mg = TEMPLATE_SUST.search(text) or TEMPLATE_NOUN.search(text)
    gender = ""
    if mg:
        g = mg.group(1).lower()
        gender = "m" if g.startswith("m") else ("f" if g.startswith("f") else "")

    # Find POS
    pos = ""
    for mh in POS_HEAD.finditer(text):
        hdr = mh.group(1).strip().lower()
        # Check if header contains gender info (e.g. {{sustantivo masculino|es}})
        if not gender and "sustantivo" in hdr:
            if "masculino" in hdr or "|m|" in hdr or "|m}}" in hdr: gender = "m"
            elif "femenino" in hdr or "|f|" in hdr or "|f}}" in hdr: gender = "f"
            
        for k, val in POS_MAP_KEYS.items():
            if k in hdr:
                pos = val
                break
        if pos: break
        
    # Fallback to bold line text
    if not pos:
        mb = BOLD_LINE.search(text)
        if mb:
            meta = mb.group(1).lower()
            if 'sustantivo' in meta:
                pos = 'noun'
                if not gender:
                    if 'masculino' in meta: gender = 'm'
                    elif 'femenino' in meta: gender = 'f'
            elif 'verbo' in meta: pos = 'verb'
            elif 'adjetivo' in meta: pos = 'adjective'

    return pos, gender

def compute_article(spanish: str, gender: str, pos: str) -> str:
    """Return el/la for display, considering euphony."""
    g = (gender or "").lower()
    p = (pos or "").lower()
    
    # Must be noun with gender m or f
    if g not in ("m", "f"): return ""
    if p and p != "noun": return ""
    
    # Clean string
    base = unicodedata.normalize("NFD", spanish).lower()
    base = "".join(ch for ch in base if unicodedata.category(ch) != "Mn")
    
    if base in NUMBER_WORDS: return ""
    
    # Heuristic: if no POS, skip verbs
    if not p and base.endswith(("ar", "er", "ir")): return ""
    
    if g == "m":
        return "el"
    if base in FEM_EL_WHITELIST:
        return "el"
    return "la"

def find_gender_badge(gender: str):
    """Return Path to gender badge image if applicable."""
    if not gender or gender.lower() == "none":
        return None
    base = "male" if gender.lower().startswith("m") else "female"
    for ext in (".png", ".jpg", ".jpeg", ".webp"):
        p = GENDER_DIR / f"{base}{ext}"
        if p.exists():
            return p
    return None
