#!/usr/bin/env python3
"""
Enrich POS (part of speech) and optionally Gender for nouns in 625_structured.es.csv,
then push updates to Anki notes.

Order of evidence for POS:
  1) Hints file (key: value)
  2) Spanish Wiktionary Spanish section (strict)
  3) English Wiktionary Spanish section (strict)
  4) CSV 'sense' column mapping (conservative)
  5) Optional verb guess by -ar/-er/-ir (only if --guess-verbs)

Gender is ONLY enriched for nouns (m/f) when found confidently in Wiktionary templates or text.

Usage examples:
  python scripts/enrich_pos_gender.py --pos-only --push
  python scripts/enrich_pos_gender.py --pos-only --gender-nouns --hints-pos prompts/pos_hints.yaml --push
  python scripts/enrich_pos_gender.py --pos-only --guess-verbs --push

Notes:
- POS values: noun | verb | adj (lowercase). Unknown stays blank.
- Creates a default hints file at prompts/pos_hints.yaml if --hints-pos is not provided and the file doesn't exist.
"""
import re
import sys
import csv
import unicodedata
from pathlib import Path
import argparse

try:
    import requests  # type: ignore
except Exception:
    print("This script requires 'requests'. Install: pip install requests")
    sys.exit(1)

BASE = Path(__file__).resolve().parent.parent
CSV_PATH = BASE / "625_structured.es.csv"
DEFAULT_HINTS = BASE / "prompts" / "pos_hints.yaml"
ANKI = "http://127.0.0.1:8765"

# ------------------- Anki helpers -------------------

def anki(action, **params):
    r = requests.post(ANKI, json={"action": action, "version": 6, "params": params}, timeout=30)
    r.raise_for_status()
    data = r.json()
    if data.get("error"):
        raise RuntimeError(data["error"]) 
    return data["result"]

# ------------------- Utilities ----------------------

def strip_accents(s: str) -> str:
    return ''.join(ch for ch in unicodedata.normalize('NFD', s) if unicodedata.category(ch) != 'Mn')

# ------------------- Wiktionary fetch --------------
WIKI_ES = "https://es.wiktionary.org/w/api.php"
WIKI_EN = "https://en.wiktionary.org/w/api.php"

LANG_HEAD_ES = re.compile(r"^==\s*(?:Español|\{\{\s*lengua\s*\|\s*es\s*\}\})\s*==\s*$", re.MULTILINE | re.IGNORECASE)
LANG_HEAD_EN = re.compile(r"^==\s*Spanish\s*==\s*$", re.MULTILINE | re.IGNORECASE)
POS_HEAD = re.compile(r"^===\s*([^=\n]+)\s*===\s*$", re.MULTILINE)
BOLD_LINE = re.compile(r"'''[^']+'''\s*\(([^)]+)\)")  # e.g., '''dólar''' (sustantivo masculino)
TEMPLATE_SUST = re.compile(r"\{\{\s*sustantivo\|es\|([mf])", re.IGNORECASE)
TEMPLATE_NOUN = re.compile(r"\{\{\s*es-noun\|([mf])", re.IGNORECASE)

INF_VERB = re.compile(r"^[a-záéíóúñ]+(ar|er|ir)$", re.IGNORECASE)

POS_MAP_KEYS = {
    'sustantivo': 'noun',
    'verbo': 'verb',
    'adjetivo': 'adj',
}


def fetch_wiki(page: str, url: str) -> str:
    try:
        resp = requests.get(url, params={
            "action": "parse",
            "prop": "wikitext",
            "page": page,
            "format": "json",
        }, timeout=10)
        if not resp.ok:
            return ""
        return resp.json().get("parse", {}).get("wikitext", {}).get("*", "")
    except Exception:
        return ""


def extract_language_section(text: str, lang: str) -> str:
    if not text:
        return ""
    if lang == 'es':
        m = LANG_HEAD_ES.search(text)
    else:
        m = LANG_HEAD_EN.search(text)
    if not m:
        return ""
    start = m.end()
    # find next language header
    rest = text[start:]
    m2 = re.search(r"^==[^=].*==\s*$", rest, re.MULTILINE)
    end = start + m2.start() if m2 else len(text)
    return text[start:end]


def parse_spanish_section(section: str):
    """Return (pos, gender) from a Spanish language section of Wiktionary wikitext."""
    if not section:
        return "", ""
    # 1) Direct template-based gender for nouns
    mg = TEMPLATE_SUST.search(section) or TEMPLATE_NOUN.search(section)
    gender = ''
    if mg:
        g = mg.group(1).lower()
        gender = 'm' if g.startswith('m') else ('f' if g.startswith('f') else '')
    # 2) Identify the first POS header within the section
    pos = ''
    for mh in POS_HEAD.finditer(section):
        hdr = mh.group(1).strip().lower()
        for key, val in POS_MAP_KEYS.items():
            if key in hdr:
                pos = val
                break
        if pos:
            break
    # 3) Fallback: bold line with (sustantivo masculino)
    if not pos:
        mb = BOLD_LINE.search(section)
        if mb:
            meta = mb.group(1).lower()
            if 'sustantivo' in meta:
                pos = 'noun'
                if not gender:
                    if 'masculino' in meta: gender = 'm'
                    elif 'femenino' in meta: gender = 'f'
            elif 'verbo' in meta:
                pos = 'verb'
            elif 'adjetivo' in meta:
                pos = 'adj'
    return pos, gender


def wiki_pos_gender(word: str):
    """Return (pos, gender) using Spanish/English Wiktionary, Spanish section only."""
    variants = [word, unicodedata.normalize('NFC', word), strip_accents(word), word.capitalize()]
    # Spanish Wiktionary first
    for v in variants:
        text = fetch_wiki(v, WIKI_ES)
        sec = extract_language_section(text, 'es') if text else ''
        if sec:
            p, g = parse_spanish_section(sec)
            if p: return p, g
    # English Wiktionary Spanish section
    for v in variants:
        text = fetch_wiki(v, WIKI_EN)
        sec = extract_language_section(text, 'en') if text else ''
        if sec:
            p, g = parse_spanish_section(sec)
            if p: return p, g
    return '', ''

# ------------------- Hints loader ------------------

def ensure_default_hints():
    if not DEFAULT_HINTS.parent.exists():
        DEFAULT_HINTS.parent.mkdir(parents=True, exist_ok=True)
    if not DEFAULT_HINTS.exists():
        DEFAULT_HINTS.write_text(
            "# POS hints (key: value)\n"
            "dólar: noun\n"
            "dolar: noun\n"
            "rojo: adj\n"
            "azul: adj\n"
            "animal: noun\n"
            "arcilla: noun\n"
            "limpiar: verb\n"
            "cerca: adj\n",
            encoding="utf-8"
        )


def load_hints(path: Path | None) -> dict:
    if path is None:
        ensure_default_hints()
        path = DEFAULT_HINTS
    if not path.exists():
        return {}
    hints = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith('#') or ':' not in s:
            continue
        k, v = s.split(':', 1)
        hints[k.strip().lower()] = v.strip().lower()
    return hints

# ------------------- CSV IO ------------------------
FIELDS = ["english","sense","pos","spanish","gender","ipa","notes"]

SENSE_MAP = {
    'verb': 'verb',
    'adjective': 'adj', 'adj.': 'adj', 'adj': 'adj',
    'noun': 'noun',
    'color': 'adj', 'season': 'noun', 'location': 'noun', 'the location': 'noun',
}

def read_rows():
    with CSV_PATH.open("r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        for k in FIELDS:
            r.setdefault(k, "")
    return rows

def write_rows(rows):
    with CSV_PATH.open("w", newline="", encoding="utf-8") as out:
        w = csv.DictWriter(out, fieldnames=FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in FIELDS})

# ------------------- Main --------------------------

def main():
    ap = argparse.ArgumentParser(description="Enrich POS/Gender in CSV and optionally push to Anki")
    ap.add_argument("--pos-only", action="store_true", help="Only fill POS when empty")
    ap.add_argument("--gender-nouns", action="store_true", help="Fill Gender for nouns (m/f) when empty")
    ap.add_argument("--guess-verbs", action="store_true", help="If wiki fails, guess verbs by -ar/-er/-ir")
    ap.add_argument("--hints-pos", default=None, help="Path to hints file (key: value) for POS overrides")
    ap.add_argument("--push", action="store_true", help="Update matching Anki notes after enrichment")
    ap.add_argument("--deck", default="My Spanish Deck::625")
    ap.add_argument("--model", default="Picture Word")
    args = ap.parse_args()

    hints = load_hints(Path(args.hints_pos) if args.hints_pos else None)

    rows = read_rows()
    updated = 0

    for r in rows:
        es = (r.get("spanish") or "").strip()
        if not es:
            continue
        key = es.lower()
        pos = (r.get("pos") or "").strip().lower()
        gen = (r.get("gender") or "").strip().lower()
        sense = (r.get("sense") or "").strip().lower()

        changed = False
        # POS enrichment path (fills only if pos is blank)
        if args.pos_only and not pos:
            # 1) hints override
            hp = hints.get(key)
            if hp in ("noun","verb","adj"):
                r["pos"] = hp
                pos = hp
                changed = True
            # 2) Wiktionary (ES then EN Spanish sections)
            if not pos:
                p, g = wiki_pos_gender(es)
                if p:
                    r["pos"] = p
                    pos = p
                    changed = True
                    if args.gender_nouns and pos == "noun" and not gen and g in ("m","f"):
                        r["gender"] = g
                        gen = g
                        changed = True
            # 3) sense mapping
            if not pos and sense:
                sm = SENSE_MAP.get(sense)
                if sm:
                    r["pos"] = sm
                    pos = sm
                    changed = True
            # 4) optional verb guess
            if not pos and args.guess_verbs and INF_VERB.match(strip_accents(es)):
                r["pos"] = "verb"
                pos = "verb"
                changed = True
        # Gender-only enrichment for nouns (when pos already set)
        elif args.gender_nouns and pos == "noun" and not gen:
            _, g = wiki_pos_gender(es)
            if g in ("m","f"):
                r["gender"] = g
                gen = g
                changed = True

        if changed:
            updated += 1

    write_rows(rows)
    print(f"CSV enriched. Rows updated: {updated}")

    if args.push and updated:
        try:
            ids = anki("findNotes", query=f'deck:"{args.deck}" note:"{args.model}"')
            if ids:
                infos = anki("notesInfo", notes=ids)
                pos_map = {}
                for r in rows:
                    sw = (r.get("spanish") or "").strip().lower()
                    pos_map[sw] = ((r.get("pos") or "").strip(), (r.get("gender") or "").strip())
                for n in infos:
                    fields = n.get("fields", {})
                    word = (fields.get("Word", {}).get("value") or "").strip().lower()
                    if not word or word not in pos_map:
                        continue
                    p, g = pos_map[word]
                    upd = {}
                    if p:
                        upd["POS"] = p
                    if g in ("m","f"):
                        upd["Gender"] = g
                        if "Article" in fields:
                            upd["Article"] = "el" if g == "m" else "la"
                    if upd:
                        anki("updateNoteFields", note={"id": n.get("noteId"), "fields": upd})
                print("Pushed POS/Gender to Anki.")
        except Exception as e:
            print(f"[warn] Could not push to Anki: {e}")

if __name__ == "__main__":
    main()
