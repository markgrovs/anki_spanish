#!/usr/bin/env python3
"""
Sentences subcommands for anki_flow.py: known, build.
- known: export known_words.json using the same filter you chose.
- build: import data/sentences_generated.json into Anki Cloze notes.
"""
import argparse
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent


def run(cmd):
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"[error] Command failed: {' '.join(cmd)}\n{e}")
        sys.exit(1)


def main():
    ap = argparse.ArgumentParser(description="Sentences helper")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("known", help="Export known words to data/known_words.json")
    p1.add_argument("--deck", default="My Spanish Deck::625")
    p1.add_argument("--model", default="Picture Word")
    p1.add_argument("--min-ivl", type=int, default=3)
    p1.add_argument("--limit", type=int, default=None)

    p2 = sub.add_parser("build", help="Build Cloze notes from data/sentences_generated.json")
    p2.add_argument("--deck", default="My Spanish Deck::625")
    p2.add_argument("--model", default="Cloze")
    p2.add_argument("--limit", type=int, default=None)

    args = ap.parse_args()

    if args.cmd == "known":
        script = BASE / "scripts" / "sentences_get_known_words.py"
        cmd = [sys.executable, str(script), "--deck", args.deck, "--model", args.model, "--min-ivl", str(args.min_ivl)]
        if args.limit: cmd += ["--limit", str(args.limit)]
        run(cmd)
    elif args.cmd == "build":
        script = BASE / "scripts" / "sentences_build.py"
        cmd = [sys.executable, str(script), "--deck", args.deck, "--model", args.model]
        if args.limit: cmd += ["--limit", str(args.limit)]
        run(cmd)

if __name__ == "__main__":
    main()
