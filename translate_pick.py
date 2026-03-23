#!/usr/bin/env python3
"""
Interactive Spanish selection (Argos + Deep + Hints + MyMemory + Wiktionary Definitions).
Refactored to use shared 'lib'.
"""
import sys
import re
import webbrowser
import time
import requests
import concurrent.futures
from pathlib import Path
from urllib.parse import quote

# Add parent to path to find lib
sys.path.append(str(Path(__file__).resolve().parent))

from lib.config import CSV_PATH, HINTS_PATH
from lib.csv_store import read_rows, write_rows
from lib.gender import wiktionary_pos_gender, heuristic_gender
from lib.anki_client import anki
from lib.wiktionary import fetch_wikitext, get_spanish_section

# Optional services
try:
    import argostranslate.translate as argos_translate
    ARGOS_OK = True
except ImportError:
    ARGOS_OK = False

try:
    from deep_translator import GoogleTranslator
    HAS_DEEP = True
except ImportError:
    HAS_DEEP = False

# Services
_ARGOS_TRANS_OBJ = None
def get_argos_trans():
    global _ARGOS_TRANS_OBJ
    if not ARGOS_OK: return None
    if _ARGOS_TRANS_OBJ: return _ARGOS_TRANS_OBJ
    try:
        t = argos_translate.get_translation_from_codes("en", "es")
        _ARGOS_TRANS_OBJ = t
        return t
    except:
        return None

def deep_translate(eng: str) -> str:
    if not HAS_DEEP: return ""
    try:
        t = GoogleTranslator(source="en", target="es").translate(eng)
        return strip_article(t)
    except:
        return ""

def get_mymemory_candidates(eng: str):
    """Fetch multiple translation candidates from MyMemory API."""
    cands = []
    try:
        url = f"https://api.mymemory.translated.net/get?q={quote(eng)}&langpair=en|es"
        resp = requests.get(url, timeout=3).json()
        matches = resp.get("matches", [])
        for m in matches:
            t = m.get("translation", "").strip()
            # Clean up articles
            t_lower = t.lower()
            for art in ["el ", "la ", "los ", "las ", "un ", "una ", "unos ", "unas "]:
                if t_lower.startswith(art):
                    t = t[len(art):].strip()
                    break
            
            if t and t.lower() not in [c.lower() for c in cands]:
                # Exclude long sentences (more than 3 words)
                if len(t.split()) <= 3:
                    cands.append(t.lower())
    except:
        pass
    return cands

def get_wiktionary_gloss_for_es_word(es_word: str):
    """Fetches English definitions of a Spanish word from EN Wiktionary."""
    txt = fetch_wikitext(es_word, "en")
    if not txt: return []
    sec = get_spanish_section(txt, "en")
    if not sec: return []
    
    glosses = []
    for line in sec.split('\n'):
        if line.startswith('#') and not line.startswith('#:'):
            # Remove templates {{...}}
            clean = re.sub(r'\{\{[^}]+\}\}', '', line[1:])
            # Remove wikitext links [[word|display]] -> display
            clean = re.sub(r'\[\[(?:[^|\]]+\|)?([^\]]+)\]\]', r'\1', clean)
            # Remove quotes
            clean = clean.replace("'''", "").replace("''", "").strip()
            # Clean up lingering wikitext artifacts like leading commas or colons
            clean = re.sub(r'^[:\s,]+', '', clean)
            if clean and clean not in glosses and len(clean) > 2:
                glosses.append(clean)
    return glosses[:3]  # Return top 3 definitions to keep it brief

# Helpers
_ARTICLE_RE = re.compile(r"^(el|la|los|las|un|una|unos|unas)\s+", re.IGNORECASE)
def strip_article(s: str) -> str:
    return _ARTICLE_RE.sub("", (s or "").strip())

# Hints
DEFAULTS = {
    ("dog","",""): "perro",
    ("water","","noun"): "agua",
    ("phone","","noun"): "teléfono",
}
COMMON_MAP = {
    "black": ["negro"], "blue": ["azul"], "red": ["rojo"],
}

def load_hints(path: Path):
    if not path.exists(): return {}, {}
    candidates = {}
    defaults = {}
    current = None
    last_key = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.strip().startswith("#"): continue
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

def normalize_key(eng, sense, pos):
    return f"{eng.lower()}|{sense.lower()}|{pos.lower()}"

def build_candidates(eng, sense, pos, hints_candidates, defaults_map):
    seen = set()
    ordered = []
    
    def add_cand(c):
        if c and c.lower() not in seen:
            ordered.append(c.lower())
            seen.add(c.lower())

    # 1. Hints
    key = (eng.lower(), sense.lower(), pos.lower())
    default = DEFAULTS.get(key, "")
    k_exact = normalize_key(*key)
    k_eng = normalize_key(eng, "", "")
    
    # Override default if in defaults_map
    dkey = k_exact if k_exact in defaults_map else k_eng
    if dkey in defaults_map: default = defaults_map[dkey]
    
    cands = hints_candidates.get(k_exact, []) or hints_candidates.get(k_eng, [])
    for c in cands: add_cand(c)
        
    # 2. Common map
    if eng.lower() in COMMON_MAP:
        for c in COMMON_MAP[eng.lower()]: add_cand(c)
            
    # 3. Argos
    t = get_argos_trans()
    if t:
        try:
            t1 = strip_article(str(t.translate(eng)).strip())
            add_cand(t1)
            # Context hints
            if sense:
                t2 = strip_article(str(t.translate(f"{eng} ({sense})")).strip())
                if t2.lower() != f"{eng} ({sense})".lower():
                    add_cand(t2)
        except: pass
        
    # 4. Deep (Google Translate)
    dt = deep_translate(eng)
    add_cand(dt)

    # 5. MyMemory API (gets multiple synonyms)
    for mc in get_mymemory_candidates(eng):
        add_cand(mc)
    if sense:
        # Try finding translations for the word with context if MyMemory supports it
        for mc in get_mymemory_candidates(f"{eng} ({sense})"):
            if not "(" in mc and not ")" in mc:  # Ensure it didn't just mirror the parens
                add_cand(mc)
    
    return default, ordered

def open_refs(eng):
    webbrowser.open_new_tab(f"https://www.spanishdict.com/translate/{quote(eng)}")
    time.sleep(0.1)
    webbrowser.open_new_tab(f"https://linguee.com/english-spanish/search?source=auto&query={quote(eng)}")
    time.sleep(0.1)
    webbrowser.open_new_tab(f"https://www.google.com/search?q={quote(eng + ' in spanish')}")

def main():
    if not CSV_PATH.exists():
        print(f"CSV not found: {CSV_PATH}")
        return
        
    hints_cands, defaults_map = load_hints(HINTS_PATH)
    rows = read_rows(CSV_PATH)
    total = len(rows)
    
    i = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        while i < total:
            row = rows[i]
            if row.get("spanish"):
                i += 1
                continue
                
            eng = row.get("english", "")
            sense = row.get("sense", "")
            pos = row.get("pos", "")
            
            default, cands = build_candidates(eng, sense, pos, hints_cands, defaults_map)
            
            print("-" * 80)
            print(f"[{i+1}/{total}] english='{eng}'  sense='{sense}'  pos='{pos}'")
            
            if cands:
                # Fetch definitions concurrently to save time
                future_to_cand = {executor.submit(get_wiktionary_gloss_for_es_word, c): c for c in cands}
                cand_definitions = {}
                for future in concurrent.futures.as_completed(future_to_cand):
                    c = future_to_cand[future]
                    try:
                        cand_definitions[c] = future.result()
                    except Exception:
                        cand_definitions[c] = []

                # Print candidates with their meanings
                for idx, c in enumerate(cands, 1):
                    defs = cand_definitions.get(c, [])
                    if defs:
                        def_str = " | ".join(defs)
                        print(f"  {idx}) {c:<15}  (EN: {def_str})")
                    else:
                        print(f"  {idx}) {c}")
            else:
                print("(no candidates - type manual or 'o' for refs)")
                
            print(f"Default: {default or '(none)'}")
            ans = input("> ").strip()
            
            if ans == "":
                if default: row["spanish"] = default
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
                row["spanish"] = ""
                row["gender"] = ""
                write_rows(rows, CSV_PATH)
                continue
            elif ans.isdigit():
                idx = int(ans)
                if 1 <= idx <= len(cands):
                    row["spanish"] = cands[idx-1]
                else:
                    print("Invalid number.")
                    continue
            else:
                # Handle inline gender "perro (m)"
                m = re.search(r"\((m|f)\)", ans, re.IGNORECASE)
                if m:
                    row["gender"] = m.group(1).lower()
                    ans = ans.replace(m.group(0), "").strip()
                row["spanish"] = ans
                
            # POS check
            if row["spanish"]:
                # Auto-fill POS if missing
                if not row.get("pos"):
                    p, _ = wiktionary_pos_gender(row["spanish"])
                    if p: row["pos"] = p
                    else:
                        # quick guess
                        if row["spanish"].endswith(("ar","er","ir")): row["pos"] = "verb"
                        
                # Gender check if noun
                if row.get("pos") == "noun" and not row.get("gender"):
                    _, g = wiktionary_pos_gender(row["spanish"])
                    if g: row["gender"] = g
                    else:
                        g = heuristic_gender(row["spanish"])
                        if g: row["gender"] = g
            
            write_rows(rows, CSV_PATH)
            i += 1

    print("Done.")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n[Interrupted] Saved progress. Exiting.")
        sys.exit(0)
