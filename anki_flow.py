#!/usr/bin/env python3
"""
Unified CLI for your Spanish→Anki workflow.

Subcommands:
  pick                Interactive Spanish selection (translate_pick.py)
  enrich              Fill missing IPA in CSV (enrich_ipa.py)
  build               Build/update Picture Word cards (build_cards.py)
  audit               Report missing counts (image/audio/ipa/gender)
  sentences known     Export known words (flexible Anki filters)
  sentences build     Build/Upsert Cloze sentence notes from JSON

Usage examples:
  python anki_flow.py pick
  python anki_flow.py enrich
  python anki_flow.py build --only-missing --limit 25
  python anki_flow.py audit
  python anki_flow.py sentences known --deck "My Spanish Deck::625" --model "*" --review-only --min-ivl 3 --use-notes --debug
  python anki_flow.py sentences build --deck "My Spanish Deck::Sentences" --model "Cloze" --limit 20 --update-existing --debug
"""
import argparse
import subprocess
import sys
from pathlib import Path
import csv

BASE = Path(__file__).resolve().parent
CSV = BASE / "625_structured.es.csv"


def run(cmd):
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"[error] Command failed: {' '.join(cmd)}\n{e}")
        sys.exit(1)

# ---------------- Core commands ----------------

def cmd_pick(args):
    script = BASE / "translate_pick.py"
    if not script.exists():
        print("translate_pick.py not found")
        sys.exit(1)
    run([sys.executable, str(script)])


def cmd_enrich(args):
    script = BASE / "enrich_ipa.py"
    if not script.exists():
        print("enrich_ipa.py not found")
        sys.exit(1)
    run([sys.executable, str(script)])


def cmd_build(args):
    script = BASE / "build_cards.py"
    if not script.exists():
        print("build_cards.py not found")
        sys.exit(1)
    cmd = [sys.executable, str(script)]
    if args.only_missing: cmd.append("--only-missing")
    if args.regen_audio: cmd.append("--regen-audio")
    if args.recalc_ipa: cmd.append("--recalc-ipa")
    if args.no_open_image_search: cmd.append("--no-open-image-search")
    if args.limit is not None: cmd += ["--limit", str(args.limit)]
    if args.deck: cmd += ["--deck", args.deck]
    if args.model: cmd += ["--model", args.model]
    if args.voice: cmd += ["--voice", args.voice]
    if args.rate: cmd += ["--rate", str(args.rate)]
    run(cmd)


def cmd_audit(args):
    if not CSV.exists():
        print(f"CSV not found: {CSV}")
        sys.exit(1)
    with CSV.open("r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    total = len(rows)
    missing_es = sum(1 for r in rows if not (r.get("spanish") or "").strip())
    missing_gender = sum(1 for r in rows if not (r.get("gender") or "").strip())
    missing_ipa = sum(1 for r in rows if not (r.get("ipa") or "").strip())
    print("Audit:")
    print(f"  Rows total:       {total}")
    print(f"  Missing Spanish:   {missing_es}")
    print(f"  Missing Gender:    {missing_gender}")
    print(f"  Missing IPA:       {missing_ipa}")
    images_dir = BASE / "media" / "images"
    audio_dir = BASE / "media" / "audio"
    from unicodedata import normalize
    def slugify(s: str) -> str:
        s = (s or "").strip().lower()
        s = normalize("NFD", s)
        s = "".join(ch for ch in s if not ord(ch) in range(0x300, 0x370))
        s = "".join(ch if (ch.isalnum() or ch in ("_","-"," ")) else "_" for ch in s)
        return "_".join(filter(None, s.split()))
    miss_img = miss_aud = 0
    for r in rows:
        es = (r.get("spanish") or "").strip()
        if not es: continue
        base = slugify(es)
        has_img = any((images_dir / f"{base}{ext}").exists() for ext in (".jpg",".jpeg",".png",".webp"))
        has_aud = (audio_dir / f"{base}.mp3").exists()
        if not has_img: miss_img += 1
        if not has_aud: miss_aud += 1
    print(f"  Missing images:    {miss_img}")
    print(f"  Missing audio:     {miss_aud}")

# ---------------- Sentences subcommands ----------------

def cmd_sentences_known(args):
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


def cmd_sentences_build(args):
    script = BASE / "scripts" / "sentences_build.py"
    cmd = [sys.executable, str(script), "--deck", args.deck, "--model", args.model]
    if args.limit: cmd += ["--limit", str(args.limit)]
    if args.update_existing: cmd.append("--update-existing")
    if args.debug: cmd.append("--debug")
    run(cmd)

# ---------------- Parser ----------------

def main():
    ap = argparse.ArgumentParser(description="Unified CLI for Spanish→Anki workflow")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("pick", help="Interactive Spanish selection")
    p1.set_defaults(func=cmd_pick)

    p2 = sub.add_parser("enrich", help="Fill IPA column using Wiktionary/phonemizer/epitran")
    p2.set_defaults(func=cmd_enrich)

    p3 = sub.add_parser("build", help="Build/update Picture Word cards")
    p3.add_argument("--only-missing", action="store_true")
    p3.add_argument("--regen-audio", action="store_true")
    p3.add_argument("--recalc-ipa", action="store_true")
    p3.add_argument("--no-open-image-search", action="store_true")
    p3.add_argument("--limit", type=int, default=None)
    p3.add_argument("--deck", default=None)
    p3.add_argument("--model", default=None)
    p3.add_argument("--voice", default=None)
    p3.add_argument("--rate", type=int, default=None)
    p3.set_defaults(func=cmd_build)

    p4 = sub.add_parser("audit", help="Report what’s missing in CSV/media")
    p4.set_defaults(func=cmd_audit)

    # Sentences group
    ps = sub.add_parser("sentences", help="Sentences helpers (known/build)")
    sub2 = ps.add_subparsers(dest="scmd", required=True)

    pk = sub2.add_parser("known", help="Export known words to data/known_words.json")
    pk.add_argument("--deck", default="My Spanish Deck::625")
    pk.add_argument("--model", default="*")
    pk.add_argument("--min-ivl", type=int, default=0)
    pk.add_argument("--min-reps", type=int, default=1)
    pk.add_argument("--review-only", action="store_true")
    pk.add_argument("--include-new", action="store_true")
    pk.add_argument("--limit", type=int, default=None)
    pk.add_argument("--use-notes", action="store_true")
    pk.add_argument("--debug", action="store_true")
    pk.set_defaults(func=cmd_sentences_known)

    pb = sub2.add_parser("build", help="Build/Upsert Cloze notes from data/sentences_generated.json")
    pb.add_argument("--deck", default="My Spanish Deck::Sentences")
    pb.add_argument("--model", default="Cloze")
    pb.add_argument("--limit", type=int, default=None)
    pb.add_argument("--update-existing", action="store_true")
    pb.add_argument("--debug", action="store_true")
    pb.set_defaults(func=cmd_sentences_build)

    args = ap.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()
