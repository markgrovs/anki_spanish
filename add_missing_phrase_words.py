#!/usr/bin/env python3
import csv, json, re, sys
from pathlib import Path
import simplemma

ROOT = Path(__file__).resolve().parent
CSV_PATH = ROOT / "625_structured.es.csv"
PHRASES  = ROOT / "data" / "phrase_cards.json"

def lemma(w: str) -> str:
    try:
        return simplemma.lemmatize(w.lower(), lang="es")
    except Exception:
        return w.lower()

SKIP = {
    "la","el","un","una","las","los","lo","al","del",
    "a","de","en","por","para","con","desde","hasta","sin","entre","sobre",
    "que","porque","y","o","u","si","como","pero",
    "mi","mis","me","te","se","tu","su","sus","nos","les","le",
    "esta","este","esto","ese","esa","eso","esos","esas","estos","estas",
    "muy","más","menos","solo","ya","también","no","sí",
}

ADDITIONS = {
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
    "despacio": ("slowly", "adverb"),
    "temprano": ("early", "adverb"),
    "aquí": ("here", "adverb"),
    "acá": ("here", "adverb"),
    "cerca": ("near / nearby", "adverb"),
    "dónde": ("where", "adverb"),
    "cuánto": ("how much", "adverb"),
    "cuándo": ("when", "adverb"),
    # Special cases that simplemma doesn't handle well
    "bajo": ("low", "adjective"),
    "pavimentar": ("to pave", "verb"),
}

def find_col(header, *names):
    for n in names:
        if n in header:
            return header.index(n)
    return None

def main():
    write = "--write" in sys.argv

    phrases = json.loads(PHRASES.read_text(encoding="utf-8"))
    raw = CSV_PATH.read_text(encoding="utf-8").splitlines()
    rows = list(csv.reader(raw))
    header = rows[0]

    i_en  = find_col(header, "english")
    i_es  = find_col(header, "spanish")
    i_pos = find_col(header, "pos")

    if i_en is None or i_es is None:
        print("!! Could not locate english/spanish columns.")
        return

    # Build existing surface + lemma sets from the CSV
    existing_surface, existing_lemma = set(), set()
    for r in rows[1:]:
        if len(r) > i_es and r[i_es].strip():
            es = r[i_es].strip().lower()
            for tok in re.findall(r"[a-záéíóúñü]+", es):
                existing_surface.add(tok)
                existing_lemma.add(lemma(tok))

    # Collect phrase tokens
    seen = {}
    for p in phrases:
        for tok in re.findall(r"[a-záéíóúñü]+", p.get("spanish", "").lower()):
            seen.setdefault(tok, p.get("spanish"))

    to_add = {}
    for tok, example in sorted(seen.items()):
        if tok in SKIP:
            continue
        if tok in existing_surface:
            continue
        if tok in ADDITIONS:
            en, pos = ADDITIONS[tok]
            to_add[tok] = (en, pos, example)
            continue
        lm = lemma(tok)
        if lm in existing_surface or lm in existing_lemma:
            continue
        if lm in ADDITIONS:
            en, pos = ADDITIONS[lm]
            to_add[lm] = (en, pos, example)

    print(f"✅ Will add {len(to_add)} new words\n")
    for es, (en, pos, ex) in sorted(to_add.items()):
        print(f"  {es:20} {pos:10} {en}")

    if write and to_add:
        with CSV_PATH.open("a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            for es, (en, pos, ex) in sorted(to_add.items()):
                row = [""] * len(header)
                row[i_en] = en
                row[i_es] = es
                if i_pos is not None:
                    row[i_pos] = pos
                w.writerow(row)
        print(f"\n✅ Appended {len(to_add)} rows to CSV")
    elif to_add:
        print("\nRun with --write to append.")

if __name__ == "__main__":
    main()
