#!/usr/bin/env python3
# PYTHON_ARGCOMPLETE_OK

import sys, os
from pathlib import Path
_VENV_PYTHON = Path(__file__).resolve().parent / ".venv312" / "bin" / "python3"
if sys.executable != str(_VENV_PYTHON) and _VENV_PYTHON.exists():
    os.execv(str(_VENV_PYTHON), [str(_VENV_PYTHON)] + sys.argv)
"""
Unified CLI for Spanish→Anki workflow.
Refactored to use shared 'lib'.
"""
import argparse
import subprocess
import sys
import csv
from pathlib import Path

try:
    import argcomplete
except ImportError:
    argcomplete = None

# Import shared config
from lib.config import BASE_DIR, CSV_PATH, DECK_NAME, MODEL_NAME, SENTENCES_DECK, SENTENCES_MODEL, PHRASE_DECK, PHRASE_MODEL

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


def cmd_enrich_all(args):
    print("--- 1/3 Enriching POS ---")
    cmd_enrich_pos(args)
    print("\n--- 2/3 Enriching Gender ---")
    cmd_enrich_gender(args)
    print("\n--- 3/3 Enriching IPA ---")
    cmd_enrich(args)

def cmd_enrich_gender(args):
    script = BASE_DIR / "scripts" / "enrich_pos_gender.py"
    cmd = [sys.executable, str(script), "--gender-nouns"]
    if args.push: cmd.append("--push")
    cmd += ["--deck", args.deck, "--model", args.model]
    run(cmd)


def cmd_smoke_test(args):
    script = BASE_DIR / "scripts" / "smoke_test.py"
    run([sys.executable, str(script)])

def cmd_pick_images(args):
    script = BASE_DIR / "scripts" / "pick_images.py"
    cmd = [sys.executable, str(script)]
    if args.limit: cmd += ["--limit", str(args.limit)]
    if args.query: cmd += ["--query", args.query]
    run(cmd)


def cmd_vocab_update(args):
    """Update 625 CSV from phrase cards (lemma-aware)."""
    import shutil, datetime
    from lib import vocab_update
    from lib.config import CSV_PATH
    if args.backup and args.write:
        ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        bak = CSV_PATH.with_name(f"{CSV_PATH.stem}.bak-{ts}{CSV_PATH.suffix}")
        shutil.copy2(CSV_PATH, bak)
        print(f"Backed up CSV to {bak}")
    count = vocab_update.update_vocab(write_mode=args.write, interactive=args.review, verbose=True)
    if args.write:
        print(f"Added {count} rows")
    else:
        print("Dry-run complete")


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
        
    with CSV_PATH.open("r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
        
    from lib.slugify import slugify
    from lib.config import IMAGES_DIR, AUDIO_DIR
    
    total = len(rows)
    translated = [r for r in rows if (r.get("spanish") or "").strip()]
    
    missing_es = total - len(translated)
    
    # We only care about missing fields for words that actually HAVE a Spanish translation
    missing_pos = 0
    missing_gender_nouns = 0
    missing_ipa = 0
    miss_img = 0
    miss_aud = 0
    
    for r in translated:
        es = r.get("spanish").strip()
        pos = (r.get("pos") or "").strip().lower()
        gen = (r.get("gender") or "").strip()
        
        if not pos: missing_pos += 1
        if pos == "noun" and not gen: missing_gender_nouns += 1
        if not r.get("ipa"): missing_ipa += 1
        
        # Check media
        slug = slugify(es)
        has_img = any((IMAGES_DIR / f"{slug}{ext}").exists() for ext in (".jpg", ".jpeg", ".png", ".webp"))
        if not has_img and (IMAGES_DIR / f"{slug}_collage.jpg").exists():
            has_img = True
        if not has_img: miss_img += 1
        
        # Check audio (approximate, audio slug uses article if present, but base is usually close enough to check if ANY audio exists)
        # To be perfectly accurate we'd compute the article, but a glob is fine for audit.
        aud_files = list(AUDIO_DIR.glob(f"*{slug}*.mp3"))
        if not aud_files: miss_aud += 1

    noun_count = sum(1 for r in translated if (r.get("pos") or "").strip().lower() == "noun")
    
    print("============================================================")
    print("  SPANISH ANKI DECK PROGRESS")
    print("============================================================")
    print(f"  Vocabulary:     {len(translated)} / {total} words translated ({(len(translated)/total)*100:.1f}%)")
    print("------------------------------------------------------------")
    print("  TO DO:")
    if missing_es > 0:
        print(f"  • {missing_es} words need translation (run: 'anki pick')")
    
    if missing_pos > 0:
        print(f"  • {missing_pos} words missing POS (run: 'anki enrich-all')")
        
    if missing_gender_nouns > 0:
        print(f"  • {missing_gender_nouns} nouns missing gender (run: 'anki enrich-all')")
        
    if missing_ipa > 0:
        print(f"  • {missing_ipa} words missing IPA (run: 'anki enrich-all')")
        
    if miss_img > 0:
        print(f"  • {miss_img} words missing Images (run: 'anki pick-images')")
        
    if miss_aud > 0:
        print(f"  • {miss_aud} words missing Audio (run: 'anki build')")
        
    if missing_es == 0 and missing_pos == 0 and missing_gender_nouns == 0 and missing_ipa == 0 and miss_img == 0 and miss_aud == 0:
        print("  • Nothing! Everything is 100% complete.")
        print("============================================================")


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
    cmd += ["--mode", args.mode]
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
    cmd += ["--mode", args.mode]
    run(cmd)

def cmd_sentences_build(args):
    script = BASE_DIR / "scripts" / "sentences_build.py"
    cmd = [sys.executable, str(script), "--deck", args.deck, "--model", args.model]
    if args.limit: cmd += ["--limit", str(args.limit)]
    if args.update_existing: cmd.append("--update-existing")
    if args.regen_audio: cmd.append("--regen-audio")
    if args.debug: cmd.append("--debug")
    run(cmd)
def cmd_phrase_build(args):
    script = BASE_DIR / "scripts" / "phrase_cards_build.py"
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
    # 2d. Enrich All
    pall = sub.add_parser("enrich-all", help="Run POS, Gender, and IPA enrichment in sequence")
    pall.add_argument("--push", action="store_true", help="Push changes to Anki immediately")
    pall.add_argument("--deck", default=DECK_NAME)
    pall.add_argument("--model", default=MODEL_NAME)
    # Arguments needed by sub-commands (defaults)
    pall.add_argument("--hints-pos", default=None)
    pall.add_argument("--guess-verbs", action="store_true")
    pall.set_defaults(func=cmd_enrich_all)


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
    pk0.add_argument("--mode", default="strict", choices=["strict", "learned", "all"])
    pk0.set_defaults(func=cmd_known)

    # 6b. Phrase Build
    ppb = sub.add_parser("phrase-build", help="Build/update travel phrase cards")
    ppb.add_argument("--deck", default=PHRASE_DECK)
    ppb.add_argument("--model", default=PHRASE_MODEL)
    ppb.add_argument("--limit", type=int, default=None)
    ppb.add_argument("--update-existing", action="store_true")
    ppb.add_argument("--regen-audio", action="store_true")
    ppb.add_argument("--debug", action="store_true")
    ppb.set_defaults(func=cmd_phrase_build)

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
    pk.add_argument("--mode", default="strict", choices=["strict", "learned", "all"])
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


    # 8b. Vocab update
    pv = sub.add_parser("vocab", help="Vocabulary helpers")
    vsub = pv.add_subparsers(dest="vcmd", required=True)
    pu = vsub.add_parser("update", help="Update 625 CSV from phrase cards")
    pu.add_argument("--review", action="store_true", help="Interactively review unknown tokens")
    pu.add_argument("--write", action="store_true", help="Append discovered words to CSV")
    pu.add_argument("--backup", action="store_true", help="Backup CSV before writing")
    pu.set_defaults(func=cmd_vocab_update)

    # 9. Smoke test
    psmoke = sub.add_parser("smoke-test", help="Run non-destructive CLI smoke tests")
    psmoke.set_defaults(func=cmd_smoke_test)

    if argcomplete:
        argcomplete.autocomplete(ap)
    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[Interrupted] Exiting anki_flow gracefully.")
        sys.exit(0)
