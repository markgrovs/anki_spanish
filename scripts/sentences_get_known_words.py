#!/usr/bin/env python3
"""
Export known words (Picture Word notes) from Anki using AnkiConnect.
Flexible filters so you can dial how "known" the words must be.
If --model "*" is used, no note-type filter is applied; we then accept any note that has a 'Word' field.
Includes a --debug flag to print diagnostics.
Optionally use findNotes/notesInfo with --use-notes to better match Browser queries.
"""
import json
import sys
from pathlib import Path
import argparse
from collections import Counter

try:
    import requests  # type: ignore
except Exception:
    print("This script requires 'requests'. Install: pip install requests")
    sys.exit(1)

BASE = Path(__file__).resolve().parent.parent
OUT = BASE / "data" / "known_words.json"
ANKI = "http://127.0.0.1:8765"


def anki(action, **params):
    r = requests.post(ANKI, json={"action": action, "version": 6, "params": params}, timeout=60)
    r.raise_for_status()
    data = r.json()
    if data.get("error"):
        raise RuntimeError(data["error"]) 
    return data["result"]


def build_query(deck: str, model: str, exclude_new: bool, min_ivl: int, min_reps: int, review_only: bool):
    parts = []
    if deck:
        parts.append(f'deck:"{deck}"')
    if model and model != "*":
        parts.append(f'note:"{model}"')
    if review_only:
        parts.append('is:review')
    if exclude_new:
        parts.append('-is:new')
    if min_ivl and min_ivl > 0:
        parts.append(f'prop:ivl>={min_ivl}')
    if min_reps and min_reps > 0:
        parts.append(f'prop:reps>={min_reps}')
    return ' '.join(parts) if parts else '*'


def export_via_cards(query: str, limit: int | None, debug: bool):
    card_ids = anki("findCards", query=query)
    if debug:
        print(f"Matched cards: {len(card_ids)}")
    if not card_ids:
        return [], {"cards": 0, "notes_skipped_no_word": 0, "models": {}}

    infos = anki("cardsInfo", cards=card_ids)
    seen_notes = set()
    words = []
    model_counts = Counter()
    field_miss = 0

    for ci in infos:
        nid = ci.get("noteId")
        mname = ci.get("modelName") or "(unknown)"
        model_counts[mname] += 1
        if nid in seen_notes:
            continue
        fields = ci.get("fields", {})
        if "Word" not in fields:
            field_miss += 1
            continue
        seen_notes.add(nid)
        word = (fields.get("Word", {}).get("value") or "").strip().lower()
        if not word:
            continue
        words.append(word)
        if limit and len(words) >= limit:
            break

    diag = {
        "cards": len(card_ids),
        "notes_skipped_no_word": field_miss,
        "models": dict(model_counts),
    }
    return words, diag


def export_via_notes(query: str, limit: int | None, debug: bool):
    note_ids = anki("findNotes", query=query)
    if debug:
        print(f"Matched notes: {len(note_ids)}")
    if not note_ids:
        return [], {"notes": 0, "notes_skipped_no_word": 0, "models": {}}

    # notesInfo returns a list of note dicts with fields and modelName
    notes = anki("notesInfo", notes=note_ids)
    words = []
    model_counts = Counter()
    field_miss = 0

    for n in notes:
        mname = n.get("modelName") or "(unknown)"
        model_counts[mname] += 1
        fields = n.get("fields", {})
        if "Word" not in fields:
            field_miss += 1
            continue
        word = (fields.get("Word", {}).get("value") or "").strip().lower()
        if not word:
            continue
        words.append(word)
        if limit and len(words) >= limit:
            break

    diag = {
        "notes": len(note_ids),
        "notes_skipped_no_word": field_miss,
        "models": dict(model_counts),
    }
    return words, diag


def main():
    ap = argparse.ArgumentParser(description="Export known Spanish words from Anki")
    ap.add_argument("--deck", default="My Spanish Deck::625")
    ap.add_argument("--model", default="*", help='Note type name or "*" for any')
    ap.add_argument("--min-ivl", type=int, default=0, help="Minimum interval (days)")
    ap.add_argument("--min-reps", type=int, default=1, help="Minimum total reviews (reps)")
    ap.add_argument("--exclude-new", action="store_true", default=True, help="Exclude new cards (default)")
    ap.add_argument("--include-new", dest="exclude_new", action="store_false", help="Include new cards")
    ap.add_argument("--review-only", action="store_true", help="Only include is:review cards")
    ap.add_argument("--limit", type=int, default=None, help="Optional max number of notes")
    ap.add_argument("--use-notes", action="store_true", help="Use findNotes/notesInfo instead of findCards/cardsInfo")
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()

    query = build_query(
        deck=args.deck,
        model=args.model,
        exclude_new=args.exclude_new,
        min_ivl=args.min_ivl,
        min_reps=args.min_reps,
        review_only=args.review_only,
    )

    if args.debug:
        print(f"Query: {query}")

    if args.use_notes:
        words, diag = export_via_notes(query, args.limit, args.debug)
    else:
        words, diag = export_via_cards(query, args.limit, args.debug)

    # dedupe while preserving order
    uniq = []
    seenw = set()
    for w in words:
        if w in seenw: continue
        seenw.add(w)
        uniq.append(w)

    if args.debug:
        for k, v in diag.items():
            if isinstance(v, dict):
                print("Model distribution:")
                for mk, mv in v.items():
                    print(f"  {mk}: {mv}")
            else:
                print(f"{k}: {v}")
        print(f"Unique words collected: {len(uniq)}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"count": len(uniq), "words": uniq, "query": query, "diag": diag}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(uniq)} words to {OUT}")

if __name__ == "__main__":
    main()
