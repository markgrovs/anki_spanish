#!/usr/bin/env python3
import re
import csv
import sys
from pathlib import Path

INPUT = Path("625.txt")
OUTPUT = Path("625_structured.csv")

# crude POS/sense extraction from parentheses
POS_HINTS = {"noun","verb","adjective","adverb","season","time","location","color","food","sport","music"}
HEADER_SKIP = ("Fluent'Forever.com", "Your first 625", "The first entries",)
PAGE_NUM_RE = re.compile(r'^\s*\d+\s*$')

def split_columns(line:str):
    # many PDFs export columns separated by 2+ spaces
    return [c.strip() for c in re.split(r"\s{2,}", line.strip()) if c.strip()]

def normalize_token(tok:str):
    tok = tok.replace("–", "-").strip()
    tok = re.sub(r"\s+", " ", tok)
    return tok

def parse_entry(entry:str):
    # Extract base and parenthetical e.g., "back (body)" → base="back", paren="body"
    m = re.match(r"^(.*?)(?:\s*\((.*?)\))?$", entry)
    base = normalize_token(m.group(1)) if m else normalize_token(entry)
    paren = normalize_token(m.group(2)) if (m and m.group(2)) else ""
    pos = ""
    sense = ""
    if paren:
        # If paren contains a known POS word, treat it as POS; else as sense
        lower = paren.lower()
        if any(p in lower for p in POS_HINTS):
            pos = lower
        else:
            sense = paren
    # remove “/new” hints inside parentheses like "old (/young)" → sense="opposite: young"
    sense = sense.replace("/"," / ").strip()
    return base, sense, pos

def expand_slash_synonyms(base:str):
    # e.g., "big/large" → ["big","large"]; keep phrases like "cell phone"
    if "/" in base and " " not in base:
        parts = [p.strip() for p in base.split("/") if p.strip()]
        # dedupe while preserving order
        seen = set()
        out = []
        for p in parts:
            if p not in seen:
                out.append(p)
                seen.add(p)
        return out
    return [base]

def is_junk(line:str):
    if not line.strip():
        return True
    if any(h in line for h in HEADER_SKIP):
        return True
    if PAGE_NUM_RE.match(line):
        return True
    return False

def main():
    rows = []
    with INPUT.open("r", encoding="utf-8") as f:
        for raw in f:
            if is_junk(raw):
                continue
            # Lines can carry 3–4 entries per line
            parts = split_columns(raw)
            for part in parts:
                base, sense, pos = parse_entry(part)
                # Expand "big/large"
                for eng in expand_slash_synonyms(base):
                    if not eng:
                        continue
                    rows.append({
                        "english": eng,
                        "sense": sense,
                        "pos": pos,
                        "spanish": "",     # fill later
                        "notes": ""        # optional
                    })
    # de-duplicate while preserving order
    seen = set()
    dedup = []
    for r in rows:
        key = (r["english"].lower(), r["sense"].lower(), r["pos"].lower())
        if key in seen:
            continue
        seen.add(key)
        dedup.append(r)

    with OUTPUT.open("w", newline="", encoding="utf-8") as out:
        w = csv.DictWriter(out, fieldnames=["english","sense","pos","spanish","notes"])
        w.writeheader()
        w.writerows(dedup)

    print(f"Wrote {len(dedup)} entries to {OUTPUT}")

if __name__ == "__main__":
    if not INPUT.exists():
        print("Missing 625.txt. Place it next to this script.")
        sys.exit(1)
    main()
