#!/usr/bin/env python3
"""
Build (or upsert) Cloze Sentence notes from JSON (AI-generated or manual).
Refactored to use shared 'lib'.
"""
import json
import sys
import re
import argparse
from pathlib import Path

# Add parent to path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from lib.config import BASE_DIR, SENTENCES_AUDIO_DIR, SENTENCES_DECK, SENTENCES_MODEL
from lib.anki_client import anki
from lib.tts import pick_working_voice
from lib.ipa import ipa_from_phonemizer, ipa_from_epitran
from lib.slugify import slugify

INP = BASE_DIR / "data" / "sentences_generated.json"

# ----------------------- Local TTS override ------------------------
# Sentences might need their own TTS wrapper if logic differs, 
# but mostly it's the same. We'll use lib.tts but ensuring we write to correct dir.
# Actually, lib.tts.tts_to_mp3 takes an output path, so we can reuse it.
from lib.tts import tts_to_mp3

def sentence_ipa(text: str) -> str:
    """Compute sentence-level IPA by concatenating word IPA."""
    tokens = re.findall(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+", text)
    if not tokens: return ""
    ipas = []
    for w in tokens:
        # Prefer phonemizer
        ip = ipa_from_phonemizer(w)
        if not ip: ip = ipa_from_epitran(w)
        
        # Remove slashes for joining
        if ip: ip = ip.replace("/", "")
        ipas.append(ip)
        
    non_empty = [x for x in ipas if x]
    if not non_empty: return ""
    return "/" + " ".join(non_empty) + "/"

def make_cloze(text: str, targets: list) -> str:
    s = text
    idx = 1
    for t in targets or []:
        if isinstance(t, dict):
            target = (t.get("target") or "").strip()
            hint = (t.get("hint") or "").strip()
        else:
            target = (t or "").strip()
            hint = ""
        if not target: continue
        
        marker = f"{{{{c{idx}::{target}{('::' + hint) if hint else ''}}}}}"
        s = s.replace(target, marker, 1)
        idx += 1
    return s

def pick_fields(model_name: str, debug: bool):
    try:
        fields = anki.model_field_names(model_name)
    except:
        return None, None, None, None, None, []
        
    field_set = set(fields)
    cloze_field = "Cloze" if "Cloze" in field_set else ("Text" if "Text" in field_set else None)
    text_field = "Text" if "Text" in field_set else None
    extra_field = "Back Extra" if "Back Extra" in field_set else ("Extra" if "Extra" in field_set else None)
    audio_field = "Audio" if "Audio" in field_set else None
    
    ipa_field = None
    for cand in ("Sentence IPA", "IPA", "SentenceIpa", "Ipa"):
        if cand in field_set:
            ipa_field = cand
            break
            
    if debug:
        print(f"Model '{model_name}' mapping -> cloze:{cloze_field} text:{text_field} extra:{extra_field} audio:{audio_field} ipa:{ipa_field}")
    return cloze_field, text_field, extra_field, audio_field, ipa_field, fields

def find_note_by_field(deck, model, field, value):
    snippet = re.sub(r"\s+", " ", value)[:50]
    q = f'deck:"{deck}" note:"{model}" "{snippet}"'
    ids = anki.find_notes(q)
    if not ids: return None
    infos = anki.notes_info(ids)
    for n in infos:
        val = (n.get("fields", {}).get(field, {}).get("value") or "").strip()
        if val == value:
            return n.get("noteId")
    return None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--deck", default=SENTENCES_DECK)
    ap.add_argument("--model", default=SENTENCES_MODEL)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--update-existing", action="store_true")
    ap.add_argument("--regen-audio", action="store_true")
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()

    if not INP.exists():
        print(f"Input JSON not found: {INP}")
        sys.exit(1)

    items = json.loads(INP.read_text(encoding="utf-8"))
    SENTENCES_AUDIO_DIR.mkdir(parents=True, exist_ok=True)

    cloze_f, text_f, extra_f, audio_f, ipa_f, all_fields = pick_fields(args.model, args.debug)
    if not cloze_f:
        print(f"[error] Model '{args.model}' missing Cloze/Text field.")
        sys.exit(1)
    
    first_field = all_fields[0] if all_fields else cloze_f
    count_add = 0
    count_upd = 0

    for i, it in enumerate(items):
        if args.limit and (count_add + count_upd) >= args.limit: break
        
        text = (it.get("text") or "").strip()
        clozes = it.get("clozes") or []
        notes = (it.get("notes") or it.get("english_gloss") or "").strip()
        tags = it.get("tags") or ["sentences"]
        
        if not text: continue
        cloze_txt = make_cloze(text, clozes)
        if "{{c" not in cloze_txt:
            if args.debug: print(f"[skip] No cloze in: {text}")
            continue

        # Audio
        base = slugify(text)
        mp3 = SENTENCES_AUDIO_DIR / f"{base}.mp3"
        if args.regen_audio and mp3.exists():
            try: mp3.unlink()
            except: pass
        
        if not mp3.exists():
            try:
                tts_to_mp3(text, mp3)
            except Exception as e:
                print(f"[warn] Audio gen failed for '{text}': {e}")

        # Media upload
        if mp3.exists():
            with open(mp3, "rb") as f:
                data = base64.b64encode(f.read()).decode("utf-8")
            anki.store_media_file(mp3.name, data)

        sent_ipa = sentence_ipa(text) if ipa_f else ""

        fields = {cloze_f: cloze_txt}
        if text_f and text_f != cloze_f: fields[text_f] = text
        if extra_f: fields[extra_f] = notes
        
        audio_val = f"[sound:{mp3.name}]" if mp3.exists() else ""
        if audio_f:
            fields[audio_f] = audio_val
        elif extra_f and audio_val:
            prev = fields.get(extra_f, "")
            fields[extra_f] = (prev + ("\n" if prev else "") + audio_val).strip()
            
        if ipa_f and sent_ipa: fields[ipa_f] = sent_ipa

        # Upsert logic
        nid = None
        if args.update_existing:
            nid = find_note_by_field(args.deck, args.model, cloze_f, cloze_txt)
            if not nid and text_f:
                nid = find_note_by_field(args.deck, args.model, text_f, text)
        
        if nid:
            anki.update_note_fields(nid, fields)
            if tags: anki.add_tags(nid, " ".join(tags))
            count_upd += 1
            if args.debug: print(f"[updated] {text}")
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
                if args.debug: print(f"[added] {text}")
            except Exception as e:
                # Rescue duplicate
                if "duplicate" in str(e).lower():
                    # try find by text or first field
                    nid2 = None
                    if text_f: nid2 = find_note_by_field(args.deck, args.model, text_f, text)
                    if not nid2: 
                        val = fields.get(first_field)
                        if val: nid2 = find_note_by_field(args.deck, args.model, first_field, val)
                    
                    if nid2:
                        anki.update_note_fields(nid2, fields)
                        if tags: anki.add_tags(nid2, " ".join(tags))
                        count_upd += 1
                        if args.debug: print(f"[dup-rescue] {text}")
                    else:
                        print(f"[error] Duplicate reported but couldn't find note: {text}")

    print(f"Done. Added {count_add}, Updated {count_upd}.")

if __name__ == "__main__":
    main()
