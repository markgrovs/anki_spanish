import re
import requests

try:
    from phonemizer import phonemize
except ImportError:
    phonemize = None

try:
    import epitran
except ImportError:
    epitran = None

_EPI_INSTANCE = None
HEADERS = {"User-Agent": "SpanishAnkiDeckBuilder/1.0"}

# ---- Primary: English Wiktionary rendered HTML (most reliable) ----

def ipa_from_wiktionary(word: str) -> str:
    """
    Fetch rendered HTML from English Wiktionary and extract IPA
    from the Spanish section. This is far more reliable than parsing
    raw wikitext templates.
    """
    url = "https://en.wiktionary.org/w/api.php"
    params = {"action": "parse", "page": word, "prop": "text", "format": "json"}
    try:
        r = requests.get(url, params=params, headers=HEADERS, timeout=10)
        r.raise_for_status()
        html = r.json().get("parse", {}).get("text", {}).get("*", "")

        # Find the Spanish section
        spanish_match = re.search(r'id="Spanish"', html)
        if not spanish_match:
            return ""

        # Slice from Spanish section to next language heading
        spanish_html = html[spanish_match.start():]
        next_h2 = re.search(r'<h2[^>]*>', spanish_html[10:])
        if next_h2:
            spanish_html = spanish_html[:next_h2.start() + 10]

        # Extract first phonemic /.../ IPA
        matches = re.findall(r'<span class="IPA nowrap">(/[^<]+/)</span>', spanish_html)
        if matches:
            return matches[0]

    except Exception as e:
        print(f"[warn] IPA HTML fetch failed for '{word}': {e}")
    return ""


# ---- Fallback: Phonemizer (espeak) ----

def ipa_from_phonemizer(word: str) -> str:
    if phonemize is None:
        return ""
    try:
        out = phonemize(
            word,
            language="es",
            backend="espeak",
            strip=True,
            with_stress=True,
            njobs=1,
        ).strip().replace(" ", "")
        if out:
            return f"/{out}/"
    except Exception:
        pass
    return ""


# ---- Fallback: Epitran ----

def ipa_from_epitran(word: str) -> str:
    global _EPI_INSTANCE
    if epitran is None:
        return ""
    try:
        if _EPI_INSTANCE is None:
            _EPI_INSTANCE = epitran.Epitran("spa-Latn")
        out = _EPI_INSTANCE.transliterate(word).strip().replace(" ", "")
        if out:
            return f"/{out}/"
    except Exception:
        pass
    return ""


# ---- Sentence IPA (bulk phonemizer) ----

def ipa_sentence_from_phonemizer(text: str) -> str:
    if phonemize is None:
        return ""
    try:
        out = phonemize(
            text,
            language="es",
            backend="espeak",
            strip=True,
            with_stress=True,
            njobs=1,
        ).strip()
        return f"/{out}/"
    except Exception:
        pass
    return ""


# ---- Main waterfall ----

def get_best_ipa(word: str) -> str:
    """Waterfall: Wiktionary HTML → Phonemizer → Epitran"""
    ip = ipa_from_wiktionary(word)
    if not ip:
        ip = ipa_from_phonemizer(word)
    if not ip:
        ip = ipa_from_epitran(word)
    return ip
