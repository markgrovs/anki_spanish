#!/usr/bin/env python3
import csv, webbrowser, time, sys, os
from pathlib import Path
from urllib.parse import quote

CSV_PATH = Path("625_structured.csv")
OUT_PATH = Path("625_structured.es.csv")
HINTS_PATH = Path("hints_es.yaml")

# Minimal YAML loader (no external deps). Accepts a tiny subset: key: value and lists under key.
# Example file:
# ---
# default_voice: Paulina
# candidates:
#   "dog|||": ["perro", "perra (hembra)"]
#   "back|body|": ["espalda"]
#   "back|direction|": ["atrás", "de vuelta"]
#   "light|/dark|adjective": ["claro"]
#   "light|/heavy|adjective": ["ligero"]
#   "light||noun": ["luz"]
#   "phone||noun": ["teléfono", "celular (LA)"]

def load_hints(path: Path):
    if not path.exists():
        return {}, {}
    # Minimal YAML parse
    candidates = {}
    defaults = {}
    current_section = None
    last_key = None
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if s.endswith(":") and not s.startswith("-"):
            # section header e.g., candidates:
            current_section = s[:-1].strip()
            continue
        if current_section == "candidates":
            if not line.startswith(" ") and ":" in line:
                # top-level key
                key, _ = line.split(":", 1)
                last_key = key.strip().strip('"')
                candidates[last_key] = []
            elif line.strip().startswith("-"):
                val = line.strip()[1:].strip().strip('"')
                if last_key:
                    candidates[last_key].append(val)
        elif current_section == "defaults":
            if ":" in line:
                k, v = line.split(":", 1)
                defaults[k.strip().strip('"')] = v.strip().strip('"')
    return candidates, defaults

# Base default suggestions (fallback if no hints found)
DEFAULTS = {
    ("dog","",""): "perro",
    ("water","","noun"): "agua",
    ("phone","","noun"): "teléfono",
    ("light","/dark","adjective"): "claro",
    ("light","/heavy","adjective"): "ligero",
    ("light","","noun"): "luz",
    ("back","body",""): "espalda",
    ("back","direction",""): "atrás",
}


def normalize_key(eng, sense, pos):
    return f"{eng.lower()}|{sense.lower()}|{pos.lower()}"


def suggest(row, hints_candidates, defaults_map):
    key = (row["english"].lower(), row["sense"].lower(), row["pos"].lower())
    default = DEFAULTS.get(key, "")
    # hints candidates by exact triple or by english-only
    k_exact = normalize_key(*key)
    k_eng_only = normalize_key(row["english"], "", "")
    cands = hints_candidates.get(k_exact, []) or hints_candidates.get(k_eng_only, [])
    # defaults_map (from hints) can override default
    dkey = k_exact if k_exact in defaults_map else k_eng_only
    if dkey in defaults_map:
        default = defaults_map[dkey]
    return default, cands


def open_refs(eng):
    webbrowser.open_new_tab(f"https://www.spanishdict.com/translate/{quote(eng)}")
    time.sleep(0.15)
    webbrowser.open_new_tab(f"https://linguee.com/english-spanish/search?source=auto&query={quote(eng)}")
    time.sleep(0.15)
    webbrowser.open_new_tab(f"https://www.google.com/search?q={quote(eng + ' in spanish')}")


def save_rows(rows):
    with OUT_PATH.open("w", newline="", encoding="utf-8") as out:
        w = csv.DictWriter(out, fieldnames=["english","sense","pos","spanish","notes"])
        w.writeheader()
        w.writerows(rows)


def main():
    if not CSV_PATH.exists():
        print("CSV not found:", CSV_PATH)
        sys.exit(1)

    hints_candidates, defaults_map = load_hints(HINTS_PATH)

    with CSV_PATH.open("r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    total = len(rows)
    changed = False

    i = 0
    while i < total:
        row = rows[i]
        # If already filled (from a previous session), skip
        if row.get("spanish"):
            i += 1
            continue
        eng = row.get("english","")
        sense = row.get("sense","")
        pos = row.get("pos","")

        default, cands = suggest(row, hints_candidates, defaults_map)

        print("-"*60)
        print(f"[{i+1}/{total}] english='{eng}'  sense='{sense}'  pos='{pos}'")
        if cands:
            print("Candidates:")
            for idx, c in enumerate(cands, 1):
                print(f"  {idx}) {c}")
        else:
            print("(no candidates in hints)")
        print(f"Default: {default if default else '(none)'}")
        print("Commands: type your Spanish; 1-9 pick candidate; d=default; o=open refs; s=skip; p=prev; u=unset; q=quit")
        ans = input("> ").strip()

        if ans == "":
            # empty input: if there is a default, accept it; else skip
            if default:
                row["spanish"] = default
                changed = True
                save_rows(rows)
                i += 1
            else:
                print("(no default; skipped)")
                i += 1
            continue
        if ans.lower() == "s":
            i += 1
            continue
        if ans.lower() == "p":
            i = max(0, i-1)
            continue
        if ans.lower() == "q":
            break
        if ans.lower() == "o":
            open_refs(eng)
            # re-prompt same item
            continue
        if ans.lower() == "u":
            # unset any existing value and re-prompt
            row["spanish"] = ""
            save_rows(rows)
            continue
        if ans.lower() == "d":
            if default:
                row["spanish"] = default
                changed = True
                save_rows(rows)
                i += 1
            else:
                print("No default available.")
            continue
        if ans.isdigit():
            if not cands:
                print("No candidates to pick; type your Spanish or press 'o' for references.")
                continue
            idx = int(ans)
            if 1 <= idx <= len(cands):
                row["spanish"] = cands[idx-1]
                changed = True
                save_rows(rows)
                i += 1
                continue
            else:
                print("Invalid candidate number.")
                continue
        # Otherwise, treat input as the chosen Spanish
        row["spanish"] = ans
        changed = True
        save_rows(rows)
        i += 1

    # Final save
    save_rows(rows)
    print(f"Saved {OUT_PATH}. Changed={changed}")

if __name__ == "__main__":
    main()
