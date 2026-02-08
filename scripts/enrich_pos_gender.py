#!/usr/bin/env python3
"""
Enrich POS/Gender using shared 'lib'.
"""
import sys
import argparse
import unicodedata
from pathlib import Path

# Add parent to path to find lib
sys.path.append(str(Path(__file__).resolve().parent.parent))

from lib.config import CSV_PATH, HINTS_PATH
from lib.csv_store import read_rows, write_rows
from lib.gender import wiktionary_pos_gender
from lib.anki_client import anki

# ------------------- Hints loader ------------------
def ensure_default_hints():
    if not HINTS_PATH.parent.exists():
        HINTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not HINTS_PATH.exists():
        HINTS_PATH.write_text(
            "# POS hints (key: value)\n"
            "dólar: noun\n"
            "rojo: adjective\n"
            "azul: adjective\n"
            "limpiar: verb\n",
            encoding="utf-8"
        )

def load_hints(path: Path | None) -> dict:
    if path is None:
        path = HINTS_PATH
        ensure_default_hints()
    if not path.exists():
        return {}
    hints = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith('#') or ':' not in s: continue
        k, v = s.split(':', 1)
        hints[k.strip().lower()] = v.strip().lower()
    return hints

def strip_accents(s: str) -> str:
    return ''.join(ch for ch in unicodedata.normalize('NFD', s) if unicodedata.category(ch) != 'Mn')

# ------------------- Main --------------------------
def main():
    ap = argparse.ArgumentParser(description="Enrich POS/Gender using lib")
    ap.add_argument("--pos-only", action="store_true")
    ap.add_argument("--gender-nouns", action="store_true")
    ap.add_argument("--guess-verbs", action="store_true")
    ap.add_argument("--hints-pos", default=None)
    ap.add_argument("--push", action="store_true")
    ap.add_argument("--deck", default="My Spanish Deck::625")
    ap.add_argument("--model", default="Picture Word")
    args = ap.parse_args()

    hints = load_hints(Path(args.hints_pos) if args.hints_pos else None)
    rows = read_rows(CSV_PATH)
    updated = 0

    for r in rows:
        es = (r.get("spanish") or "").strip()
        if not es: continue
        
        key = es.lower()
        pos = (r.get("pos") or "").strip().lower()
        gen = (r.get("gender") or "").strip().lower()
        sense = (r.get("sense") or "").strip().lower()
        
        changed = False
        
        # POS enrichment
        if args.pos_only and not pos:
            # 1. Hint
            hp = hints.get(key)
            if hp in ("noun", "verb", "adjective"):
                r["pos"] = hp
                pos = hp
                changed = True
            
            # 2. Wiktionary
            if not pos:
                p, g = wiktionary_pos_gender(es)
                if p:
                    r["pos"] = p
                    pos = p
                    changed = True
                    # If we got gender and didn't have it, grab it
                    if args.gender_nouns and pos == "noun" and not gen and g in ("m", "f"):
                        r["gender"] = g
                        gen = g
                        changed = True
            
            # 3. Sense mapping
            SENSE_MAP = {
                'verb': 'verb',
                'adjective': 'adjective', 'adj': 'adjective',
                'noun': 'noun',
                'color': 'noun', 'season': 'noun', 'location': 'noun',
            }
            if not pos and sense in SENSE_MAP:
                r["pos"] = SENSE_MAP[sense]
                pos = r["pos"]
                changed = True

            # 4. Verb guess
            if not pos and args.guess_verbs:
                if strip_accents(es).endswith(("ar", "er", "ir")):
                    r["pos"] = "verb"
                    pos = "verb"
                    changed = True

        # Gender enrichment for nouns
        elif args.gender_nouns and pos == "noun" and not gen:
            _, g = wiktionary_pos_gender(es)
            if g in ("m", "f"):
                r["gender"] = g
                gen = g
                changed = True
        
        if changed: updated += 1

    if updated:
        write_rows(rows, CSV_PATH)
        print(f"CSV enriched. Rows updated: {updated}")
    else:
        print("No updates found.")

    if args.push and updated:
        try:
            ids = anki.find_notes(query=f'deck:"{args.deck}" note:"{args.model}"')
            if ids:
                infos = anki.notes_info(ids)
                pos_map = {
                    (r.get("spanish") or "").strip().lower(): (r.get("pos"), r.get("gender"))
                    for r in rows if r.get("spanish")
                }
                
                pushed = 0
                for n in infos:
                    w = (n.get("fields", {}).get("Word", {}).get("value") or "").strip().lower()
                    if w in pos_map:
                        p_new, g_new = pos_map[w]
                        upd = {}
                        if p_new: upd["POS"] = p_new
                        if g_new in ("m", "f"): 
                            upd["Gender"] = g_new
                            upd["Article"] = "el" if g_new == "m" else "la"
                        
                        if upd:
                            anki.update_note_fields(n.get("noteId"), upd)
                            pushed += 1
                print(f"Pushed updates to {pushed} Anki notes.")
        except Exception as e:
            print(f"[warn] Push failed: {e}")

if __name__ == "__main__":
    main()
