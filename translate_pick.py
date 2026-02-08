#!/usr/bin/env python3
"""
Interactive Spanish selection (Argos + Deep + Hints).
Refactored to use shared 'lib'.
"""
import sys
import re
import webbrowser
import time
from pathlib import Path
from urllib.parse import quote

# Add parent to path to find lib
# (Since translate_pick.py is in root, it should just find lib directly if we run it from root,
#  but adding CWD explicitly helps if run via python translate_pick.py)
sys.path.append(str(Path(__file__).resolve().parent))

from lib.config import CSV_PATH, HINTS_PATH
from lib.csv_store import read_rows, write_rows
from lib.gender import wiktionary_pos_gender, heuristic_gender
from lib.anki_client import anki

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

def libre_translate(eng: str):
    # If using local libretranslate or public API, implement here.
    # For now, placeholder or removed if not used.
    return ""

def deep_translate(eng: str) -> str:
    if not HAS_DEEP: return ""
    try:
        t = GoogleTranslator(source="en", target="es").translate(eng)
        return strip_article(t)
    except:
        return ""

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
    
    # 1. Hints
    key = (eng.lower(), sense.lower(), pos.lower())
    default = DEFAULTS.get(key, "")
    k_exact = normalize_key(*key)
    k_eng = normalize_key(eng, "", "")
    
    # Override default if in defaults_map
    dkey = k_exact if k_exact in defaults_map else k_eng
    if dkey in defaults_map: default = defaults_map[dkey]
    
    cands = hints_candidates.get(k_exact, []) or hints_candidates.get(k_eng, [])
    for c in cands:
        if c and c not in seen: ordered.append(c); seen.add(c)
        
    # 2. Common map
    if eng.lower() in COMMON_MAP:
        for c in COMMON_MAP[eng.lower()]:
            if c not in seen: ordered.append(c); seen.add(c)
            
    # 3. Argos
    t = get_argos_trans()
    if t:
        try:
            t1 = strip_article(str(t.translate(eng)).strip())
            if t1 and t1 not in seen: ordered.append(t1); seen.add(t1)
            # Context hints
            if sense:
                t2 = strip_article(str(t.translate(f"{eng} ({sense})")).strip())
                if t2 and t2 not in seen and t2.lower() != f"{eng} ({sense})".lower():
                    ordered.append(t2); seen.add(t2)
        except: pass
        
    # 4. Deep
    dt = deep_translate(eng)
    if dt and dt not in seen: ordered.append(dt); seen.add(dt)
    
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
    try:
        while i < total:
        row = rows[i]
        if row.get("spanish"):
            i += 1
            continue
            
        eng = row.get("english", "")
        sense = row.get("sense", "")
        pos = row.get("pos", "")
        
        default, cands = build_candidates(eng, sense, pos, hints_cands, defaults_map)
        
        print("-" * 60)
        print(f"[{i+1}/{total}] english='{eng}'  sense='{sense}'  pos='{pos}'")
        if cands:
            for idx, c in enumerate(cands, 1):
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
