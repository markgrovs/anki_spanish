#!/usr/bin/env python3
"""
Build or update Fluent Forever-style Picture Word cards for Anki.

Key features:
- Reentrant: add new notes or update existing ones.
- Auto-generate audio (macOS say) with padding for clarity.
- Gender badge overlay (via HTML) and dedicated Gender field.
- Fills missing Gender and IPA automatically (and writes back to CSV).
- POS + Article support:
    - POS written to notes from CSV when present
    - Article computed only for nouns with known Gender: el/la (with euphony for some feminine a-/ha- nouns)
- IPA backends: Wiktionary -> phonemizer (espeak) -> epitran (fallback).
- Friendly CLI with flags, graceful Ctrl+C handling, and summary.
- NEW: Multi-image support for a word:
    - animal.jpg (single)
    - animal-1.jpg, animal-2.jpg, ... -> collage
    - images/animal/ (folder) -> collage
  Collage is generated (if Pillow is installed) and used as the Image. If Pillow is missing, falls back to the first image.
- NEW: --recalc-pos to force recomputing Article/POS push even if nothing is "missing".

Requires Anki + AnkiConnect running, and ffmpeg installed.
Optional: requests (Wiktionary), phonemizer+espeak, epitran, Pillow (for collages).
"""
import os
import sys
import time
import base64
import subprocess
import unicodedata
import webbrowser
import csv
import argparse
import signal
from pathlib import Path
from urllib.parse import quote

# Optional deps
try:
    import requests  # type: ignore
except Exception:
    requests = None

try:
    from phonemizer import phonemize  # type: ignore
except Exception:
    phonemize = None

try:
    import epitran  # type: ignore
except Exception:
    epitran = None

try:
    from PIL import Image  # type: ignore
except Exception:
    Image = None

# ---------------------- Config (defaults; can be overridden by CLI) ---------
BASE_DIR = Path(__file__).resolve().parent
CSV_PATH = BASE_DIR / "625_structured.es.csv"
DECK_NAME = "My Spanish Deck::625"
MODEL_NAME = "Picture Word"  # fields expected: Word, Image, Audio, Notes, IPA, Gender, POS, Article

VOICE = "Paulina"
SPEAKING_RATE = 150

IMAGES_DIR = BASE_DIR / "media" / "images"
AUDIO_DIR = BASE_DIR / "media" / "audio"
GENDER_DIR = BASE_DIR / "media" / "gender"

ANKI = "http://127.0.0.1:8765"

OPEN_IMAGE_SEARCH_IF_MISSING = True
FORCE_REGENERATE_AUDIO = False
DRY_RUN = False
ONLY_MISSING = False
LIMIT = None
RECALC_IPA = False
RECALC_POS = False
DISABLE_WIKT = False
DISABLE_PHON = False
DISABLE_EPIT = False

# ---------------------- Small utilities ------------------------------------
def info(msg: str):
    print(msg, flush=True)

def warn(msg: str):
    print(f"[warn] {msg}", flush=True)

# ---------------------- Anki helpers ---------------------------------------
def anki(action, **params):
    if DRY_RUN:
        if action in ("findNotes", "notesInfo", "modelFieldNames"):
            return []
        if action in ("storeMediaFile", "updateNoteFields", "addTags", "addNote"):
            return True
        return None
    if requests is None:
        raise RuntimeError("requests module not installed; needed for AnkiConnect HTTP calls")
    r = requests.post(ANKI, json={"action": action, "version": 6, "params": params}, timeout=30)
    r.raise_for_status()
    data = r.json()
    if data.get("error"):
        raise RuntimeError(f"Anki error: {data['error']}")
    return data["result"]

EXPECTED_FIELDS = ["Word", "Image", "Audio", "Notes", "IPA", "Gender", "POS", "Article"]

def verify_model_fields():
    try:
        fields = anki("modelFieldNames", modelName=MODEL_NAME)
    except Exception as e:
        warn(f"Could not query model fields for '{MODEL_NAME}': {e}")
        return
    missing = [f for f in EXPECTED_FIELDS if f not in fields]
    if missing:
        raise RuntimeError(
            f"Model '{MODEL_NAME}' missing fields: {missing}.\n"
            f"Found: {fields}. Add the fields in Anki (Tools > Manage Note Types > Fields…)."
        )

# ---------------------- Files / media --------------------------------------
def ensure_dirs():
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    GENDER_DIR.mkdir(parents=True, exist_ok=True)


def store_media(filename: str, path: Path):
    if DRY_RUN or not path.exists():
        return
    with open(path, "rb") as f:
        data = base64.b64encode(f.read()).decode("utf-8")
    anki("storeMediaFile", filename=filename, data=data)


def slugify(s: str) -> str:
    s = s.strip().lower()
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    s = "".join(ch if (ch.isalnum() or ch in ("_", "-", " ")) else "_" for ch in s)
    s = "_".join(filter(None, s.split()))
    return s

# ----------- Gender helpers (support .png/.jpg/.jpeg) ----------------------
FEM_SUFFIXES = ("ción", "sión", "dad", "tad", "tud", "umbre", "ie")
MASC_SUFFIXES = ("aje", "or", "án", "ambre")
GENDER_EX = {
    "mano": "f", "día": "m", "mapa": "m", "planeta": "m",
    "idioma": "m", "tema": "m", "poema": "m", "programa": "m",
    "sistema": "m", "problema": "m",
}
# Common feminine nouns with "el" by euphony in singular
FEM_EL_WHITELIST = {
    "agua", "aguila", "águila", "arma", "alma", "aula", "hacha", "hada", "hambre", "area", "área", "ala",
}

def detect_gender(word: str, pos: str = "") -> str:
    head = (word or "").strip().split()[0].lower()
    if not head or head.endswith(("ar", "er", "ir")):
        return ""
    if head in GENDER_EX:
        return GENDER_EX[head]
    if any(head.endswith(s) for s in FEM_SUFFIXES):
        return "f"
    if any(head.endswith(s) for s in MASC_SUFFIXES):
        return "m"
    if head.endswith("a"):
        return "f"
    if head.endswith("o"):
        return "m"
    return ""


def find_gender_badge(gender: str) -> Path | None:
    if not gender:
        return None
    base = "male" if gender.lower().startswith("m") else "female"
    for ext in (".png", ".jpg", ".jpeg", ".webp"):
        p = GENDER_DIR / f"{base}{ext}"
        if p.exists():
            return p
    return None

# ---------------------- Voice selection & TTS -------------------------------
PREFERRED_VOICES = [
    VOICE,
    "Paulina", "Luciana", "Diego", "Monica", "Jorge",
]
_PICKED_VOICE = None

def pick_working_voice() -> str:
    global _PICKED_VOICE
    if _PICKED_VOICE is not None:
        return _PICKED_VOICE
    test_aiff = AUDIO_DIR / "_voice_test.aiff"
    for v in [x for x in PREFERRED_VOICES if x]:
        try:
            subprocess.run(
                ["say", "-v", v, "-r", str(SPEAKING_RATE), "prueba", "-o", str(test_aiff)],
                check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            if test_aiff.exists():
                try: test_aiff.unlink()
                except Exception: pass
            _PICKED_VOICE = v
            info(f"Using voice: {v}")
            return v
        except Exception:
            continue
    _PICKED_VOICE = ""
    info("Using system default voice (no -v).")
    return _PICKED_VOICE


def tts_to_mp3(text: str, out_mp3: Path):
    aiff = out_mp3.with_suffix(".aiff")
    voice = pick_working_voice()
    cmd = ["say", "-r", str(SPEAKING_RATE), text, "-o", str(aiff)]
    if voice:
        cmd = ["say", "-v", voice, "-r", str(SPEAKING_RATE), text, "-o", str(aiff)]
    if not DRY_RUN:
        subprocess.run(cmd, check=True)
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", str(aiff),
                "-ar", "44100", "-ac", "1",
                "-af", "adelay=120:all=1,apad=pad_dur=0.35",
                "-c:a", "libmp3lame", "-b:a", "160k",
                str(out_mp3),
            ],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        try: aiff.unlink()
        except FileNotFoundError: pass

# ---------------------- IPA backends ---------------------------------------
import re as _re
_IPA_SLASH_RE = _re.compile(r"/(.*?)/")
_IPA_TMPL_RE = _re.compile(r"\{\{\s*(?:AFI|IPA)[^}]*\}\}", _re.IGNORECASE)

def _fetch_wikt(page: str, lang: str) -> str:
    if requests is None or DISABLE_WIKT:
        return ""
    url = f"https://{lang}.wiktionary.org/w/api.php"
    try:
        resp = requests.get(url, params={
            "action": "parse", "prop": "wikitext", "page": page, "format": "json"
        }, timeout=10)
        if not resp.ok:
            return ""
        return resp.json().get("parse", {}).get("wikitext", {}).get("*", "")
    except Exception:
        return ""

def ipa_from_wiktionary(word: str) -> str:
    for lang in ("es", "en"):
        txt = _fetch_wikt(word, lang)
        if not txt:
            continue
        for m in _IPA_TMPL_RE.finditer(txt):
            seg = m.group(0)
            m2 = _IPA_SLASH_RE.search(seg)
            if m2:
                return m2.group(0)
        hits = _IPA_SLASH_RE.findall(txt)
        for s in hits:
            if any(ch in s for ch in "ɾʝʎðɣθβˈˌ") or len(s) >= 3:
                return f"/{s}/"
    return ""

def ipa_from_phonemizer(word: str) -> str:
    if phonemize is None or DISABLE_PHON:
        return ""
    try:
        out = phonemize(
            word,
            language="es",
            backend="espeak",
            strip=True,
            with_stress=True,
            njobs=1,
        ).strip()
        out = out.replace(" ", "")
        if out:
            return f"/{out}/"
    except Exception:
        return ""
    return ""

def ipa_from_epitran(word: str) -> str:
    if epitran is None or DISABLE_EPIT:
        return ""
    try:
        epi = epitran.Epitran("spa-Latn")
        out = epi.transliterate(word).strip().replace(" ", "")
        if out:
            return f"/{out}/"
    except Exception:
        return ""
    return ""

# ---------------------- CSV IO ---------------------------------------------
FIELDNAMES = ["english", "sense", "pos", "spanish", "gender", "ipa", "notes"]

def read_rows(path: Path):
    with path.open("r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        for k in FIELDNAMES:
            r.setdefault(k, "")
    return rows

def write_rows(path: Path, rows):
    with path.open("w", newline="", encoding="utf-8") as out:
        w = csv.DictWriter(out, fieldnames=FIELDNAMES)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in FIELDNAMES})

# ---------------------- Multi-image and collage -----------------------------
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp")


def collect_image_sources(slug: str) -> list[Path]:
    sources = []
    # numbered files
    for ext in IMAGE_EXTS:
        p = IMAGES_DIR / f"{slug}{ext}"
        if p.exists():
            sources.append(p)
    for i in range(1, 10):
        for ext in IMAGE_EXTS:
            p = IMAGES_DIR / f"{slug}-{i}{ext}"
            if p.exists():
                sources.append(p)
    # folder of images
    folder = IMAGES_DIR / slug
    if folder.exists() and folder.is_dir():
        for p in sorted(folder.iterdir()):
            if p.suffix.lower() in IMAGE_EXTS and p.is_file():
                sources.append(p)
    # dedupe while preserving order
    uniq = []
    seen = set()
    for p in sources:
        if p in seen:
            continue
        seen.add(p)
        uniq.append(p)
    return uniq


def create_collage(images: list[Path], out_path: Path, max_cells: int = 4) -> Path | None:
    if Image is None:
        warn("Pillow is not installed; cannot create collages. Install with: pip install Pillow")
        return None
    if not images:
        return None
    imgs = images[:max_cells]
    n = len(imgs)
    # layout
    if n == 1:
        return imgs[0]
    cols = 2 if n >= 2 else 1
    rows = 2 if n >= 3 else 1
    tile_w, tile_h = 600, 450  # 4:3 tiles look good
    from math import ceil
    if n > 4:
        cols = 3
        rows = ceil(n / cols)
        tile_w, tile_h = 500, 375
    W, H = cols * tile_w, rows * tile_h
    canvas = Image.new("RGB", (W, H), (0, 0, 0))
    idx = 0
    for r in range(rows):
        for c in range(cols):
            if idx >= n:
                break
            im = Image.open(imgs[idx]).convert("RGB")
            im.thumbnail((tile_w, tile_h))
            # center within tile
            x0 = c * tile_w + (tile_w - im.width) // 2
            y0 = r * tile_h + (tile_h - im.height) // 2
            canvas.paste(im, (x0, y0))
            idx += 1
    canvas.save(out_path)
    return out_path

# ---------------------- Image discovery ------------------------------------

def find_base_image(spanish: str) -> Path | None:
    slug = slugify(spanish)
    sources = collect_image_sources(slug)
    if not sources:
        return None
    if len(sources) == 1:
        return sources[0]
    # create or reuse collage
    collage = IMAGES_DIR / f"{slug}_collage.jpg"
    if collage.exists():
        return collage
    out = create_collage(sources, collage)
    return out or sources[0]


def ensure_base_image(spanish: str) -> Path | None:
    img = find_base_image(spanish)
    if img:
        return img
    if not OPEN_IMAGE_SEARCH_IF_MISSING:
        warn(f"No base image for '{spanish}'. Skipping.")
        return None
    url = f"https://www.google.com/search?tbm=isch&q={quote(spanish)}"
    info(f"No base image for '{spanish}'. Opening image search:\n  {url}")
    webbrowser.open_new_tab(url)
    target_stem = slugify(spanish)
    info(f"Save images as {IMAGES_DIR}/{target_stem}.jpg or {target_stem}-1.jpg, {target_stem}-2.jpg, ... or into folder {IMAGES_DIR}/{target_stem}/. Waiting up to 3 minutes…")
    deadline = time.time() + 180
    while time.time() < deadline:
        img = find_base_image(spanish)
        if img:
            return img
        time.sleep(1)
    warn(f"Skipped: no image saved for '{spanish}'.")
    return None

# ---------------------- Image HTML composition (gender badge overlay) -------

def compose_image_html(main_image_name: str, gender: str | None) -> str:
    """Return HTML that shows the main image and overlays a gender badge if provided."""
    badge_path = find_gender_badge(gender or "")
    if not badge_path:
        return f'<img src="{main_image_name}">'
    badge_name = badge_path.name
    return (
        '<div style="position:relative; display:inline-block;">'
        f'  <img src="{main_image_name}">'
        f'  <img src="{badge_name}" style="position:absolute; top:6px; right:6px; width:56px; height:56px; opacity:0.9;">'
        "</div>"
    )

# ---------------------- Articles (display + audio) --------------------------

def compute_article(spanish: str, gender: str, pos: str) -> str:
    """Return el/la for display & audio when appropriate.
    Uses euphonic 'el' for some feminine nouns starting with stressed a-/ha-
    via a conservative whitelist.
    """
    if pos != "noun" or gender not in ("m", "f"):
        return ""
    if gender == "m":
        return "el"
    # feminine
    base = unicodedata.normalize("NFD", spanish).lower()
    base = "".join(ch for ch in base if unicodedata.category(ch) != "Mn")
    if base in FEM_EL_WHITELIST:
        return "el"
    return "la"

# ---------------------- Main build loop ------------------------------------

def main():
    global DECK_NAME, MODEL_NAME, CSV_PATH, VOICE, SPEAKING_RATE
    global OPEN_IMAGE_SEARCH_IF_MISSING, FORCE_REGENERATE_AUDIO, DRY_RUN, ONLY_MISSING, LIMIT
    global RECALC_IPA, RECALC_POS, DISABLE_WIKT, DISABLE_PHON, DISABLE_EPIT

    ap = argparse.ArgumentParser(description="Build/Update Anki Picture Word cards with audio, IPA, Gender, POS, and collages")
    ap.add_argument("--deck", default=DECK_NAME)
    ap.add_argument("--model", default=MODEL_NAME)
    ap.add_argument("--csv", default=str(CSV_PATH))
    ap.add_argument("--voice", default=VOICE)
    ap.add_argument("--rate", type=int, default=SPEAKING_RATE)
    ap.add_argument("--only-missing", action="store_true")
    ap.add_argument("--regen-audio", action="store_true")
    ap.add_argument("--recalc-ipa", action="store_true")
    ap.add_argument("--recalc-pos", action="store_true", help="Force recompute Article for nouns and push POS even if nothing missing")
    ap.add_argument("--no-open-image-search", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-wikt", action="store_true")
    ap.add_argument("--no-phon", action="store_true")
    ap.add_argument("--no-epit", action="store_true")
    args = ap.parse_args()

    DECK_NAME = args.deck
    MODEL_NAME = args.model
    CSV_PATH = Path(args.csv)
    VOICE = args.voice
    SPEAKING_RATE = args.rate
    ONLY_MISSING = args.only_missing
    FORCE_REGENERATE_AUDIO = args.regen_audio
    RECALC_IPA = args.recalc_ipa
    RECALC_POS = args.recalc_pos
    OPEN_IMAGE_SEARCH_IF_MISSING = not args.no_open_image_search
    DRY_RUN = args.dry_run
    DISABLE_WIKT = args.no_wikt
    DISABLE_PHON = args.no_phon
    DISABLE_EPIT = args.no_epit
    if args.limit and args.limit > 0:
        global LIMIT
        LIMIT = args.limit

    ensure_dirs()

    if not CSV_PATH.exists():
        warn(f"CSV not found: {CSV_PATH}")
        return

    verify_model_fields()

    rows = read_rows(CSV_PATH)
    total = len(rows)

    added = updated = skipped = audio_failed = image_missing = enriched_ipa = enriched_gender = 0

    info(f"Processing {total} rows… (Keep Anki open)")

    processed = 0
    for r in rows:
        if LIMIT and processed >= LIMIT:
            break
        spanish = (r.get("spanish") or "").strip()
        if not spanish:
            skipped += 1
            continue

        english = (r.get("english") or "").strip()
        sense = (r.get("sense") or "").strip()
        pos = (r.get("pos") or "").strip().lower()
        gender = (r.get("gender") or "").strip().lower()
        ipa_text = (r.get("ipa") or "").strip()

        # Enrich missing gender/IPA
        if not gender and pos == "noun":
            g = detect_gender(spanish, pos)
            if g:
                r["gender"] = g
                gender = g
                enriched_gender += 1
        if RECALC_IPA or not ipa_text:
            ip = ""
            if not DISABLE_WIKT:
                ip = ipa_from_wiktionary(spanish)
            if not ip and not DISABLE_PHON:
                ip = ipa_from_phonemizer(spanish)
            if not ip and not DISABLE_EPIT:
                ip = ipa_from_epitran(spanish)
            if ip:
                r["ipa"] = ip
                ipa_text = ip
                enriched_ipa += 1

        # Compute Article (for display and audio) only for nouns with gender m/f
        article = compute_article(spanish, gender, pos)

        # Decide if we should process this row
        needs = []
        img_path = find_base_image(spanish)
        if img_path is None:
            needs.append("image")
        # Use article+word for audio text if applicable
        audio_text = f"{article} {spanish}".strip() if article else spanish
        base = slugify(audio_text)
        mp3_path = AUDIO_DIR / f"{base}.mp3"
        if not mp3_path.exists():
            needs.append("audio")
        if pos == "noun" and not gender:
            needs.append("gender")
        if not ipa_text:
            needs.append("ipa")
        # Process if something is missing OR we’re forcing POS/article recompute
        if ONLY_MISSING and not needs and not RECALC_POS and not RECALC_IPA:
            skipped += 1
            continue

        # Ensure image (may prompt)
        if img_path is None:
            img_path = ensure_base_image(spanish)
            if img_path is None:
                image_missing += 1
                continue

        # Ensure/regen audio
        try:
            if FORCE_REGENERATE_AUDIO and mp3_path.exists():
                try: mp3_path.unlink()
                except Exception: pass
            if not mp3_path.exists():
                info(f"Generating audio: {audio_text}")
                tts_to_mp3(audio_text, mp3_path)
        except Exception as e:
            warn(f"Audio generation failed for '{spanish}': {e}")
            audio_failed += 1
            continue

        # Upload media
        store_media(img_path.name, img_path)
        store_media(mp3_path.name, mp3_path)

        # Compose fields
        image_html = compose_image_html(img_path.name, gender)
        audio_field = f"[sound:{mp3_path.name}]"
        notes_bits = []
        if english: notes_bits.append(f"EN: {english}")
        if sense: notes_bits.append(f"Sense: {sense}")
        if pos: notes_bits.append(f"POS: {pos}")
        if gender: notes_bits.append(f"Gender: {gender}")
        if ipa_text: notes_bits.append(f"IPA: {ipa_text}")
        notes_text = " • ".join(notes_bits)

        fields = {
            "Word": spanish,
            "Image": image_html,
            "Audio": audio_field,
            "Notes": notes_text,
            "IPA": ipa_text,
            "Gender": gender,
            "POS": pos,
            "Article": article,
        }

        # Add or update note
        # Find by exact Word match
        ids = anki("findNotes", query=f'deck:"{DECK_NAME}" note:"{MODEL_NAME}" "{spanish}"')
        existing_id = None
        if ids:
            infos = anki("notesInfo", notes=ids)
            for ninfo in infos:
                w = (ninfo.get("fields", {}).get("Word", {}).get("value") or "").strip()
                if w == spanish:
                    existing_id = ninfo.get("noteId")
                    break

        tags = ["625:auto"]
        if gender: tags.append(f"gender:{gender}")
        if pos: tags.append(f"pos:{pos}")

        if existing_id:
            anki("updateNoteFields", note={"id": existing_id, "fields": fields})
            if tags:
                anki("addTags", notes=[existing_id], tags=" ".join(tags))
            updated += 1
            info(f"Updated: {spanish}")
        else:
            note = {
                "deckName": DECK_NAME,
                "modelName": MODEL_NAME,
                "fields": fields,
                "options": {"allowDuplicate": False},
                "tags": tags,
            }
            anki("addNote", note=note)
            added += 1
            info(f"Added: {spanish}")

        processed += 1

    # Write back CSV (including any enriched POS/Gender/IPA changes)
    write_rows(CSV_PATH, rows)

    print("\nSummary:")
    print(f"  Added:    {added}")
    print(f"  Updated:  {updated}")
    print(f"  Skipped:  {skipped}")
    print(f"  Images missing: {image_missing}")
    print(f"  Audio failed:   {audio_failed}")
    print(f"  Enriched IPA:   {enriched_ipa}")
    print(f"  Enriched Gender:{enriched_gender}")

if __name__ == "__main__":
    main()
