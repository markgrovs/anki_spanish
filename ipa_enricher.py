#!/usr/bin/env python3
import csv
import re
import sys
from pathlib import Path

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

BASE_DIR = Path(__file__).resolve().parent
CSV_PATH = BASE_DIR / "625_structured.es.csv"
OUT_PATH = BASE_DIR / "625_structured.es.csv"  # in-place update

IPA_SLASH_RE = re.compile(r"/(.*?)/")
TEMPLATE_RE = re.compile(r"\{\{\s*(?:AFI|IPA)[^}]*\}\}", re.IGNORECASE)


def read_rows(path: Path):
    with path.open("r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    # Ensure columns exist
    for r in rows:
        r.setdefault("ipa", "")
        r.setdefault("gender", "")
        r.setdefault("notes", "")
    return rows


def write_rows(path: Path, rows):
    fieldnames = ["english", "sense", "pos", "spanish", "gender", "ipa", "notes"]
    with path.open("w", newline="", encoding="utf-8") as out:
        w = csv.DictWriter(out, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            # keep only known keys
            row = {k: r.get(k, "") for k in fieldnames}
            w.writerow(row)


# ---------------- Wiktionary fetch -----------------

def _fetch_wikt(page: str, lang: str) -> str:
    if not requests:
        return ""
    url = f"https://{lang}.wiktionary.org/w/api.php"
    try:
        resp = requests.get(url, params={
            "action": "parse",
            "prop": "wikitext",
            "page": page,
            "format": "json",
        }, timeout=10)
        if not resp.ok:
            return ""
        data = resp.json()
        return data.get("parse", {}).get("wikitext", {}).get("*", "")
    except Exception:
        return ""


def ipa_from_wiktionary(word: str) -> str:
    # Try Spanish Wiktionary first, then English
    for lang in ("es", "en"):
        txt = _fetch_wikt(word, lang)
        if not txt:
            continue
        # Find IPA/AFI templates first
        for m in TEMPLATE_RE.finditer(txt):
            segment = m.group(0)
            m2 = IPA_SLASH_RE.search(segment)
            if m2:
                ipa = m2.group(0)
                if ipa:
                    return ipa
        # Fallback: any /…/ that resembles IPA
        allslashes = IPA_SLASH_RE.findall(txt)
        for s in allslashes:
            # Heuristic: has IPA chars like ɾ, ʝ, ʎ, ð, ɣ, ˈ, etc. or typical vowels/consonants
            if any(ch in s for ch in "ɾʝʎðɣθβˈˌ") or len(s) >= 3:
                return f"/{s}/"
    return ""


# --------------- Phonemizer / Epitran -------------

def ipa_from_phonemizer(word: str) -> str:
    if phonemize is None:
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
    if epitran is None:
        return ""
    try:
        epi = epitran.Epitran("spa-Latn")
        out = epi.transliterate(word).strip()
        out = out.replace(" ", "")
        if out:
            return f"/{out}/"
    except Exception:
        return ""
    return ""


def main():
    if not CSV_PATH.exists():
        print("CSV not found:", CSV_PATH)
        sys.exit(1)

    rows = read_rows(CSV_PATH)
    total = len(rows)
    updated = 0

    for i, r in enumerate(rows, 1):
        if r.get("ipa"):
            continue
        word = (r.get("spanish") or "").strip()
        if not word:
            continue
        # Try sources in order: Wiktionary → Phonemizer → Epitran
        ipa = ipa_from_wiktionary(word)
        if not ipa:
            ipa = ipa_from_phonemizer(word)
        if not ipa:
            ipa = ipa_from_epitran(word)
        if ipa:
            r["ipa"] = ipa
            updated += 1
            if updated % 20 == 0:
                print(f"[{i}/{total}] added IPA for {updated} words so far…")

    write_rows(OUT_PATH, rows)
    print(f"Done. Updated {updated} entries. Wrote {OUT_PATH}.")


if __name__ == "__main__":
    main()
