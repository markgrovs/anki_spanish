#!/usr/bin/env python3
"""
Build (or upsert) Cloze Sentence notes from JSON (AI-generated or manual).
Input: data/sentences_generated.json
Each item: {"text": "Veo el perro.", "clozes": ["Veo"], "notes": "I see the dog", "tags": ["present","articles"]}

Key features:
- Detect target fields dynamically (Cloze/Text/Back Extra/Audio/Sentence IPA).
- Create audio with macOS TTS, attach to Audio (or Back Extra if missing).
- Optional sentence-level IPA using phonemizer (espeak) or epitran if available.
- Reentrant: allowDuplicate=False skips exact duplicates by first field.
- --update-existing upserts by exact cloze-field text (updates Text/Back Extra/Audio/tags if found).
- High‑quality audio pipeline with padding; auto‑select a working voice to avoid voice errors.
- --regen-audio to force re-generate sentence MP3s.

Robust duplicate rescue:
- On duplicate add, also search by the Text field (plain sentence) in case searching by cloze fails.
- Finally, search by the model's first field value used for duplicate detection.
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

# Optional deps for IPA
try:
    from phonemizer import phonemize  # type: ignore
except Exception:
    phonemize = None

try:
    import epitran  # type: ignore
except Exception:
    epitran = None

BASE = Path(__file__).resolve().parent.parent
INP = BASE / "data" / "sentences_generated.json"
AUDIO_DIR = BASE / "media" / "sentences_audio"
ANKI = "http://127.0.0.1:8765"
VOICE = "Paulina"
RATE = 150

# ----------------------- Anki helpers -----------------------

def anki(action, **params):
    r = requests.post(ANKI, json={"action": action, "version": 6, "params": params}, timeout=60)
    r.raise_for_status()
    data = r.json()
    if data.get("error"):
        raise RuntimeError(data["error"]) 
    return data["result"]

# ----------------------- TTS helpers ------------------------

def pick_working_voice(preferred: str) -> str:
    candidates = [preferred, "Paulina", "Luciana", "Diego", "Monica", "Jorge", None]
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    test_aiff = AUDIO_DIR / "_voice_test.aiff"
    for v in candidates:
        try:
            cmd = ["say", "-r", str(RATE), "prueba", "-o", str(test_aiff)]
            if v:
                cmd = ["say", "-v", v, "-r", str(RATE), "prueba", "-o", str(test_aiff)]
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if test_aiff.exists():
                try: test_aiff.unlink()
                except Exception: pass
            return v or ""
        except Exception:
            continue
    return ""

SELECTED_VOICE = None

def tts_to_mp3(text: str, out_mp3: Path):
    global SELECTED_VOICE
    if SELECTED_VOICE is None:
        SELECTED_VOICE = pick_working_voice(VOICE)
    aiff = out_mp3.with_suffix(".aiff")
    cmd = ["say", "-r", str(RATE), text, "-o", str(aiff)]
    if SELECTED_VOICE:
        cmd = ["say", "-v", SELECTED_VOICE, "-r", str(RATE), text, "-o", str(aiff)]
    subprocess.run(cmd, check=True)
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", str(aiff),
            "-ar", "44100", "-ac", "1",
            "-af", "adelay=120:all=1,apad=pad_dur=0.35",
            "-c:a", "libmp3lame", "-b:a", "160k",
            str(out_mp3),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try: aiff.unlink()
    except FileNotFoundError: pass

# ----------------------- Utilities -------------------------

def store_media(filename: str, path: Path):
    with open(path, "rb") as f:
        data = base64.b64encode(f.read()).decode("utf-8")
    anki("storeMediaFile", filename=filename, data=data)

# Filename slug for sentence audio

def slugify_filename(text: str) -> str:
    s = text.lower().strip()
    s = s.replace(" ", "_")
    s = re.sub(r"[^a-z0-9_\-]", "", s)
    s = re.sub(r"_+", "_", s)
    return s[:64] or "sentence"

# Cloze builder (supports optional hint objects: {"target":"perro","hint":"animal"})

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
        if not target:
            continue
        marker = f"{{{{c{idx}::{target}{('::' + hint) if hint else ''}}}}}"
        s = s.replace(target, marker, 1)
        idx += 1
    return s

_WORD_RE = re.compile(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+", re.UNICODE)

_EPI = None

def ipa_word(word: str) -> str:
    global _EPI
    # Prefer phonemizer (espeak)
    if phonemize is not None:
        try:
            out = phonemize(word, language="es", backend="espeak", strip=True, with_stress=True, njobs=1)
            out = (out or "").strip().replace(" ", "")
            if out:
                return out
        except Exception:
            pass
    # Fallback to epitran
    if epitran is not None:
        try:
            if _EPI is None:
                _EPI = epitran.Epitran("spa-Latn")
            out = _EPI.transliterate(word).strip().replace(" ", "")
            if out:
                return out
        except Exception:
            pass
    return ""

def sentence_ipa(text: str) -> str:
    tokens = _WORD_RE.findall(text)
    if not tokens:
        return ""
    ipas = []
    for w in tokens:
        ip = ipa_word(w)
        if not ip:
            ip = ""
        ipas.append(ip)
    non_empty = sum(1 for x in ipas if x)
    if non_empty == 0:
        return ""
    joined = " ".join(x for x in ipas if x)
    return f"/{joined}/"

# ----------------------- Field mapping ---------------------

def get_model_fields(model_name: str):
    try:
        return anki("modelFieldNames", modelName=model_name) or []
    except Exception:
        return []


def pick_fields(model_name: str, debug: bool):
    fields = get_model_fields(model_name)
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
        print(f"Model '{model_name}' fields: {fields}")
        print(f"Mapping → cloze:{cloze_field} text:{text_field} extra:{extra_field} audio:{audio_field} sentence_ipa:{ipa_field}")
    return cloze_field, text_field, extra_field, audio_field, ipa_field, fields

# ----------------------- Upsert helpers --------------------

def find_note_by_field(deck: str, model: str, field_name: str, value: str, debug: bool):
    snippet = re.sub(r"\s+", " ", value)[:50]
    q = f'deck:"{deck}" note:"{model}" "{snippet}"'
    try:
        note_ids = anki("findNotes", query=q)
        if not note_ids:
            return None
        infos = anki("notesInfo", notes=note_ids)
        for n in infos:
            fields = n.get("fields", {})
            val = (fields.get(field_name, {}).get("value") or "").strip()
            if val == value:
                if debug:
                    print(f"[match:{field_name}] noteId={n.get('noteId')}")
                return n.get("noteId")
    except Exception as e:
        if debug:
            print(f"[warn] find_note_by_field failed: {e}")
    return None

# ----------------------- Main --------------------------------

def main():
    ap = argparse.ArgumentParser(description="Build/Upsert Cloze Sentence notes from JSON")
    ap.add_argument("--deck", default="My Spanish Deck::Sentences")
    ap.add_argument("--model", default="Cloze")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--update-existing", action="store_true")
    ap.add_argument("--regen-audio", action="store_true")
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

    cloze_field, text_field, extra_field, audio_field, ipa_field, model_fields = pick_fields(args.model, args.debug)
    if cloze_field is None:
        print(f"[error] The target model '{args.model}' has no suitable field for cloze text (needs 'Cloze' or 'Text').")
        sys.exit(1)
    first_field = model_fields[0] if model_fields else cloze_field

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
        if args.regen_audio and mp3.exists():
            try: mp3.unlink()
            except Exception: pass
        if not mp3.exists():
            tts_to_mp3(text, mp3)
        store_media(mp3.name, mp3)

        # Optional sentence IPA
        sent_ipa = sentence_ipa(text) if ipa_field else ""

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
        if ipa_field and sent_ipa:
            fields[ipa_field] = sent_ipa

        # Upsert: update if --update-existing and found; else try add; if duplicate error, rescue
        nid = None
        if args.update_existing:
            # 1) Try match by cloze field (exact)
            nid = find_note_by_field(args.deck, args.model, cloze_field, cloze_txt, args.debug)
            # 2) Fallback: match by Text field if available (exact)
            if not nid and text_field:
                nid = find_note_by_field(args.deck, args.model, text_field, text, args.debug)
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
                # fall through to add

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
            msg = str(e).lower()
            if "duplicate" in msg:
                # Rescue: search by Text, then by first_field value used for duplicate detection
                nid2 = None
                if text_field:
                    nid2 = find_note_by_field(args.deck, args.model, text_field, text, args.debug)
                if not nid2:
                    first_val = fields.get(first_field)
                    if first_val:
                        nid2 = find_note_by_field(args.deck, args.model, first_field, first_val, args.debug)
                if nid2:
                    try:
                        anki("updateNoteFields", note={"id": nid2, "fields": fields})
                        if tags:
                            anki("addTags", notes=[nid2], tags=" ".join(tags))
                        count_upd += 1
                        if args.debug:
                            print(f"[dup→updated] {text}")
                        continue
                    except Exception as e2:
                        print(f"[error] duplicate update failed for: {text}\nReason: {e2}")
                else:
                    print(f"[warn] duplicate reported but no matching note found for cloze/text/first-field. Skipped: {text}")
            else:
                print(f"[error] addNote failed for: {text}\nReason: {e}\nFields used: {fields}")
                continue

    print(f"Done. Added {count_add}, Updated {count_upd}.")

if __name__ == "__main__":
    main()
