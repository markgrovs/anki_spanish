#!/usr/bin/env python3
"""
Export known words from Anki using shared 'lib'.
"""
import sys
import json
import argparse
from pathlib import Path
from collections import Counter

# Add parent to path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from lib.config import BASE_DIR, DECK_NAME
from lib.anki_client import anki

OUT = BASE_DIR / "data" / "known_words.json"

def build_query(deck, model, exclude_new, min_ivl, min_reps, review_only):
    parts = []
    if deck: parts.append(f'deck:"{deck}"')
    if model and model != "*": parts.append(f'note:"{model}"')
    if review_only: parts.append('is:review')
    if exclude_new: parts.append('-is:new')
    if min_ivl > 0: parts.append(f'prop:ivl>={min_ivl}')
    if min_reps > 0: parts.append(f'prop:reps>={min_reps}')
    return ' '.join(parts) if parts else '*'

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--deck", default=DECK_NAME)
    ap.add_argument("--model", default="*")
    ap.add_argument("--min-ivl", type=int, default=0)
    ap.add_argument("--min-reps", type=int, default=0)
    ap.add_argument("--exclude-new", action="store_true", default=True)
    ap.add_argument("--include-new", dest="exclude_new", action="store_false")
    ap.add_argument("--review-only", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--use-notes", action="store_true", default=True)
    ap.add_argument("--debug", action="store_true")
    ap.add_argument("--mode", choices=["strict", "learned", "all"], default="strict", 
                    help="strict=reviewed(reps>0), learned=seen(-is:new), all=everything")
    
    args = ap.parse_args()

    # Apply mode defaults if not overridden explicitly
    # Note: args.min_reps is 0 by default now due to my previous logic change request
    
    if args.mode == "strict":
        # Strict: must have > 0 reps
        if args.min_reps == 0: 
            args.min_reps = 1
        args.exclude_new = True
    elif args.mode == "learned":
        # Learned: seen at least once (learning or review), so exclude new is enough
        args.min_reps = 0
        args.exclude_new = True
    elif args.mode == "all":
        # All: include new
        args.min_reps = 0
        args.exclude_new = False

    query = build_query(args.deck, args.model, args.exclude_new, args.min_ivl, args.min_reps, args.review_only)
    if args.debug: print(f"Query: {query}")

    words = []
    diag = {"count": 0, "skipped": 0, "models": Counter()}

    try:
        if args.use_notes:
            ids = anki.find_notes(query)
            if ids:
                infos = anki.notes_info(ids)
                for n in infos:
                    m = n.get("modelName", "unknown")
                    diag["models"][m] += 1
                    w = (n.get("fields", {}).get("Word", {}).get("value") or "").strip().lower()
                    if w: words.append(w)
                    else: diag["skipped"] += 1
        else:
            ids = anki.invoke("findCards", query=query)
            if ids:
                infos = anki.invoke("cardsInfo", cards=ids)
                seen_notes = set()
                for c in infos:
                    nid = c.get("noteId")
                    if nid in seen_notes: continue
                    seen_notes.add(nid)
                    
                    m = c.get("modelName", "unknown")
                    diag["models"][m] += 1
                    w = (c.get("fields", {}).get("Word", {}).get("value") or "").strip().lower()
                    if w: words.append(w)
                    else: diag["skipped"] += 1

    except Exception as e:
        print(f"[error] {e}")
        sys.exit(1)

    # Dedupe
    uniq = list(dict.fromkeys(words))
    if args.limit: uniq = uniq[:args.limit]

    diag["count"] = len(uniq)
    diag["models"] = dict(diag["models"])

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "count": len(uniq),
        "words": uniq,
        "query": query,
        "diag": diag
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    
    print(f"Exported {len(uniq)} words to {OUT}")

if __name__ == "__main__":
    main()
