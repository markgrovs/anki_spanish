#!/usr/bin/env python3
"""
push_image.py — Override an existing card's image with a local replacement.

Usage:
    anki push-image <word> [--no-rename]

What it does:
    1. Finds the note for <word> (default deck/model from lib.config).
    2. Reads the filename its Image field references (<img src="...">),
       skipping gender badges — that filename is the contract with Anki.
    3. Picks the newest local single image for the word
       (media/images/<slug>.jpg|jpeg|png|webp). A <slug>_collage.jpg only
       counts if the note itself references it (collages are derived
       artifacts, never user replacements).
    4. If the local name differs from the referenced one, archives the old
       file to tmp/ (never deletes) and renames the replacement to match,
       so the repo stays canonical for future rebuilds. --no-rename skips.
    5. Pushes via AnkiConnect storeMediaFile, which overwrites the file in
       collection.media in place — no note edit needed.

The card shows the new image on next review; it syncs to AnkiWeb on the
next sync.
"""
import argparse
import datetime
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.anki_client import anki
from lib.config import BASE_DIR, DECK_NAME, IMAGES_DIR, MODEL_NAME
from lib.slugify import slugify

IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp")
GENDER_BADGES = {"male.jpeg", "female.jpeg"}
TMP_DIR = BASE_DIR / "tmp"


def info(msg):
    print(f"[push-image] {msg}")


def die(msg):
    print(f"[push-image] ERROR: {msg}")
    sys.exit(1)


def find_note(word, deck, model):
    ids = anki.find_notes(query=f'deck:"{deck}" note:"{model}" Word:"{word}"')
    if not ids:
        return None
    infos = anki.notes_info(ids)
    w = word.strip().lower()
    exact = [
        n for n in infos
        if (n.get("fields", {}).get("Word", {}).get("value") or "").strip().lower() == w
    ]
    if not exact:
        return None
    if len(exact) > 1:
        die(f"{len(exact)} notes have Word '{word}' — ambiguous, aborting")
    return exact[0]


def referenced_image(note):
    """First non-badge <img src> in the Image field = the base image filename."""
    html = (note.get("fields", {}).get("Image", {}).get("value") or "")
    for m in re.finditer(r'<img\s+[^>]*src="([^"]+)"', html):
        if m.group(1) not in GENDER_BADGES:
            return m.group(1)
    return None


def main():
    ap = argparse.ArgumentParser(
        description="Override an existing card's image with a local replacement"
    )
    ap.add_argument("word", help="Spanish word on the card (Word field), e.g. verano")
    ap.add_argument("--deck", default=DECK_NAME)
    ap.add_argument("--model", default=MODEL_NAME)
    ap.add_argument(
        "--no-rename", action="store_true",
        help="push without renaming the local file to the note's referenced filename",
    )
    args = ap.parse_args()

    word = args.word.strip()
    slug = slugify(word)

    note = find_note(word, args.deck, args.model)
    if not note:
        die(f"no '{args.model}' note with Word '{word}' in '{args.deck}' — build the card first (anki build)")
    target = referenced_image(note)
    if not target:
        die(f"note for '{word}' has no <img src> in its Image field")

    collage = IMAGES_DIR / f"{slug}_collage.jpg"
    target_path = IMAGES_DIR / target

    # candidates: single images always; collage only if the note references it
    cands = [IMAGES_DIR / f"{slug}{ext}" for ext in IMAGE_EXTS]
    cands = [p for p in cands if p.exists()]
    if target_path == collage and collage.exists():
        cands.append(collage)
    if not cands:
        die(f"no local image at media/images/{slug}.jpg|jpeg|png|webp — run: anki pick-images --query {word}")

    if len(cands) > 1:
        info(f"multiple local candidates: {', '.join(p.name for p in cands)} — newest wins")

    # newest file wins; ties prefer the referenced name
    chosen = max(cands, key=lambda p: (p.stat().st_mtime, p.name == target))
    if chosen != target_path:
        info(f"note references '{target}'; newest local candidate is '{chosen.name}'")

    if chosen != target_path and not args.no_rename:
        if target_path.exists():
            TMP_DIR.mkdir(parents=True, exist_ok=True)
            ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
            archived = TMP_DIR / f"{target_path.stem}_rejected-{ts}{target_path.suffix}"
            shutil.move(str(target_path), str(archived))
            info(f"archived old image -> {archived.relative_to(BASE_DIR)}")
        shutil.move(str(chosen), str(target_path))
        info(f"renamed {chosen.name} -> {target_path.name} (repo stays canonical)")
        chosen = target_path
    elif chosen != target_path:
        info("warning: --no-rename set; local filename now differs from the note's reference")

    result = anki.store_media_file(target, path=str(chosen.resolve()))
    info(f"pushed {target} ({chosen.stat().st_size:,} bytes) into Anki media (storeMediaFile: {result})")

    if collage.exists() and chosen != collage:
        info(f"note: {collage.name} still exists locally — delete it if it contains the rejected image, or it can resurface in future collages")

    info(f"done — '{word}' now shows {target}. No note edit needed; syncs on next Anki sync.")


if __name__ == "__main__":
    main()
