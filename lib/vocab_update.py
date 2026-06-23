"""
vocab_update.py

Extract missing Spanish words from phrases and append to 625 CSV.
Lemma-aware; safe and idempotent.
"""
import csv
import json
import re
import sys
from pathlib import Path
from typing import Set, Dict, Tuple, List

import simplemma

from .config import BASE_DIR, CSV_PATH

SKIP_TOKENS = {
    "la","el","un","una","las","los","lo","al","del",
    "a","de","en","por","para","con","desde","hasta","sin","entre","sobre",
    "que","porque","y","o","u","si","como","pero",
    "mi","mis","me","te","se","tu","su","sus","nos","les","le",
    "esta","este","esto","ese","esa","eso","esos","esas","estos","estas",
    "muy","más","menos","solo","ya","también","no","sí",
}

# Comprehensive vocabulary mapping for common travel phrases
VOCAB_MAP = {
    # ---- verbs ----
    "necesitar": ("to need", "verb"),
    "querer": ("to want", "verb"),
    "poder": ("to be able / can", "verb"),
    "ir": ("to go", "verb"),
    "tener": ("to have", "verb"),
    "estar": ("to be (location/state)", "verb"),
    "ser": ("to be (essence)", "verb"),
    "haber": ("there to be (hay)", "verb"),
    "buscar": ("to look for", "verb"),
    "quedar": ("to stay / remain", "verb"),
    "reparar": ("to repair", "verb"),
    "costar": ("to cost", "verb"),
    "arrancar": ("to start (engine)", "verb"),
    "revisar": ("to check / inspect", "verb"),
    "hablar": ("to speak", "verb"),
    "llenar": ("to fill", "verb"),
    "mostrar": ("to show", "verb"),
    "conocer": ("to know (be familiar with)", "verb"),
    "abrir": ("to open", "verb"),
    "dejar": ("to leave / let", "verb"),
    "detener": ("to stop / detain", "verb"),
    "salir": ("to leave / go out", "verb"),
    "cambiar": ("to change", "verb"),
    "perder": ("to lose", "verb"),
    "ayudar": ("to help", "verb"),
    "empujar": ("to push", "verb"),
    "hacer": ("to do / make", "verb"),
    "conseguir": ("to get / obtain", "verb"),
    "evitar": ("to avoid", "verb"),
    "valer": ("to be worth", "verb"),
    "aprender": ("to learn", "verb"),
    "probar": ("to try / taste", "verb"),
    "tomar": ("to take", "verb"),
    "recomendar": ("to recommend", "verb"),
    "acampar": ("to camp", "verb"),
    "descansar": ("to rest", "verb"),
    "ver": ("to see", "verb"),
    "pagar": ("to pay", "verb"),
    "comprar": ("to buy", "verb"),
    "comer": ("to eat", "verb"),
    "estacionar": ("to park", "verb"),
    "encontrar": ("to find", "verb"),
    "arreglar": ("to fix", "verb"),
    "pavimentar": ("to pave", "verb"),
    
    # ---- nouns ----
    "moto": ("motorcycle", "noun"),
    "motocicleta": ("motorcycle", "noun"),
    "hotel": ("hotel", "noun"),
    "reservación": ("reservation", "noun"),
    "reserva": ("reservation / booking", "noun"),
    "huésped": ("guest", "noun"),
    "problema": ("problem", "noun"),
    "cajero": ("ATM / cashier", "noun"),
    "mecánico": ("mechanic", "noun"),
    "favor": ("favor", "noun"),
    "estacionamiento": ("parking lot", "noun"),
    "camino": ("road / path", "noun"),
    "sol": ("sun", "noun"),
    "agua": ("water", "noun"),
    "comida": ("food", "noun"),
    "agujero": ("hole", "noun"),
    "foto": ("photo", "noun"),
    "frontera": ("border", "noun"),
    "pasaporte": ("passport", "noun"),
    "mochila": ("backpack", "noun"),
    "llanta": ("tire", "noun"),
    "cadena": ("chain", "noun"),
    "presión": ("pressure", "noun"),
    "lugar": ("place", "noun"),
    "hora": ("hour", "noun"),
    "ciudad": ("city", "noun"),
    "casco": ("helmet", "noun"),
    "ley": ("law", "noun"),
    "chaqueta": ("jacket", "noun"),
    "ruta": ("route", "noun"),
    "wifi": ("wifi", "noun"),
    "policía": ("police", "noun"),
    "ferry": ("ferry", "noun"),
    "mediodía": ("noon / midday", "noun"),
    "mercado": ("market", "noun"),
    "palabra": ("word", "noun"),
    "baño": ("bathroom", "noun"),
    "cartera": ("wallet", "noun"),
    "herramienta": ("tool", "noun"),
    "hostal": ("hostel", "noun"),
    "día": ("day", "noun"),
    "altitud": ("altitude", "noun"),
    "viajero": ("traveler", "noun"),
    "oficial": ("officer / official", "noun"),
    "aduana": ("customs", "noun"),
    "autopista": ("highway", "noun"),
    "carpa": ("tent", "noun"),
    "cuota": ("installment / fee", "noun"),
    "veterinario": ("veterinarian", "noun"),
    "vista": ("view", "noun"),
    "montaña": ("mountain", "noun"),
    "pena": ("trouble (vale la pena = worth it)", "noun"),
    "cámara": ("inner tube / camera", "noun"),
    "lluvia": ("rain", "noun"),
    "documento": ("document", "noun"),
    "tarjeta": ("card", "noun"),
    "noche": ("night", "noun"),
    "mapa": ("map", "noun"),
    "mañana": ("morning / tomorrow", "noun"),
    "puesta": ("sunset (puesta de sol)", "noun"),
    "seguro": ("insurance", "noun"),
    
    # ---- adjectives ----
    "roto": ("broken", "adjective"),
    "desinflado": ("deflated / flat", "adjective"),
    "flojo": ("loose", "adjective"),
    "caro": ("expensive", "adjective"),
    "fuerte": ("strong", "adjective"),
    "caliente": ("hot", "adjective"),
    "bueno": ("good", "adjective"),
    "mucho": ("many / much", "adjective"),
    "local": ("local", "adjective"),
    "increíble": ("incredible", "adjective"),
    "próximo": ("next", "adjective"),
    "requerido": ("required", "adjective"),
    "enfermo": ("sick", "adjective"),
    "mojado": ("wet", "adjective"),
    "automático": ("automatic", "adjective"),
    "otro": ("other", "adjective"),
    "alguno": ("some", "adjective"),
    "bajo": ("low", "adjective"),
    
    # ---- adverbs / question words ----
    "despacio": ("slowly", "adverb"),
    "temprano": ("early", "adverb"),
    "aquí": ("here", "adverb"),
    "acá": ("here", "adverb"),
    "cerca": ("near / nearby", "adverb"),
    "dónde": ("where", "adverb"),
    "cuánto": ("how much", "adverb"),
    "cuándo": ("when", "adverb"),
}


def lemma(w: str) -> str:
    """Lemmatize a Spanish word."""
    try:
        return simplemma.lemmatize(w.lower(), lang="es")
    except Exception:
        return w.lower()


def get_csv_words() -> Tuple[Set[str], Set[str]]:
    """Load existing Spanish words from CSV. Return (surface_forms, lemmas)."""
    surface, lemmas = set(), set()
    
    if not CSV_PATH.exists():
        return surface, lemmas
    
    with CSV_PATH.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            es = (row.get("spanish") or "").strip().lower()
            if es:
                for token in re.findall(r"[a-záéíóúñü]+", es):
                    surface.add(token)
                    lemmas.add(lemma(token))
    
    return surface, lemmas


def get_phrase_tokens() -> Dict[str, str]:
    """Extract all tokens from phrase_cards.json. Return {token: example_phrase}."""
    phrases_path = BASE_DIR / "data" / "phrase_cards.json"
    if not phrases_path.exists():
        return {}
    
    phrases = json.loads(phrases_path.read_text(encoding="utf-8"))
    tokens = {}
    
    for phrase in phrases:
        spanish = phrase.get("spanish", "")
        for token in re.findall(r"[a-záéíóúñü]+", spanish.lower()):
            tokens.setdefault(token, spanish)
    
    return tokens


def find_missing(
    phrase_tokens: Dict[str, str],
    csv_surface: Set[str],
    csv_lemmas: Set[str],
) -> Tuple[Dict[str, Tuple[str, str, str]], List[Tuple[str, str, str]]]:
    """
    Find phrase tokens not in CSV.
    Return (to_add, unknowns) where:
      to_add: {spanish: (english, pos, example)}
      unknowns: [(token, lemma, example), ...]
    """
    to_add = {}
    unknowns = []
    
    for token, example in sorted(phrase_tokens.items()):
        # Skip function words
        if token in SKIP_TOKENS:
            continue
        
        # Exact match → skip
        if token in csv_surface:
            continue
        
        # Check if token is in VOCAB_MAP
        if token in VOCAB_MAP:
            en, pos = VOCAB_MAP[token]
            to_add[token] = (en, pos, example)
            continue
        
        # Lemmatize and check
        lem = lemma(token)
        if lem in csv_surface or lem in csv_lemmas:
            continue
        
        if lem in VOCAB_MAP:
            en, pos = VOCAB_MAP[lem]
            to_add[lem] = (en, pos, example)
        else:
            unknowns.append((token, lem, example))
    
    return to_add, unknowns


def write_csv(to_add: Dict[str, Tuple[str, str, str]]) -> int:
    """Append rows to CSV. Return count of rows added."""
    if not to_add or not CSV_PATH.exists():
        return 0
    
    with CSV_PATH.open("r", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
    
    # Find column indices
    try:
        i_en = header.index("english")
        i_es = header.index("spanish")
        i_pos = header.index("pos") if "pos" in header else None
    except ValueError:
        print("ERROR: Could not find english/spanish/pos columns in CSV header")
        return 0
    
    # Append rows
    with CSV_PATH.open("a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        for es, (en, pos, _) in sorted(to_add.items()):
            row = [""] * len(header)
            row[i_en] = en
            row[i_es] = es
            if i_pos is not None:
                row[i_pos] = pos
            writer.writerow(row)
    
    return len(to_add)


def interactive_review(
    unknowns: List[Tuple[str, str, str]],
    csv_surface: Set[str],
    csv_lemmas: Set[str],
) -> Dict[str, Tuple[str, str, str]]:
    """
    Interactively review unknown tokens.
    Return dict of {spanish: (english, pos, example)} to add.
    """
    reviewed = {}
    
    for i, (token, lem, example) in enumerate(unknowns, 1):
        print(f"\n[{i}/{len(unknowns)}] {token}")
        print(f"   Lemma suggests: {lem}")
        print(f"   Example: {example}")
        
        # Check if the suggested lemma is already in CSV
        if lem in csv_surface or lem in csv_lemmas:
            print(f"   ✓ '{lem}' already in your deck. Skipping.")
            continue
        
        # Prompt user
        while True:
            resp = input(f"   (a)dd '{lem}' | (s)kip | (e)dit english | (m)anual? > ").strip().lower()
            
            if resp == "a":
                # Auto-add using lemma as base
                if lem in VOCAB_MAP:
                    en, pos = VOCAB_MAP[lem]
                    reviewed[lem] = (en, pos, example)
                    print(f"   ✓ Added: {lem} ({pos}) = {en}")
                else:
                    print(f"   ✗ No mapping for '{lem}'. Try (e) or (m).")
                break
            
            elif resp == "s":
                print(f"   - Skipped")
                break
            
            elif resp == "e":
                en = input(f"   English for '{lem}': ").strip()
                pos = input(f"   POS (noun/verb/adjective/adverb): ").strip().lower()
                if pos not in ("noun", "verb", "adjective", "adverb"):
                    print(f"   Invalid POS. Try again.")
                    continue
                reviewed[lem] = (en, pos, example)
                print(f"   ✓ Added: {lem} ({pos}) = {en}")
                break
            
            elif resp == "m":
                es = input(f"   Spanish word: ").strip()
                en = input(f"   English: ").strip()
                pos = input(f"   POS (noun/verb/adjective/adverb): ").strip().lower()
                if pos not in ("noun", "verb", "adjective", "adverb"):
                    print(f"   Invalid POS. Try again.")
                    continue
                reviewed[es] = (en, pos, example)
                print(f"   ✓ Added: {es} ({pos}) = {en}")
                break
            
            else:
                print(f"   Invalid choice. Try (a), (s), (e), or (m).")
    
    return reviewed


def update_vocab(write_mode: bool = False, interactive: bool = False, verbose: bool = True) -> int:
    """
    Main entry point. Extract missing vocab from phrases and optionally write.
    Returns count of rows added (0 if dry-run).
    """
    csv_surface, csv_lemmas = get_csv_words()
    phrase_tokens = get_phrase_tokens()
    to_add, unknowns = find_missing(phrase_tokens, csv_surface, csv_lemmas)
    
    if verbose:
        print(f"\n✅ Found {len(to_add)} new vocabulary items to add")
        for es, (en, pos, _) in sorted(to_add.items()):
            print(f"   {es:20} {pos:10} {en}")
    
    # Interactive review of unknowns
    reviewed = {}
    if unknowns:
        if verbose:
            print(f"\n⚠️  {len(unknowns)} tokens need review")
        if interactive or write_mode:
            print()
            reviewed = interactive_review(unknowns, csv_surface, csv_lemmas)
            if reviewed:
                to_add.update(reviewed)
                if verbose:
                    print(f"\n✓ Added {len(reviewed)} reviewed items")
        elif verbose:
            print(f"   Run with --review to interactively add them:")
            for token, lem, example in unknowns[:5]:
                print(f"     • {token:20} (base: {lem})")
            if len(unknowns) > 5:
                print(f"     ... and {len(unknowns) - 5} more")
    
    if verbose and to_add:
        print(f"\n{len(to_add)} items ready to add")
        if not write_mode:
            print(f"   Run with --write to append to CSV")
    
    if write_mode:
        count = write_csv(to_add)
        if verbose and count > 0:
            print(f"\n✅ Appended {count} rows to {CSV_PATH.name}")
        return count
    
    return 0
