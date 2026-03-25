#!/usr/bin/env python3

import csv
import argparse
from pathlib import Path

BASE_DIR = Path("/Users/markgroves/Documents/[06] Development/spanish_anki")
BACKLOG = BASE_DIR / "data" / "word_backlog.csv"

def ensure_file():
    if not BACKLOG.exists():
        BACKLOG.parent.mkdir(parents=True, exist_ok=True)
        with BACKLOG.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["surface", "lemma", "english", "source_sentence", "source_topic", "status", "notes"])

def row_exists(surface, lemma):
    if not BACKLOG.exists():
        return False
    with BACKLOG.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["surface"].strip() == surface.strip() and row["lemma"].strip() == lemma.strip():
                return True
    return False

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--surface", required=True)
    parser.add_argument("--lemma", default="")
    parser.add_argument("--english", default="")
    parser.add_argument("--source-sentence", default="")
    parser.add_argument("--source-topic", default="")
    parser.add_argument("--notes", default="")
    args = parser.parse_args()

    ensure_file()

    surface = args.surface.strip()
    lemma = args.lemma.strip() or surface

    if row_exists(surface, lemma):
        print(f"Already exists: surface={surface}, lemma={lemma}")
        return

    with BACKLOG.open("a", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            surface,
            lemma,
            args.english.strip(),
            args.source_sentence.strip(),
            args.source_topic.strip(),
            "new",
            args.notes.strip()
        ])

    print(f"Added: surface={surface}, lemma={lemma}")

if __name__ == "__main__":
    main()
