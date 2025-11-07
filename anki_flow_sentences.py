#!/usr/bin/env python3
"""
Unified CLI (sentences): pass-through wrapper for sentences helpers.
Supports:
  sentences known --deck --model --min-ivl --min-reps --review-only --include-new --limit --use-notes --debug
  sentences build --deck --model --limit
"""
import argparse
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent


def run(cmd):
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"[error] Command failed: {' '.join(cmd)}\n{e}")
        sys.exit(1)


def main():
    ap = argparse.ArgumentParser(description="Unified CLI (sentences)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("sentences", help="Sentences helpers (known/build)")
    sub2 = p1.add_subparsers(dest="scmd", required=True)

    pk = sub2.add_parser("known", help="Export known words to data/known_words.json")
    pk.add_argument("--deck", default="My Spanish Deck::625")
    pk.add_argument("--model", default="*", help='Note type name or "*" for any')
    pk.add_argument("--min-ivl", type=int, default=0)
    pk.add_argument("--min-reps", type=int, default=1)
    pk.add_argument("--review-only", action="store_true")
    pk.add_argument("--include-new", action="store_true")
    pk.add_argument("--limit", type=int, default=None)
    pk.add_argument("--use-notes", action="store_true")
    pk.add_argument("--debug", action="store_true")

    pb = sub2.add_parser("build", help="Build Cloze notes from data/sentences_generated.json")
    pb.add_argument("--deck", default="My Spanish Deck::625")
    pb.add_argument("--model", default="Cloze")
    pb.add_argument("--limit", type=int, default=None)

    args = ap.parse_args()

    if args.cmd == "sentences" and args.scmd == "known":
        script = BASE / "scripts" / "sentences_get_known_words.py"
        cmd = [sys.executable, str(script), "--deck", args.deck, "--model", args.model]
        if args.min_ivl: cmd += ["--min-ivl", str(args.min_ivl)]
        if args.min_reps is not None: cmd += ["--min-reps", str(args.min_reps)]
        if args.review_only: cmd.append("--review-only")
        if not args.include_new: cmd.append("--exclude-new")
        else: cmd.append("--include-new")
        if args.limit: cmd += ["--limit", str(args.limit)]
        if args.use_notes: cmd.append("--use-notes")
        if args.debug: cmd.append("--debug")
        run(cmd)
    elif args.cmd == "sentences" and args.scmd == "build":
        script = BASE / "scripts" / "sentences_build.py"
        cmd = [sys.executable, str(script), "--deck", args.deck, "--model", args.model]
        if args.limit: cmd += ["--limit", str(args.limit)]
        run(cmd)

if __name__ == "__main__":
    main()
