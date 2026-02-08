#!/usr/bin/env python3
"""
Unified CLI for Spanish→Anki workflow.
Refactored to use shared 'lib'.
"""
import argparse
import subprocess
import sys
import csv
from pathlib import Path

# Import shared config
from lib.config import BASE_DIR, CSV_PATH, DECK_NAME, MODEL_NAME, SENTENCES_DECK, SENTENCES_MODEL

def run(cmd):
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"[error] Command failed: {' '.join(cmd)}\n{e}")
        sys.exit(1)

# ---------------- Core commands ----------------

def cmd_pick(args):
    script = BASE_DIR / "translate_pick.py"
    run([sys.executable, str(script)])

def cmd_enrich(args):
    script = BASE_DIR / "enrich_ipa.py"
    run([sys.executable, str(script)])

def cmd_enrich_pos(args):
    script = BASE_DIR / "scripts" / "enrich_pos_gender.py"
    cmd = [sys.executable, str(script), "--pos-only"]
    if args.hints_pos: cmd += ["--hints-pos", args.hints_pos]
    if args.guess_verbs: cmd.append("--guess-verbs")
    if args.push: cmd.append("--push")
    cmd += ["--deck", args.deck, "--model", args.model]
    run(cmd)

def cmd_enrich_gender(args):
    script = BASE_DIR / "scripts" / "enrich_pos_gender.py"
    cmd = [sys.executable, str(script), "--gender-nouns"]
    if args.push: cmd.append("--push")
    cmd += ["--deck", args.deck, "--model", args.model]
    run(cmd)


def cmd_pick_images(args):
    script = BASE_DIR / "scripts" / "pick_images.py"
    cmd = [sys.executable, str(script)]
    if args.limit: cmd += ["--limit", str(args.limit)]
    if args.query: cmd += ["--query", args.query]
    run(cmd)

def cmd_build(args):
    script = BASE_DIR / "build_cards.py"
    cmd = [sys.executable, str(script)]
    if args.only_missing: cmd.append("--only-missing")
    if args.regen_audio: cmd.append("--regen-audio")
    if args.recalc_ipa: cmd.append("--recalc-ipa")
    if args.recalc_pos: cmd.append("--recalc-pos")
    if args.no_open_image_search: cmd.append("--no-open-image-search")
    if args.limit: cmd += ["--limit", str(args.limit)]
    cmd += ["--deck", args.deck, "--model", args.model]
    if args.voice: cmd += ["--voice", args.voice]
    if args.rate: cmd += ["--rate", str(args.rate)]
    run(cmd)

def cmd_audit(args):
    if not CSV_PATH.exists():
        print(f"CSV not found: {CSV_PATH}")
        sys.exit(1)
        
    # Use lib logic implicitly by reading rows roughly
    with CSV_PATH.open("r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
        
    total = len(rows)
    missing_es = sum(1 for r in rows if not (r.get("spanish") or "").strip())
    missing_pos = sum(1 for r in rows if not (r.get("pos") or "").strip())
    missing_ipa = sum(1 for r in rows if not (r.get("ipa") or "").strip())
    
    print("Audit:")
    print(f"  Rows total:       {total}")
    print(f"  Missing Spanish:   {missing_es}")
    print(f"  Missing POS:       {missing_pos}")
    print(f"  Missing IPA:       {missing_ipa}")
    
    # We could import lib.media to check images, but simple check matches old logic
    images_dir = BASE_DIR / "media" / "images"
    audio_dir = BASE_DIR / "media" / "audio"
    
    miss_img = 0
    miss_aud = 0
    
    # Simple check for now
    from lib.slugify import slugify
    
    for r in rows:
        es = (r.get("spanish") or "").strip()
        if not es: continue
        
        # Check image
        slug = slugify(es)
        has_img = any((images_dir / f"{slug}{ext}").exists() for ext in (".jpg", ".jpeg", ".png", ".webp"))
        if not has_img: 
            # try collage
            if (images_dir / f"{slug}_collage.jpg").exists(): has_img = True
            
        # Check audio (approximate - build_cards does full logic)
        # We can't easily check audio without knowing article/gender logic here.
        # So we skip rigorous audio check in quick audit.
        
        if not has_img: miss_img += 1
        
    print(f"  Missing images:    {miss_img} (approx)")

def cmd_sync(args):
    script = BASE_DIR / "scripts" / "sync_check.py"
    cmd = [sys.executable, str(script)]
    if args.fix: cmd.append("--fix")
    if args.dry_run: cmd.append("--dry-run")
    cmd += ["--deck", args.deck, "--model", args.model]
    run(cmd)

def cmd_known(args):
    script = BASE_DIR / "scripts" / "sentences_get_known_words.py"
    cmd = [sys.executable, str(script), "--deck", args.deck, "--model", args.model]
    if args.min_ivl: cmd += ["--min-ivl", str(args.min_ivl)]
    if args.min_reps: cmd += ["--min-reps", str(args.min_reps)]
    if args.review_only: cmd.append("--review-only")
    if not args.include_new: cmd.append("--exclude-new")
    else: cmd.append("--include-new")
    if args.limit: cmd += ["--limit", str(args.limit)]
    if args.use_notes: cmd.append("--use-notes")
    if args.debug: cmd.append("--debug")
    run(cmd)


def cmd_sentences_known(args):
    script = BASE_DIR / "scripts" / "sentences_get_known_words.py"
    cmd = [sys.executable, str(script), "--deck", args.deck, "--model", args.model]
    if args.min_ivl: cmd += ["--min-ivl", str(args.min_ivl)]
    if args.min_reps: cmd += ["--min-reps", str(args.min_reps)]
    if args.review_only: cmd.append("--review-only")
    if not args.include_new: cmd.append("--exclude-new")
    else: cmd.append("--include-new")
    if args.limit: cmd += ["--limit", str(args.limit)]
    if args.use_notes: cmd.append("--use-notes")
    if args.debug: cmd.append("--debug")
    run(cmd)

def cmd_sentences_build(args):
    script = BASE_DIR / "scripts" / "sentences_build.py"
    cmd = [sys.executable, str(script), "--deck", args.deck, "--model", args.model]
    if args.limit: cmd += ["--limit", str(args.limit)]
    if args.update_existing: cmd.append("--update-existing")
    if args.regen_audio: cmd.append("--regen-audio")
    if args.debug: cmd.append("--debug")
    run(cmd)

# ---------------- Parser ----------------

def main():
    ap = argparse.ArgumentParser(description="Unified CLI for Spanish→Anki workflow")
    sub = ap.add_subparsers(dest="cmd", required=True)

    # 1. Pick
    p1 = sub.add_parser("pick", help="Interactive Spanish selection")
    p1.set_defaults(func=cmd_pick)

    # 2. Enrich
    p2 = sub.add_parser("enrich", help="Fill IPA column")
    p2.set_defaults(func=cmd_enrich)

    # 2b. Enrich POS
    ppos = sub.add_parser("enrich-pos", help="Fill POS")
    ppos.add_argument("--push", action="store_true")
    ppos.add_argument("--hints-pos", default=None)
    ppos.add_argument("--guess-verbs", action="store_true")
    ppos.add_argument("--deck", default=DECK_NAME)
    ppos.add_argument("--model", default=MODEL_NAME)
    ppos.set_defaults(func=cmd_enrich_pos)

    # 2c. Enrich Gender
    pgen = sub.add_parser("enrich-gender", help="Fill Gender")
    pgen.add_argument("--push", action="store_true")
    pgen.add_argument("--deck", default=DECK_NAME)
    pgen.add_argument("--model", default=MODEL_NAME)
    pgen.set_defaults(func=cmd_enrich_gender)

    # 3. Build
    p3 = sub.add_parser("build", help="Build/update cards")
    p3.add_argument("--only-missing", action="store_true")
    p3.add_argument("--regen-audio", action="store_true")
    p3.add_argument("--recalc-ipa", action="store_true")
    p3.add_argument("--recalc-pos", action="store_true")
    p3.add_argument("--no-open-image-search", action="store_true")
    p3.add_argument("--limit", type=int, default=None)
    p3.add_argument("--dry-run", action="store_true")
    p3.add_argument("--deck", default=DECK_NAME)
    p3.add_argument("--model", default=MODEL_NAME)
    p3.add_argument("--voice", default=None)
    p3.add_argument("--rate", type=int, default=None)
    p3.set_defaults(func=cmd_build)

    # 4. Audit
    p4 = sub.add_parser("audit", help="Report missing")
    p4.set_defaults(func=cmd_audit)

    # 5. Sync
    psync = sub.add_parser("sync", help="Check/fix CSV ↔ Anki sync")
    psync.add_argument("--fix", action="store_true")
    psync.add_argument("--dry-run", action="store_true")
    psync.add_argument("--deck", default=DECK_NAME)
    psync.add_argument("--model", default=MODEL_NAME)
    psync.set_defaults(func=cmd_sync)

    # 6. Known
    pk0 = sub.add_parser("known", help="Export known words")
    pk0.add_argument("--deck", default=DECK_NAME)
    pk0.add_argument("--model", default="*")
    pk0.add_argument("--min-ivl", type=int, default=0)
    pk0.add_argument("--min-reps", type=int, default=1)
    pk0.add_argument("--review-only", action="store_true")
    pk0.add_argument("--include-new", action="store_true")
    pk0.add_argument("--limit", type=int, default=None)
    pk0.add_argument("--use-notes", action="store_true")
    pk0.add_argument("--debug", action="store_true")
    pk0.set_defaults(func=cmd_known)

    # 7. Sentences
    ps = sub.add_parser("sentences", help="Sentences helpers")
    sub2 = ps.add_subparsers(dest="scmd", required=True)

    pk = sub2.add_parser("known", help="Export known words")
    pk.add_argument("--deck", default=DECK_NAME)
    pk.add_argument("--model", default="*")
    pk.add_argument("--min-ivl", type=int, default=0)
    pk.add_argument("--min-reps", type=int, default=1)
    pk.add_argument("--review-only", action="store_true")
    pk.add_argument("--include-new", action="store_true")
    pk.add_argument("--limit", type=int, default=None)
    pk.add_argument("--use-notes", action="store_true")
    pk.add_argument("--debug", action="store_true")
    pk.set_defaults(func=cmd_sentences_known)

    pb = sub2.add_parser("build", help="Build Cloze notes")
    pb.add_argument("--deck", default=SENTENCES_DECK)
    pb.add_argument("--model", default=SENTENCES_MODEL)
    pb.add_argument("--limit", type=int, default=None)
    pb.add_argument("--update-existing", action="store_true")
    pb.add_argument("--regen-audio", action="store_true")
    pb.add_argument("--debug", action="store_true")
    pb.set_defaults(func=cmd_sentences_build)

    
    # 8. Pick Images
    pimg = sub.add_parser("pick-images", help="Interactive image picker (Pixabay)")
    pimg.add_argument("--limit", type=int, default=10, help="Batch size")
    pimg.add_argument("--query", type=str, help="Specific word to process (optional)")
    pimg.set_defaults(func=cmd_pick_images)

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()

if __name__ == "__main__":
    main()
