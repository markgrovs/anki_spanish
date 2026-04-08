#!/usr/bin/env python3
"""
Build or update Fluent Forever-style Picture Word cards for Anki.
Refactored to use shared 'lib' modules.
"""
import sys
import base64
import webbrowser
import argparse
from pathlib import Path
from urllib.parse import quote

# Import shared library
from lib.config import (
    DECK_NAME as CONF_DECK, 
    MODEL_NAME as CONF_MODEL, 
    CSV_PATH, IMAGES_DIR, AUDIO_DIR, 
    VOICE_NAME, SPEAKING_RATE
)
from lib.anki_client import anki
from lib.csv_store import read_rows, write_rows
from lib.slugify import slugify
from lib.tts import tts_to_mp3
from lib.gender import (
    heuristic_gender, compute_article, find_gender_badge, wiktionary_pos_gender
)
from lib.ipa import get_best_ipa, ipa_from_wiktionary, ipa_from_phonemizer, ipa_from_epitran

# Optional deps
try:
    from PIL import Image
except ImportError:
    Image = None



# ---------------------- Small utilities ------------------------------------
def info(msg: str):
    print(msg, flush=True)

def warn(msg: str):
    print(f"[warn] {msg}", flush=True)

# ---------------------- Anki verification ----------------------------------
EXPECTED_FIELDS = ["Word", "Image", "Audio", "Notes", "IPA", "Gender", "POS", "Article"]

def verify_model_fields(cfg):
    if cfg["dry_run"]: return
    try:
        fields = anki.model_field_names(cfg["model"])
    except Exception as e:
        warn(f"Could not query fields for '{CFG['model']}': {e}")
        return
    missing = [f for f in EXPECTED_FIELDS if f not in fields]
    if missing:
        raise RuntimeError(
            f"Model '{CFG['model']}' missing fields: {missing}.\n"
            f"Found: {fields}. Please add them in Anki."
        )

# ---------------------- Media / Images -------------------------------------
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp")

def collect_image_sources(slug: str) -> list[Path]:
    sources = []
    # numbered files
    for ext in IMAGE_EXTS:
        p = IMAGES_DIR / f"{slug}{ext}"
        if p.exists(): sources.append(p)
    for i in range(1, 10):
        for ext in IMAGE_EXTS:
            p = IMAGES_DIR / f"{slug}-{i}{ext}"
            if p.exists(): sources.append(p)
    # folder
    folder = IMAGES_DIR / slug
    if folder.exists() and folder.is_dir():
        for p in sorted(folder.iterdir()):
            if p.suffix.lower() in IMAGE_EXTS and p.is_file():
                sources.append(p)
    # dedupe
    uniq = []
    seen = set()
    for p in sources:
        if p in seen: continue
        seen.add(p)
        uniq.append(p)
    return uniq

def create_collage(images: list[Path], out_path: Path, max_cells: int = 4) -> Path | None:
    if Image is None:
        warn("Pillow not installed; cannot create collages.")
        return None
    if not images: return None
    imgs = images[:max_cells]
    n = len(imgs)
    if n == 1: return imgs[0]
    
    cols = 2 if n >= 2 else 1
    rows = 2 if n >= 3 else 1
    tile_w, tile_h = 600, 450
    if n > 4:
        from math import ceil
        cols = 3
        rows = ceil(n / cols)
        tile_w, tile_h = 500, 375
        
    W, H = cols * tile_w, rows * tile_h
    canvas = Image.new("RGB", (W, H), (0, 0, 0))
    
    idx = 0
    for r in range(rows):
        for c in range(cols):
            if idx >= n: break
            im = Image.open(imgs[idx]).convert("RGB")
            im.thumbnail((tile_w, tile_h))
            x0 = c * tile_w + (tile_w - im.width) // 2
            y0 = r * tile_h + (tile_h - im.height) // 2
            canvas.paste(im, (x0, y0))
            idx += 1
    canvas.save(out_path)
    return out_path

def find_base_image(spanish: str) -> Path | None:
    slug = slugify(spanish)
    sources = collect_image_sources(slug)
    if not sources: return None
    if len(sources) == 1: return sources[0]
    
    collage = IMAGES_DIR / f"{slug}_collage.jpg"
    if collage.exists(): return collage
    
    out = create_collage(sources, collage)
    return out or sources[0]

def ensure_base_image(spanish: str, cfg: dict) -> Path | None:
    img = find_base_image(spanish)
    if img: return img
    if not cfg["open_image"]:
        warn(f"No base image for '{spanish}'. Skipping.")
        return None
        
    url = f"https://www.google.com/search?tbm=isch&q={quote(spanish)}"
    info(f"No base image for '{spanish}'. Opening search:\n  {url}")
    webbrowser.open_new_tab(url)
    target_stem = slugify(spanish)
    info(f"Save image as {IMAGES_DIR}/{target_stem}.jpg")
    
    while True:
        try:
            input(f" >>> Press Enter when saved '{spanish}'...")
            img = find_base_image(spanish)
            if img: return img
            print(f"No image found for '{target_stem}'. Try again.")
        except KeyboardInterrupt:
            print("\nSkipping...")
            return None

def compose_image_html(main_image_name: str, gender: str | None) -> str:
    badge_path = find_gender_badge(gender or "")
    if not badge_path:
        return f'<img src="{main_image_name}">'
    return (
        '<div style="position:relative; display:inline-block;">'
        f'  <img src="{main_image_name}">'
        f'  <img src="{badge_path.name}" style="position:absolute; top:6px; right:6px; width:56px; height:56px; opacity:0.9;">'
        "</div>"
    )

def store_media_safe(filename, path, cfg):
    if cfg["dry_run"] or not path.exists(): return
    with open(path, "rb") as f:
        data = base64.b64encode(f.read()).decode("utf-8")
    anki.store_media_file(filename, data)

# ---------------------- Main Build ----------------------------------------
def main():
    # Default config
    cfg = {
        "deck": CONF_DECK,
        "model": CONF_MODEL,
        "voice": VOICE_NAME,
        "rate": SPEAKING_RATE,
        "dry_run": False,
        "force_audio": False,
        "open_image": True,
        "recalc_ipa": False,
        "recalc_pos": False,
        "only_missing": False,
        "limit": None,
        "disable_wikt": False,
        "disable_phon": False,
        "disable_epit": False,
    }

    ap = argparse.ArgumentParser(description="Build/Update Anki cards (using lib)")
    ap.add_argument("--deck", default=CONF_DECK)
    ap.add_argument("--model", default=CONF_MODEL)
    ap.add_argument("--csv", default=str(CSV_PATH))
    ap.add_argument("--voice", default=VOICE_NAME)
    ap.add_argument("--rate", type=int, default=SPEAKING_RATE)
    ap.add_argument("--only-missing", action="store_true")
    ap.add_argument("--regen-audio", action="store_true")
    ap.add_argument("--recalc-ipa", action="store_true")
    ap.add_argument("--recalc-pos", action="store_true")
    ap.add_argument("--no-open-image-search", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-wikt", action="store_true")
    ap.add_argument("--no-phon", action="store_true")
    ap.add_argument("--no-epit", action="store_true")
    args = ap.parse_args()

    cfg.update({
        "deck": args.deck,
        "model": args.model,
        "voice": args.voice,
        "rate": args.rate,
        "only_missing": args.only_missing,
        "force_audio": args.regen_audio,
        "recalc_ipa": args.recalc_ipa,
        "recalc_pos": args.recalc_pos,
        "open_image": not args.no_open_image_search,
        "limit": args.limit,
        "dry_run": args.dry_run,
        "disable_wikt": args.no_wikt,
        "disable_phon": args.no_phon,
        "disable_epit": args.no_epit,
    })

    if not Path(args.csv).exists():
        warn(f"CSV not found: {args.csv}")
        return

    if not cfg["dry_run"]:
        verify_model_fields(cfg)
    rows = read_rows(Path(args.csv))
    
    counts = {"added":0, "updated":0, "skipped":0, "audio_fail":0, "img_miss":0, "enriched_ipa":0, "enriched_gender":0}
    info(f"Processing {len(rows)} rows...")

    processed = 0
    for r in rows:
        if cfg["limit"] and processed >= cfg["limit"]: break
        
        spanish = (r.get("spanish") or "").strip()
        if not spanish:
            counts["skipped"] += 1
            continue

        english = (r.get("english") or "").strip()
        sense = (r.get("sense") or "").strip()
        pos = (r.get("pos") or "").strip().lower()
        gender = (r.get("gender") or "").strip().lower()
        ipa_text = (r.get("ipa") or "").strip()

        # 1. Enrich Gender (nouns only — numerals, verbs, adjectives never get gender)
        if not gender and pos == "noun":
            # Try heuristic
            g = heuristic_gender(spanish)
            # Try wiktionary if needed (optional deep check not done here to keep it fast, unless requested)
            if not g and cfg["recalc_pos"]:
                _, wg = wiktionary_pos_gender(spanish)
                if wg: g = wg
            
            if g:
                r["gender"] = g
                gender = g
                counts["enriched_gender"] += 1

        # 2. Enrich IPA
        if cfg["recalc_ipa"] or not ipa_text:
            ip = ""
            if not cfg["disable_wikt"]: ip = ipa_from_wiktionary(spanish)
            if not ip and not cfg["disable_phon"]: ip = ipa_from_phonemizer(spanish)
            if not ip and not cfg["disable_epit"]: ip = ipa_from_epitran(spanish)
            
            if ip:
                r["ipa"] = ip
                ipa_text = ip
                counts["enriched_ipa"] += 1

        # 3. Compute Article & Audio text
        article = compute_article(spanish, gender, pos)
        audio_text = f"{article} {spanish}".strip() if article else spanish
        mp3_name = slugify(audio_text) + ".mp3"
        mp3_path = AUDIO_DIR / mp3_name
        
        img_path = find_base_image(spanish)
        
        # 4. Check if work needed
        needs = []
        if not img_path: needs.append("image")
        if not mp3_path.exists(): needs.append("audio")
        if not ipa_text: needs.append("ipa")
        
        if cfg["only_missing"] and not needs and not cfg["recalc_pos"] and not cfg["recalc_ipa"]:
            counts["skipped"] += 1
            continue

        # 5. Acquire Assets
        if not img_path:
            img_path = ensure_base_image(spanish, cfg)
            if not img_path:
                counts["img_miss"] += 1
                continue
        
        try:
            if cfg["force_audio"] and mp3_path.exists():
                try: mp3_path.unlink()
                except: pass
            if not mp3_path.exists():
                info(f"Generating audio: {audio_text}")
                tts_to_mp3(audio_text, mp3_path)
        except Exception as e:
            warn(f"Audio failed '{spanish}': {e}")
            counts["audio_fail"] += 1
            continue

        # 6. Upload Media
        store_media_safe(img_path.name, img_path, cfg)
        store_media_safe(mp3_path.name, mp3_path, cfg)
        
        # 7. Build Note Fields
        notes_bits = []
        if english: notes_bits.append(f"EN: {english}")
        if sense: notes_bits.append(f"Sense: {sense}")
        if pos: notes_bits.append(f"POS: {pos}")
        if gender and gender != "none": notes_bits.append(f"Gender: {gender}")
        if ipa_text: notes_bits.append(f"IPA: {ipa_text}")
        
        # Numerals never show gender or article
        display_gender = "" if pos == "numeral" else (gender if gender != "none" else "")
        display_article = "" if pos == "numeral" else article

        fields = {
            "Word": spanish,
            "Image": compose_image_html(img_path.name, display_gender),
            "Audio": f"[sound:{mp3_path.name}]",
            "Notes": " • ".join(notes_bits),
            "IPA": ipa_text,
            "Gender": display_gender,
            "POS": pos,
            "Article": display_article,
        }
        
        tags = ["625:auto"]
        if gender and gender != "none": tags.append(f"gender:{gender}")
        if pos: tags.append(f"pos:{pos}")
        
        if cfg["dry_run"]:
            info(f"[dry-run] Would upsert: {spanish}")
        else:
            ids = anki.find_notes(query=f'deck:"{cfg["deck"]}" note:"{cfg["model"]}" "{spanish}"')
            existing_id = None
            if ids:
                infos = anki.notes_info(ids)
                for n in infos:
                    w = (n.get("fields", {}).get("Word", {}).get("value") or "").strip()
                    if w == spanish:
                        existing_id = n.get("noteId")
                        break
            
            if existing_id:
                anki.update_note_fields(existing_id, fields)
                if tags: anki.add_tags(existing_id, " ".join(tags))
                counts["updated"] += 1
                info(f"Updated: {spanish}")
            else:
                note = {
                    "deckName": cfg["deck"],
                    "modelName": cfg["model"],
                    "fields": fields,
                    "options": {"allowDuplicate": False},
                    "tags": tags,
                }
                anki.add_note(note)
                counts["added"] += 1
                info(f"Added: {spanish}")

        processed += 1

    # Write back CSV
    write_rows(rows, Path(args.csv))

    print("\nSummary:")
    for k, v in counts.items():
        print(f"  {k}: {v}")

    # Automatic Sync Check
    if not cfg["dry_run"]:
        try:
            from scripts.sync_check import main as sync_main
            print("\n--- Post-build sync check ---")
            # We can invoke it directly or via subprocess. Direct is faster if safe.
            # But subprocess is safer to avoid pollution. Let's use subprocess to be sure.
            import subprocess
            from lib.config import BASE_DIR
            subprocess.run([sys.executable, str(BASE_DIR / "scripts" / "sync_check.py")], cwd=str(BASE_DIR))
        except Exception:
            pass

if __name__ == "__main__":
    main()
