#!/usr/bin/env python3
"""
Build (or upsert) Travel Phrase notes from JSON.
"""
import json
import base64
import sys
import re
import argparse
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from lib.config import BASE_DIR, PHRASE_AUDIO_DIR, PHRASE_DECK, PHRASE_MODEL
from lib.anki_client import anki
from lib.slugify import slugify
from lib.tts import tts_to_mp3
from lib.ipa import get_best_ipa

INP = BASE_DIR / "data" / "phrase_cards.json"

def pick_fields(model_name: str, debug: bool):
    try:
        fields = anki.model_field_names(model_name)
    except Exception:
        return None, []
    field_set = set(fields)
    required_map = {
        "English": "English" if "English" in field_set else None,
        "Spanish": "Spanish" if "Spanish" in field_set else None,
        "Pattern": "Pattern" if "Pattern" in field_set else None,
        "Topic": "Topic" if "Topic" in field_set else None,
        "Notes": "Notes" if "Notes" in field_set else None,
        "Audio": "Audio" if "Audio" in field_set else None,
        "Word IPA": "Word IPA" if "Word IPA" in field_set else ("WordIpa" if "WordIpa" in field_set else None),
    }
    if debug:
        print(f"Model '{model_name}' fields: {fields}")
    return required_map, fields

def find_note_by_field(deck, model, field, value):
    snippet = re.sub(r"\s+", " ", value)[:50]
    q = f'deck:"{deck}" note:"{model}" "{snippet}"'
    ids = anki.find_notes(q)
    if not ids:
        return None
    infos = anki.notes_info(ids)
    for n in infos:
        val = (n.get("fields", {}).get(field, {}).get("value") or "").strip()
        if val == value:
            return n.get("noteId")
    return None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--deck", default=PHRASE_DECK)
    ap.add_argument("--model", default=PHRASE_MODEL)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--update-existing", action="store_true")
    ap.add_argument("--regen-audio", action="store_true")
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()

    if not INP.exists():
        print(f"Input JSON not found: {INP}")
        sys.exit(1)

    items = json.loads(INP.read_text(encoding="utf-8"))
    PHRASE_AUDIO_DIR.mkdir(parents=True, exist_ok=True)

    field_map, all_fields = pick_fields(args.model, args.debug)
    if not field_map or not field_map.get("English") or not field_map.get("Spanish"):
        print(f"[error] Model '{args.model}' missing required English/Spanish fields.")
        sys.exit(1)

    count_add = 0
    count_upd = 0
    total = len(items)
    print(f"Processing {total} phrase cards...")

    for i, it in enumerate(items):
        if args.limit and (count_add + count_upd) >= args.limit:
            break

        english = (it.get("english") or "").strip()
        spanish = (it.get("spanish") or "").strip()
        pattern = (it.get("pattern") or "").strip()
        topic = (it.get("topic") or "").strip()
        notes = (it.get("notes") or "").strip()
        tags = it.get("tags") or ["travel_phrase"]
        want_audio = bool(it.get("audio", True))

        if not english or not spanish:
            print(f"[{i+1}/{total}] Skipped (missing english/spanish)")
            continue

        mp3 = None
        audio_val = ""
        if want_audio:
            base = slugify(spanish)
            mp3 = PHRASE_AUDIO_DIR / f"{base}.mp3"
            if args.regen_audio and mp3.exists():
                try:
                    mp3.unlink()
                except Exception:
                    pass
            if not mp3.exists():
                try:
                    tts_to_mp3(spanish, mp3)
                except Exception as e:
                    print(f"[warn] Audio gen failed for '{spanish}': {e}")
            if mp3.exists():
                with open(mp3, "rb") as f:
                    data = base64.b64encode(f.read()).decode("utf-8")
                anki.store_media_file(mp3.name, data)
                audio_val = f"[sound:{mp3.name}]"

        # Generate Word IPA if field exists
        word_ipa_val = ""
        if field_map.get("Word IPA") and spanish:
            # Tokenize keeping punctuation out of the lookup but in the display if possible
            # For a simple v1, we just extract words, look them up, and join with middle dots.
            import re
            words = re.findall(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+", spanish)
            ipa_pairs = []
            for w in words:
                ip = get_best_ipa(w.lower())
                if ip:
                    ipa_pairs.append(f"{w} {ip}")
                else:
                    ipa_pairs.append(w)
            word_ipa_val = " &middot; ".join(ipa_pairs)

        fields = {
            field_map["English"]: english,
            field_map["Spanish"]: spanish,
        }
        if field_map.get("Word IPA") and word_ipa_val:
            fields[field_map["Word IPA"]] = word_ipa_val

        if field_map.get("Pattern"):
            fields[field_map["Pattern"]] = pattern
        if field_map.get("Topic"):
            fields[field_map["Topic"]] = topic
        if field_map.get("Notes"):
            fields[field_map["Notes"]] = notes
        if field_map.get("Audio"):
            fields[field_map["Audio"]] = audio_val

        nid = None
        if args.update_existing:
            nid = find_note_by_field(args.deck, args.model, field_map["Spanish"], spanish)
            if not nid:
                nid = find_note_by_field(args.deck, args.model, field_map["English"], english)

        if nid:
            anki.update_note_fields(nid, fields)
            if tags:
                anki.add_tags(nid, " ".join(tags))
            count_upd += 1
            print(f"[{i+1}/{total}] Updated: {spanish}")
        else:
            note = {
                "deckName": args.deck,
                "modelName": args.model,
                "fields": fields,
                "options": {"allowDuplicate": False},
                "tags": tags,
            }
            try:
                anki.add_note(note)
                count_add += 1
                print(f"[{i+1}/{total}] Added:   {spanish}")
            except Exception as e:
                if "duplicate" in str(e).lower():
                    nid2 = find_note_by_field(args.deck, args.model, field_map["Spanish"], spanish)
                    if not nid2:
                        nid2 = find_note_by_field(args.deck, args.model, field_map["English"], english)
                    if nid2:
                        anki.update_note_fields(nid2, fields)
                        if tags:
                            anki.add_tags(nid2, " ".join(tags))
                        count_upd += 1
                        print(f"[{i+1}/{total}] Rescued: {spanish}")
                    else:
                        print(f"[error] Duplicate reported but couldn't find note: {spanish}")
                else:
                    raise

    print(f"Done. Added {count_add}, Updated {count_upd}.")

if __name__ == "__main__":
    main()
