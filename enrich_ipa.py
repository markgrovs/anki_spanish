#!/usr/bin/env python3
"""
Enrich IPA in 625_structured.es.csv using shared library logic.
"""
from pathlib import Path
from lib.csv_store import read_rows, write_rows
from lib.ipa import get_best_ipa
from lib.config import CSV_PATH

def main():
    if not CSV_PATH.exists():
        print(f"CSV not found: {CSV_PATH}")
        return

    rows = read_rows(CSV_PATH)
    total = len(rows)
    updated = 0
    
    print(f"Checking IPA for {total} rows...")

    for i, r in enumerate(rows, 1):
        if r.get("ipa"):
            continue
            
        word = (r.get("spanish") or "").strip()
        if not word:
            continue
            
        ipa = get_best_ipa(word)
        if ipa:
            r["ipa"] = ipa
            updated += 1
            if updated % 20 == 0:
                print(f"[{i}/{total}] added IPA for {updated} words so far...")

    if updated:
        write_rows(rows, CSV_PATH)
        print(f"Done. Updated {updated} entries.")
    else:
        print("Done. No new IPA entries found.")

if __name__ == "__main__":
    main()
