#!/usr/bin/env python3
"""
Build or update Fluent Forever-style Picture Word cards for Anki.

Key features:
- Reentrant: add new notes or update existing ones.
- Auto-generate audio (macOS say) with padding for clarity.
- Overlay gender badge on image; also writes Gender field.
- Fills missing Gender and IPA automatically (and writes back to CSV).
- NEW: IPA backends: Wiktionary -> phonemizer (espeak) -> epitran (fallback).
- NEW: Friendly CLI with flags, graceful Ctrl+C handling, and summary.

Requires Anki + AnkiConnect running, and ffmpeg installed.
Optional: requests (for Wiktionary IPA), phonemizer+espeak, epitran.
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
except Exception:  # pragma: no cover
    requests = None

try:
    from phonemizer import phonemize  # type: ignore
except Exception:
    phonemize = None

try:
    import epitran  # type: ignore
except Exception:
    epitran = None

# ---------------------- Config (defaults; can be overridden by CLI) ---------
BASE_DIR = Path(__file__).resolve().parent
CSV_PATH = BASE_DIR / "625_structured.es.csv"  # must include at least 'spanish' column
DECK_NAME = "My Spanish Deck::625"
MODEL_NAME = "Picture Word"  # expected fields: Word, Image, Audio, Notes, IPA, Gender

VOICE = "Paulina"            # Preferred Spanish voice name (auto-fallback will try others)
SPEAKING_RATE = 150          # say -r value (~140–160 natural for single words)

IMAGES_DIR = BASE_DIR / "media" / "images"
AUDIO_DIR = BASE_DIR / "media" / "audio"
GENDER_DIR = BASE_DIR / "media" / "gender"  # put male.png / female.png (or .jpg/.jpeg/.webp)

ANKI = "http://127.0.0.1:8765"

OPEN_IMAGE_SEARCH_IF_MISSING = True
FORCE_REGENERATE_AUDIO = False
DRY_RUN = False
ONLY_MISSING = False
LIMIT = None
RECALC_IPA = False
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
        # Simulate result structures for dry run
        if action == "findNotes":
            return []
        if action in ("storeMediaFile", "updateNoteFields", "addTags", "addNote"):
            return True
        if action == "modelFieldNames":
            return ["Word", "Image", "Audio", "Notes", "IPA", "Gender"]
        return None
    if requests is None:
        raise RuntimeError("requests module not installed; needed for AnkiConnect HTTP calls")
    r = requests.post(ANKI, json={"action": action, "version": 6, "params": params}, timeout=30)
    r.raise_for_status()
    data = r.json()
    if data.get("error"):
        raise RuntimeError(f"Anki error: {data['error']}")
    return data["result"]

EXPECTED_FIELDS = ["Word", "Image", "Audio", "Notes", "IPA", "Gender"]

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
    VOICE,          # user preference
    "Paulina",     # es-MX
    "Luciana",     # es-AR
    "Diego",       # es-AR
    "Monica",      # es-ES
    "Jorge",       # es-ES
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
    """Generate MP3 via CLI 'say' to AIFF, then ffmpeg to MP3 with padding."""
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

# ---------------------- Image / audio discovery ----------------------------

def ensure_audio(spanish: str) -> Path:
    base = slugify(spanish)
    mp3 = AUDIO_DIR / f"{base}.mp3"
    if FORCE_REGENERATE_AUDIO and mp3.exists() and not DRY_RUN:
        try: mp3.unlink()
        except Exception: pass
    if not mp3.exists() and not DRY_RUN:
        info(f"Generating audio: {spanish}")
        tts_to_mp3(spanish, mp3)
    return mp3


def find_base_image(spanish: str) -> Path | None:
    base = slugify(spanish)
    for ext in (".jpg", ".jpeg", ".png", ".webp"):
        p = IMAGES_DIR / f"{base}{ext}"
        if p.exists():
            return p
    return None


def ensure_base_image(spanish: str) -> Path | None:
    img = find_base_image(spanish)
    if img or DRY_RUN:
        return img
    if not OPEN_IMAGE_SEARCH_IF_MISSING:
        warn(f"No base image for '{spanish}'. Skipping.")
        return None
    url = f"https://www.google.com/search?tbm=isch&q={quote(spanish)}"
    info(f"No base image for '{spanish}'. Opening image search:\n  {url}")
    webbrowser.open_new_tab(url)
    target_stem = slugify(spanish)
    info(f"Save an image to {IMAGES_DIR}/{target_stem}.jpg (or .png/.jpeg/.webp). Waiting up to 3 minutes…")
    deadline = time.time() + 180
    while time.time() < deadline:
        img = find_base_image(spanish)
        if img:
            return img
        time.sleep(1)
    warn(f"Skipped: no image saved for '{spanish}'.")
    return None

# ---------------------- Compose card fields --------------------------------

def compose_image_html(main_image_name: str, gender: str | None) -> str:
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


def get_existing_note_id_by_word(word: str) -> int | None:
    ids = anki("findNotes", query=f'note:"{MODEL_NAME}" deck:"{DECK_NAME}" "{word}"')
    if not ids:
        return None
    infos = anki("notesInfo", notes=ids)
    for info in infos:
        fields = info.get("fields", {})
        w = fields.get("Word", {}).get("value", "").strip()
        if w == word:
            return info.get("noteId")
    return None


def ensure_badges_uploaded():
    for name in ("male", "female"):
        for ext in (".png", ".jpg", ".jpeg", ".webp"):
            p = GENDER_DIR / f"{name}{ext}"
            if p.exists():
                store_media(p.name, p)
                break

# ---------------------- CLI -------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(description="Build/Update Anki Picture Word cards with audio, IPA, and gender")
    p.add_argument("--deck", default=DECK_NAME, help="Deck name (can include :: subdecks)")
    p.add_argument("--model", default=MODEL_NAME, help="Model / Note Type name")
    p.add_argument("--csv", default=str(CSV_PATH), help="Path to CSV source")
    p.add_argument("--voice", default=VOICE, help="Preferred macOS TTS voice name")
    p.add_argument("--rate", type=int, default=SPEAKING_RATE, help="Speaking rate for 'say'")
    p.add_argument("--only-missing", action="store_true", help="Process only rows missing image/audio/ipa/gender")
    p.add_argument("--regen-audio", action="store_true", help="Force regenerate audio MP3s")
    p.add_argument("--recalc-ipa", action="store_true", help="Recompute IPA even if present (overwrite)")
    p.add_argument("--no-open-image-search", action="store_true", help="Do not open browser when image missing")
    p.add_argument("--limit", type=int, default=None, help="Process at most N rows")
    p.add_argument("--dry-run", action="store_true", help="No writes to Anki or files")
    p.add_argument("--check-voices", action="store_true", help="Print available Spanish voices and exit")
    p.add_argument("--no-wikt", action="store_true", help="Disable Wiktionary for IPA")
    p.add_argument("--no-phon", action="store_true", help="Disable phonemizer for IPA")
    p.add_argument("--no-epit", action="store_true", help="Disable epitran for IPA")
    return p.parse_args()


def list_spanish_voices():
    try:
        out = subprocess.check_output(["say", "-v", "?"], text=True)
        for line in out.splitlines():
            if any(tok in line.lower() for tok in ["spanish", "es-", "mexican", "argentine"]):
                print(line)
    except Exception as e:
        warn(f"Could not list voices: {e}")

# ---------------------- Main -----------------------------------------------
STOP = False

def handle_sigint(signum, frame):
    global STOP
    STOP = True
    info("\nStopping after current item… (Ctrl+C received)")


def main():
    global DECK_NAME, MODEL_NAME, CSV_PATH, VOICE, SPEAKING_RATE
    global OPEN_IMAGE_SEARCH_IF_MISSING, FORCE_REGENERATE_AUDIO, DRY_RUN, ONLY_MISSING, LIMIT
    global RECALC_IPA, DISABLE_WIKT, DISABLE_PHON, DISABLE_EPIT

    args = parse_args()
    DECK_NAME = args.deck
    MODEL_NAME = args.model
    CSV_PATH = Path(args.csv)
    VOICE = args.voice
    SPEAKING_RATE = args.rate
    ONLY_MISSING = args.only_missing
    FORCE_REGENERATE_AUDIO = args.regen_audio
    RECALC_IPA = args.recalc_ipa
    OPEN_IMAGE_SEARCH_IF_MISSING = not args.no_open_image_search
    DRY_RUN = args.dry_run
    DISABLE_WIKT = args.no_wikt
    DISABLE_PHON = args.no_phon
    DISABLE_EPIT = args.no_epit
    if args.limit and args.limit > 0:
        global LIMIT
        LIMIT = args.limit

    if args.check_voices:
        list_spanish_voices()
        return

    ensure_dirs()

    # Graceful Ctrl+C
    signal.signal(signal.SIGINT, handle_sigint)

    if not CSV_PATH.exists():
        warn(f"CSV not found: {CSV_PATH}")
        return

    verify_model_fields()

    rows = read_rows(CSV_PATH)
    total = len(rows)

    added = updated = skipped = audio_failed = image_missing = enriched_ipa = enriched_gender = 0

    info(f"Processing {total} rows… (Keep Anki open)")

    processed = 0
    for row in rows:
        if STOP:
            break
        spanish = (row.get("spanish") or "").strip()
        if not spanish:
            skipped += 1
            continue

        english = (row.get("english") or "").strip()
        sense = (row.get("sense") or "").strip()
        pos = (row.get("pos") or "").strip()
        gender = (row.get("gender") or "").strip()
        ipa_text = (row.get("ipa") or "").strip()

        # Enrich missing gender/IPA on the fly (or recompute IPA if requested)
        if not gender:
            g = detect_gender(spanish, pos)
            if g:
                row["gender"] = g
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
                row["ipa"] = ip
                ipa_text = ip
                enriched_ipa += 1

        # Skip rows that already have everything when ONLY_MISSING
        needs = []
        img_path = find_base_image(spanish)
        if img_path is None: needs.append("image")
        base = slugify(spanish)
        mp3_path = AUDIO_DIR / f"{base}.mp3"
        if not mp3_path.exists(): needs.append("audio")
        if not gender: needs.append("gender")
        if not ipa_text: needs.append("ipa")
        if ONLY_MISSING and not needs:
            skipped += 1
            continue

        # Ensure image (may prompt)
        if img_path is None:
            img_path = ensure_base_image(spanish)
            if img_path is None:
                image_missing += 1
                continue

        # Ensure audio
        try:
            mp3_path = ensure_audio(spanish)
        except Exception as e:
            warn(f"Audio generation failed for '{spanish}': {e}")
            audio_failed += 1
            continue

        # Upload media (base + badges)
        store_media(img_path.name, img_path)
        store_media(mp3_path.name, mp3_path)
        ensure_badges_uploaded()

        # Compose fields
        image_html = compose_image_html(img_path.name, gender)
        audio_field = f"[sound:{mp3_path.name}]"
        # Keep Notes for reference (not displayed on card if your template omits it)
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
        }

        existing_id = get_existing_note_id_by_word(spanish)
        tags = ["625:auto"]
        if gender: tags.append(f"gender:{gender.lower()}")
        if pos: tags.append(f"pos:{pos.lower()}")

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
        if LIMIT and processed >= LIMIT:
            break

    # Write back enriched CSV (only if changes in ipa/gender)
    try:
        write_rows(CSV_PATH, rows)
    except Exception as e:
        warn(f"Could not write back CSV: {e}")

    # Summary
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
