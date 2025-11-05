#!/usr/bin/env python3
import csv, webbrowser, time
from pathlib import Path
from urllib.parse import quote

CSV_PATH = Path("625_structured.csv")
OUT_PATH = Path("625_structured.es.csv")

# Optionally seed default suggestions for common senses
DEFAULTS = {
    # examples; expand as you go
    ("dog","",""): "perro",
    ("water","","noun"): "agua",
    ("phone","","noun"): "teléfono",
    ("light","/dark","adjective"): "claro",
    ("light","/heavy","adjective"): "ligero",
    ("light","","noun"): "luz",
    ("back","body",""): "espalda",
    ("back","direction",""): "atrás",
}

def suggest(row):
    key = (row["english"].lower(), row["sense"].lower(), row["pos"].lower())
    return DEFAULTS.get(key, "")

def main():
    rows = []
    with CSV_PATH.open("r", encoding="utf-8") as f:
        r = csv.DictReader(f)
        rows = list(r)

    for i, row in enumerate(rows, 1):
        if row["spanish"]:
            continue
        eng = row["english"]
        sense = row["sense"]
        pos = row["pos"]
        query = eng
        if sense:
            query += f" ({sense})"
        url = f"https://www.spanishdict.com/translate/{quote(eng)}"
        webbrowser.open_new_tab(url)
        time.sleep(0.2)
        print(f"[{i}/{len(rows)}] {eng}  sense='{sense}'  pos='{pos}'")
        default = suggest(row)
        ans = input(f"Spanish [{default}]: ").strip()
        if ans.lower() == "s":
            continue
        row["spanish"] = ans if ans else default

    with OUT_PATH.open("w", newline="", encoding="utf-8") as out:
        w = csv.DictWriter(out, fieldnames=["english","sense","pos","spanish","notes"])
        w.writeheader()
        w.writerows(rows)

    print(f"Saved {OUT_PATH}")

if __name__ == "__main__":
    main()
