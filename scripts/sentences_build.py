#!/usr/bin/env python3
"""
Build (or upsert) Cloze Sentence notes from JSON (AI-generated or manual).
Input: data/sentences_generated.json
Each item: {"text": "Veo el perro.", "clozes": ["Veo"], "notes": "I see the dog", "tags": ["present","articles"]}

Key features:
- Detect target fields dynamically (Cloze/Text/Back Extra/Audio).
- Create audio with macOS TTS, attach to Audio (or Back Extra if missing).
- Reentrant: allowDuplicate=False skips exact duplicates by first field.
- NEW: --update-existing upserts by exact cloze-field text (updates Text/Back Extra/Audio/tags if found).
"""
import json
import sys
import subprocess
from pathlib import Path
import argparse
import base64
import re

try:
    import requests  # type: ignore
except Exception:
    print("This script requires 'requests'. Install: pip install requests")
    sys.exit(1)

BASE = Path(__file__).resolve().parent.parent
INP = BASE / "data" / "sentences_generated.json"
AUDIO_DIR = BASE / "media" / "sentences_audio"
ANKI = "http://127.0.0.1:8765"
VOICE = "Paulina"
RATE = 150


def anki(action, **params):
    r = requests.post(ANKI, json={"action": action, "version": 6, "params": params}, timeout=60)
    r.raise_for_status()
    data = r.json()
    if data.get("error"):
        raise RuntimeError(data["error"]) 
    return data["result"]


def tts(text: str, out_mp3: Path):
    aiff = out_mp3.with_suffix(".aiff")
    subprocess.run(["say", "-v", VOICE, "-r", str(RATE), text, "-o", str(aiff)], check=True)
    subprocess.run(["ffmpeg", "-y", "-i", str(aiff), "-ar", "44100", "-ac", "1", "-c:a", "libmp3lame", "-b:a", "160k", str(out_mp3)], check=True)
    try: aiff.unlink()
    except FileNotFoundError: pass


def store_media(filename: str, path: Path):
    with open(path, "rb") as f:
        data = base64.b64encode(f.read()).decode("utf-8")
    anki("storeMediaFile", filename=filename, data=data)


def make_cloze(text: str, targets: list[str]) -> str:
    s = text
    idx = 1
    for t in targets:
        if not t: continue
        s = s.replace(t, f"{{{{c{idx}::{t}}}}}", 1)
        idx += 1
    return s


def slugify_filename(text: str) -> str:
    s = text.lower().strip()
    s = s.replace(" ", "_")
    s = re.sub(r"[^a-z0-9_\-]", "", s)
    s = re.sub(r"_+", "_", s)
    return s[:64] or "sentence"


def pick_fields(model_name: str, debug: bool):
    try:
        fields = anki("modelFieldNames", modelName=model_name) or []
    except Exception as e:
        if debug:
            print(f"[warn] Could not fetch model fields for '{model_name}': {e}")
        fields = []
    field_set = set(fields)
    cloze_field = "Cloze" if "Cloze" in field_set else ("Text" if "Text" in field_set else None)
    text_field = "Text" if "Text" in field_set else None
    extra_field = "Back Extra" if "Back Extra" in field_set else ("Extra" if "Extra" in field_set else None)
    audio_field = "Audio" if "Audio" in field_set else None
    if debug:
        print(f"Model '{model_name}' fields: {fields}")
        print(f"Mapping → cloze:{cloze_field} text:{text_field} extra:{extra_field} audio:{audio_field}")
    return cloze_field, text_field, extra_field, audio_field


def find_existing_note(deck: str, model: str, cloze_field: str, cloze_txt: str, debug: bool):
    """Try to find an existing note whose cloze_field matches cloze_txt exactly."""
    # Narrow search by deck+model and a substring of the text, then confirm by exact field match
    snippet = re.sub(r"\s+", " ", cloze_txt)[:40]
    query = f'deck:"{deck}" note:"{model}" "{snippet}"'
    try:
        note_ids = anki("findNotes", query=query)
        if not note_ids:
            return None
        infos = anki("notesInfo", notes=note_ids)
        for n in infos:
            fields = n.get("fields", {})
            val = (fields.get(cloze_field, {}).get("value") or "").strip()
            if val == cloze_txt:
                if debug:
                    print(f"[update] Found existing note {n.get('noteId')} for cloze match.")
                return n.get("noteId")
    except Exception as e:
        if debug:
            print(f"[warn] find_existing_note failed: {e}")
    return None


def main():
    ap = argparse.ArgumentParser(description="Build/Upsert Cloze Sentence notes from JSON")
    ap.add_argument("--deck", default="My Spanish Deck::625")
    ap.add_argument("--model", default="Cloze")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--update-existing", action="store_true", help="Update notes whose cloze field matches exactly")
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()

    if not INP.exists():
        print(f"Input JSON not found: {INP}")
        sys.exit(1)

    items = json.loads(INP.read_text(encoding="utf-8"))
    if not isinstance(items, list):
        print("Invalid JSON: must be a list of sentence objects")
        sys.exit(1)

    AUDIO_DIR.mkdir(parents=True, exist_ok=True)

    cloze_field, text_field, extra_field, audio_field = pick_fields(args.model, args.debug)
    if cloze_field is None:
        print(f"[error] The target model '{args.model}' has no suitable field for cloze text (needs 'Cloze' or 'Text').")
        sys.exit(1)

    count_add = 0
    count_upd = 0

    for it in items:
        if args.limit and (count_add + count_upd) >= args.limit:
            break
        text = (it.get("text") or "").strip()
        clozes = it.get("clozes") or []
        notes = (it.get("notes") or it.get("english_gloss") or "").strip()
        tags = it.get("tags") or ["sentences"]
        if not text:
            continue
        cloze_txt = make_cloze(text, clozes)
        if "{{c" not in cloze_txt:
            if args.debug:
                print(f"[skip] No cloze markers in: {text}")
            continue

        # Audio
        base = slugify_filename(text)
        mp3 = AUDIO_DIR / f"{base}.mp3"
        if not mp3.exists():
            tts(text, mp3)
        store_media(mp3.name, mp3)

        # Prepare fields per model
        fields = {cloze_field: cloze_txt}
        if text_field and text_field != cloze_field:
            fields[text_field] = text
        if extra_field:
            fields[extra_field] = notes
        if audio_field:
            fields[audio_field] = f"[sound:{mp3.name}]"
        else:
            if extra_field:
                prev = fields.get(extra_field, "")
                fields[extra_field] = (prev + ("\n" if prev else "") + f"[sound:{mp3.name}]").strip()

        if args.update_existing:
            nid = find_existing_note(args.deck, args.model, cloze_field, cloze_txt, args.debug)
            if nid:
                try:
                    anki("updateNoteFields", note={"id": nid, "fields": fields})
                    if tags:
                        anki("addTags", notes=[nid], tags=" ".join(tags))
                    count_upd += 1
                    if args.debug:
                        print(f"[updated] {text}")
                    continue
                except Exception as e:
                    print(f"[error] updateNoteFields failed for: {text}\nReason: {e}")
                    # Fall through to add as new

        # Add new note
        note = {
            "deckName": args.deck,
            "modelName": args.model,
            "fields": fields,
            "options": {"allowDuplicate": False},
            "tags": tags,
        }
        try:
            anki("addNote", note=note)
            count_add += 1
            if args.debug:
                print(f"[added] {text}")
        except Exception as e:
            print(f"[error] addNote failed for: {text}\nReason: {e}\nFields used: {fields}")
            continue

    print(f"Done. Added {count_add}, Updated {count_upd}.")

if __name__ == "__main__":
    main()
