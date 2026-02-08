#!/usr/bin/env python3
"""
Sync checker: compare CSV ↔ Anki and report/fix discrepancies.

Usage:
  python scripts/sync_check.py                  # Report only
  python scripts/sync_check.py --fix            # Auto-fix what it can
  python scripts/sync_check.py --fix --dry-run  # Show what --fix would do

Checks performed:
  1. Words in Anki but missing from CSV  (orphaned Anki notes)
  2. Words in CSV with spanish filled but not in Anki  (unbuilt cards)
  3. Field mismatches (Gender, POS, IPA, Article differ between CSV and Anki)
  4. Duplicate Word values within Anki
  5. Case mismatches (e.g., "Frío" vs "frío")

Fix actions (with --fix):
  - Push CSV values → Anki for field mismatches (CSV is source of truth)
  - Report orphans and unbuilt cards (manual decision needed)
"""
import sys
import csv
import argparse

from pathlib import Path

import sys
# Add parent to path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from lib.config import CSV_PATH, FIELDNAMES
from lib.anki_client import anki
from lib.csv_store import read_rows
from lib.gender import compute_article


try:
    import requests
except ImportError:
    print("This script requires 'requests'. Install: pip install requests")
    sys.exit(1)

BASE = Path(__file__).resolve().parent.parent
CSV_PATH = BASE / "625_structured.es.csv"
ANKI = "http://127.0.0.1:8765"

FIELDNAMES = ["english", "sense", "pos", "spanish", "gender", "ipa", "notes"]







# ---- Main ----

def main():
    ap = argparse.ArgumentParser(description="Check and fix CSV ↔ Anki sync")
    ap.add_argument("--fix", action="store_true", help="Auto-fix field mismatches (CSV → Anki)")
    ap.add_argument("--dry-run", action="store_true", help="With --fix, show changes without applying")
    ap.add_argument("--deck", default="My Spanish Deck::625")
    ap.add_argument("--model", default="Picture Word")
    args = ap.parse_args()

    rows = read_rows(CSV_PATH)
    csv_by_word = {}
    for r in rows:
        s = (r.get("spanish") or "").strip()
        if s:
            csv_by_word[s] = r

    # Fetch all Anki notes
    note_ids = anki.find_notes(query=f'deck:"{args.deck}" note:"{args.model}"')
    if not note_ids:
        print(f"No notes found in deck '{args.deck}' with model '{args.model}'")
        return

    note_infos = anki.notes_info(notes=note_ids)
    anki_by_word = {}
    duplicates = []
    for n in note_infos:
        f = n.get("fields", {})
        w = (f.get("Word", {}).get("value") or "").strip()
        if not w:
            continue
        if w in anki_by_word:
            duplicates.append(w)
        anki_by_word[w] = n

    anki_words = set(anki_by_word.keys())
    csv_words = set(csv_by_word.keys())

    # ---- Check 1: Orphaned Anki notes ----
    orphans = sorted(anki_words - csv_words)

    # ---- Check 1b: Case mismatches (may be hiding orphans) ----
    csv_lower = {w.lower(): w for w in csv_words}
    case_mismatches = []
    true_orphans = []
    for w in orphans:
        if w.lower() in csv_lower:
            case_mismatches.append((w, csv_lower[w.lower()]))
        else:
            true_orphans.append(w)

    # ---- Check 2: Unbuilt cards ----
    unbuilt = sorted(csv_words - anki_words)

    # ---- Check 3: Field mismatches ----
    field_diffs = []
    in_both = anki_words & csv_words
    for w in sorted(in_both):
        csv_row = csv_by_word[w]
        anki_note = anki_by_word[w]
        af = anki_note.get("fields", {})
        nid = anki_note.get("noteId")

        diffs = {}
        # Compare Gender
        csv_gender = (csv_row.get("gender") or "").strip().lower()
        anki_gender = (af.get("Gender", {}).get("value") or "").strip().lower()
        if csv_gender != anki_gender:
            diffs["Gender"] = (anki_gender, csv_gender)

        # Compare POS
        csv_pos = (csv_row.get("pos") or "").strip().lower()
        anki_pos = (af.get("POS", {}).get("value") or "").strip().lower()
        if csv_pos != anki_pos:
            diffs["POS"] = (anki_pos, csv_pos)

        # Compare IPA
        csv_ipa = (csv_row.get("ipa") or "").strip()
        anki_ipa = (af.get("IPA", {}).get("value") or "").strip()
        if csv_ipa != anki_ipa:
            diffs["IPA"] = (anki_ipa, csv_ipa)

        # Compare Article (derived from CSV gender+pos)
        csv_article = compute_article(w, csv_gender, csv_pos)
        anki_article = (af.get("Article", {}).get("value") or "").strip().lower()
        if csv_article != anki_article:
            diffs["Article"] = (anki_article, csv_article)

        if diffs:
            field_diffs.append((w, nid, diffs))

    # ---- Check 4: Duplicates ----
    dupes = sorted(set(duplicates))

    # ---- Report ----
    print("=" * 60)
    print("  CSV ↔ Anki Sync Report")
    print("=" * 60)
    print(f"  CSV words (with spanish):  {len(csv_words)}")
    print(f"  Anki notes:                {len(anki_words)}")
    print(f"  In sync:                   {len(in_both)}")
    print()

    all_clean = True

    if dupes:
        all_clean = False
        print(f"⚠️  DUPLICATES in Anki ({len(dupes)}):")
        for w in dupes:
            print(f"    {w}")
        print("  → Fix manually in Anki (delete the extra note)")
        print()

    if case_mismatches:
        all_clean = False
        print(f"⚠️  CASE MISMATCHES ({len(case_mismatches)}):")
        for anki_w, csv_w in case_mismatches:
            print(f"    Anki: {anki_w!r}  ←→  CSV: {csv_w!r}")
        print("  → Anki Word field should match CSV exactly")
        print()

    if true_orphans:
        all_clean = False
        print(f"⚠️  IN ANKI BUT NOT IN CSV ({len(true_orphans)}):")
        for w in true_orphans:
            print(f"    {w}")
        print("  → Either add to CSV or delete from Anki")
        print()

    if unbuilt:
        # This is expected — just informational
        print(f"ℹ️  IN CSV BUT NOT YET IN ANKI ({len(unbuilt)}):")
        if len(unbuilt) <= 20:
            for w in unbuilt:
                print(f"    {w}")
        else:
            for w in unbuilt[:10]:
                print(f"    {w}")
            print(f"    ... and {len(unbuilt) - 10} more")
        print("  → Run 'python anki_flow.py build' to create these cards")
        print()

    if field_diffs:
        all_clean = False
        print(f"⚠️  FIELD MISMATCHES ({len(field_diffs)}):")
        for w, nid, diffs in field_diffs:
            print(f"    {w} (noteId {nid}):")
            for field, (anki_val, csv_val) in diffs.items():
                print(f"      {field}: Anki={anki_val!r} → CSV={csv_val!r}")

        if args.fix:
            print()
            fixed = 0
            for w, nid, diffs in field_diffs:
                updates = {}
                for field, (anki_val, csv_val) in diffs.items():
                    updates[field] = csv_val
                if updates:
                    if args.dry_run:
                        print(f"  [dry-run] Would update {w}: {updates}")
                    else:
                        anki.update_note_fields(nid, updates)
                        fixed += 1
            if args.dry_run:
                print(f"\n  Dry run complete. {len(field_diffs)} notes would be updated.")
            else:
                print(f"\n  ✅ Fixed {fixed} notes (CSV → Anki).")
        else:
            print("  → Run with --fix to push CSV values to Anki")
        print()

    if all_clean and not unbuilt:
        print("✅ Everything is in sync!")
    elif all_clean:
        print("✅ All built cards are in sync with CSV.")

    print()

if __name__ == "__main__":
    main()
