import csv
from .config import CSV_PATH, FIELDNAMES

def read_rows(path=CSV_PATH):
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    # Ensure all fields are present
    for r in rows:
        for k in FIELDNAMES:
            r.setdefault(k, "")
    return rows

def write_rows(rows, path=CSV_PATH):
    with path.open("w", newline="", encoding="utf-8") as out:
        w = csv.DictWriter(out, fieldnames=FIELDNAMES)
        w.writeheader()
        for r in rows:
            # Filter to only known fields
            row = {k: r.get(k, "") for k in FIELDNAMES}
            w.writerow(row)
