#!/usr/bin/env python3
import csv, webbrowser, time, sys, os, re
from pathlib import Path
from urllib.parse import quote

# Inputs/Outputs
BASE_DIR = Path(__file__).resolve().parent
SRC_CSV = BASE_DIR / "625_structured.es.csv"  # prefer already-progress file
if not SRC_CSV.exists():
    SRC_CSV = BASE_DIR / "625_structured.csv"
OUT_CSV = BASE_DIR / "625_structured.es.csv"
HINTS_PATH = BASE_DIR / "hints_es.yaml"

# Optional services
LIBRE_URL = os.getenv("LIBRETRANSLATE_URL", "")  # e.g., https://libretranslate.com

# --- Argos Translate detection (robust across versions) ---------------------
ARGOS_OK = False

def _argos_detect_en_es() -> bool:
    # Try API-based detection first
    try:
        import argostranslate.translate as argos_translate  # type: ignore
        langs = getattr(argos_translate, "get_installed_languages", lambda: [])()
        for lang in langs:
            code = getattr(lang, "code", None) or getattr(lang, "lang_code", None)
            if code in ("en", "eng"):
                for t in getattr(lang, "translations", []) or []:
                    # Try multiple ways to get destination code depending on Argos version
                    to_code = None
                    to_obj = (
                        getattr(t, "to_lang", None)
                        or getattr(t, "to_language", None)
                        or getattr(t, "to", None)
                        or getattr(t, "tgt_lang", None)
                    )
                    if to_obj is not None:
                        to_code = getattr(to_obj, "code", None)
                    # Direct code attributes on the translation object
                    to_code = (
                        to_code
                        or getattr(t, "to_code", None)
                        or getattr(t, "tgt_code", None)
                        or getattr(t, "code", None)
                    )
                    if to_code in ("es", "spa"):
                        return True
    except Exception:
        pass
    # Fallback: check installed packages metadata
    try:
        import argostranslate.package as argos_package  # type: ignore
        pkgs = getattr(argos_package, "get_installed_packages", lambda: [])()
        for p in pkgs or []:
            name = (getattr(p, "name", "") or getattr(p, "id", "") or "").lower()
            ptype = (getattr(p, "package_type", "") or getattr(p, "type", "") or "").lower()
            from_code = getattr(p, "from_code", None) or getattr(p, "fromCode", None)
            to_code = getattr(p, "to_code", None) or getattr(p, "toCode", None)
            if (
                ("translate" in name or ptype == "translate")
                and ((from_code == "en" and to_code == "es") or ("en_es" in name) or ("en-es" in name) or ("translate-en_es" in name))
            ):
                return True
    except Exception:
        pass
    # Last-chance: try a tiny translation call and see if it returns something plausible
    try:
        import argostranslate.translate as argos_translate  # type: ignore
        text = "test"
        res = argos_translate.translate(text, "en", "es")
        if isinstance(res, str) and res and res != text:
            return True
    except Exception:
        pass
    return False

ARGOS_OK = _argos_detect_en_es()

# Optional online translator (no API key; scrapes web)
HAS_DEEP = False
try:
    from deep_translator import GoogleTranslator  # type: ignore
    HAS_DEEP = True
except Exception:
    HAS_DEEP = False

# ------------------------ Hints (tiny YAML loader) -------------------------

def load_hints(path: Path):
    if not path.exists():
        return {}, {}
    candidates = {}
    defaults = {}
    current = None
    last_key = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        if line.strip().endswith(":") and not line.strip().startswith("-"):
            current = line.strip()[:-1]
            continue
        if current == "candidates":
            if not line.startswith(" ") and ":" in line:
                k, _ = line.split(":", 1)
                last_key = k.strip().strip('"')
                candidates[last_key] = []
            elif line.strip().startswith("-") and last_key:
                val = line.strip()[1:].strip().strip('"')
                candidates[last_key].append(val)
        elif current == "defaults":
            if ":" in line:
                k, v = line.split(":", 1)
                defaults[k.strip().strip('"')] = v.strip().strip('"')
    return candidates, defaults

# Built-in seed defaults for speed
DEFAULTS = {
    ("dog","",""): "perro",
    ("water","","noun"): "agua",
    ("phone","","noun"): "teléfono",
    ("light","/dark","adjective"): "claro",
    ("light","/heavy","adjective"): "ligero",
    ("light","","noun"): "luz",
    ("back","body",""): "espalda",
    ("back","direction",""): "atrás",
}

COMMON_MAP = {
    "black": ["negro"],
    "clay": ["arcilla"],
    "disease": ["enfermedad"],
    "actor": ["actor"],
    "doctor": ["médico", "doctora"],
    "afternoon": ["tarde"],
    "blue": ["azul"],
    "clock": ["reloj"],
    "dollar": ["dólar"],
    "air": ["aire"],
    "boat": ["barco"],
    "door": ["puerta"],
    "body": ["cuerpo"],
    "clothing": ["ropa"],
    "alive": ["vivo"],
    "bone": ["hueso"],
    "down": ["abajo"],
}

# ------------------------ Candidate suggestion ----------------------------

def normalize_key(eng, sense, pos):
    return f"{eng.lower()}|{sense.lower()}|{pos.lower()}"


def suggest_from_hints(row, hints_candidates, defaults_map):
    key = (row["english"].lower(), row["sense"].lower(), row["pos"].lower())
    default = DEFAULTS.get(key, "")
    k_exact = normalize_key(*key)
    k_eng_only = normalize_key(row["english"], "", "")
    cands = hints_candidates.get(k_exact, []) or hints_candidates.get(k_eng_only, [])
    dkey = k_exact if k_exact in defaults_map else k_eng_only
    if dkey in defaults_map:
        default = defaults_map[dkey]
    return default, cands


def suggest_from_common(eng):
    return COMMON_MAP.get(eng.lower(), [])


def libre_translate(eng: str) -> str:
    if not LIBRE_URL:
        return ""
    try:
        import requests  # type: ignore
        r = requests.post(f"{LIBRE_URL}/translate", data={
            "q": eng,
            "source": "en",
            "target": "es",
            "format": "text"
        }, timeout=10)
        if r.ok:
            return r.json().get("translatedText", "")
    except Exception:
        return ""
    return ""

# Helpers to clean MT outputs
_ARTICLE_RE = re.compile(r"^(el|la|los|las|un|una|unos|unas)\s+", re.IGNORECASE)

def strip_article(s: str) -> str:
    return _ARTICLE_RE.sub("", s.strip())


def argos_translate_suggest(eng: str, sense: str, pos: str) -> list[str]:
    if not ARGOS_OK:
        return []
    out = []
    try:
        import argostranslate.translate as argos_translate  # type: ignore
        t1 = strip_article(argos_translate.translate(eng, "en", "es").strip())
        if t1:
            out.append(t1)
        hint = eng
        if sense:
            hint = f"{eng} ({sense})"
        elif pos:
            hint = f"{eng} ({pos})"
        if hint != eng:
            t2 = strip_article(argos_translate.translate(hint, "en", "es").strip())
            if t2 and t2 not in out:
                out.append(t2)
    except Exception:
        pass
    return out


def deep_translate(eng: str) -> str:
    if not HAS_DEEP:
        return ""
    try:
        from deep_translator import GoogleTranslator  # local import for robustness
        t = GoogleTranslator(source="en", target="es").translate(eng)
        return strip_article(t)
    except Exception:
        return ""


def build_candidates(eng, sense, pos, hints_candidates, defaults_map):
    seen = set()
    ordered = []

    default, hint_cands = suggest_from_hints({"english":eng, "sense":sense, "pos":pos}, hints_candidates, defaults_map)
    for c in hint_cands:
        if c and c not in seen:
            ordered.append(c); seen.add(c)

    for c in suggest_from_common(eng):
        if c and c not in seen:
            ordered.append(c); seen.add(c)

    for c in argos_translate_suggest(eng, sense, pos):
        if c and c not in seen:
            ordered.append(c); seen.add(c)

    dt = deep_translate(eng)
    if dt and dt not in seen:
        ordered.append(dt); seen.add(dt)

    lt = libre_translate(eng)
    if lt:
        lt = strip_article(lt)
        if lt and lt not in seen:
            ordered.append(lt); seen.add(lt)

    return default, ordered

# ------------------------ POS & Gender detection ---------------------------

EXCEPTIONS = {
    "mano": "f", "día": "m", "mapa": "m", "planeta": "m",
    "idioma": "m", "tema": "m", "poema": "m", "programa": "m",
    "sistema": "m", "problema": "m",
}

FEM_SUFFIXES = ("ción","sión","dad","tad","tud","umbre","ie")
MASC_SUFFIXES = ("aje","or","án","ambre")

WIKT_POS_HEADERS = (
    ("=== sustantivo ===", "noun"),
    ("=== verbo ===", "verb"),
    ("=== adjetivo ===", "adjective"),
)


def heuristic_gender(word: str) -> str:
    w = word.lower()
    if w in EXCEPTIONS:
        return EXCEPTIONS[w]
    if any(w.endswith(suf) for suf in FEM_SUFFIXES):
        return "f"
    if any(w.endswith(suf) for suf in MASC_SUFFIXES):
        return "m"
    if w.endswith("a"):
        return "f"
    if w.endswith("o"):
        return "m"
    return ""


def wiktionary_gender(word: str) -> str:
    try:
        import requests  # type: ignore
        url = "https://es.wiktionary.org/w/api.php"
        r = requests.get(url, params={"action":"parse","prop":"wikitext","page":word,"format":"json"}, timeout=8)
        if r.ok and "parse" in r.json():
            text = r.json()["parse"]["wikitext"]["*"].lower()
            if "sustantivo masculino" in text or "{{sustantivo|es|m" in text or "{{es-sustantivo|m" in text or "{{es-nombre|m" in text:
                return "m"
            if "sustantivo femenino" in text or "{{sustantivo|es|f" in text or "{{es-sustantivo|f" in text or "{{es-nombre|f" in text:
                return "f"
    except Exception:
        pass
    try:
        import requests  # type: ignore
        url = "https://en.wiktionary.org/w/api.php"
        r = requests.get(url, params={"action":"parse","prop":"wikitext","page":word,"format":"json"}, timeout=8)
        if r.ok and "parse" in r.json():
            text = r.json()["parse"]["wikitext"]["*"].lower()
            if "{{es-noun|m" in text:
                return "m"
            if "{{es-noun|f" in text:
                return "f"
    except Exception:
        pass
    return ""


def detect_gender_if_noun(spanish: str, pos: str) -> str:
    head = spanish.strip().split()[0]
    if pos and pos != "noun":
        return ""
    if head.endswith(("ar","er","ir")):
        return ""
    g = wiktionary_gender(head)
    if g:
        return g
    return heuristic_gender(head)


def wiktionary_pos(spanish: str) -> list[str]:
    """Return ['noun','verb','adjective'] candidates by scanning Spanish section headers."""
    try:
        import requests  # type: ignore
        url = "https://es.wiktionary.org/w/api.php"
        r = requests.get(url, params={"action":"parse","prop":"wikitext","page":spanish,"format":"json"}, timeout=8)
        if not (r.ok and "parse" in r.json()):
            return []
        text = r.json()["parse"]["wikitext"]["*"].lower()
        # Ensure we're under the Spanish section
        if "== español ==" not in text and "{{lengua|es}}" not in text:
            return []
        found = []
        for hdr, tag in WIKT_POS_HEADERS:
            if hdr in text:
                found.append(tag)
        # Also check templates when headers are missing
        if ("{{es-sustantivo" in text or "{{sustantivo|es" in text) and "noun" not in found:
            found.append("noun")
        if ("{{es-verbo" in text or "{{verbo|es" in text) and "verb" not in found:
            found.append("verb")
        if ("{{es-adjetivo" in text or "{{adjetivo|es" in text) and "adjective" not in found:
            found.append("adjective")
        return found
    except Exception:
        return []


def guess_pos(spanish: str, sense: str) -> list[str]:
    # Use CSV sense as a weak hint; otherwise minimal heuristics
    sense_low = (sense or "").lower()
    if sense_low in ("noun","verb","adjective"):
        return [sense_low]
    w = spanish.lower()
    if w.endswith(("ar","er","ir")):
        return ["verb"]
    # default none; user will choose
    return []

# ------------------------ References ---------------------------------------

def open_refs(eng):
    webbrowser.open_new_tab(f"https://www.spanishdict.com/translate/{quote(eng)}")
    time.sleep(0.12)
    webbrowser.open_new_tab(f"https://linguee.com/english-spanish/search?source=auto&query={quote(eng)}")
    time.sleep(0.12)
    webbrowser.open_new_tab(f"https://www.google.com/search?q={quote(eng + ' in spanish')}")

# ------------------------ IO helpers ---------------------------------------

def read_rows(path: Path):
    with path.open("r", encoding="utf-8") as f:
        r = list(csv.DictReader(f))
    for row in r:
        row.setdefault("gender", "")
        row.setdefault("ipa", "")
        row.setdefault("notes", "")
    return r


def write_rows(path: Path, rows):
    fieldnames = ["english","sense","pos","spanish","gender","ipa","notes"]
    with path.open("w", newline="", encoding="utf-8") as out:
        w = csv.DictWriter(out, fieldnames=fieldnames)
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fieldnames})

# ------------------------ Main loop ----------------------------------------

def main():
    if not SRC_CSV.exists():
        print("CSV not found:", SRC_CSV)
        sys.exit(1)

    if not ARGOS_OK:
        print("[Info] Argos Translate en→es model not detected (or not visible to Python). Using other sources for candidates.")
    else:
        print("[Info] Argos Translate en→es is available.")

    hints_candidates, defaults_map = load_hints(HINTS_PATH)
    rows = read_rows(SRC_CSV)
    total = len(rows)

    i = 0
    while i < total:
        row = rows[i]
        if row.get("spanish"):
            i += 1
            continue
        eng = row.get("english","")
        sense = row.get("sense","")
        pos = row.get("pos","")

        default, cands = build_candidates(eng, sense, pos, hints_candidates, defaults_map)

        print("-"*60)
        print(f"[{i+1}/{total}] english='{eng}'  sense='{sense}'  pos='{pos}'")
        if cands:
            print("Candidates:")
            for idx, c in enumerate(cands, 1):
                print(f"  {idx}) {c}")
        else:
            print("(no candidates — press 'o' to open references or type your Spanish)")
        print(f"Default: {default if default else '(none)'}")
        print("Commands: type Spanish; 1-9 pick; d=default; g=gender guess; o=open refs; s=skip; p=prev; u=unset; q=quit")
        ans = input("> ").strip()

        if ans == "":
            if default:
                row["spanish"] = default
            else:
                i += 1
                continue
        elif ans.lower() == "s":
            i += 1
            continue
        elif ans.lower() == "p":
            i = max(0, i-1)
            continue
        elif ans.lower() == "q":
            break
        elif ans.lower() == "o":
            open_refs(eng)
            continue
        elif ans.lower() == "u":
            row["spanish"] = ""; row["gender"] = ""
            write_rows(OUT_CSV, rows)
            continue
        elif ans.lower() == "d":
            if default:
                row["spanish"] = default
            else:
                print("No default available.")
                continue
        elif ans.lower() == "g":
            target = default or (cands[0] if cands else "")
            if not target:
                print("No target to guess. Type a Spanish word first.")
                continue
            g = detect_gender_if_noun(target, pos)
            print(f"Gender guess for '{target}': {g or 'unknown'}")
            continue
        elif ans.isdigit():
            idx = int(ans)
            if 1 <= idx <= len(cands):
                row["spanish"] = cands[idx-1]
            else:
                print("Invalid candidate number.")
                continue
        else:
            m = re.search(r"\b\((m|f)\)\b", ans, re.IGNORECASE) or re.search(r"\b(m|f)\b$", ans, re.IGNORECASE)
            if m:
                row["gender"] = m.group(1).lower()
                ans = re.sub(r"\s*\((m|f)\)\s*", " ", ans, flags=re.IGNORECASE)
                ans = re.sub(r"\s\b(m|f)\b\s*$", "", ans, flags=re.IGNORECASE).strip()
            row["spanish"] = ans

        # POS selection step (immediate, interactive)
        if row["spanish"]:
            pos_cands = []
            wikt_pos = wiktionary_pos(row["spanish"])  # ['noun','verb','adjective']
            if wikt_pos:
                pos_cands.extend(wikt_pos)
            for gpos in guess_pos(row["spanish"], sense):
                if gpos not in pos_cands:
                    pos_cands.append(gpos)
            # Unique and order: noun, adjective, verb
            order = {"noun":0, "adjective":1, "verb":2}
            pos_cands = sorted(dict.fromkeys(pos_cands), key=lambda x: order.get(x, 99))
            if not pos_cands:
                pos_cands = [p for p in ("noun","adjective","verb")]
            # Default: if current pos matches, keep; else use first candidate
            pos_default = row.get("pos") or (pos_cands[0] if pos_cands else "")
            print("POS candidates:")
            for k, tag in enumerate(pos_cands, 1):
                print(f"  {k}) {tag}")
            print(f"Default POS: {pos_default or '(none)'}   (enter number/tag, or Enter to accept)")
            ans_pos = input("pos> ").strip().lower()
            if ans_pos.isdigit():
                k = int(ans_pos)
                if 1 <= k <= len(pos_cands):
                    row["pos"] = pos_cands[k-1]
            elif ans_pos in ("noun","verb","adjective"):
                row["pos"] = ans_pos
            elif not row.get("pos"):
                row["pos"] = pos_default

            # Gender selection step if POS is noun
            if row.get("pos") == "noun":
                g_cands = []
                g_wikt = detect_gender_if_noun(row["spanish"], "noun")
                if g_wikt:
                    g_cands.append(g_wikt)
                # Always include both as options, and 'none' for nouns that shouldn't carry an article (e.g., numbers)
                for gopt in ("m","f","none"):
                    if gopt not in g_cands:
                        g_cands.append(gopt)
                # Default: keep existing, else Wiktionary guess, else 'none'
                g_default = row.get("gender") or (g_wikt or "none")
                print("Gender candidates (for noun):")
                label = {"m":"m (el)", "f":"f (la)", "none":"none (no article)"}
                for k, g in enumerate(g_cands, 1):
                    print(f"  {k}) {label.get(g, g)}")
                print(f"Default Gender: {label.get(g_default,g_default) or '(none)'}   (enter number/m/f/none, or Enter to accept)")
                ans_g = input("gender> ").strip().lower()
                if ans_g.isdigit():
                    k = int(ans_g)
                    if 1 <= k <= len(g_cands):
                        row["gender"] = g_cands[k-1]
                elif ans_g in ("m","f","none","n"):
                    row["gender"] = ("none" if ans_g == "n" else ans_g)
                elif not row.get("gender"):
                    row["gender"] = g_default
            else:
                # Not a noun, clear gender
                row["gender"] = ""

        write_rows(OUT_CSV, rows)
        i += 1

    write_rows(OUT_CSV, rows)
    print(f"Saved {OUT_CSV}")

if __name__ == "__main__":
    main()
