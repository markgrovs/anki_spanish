import requests
import re

WIKI_ES = "https://es.wiktionary.org/w/api.php"
WIKI_EN = "https://en.wiktionary.org/w/api.php"

def fetch_wikitext(page: str, lang="es") -> str:
    """Fetch raw wikitext from Wiktionary (es or en)."""
    url = WIKI_ES if lang == "es" else WIKI_EN
    try:
        headers = {"User-Agent": "SpanishAnkiDeckBuilder/1.0 (markgroves@example.com)"}
        resp = requests.get(url, headers=headers, params={
            "action": "parse",
            "prop": "wikitext",
            "page": page,
            "format": "json",
        }, timeout=10)
        if not resp.ok:
            return ""
        data = resp.json()
        return data.get("parse", {}).get("wikitext", {}).get("*", "")
    except Exception as e:
        print(f"[warn] Wiktionary fetch error: {e}")
        return ""

def get_spanish_section(text: str, lang_code="es") -> str:
    """Extract the Spanish section from raw wikitext."""
    if not text:
        return ""
    
    if lang_code == "es":
        # ES Wiktionary: look for {{lengua|es}} or == Español ==
        m = re.search(r"^==\s*(?:Español|\{\{\s*lengua\s*\|\s*es\s*\}\})\s*==\s*$", text, re.MULTILINE | re.IGNORECASE)
    else:
        # EN Wiktionary: look for == Spanish ==
        m = re.search(r"^==\s*Spanish\s*==\s*$", text, re.MULTILINE | re.IGNORECASE)

    if not m:
        return ""
    
    start = m.end()
    rest = text[start:]
    # Find next language header (== Header ==)
    m2 = re.search(r"^==[^=].*==\s*$", rest, re.MULTILINE)
    end = m2.start() if m2 else len(rest)
    return rest[:end]
