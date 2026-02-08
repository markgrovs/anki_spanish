#!/usr/bin/env python3
"""
Interactive Image Picker:
1. Finds words missing images in CSV.
2. Fetches 4 candidates from Pixabay.
3. Shows a 2x2 collage in 'Preview'.
4. Asks user to pick 1, 2, 3, 4.
5. Saves the winner.
"""
import sys
import shutil
import argparse
import subprocess
from pathlib import Path
import time

# Add parent to path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from lib.config import CSV_PATH, IMAGES_DIR
from lib.csv_store import read_rows
from lib.slugify import slugify
from lib.image_search import search_pixabay, download_image
from lib.collage import create_collage

# Temp dir for candidates
TMP_DIR = Path("tmp/candidates")

def open_image_viewer(path: Path):
    """Open image in default OS viewer (Preview on macOS)."""
    if sys.platform == "darwin":
        subprocess.run(["open", str(path)])
    else:
        # Linux/Windows fallback
        subprocess.run(["xdg-open", str(path)])

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--query", type=str, help="Specific word to process")
    args = ap.parse_args()

    if not CSV_PATH.exists():
        print("CSV not found.")
        return

    rows = read_rows(CSV_PATH)
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    
    # Identify missing
    missing = []
    
    # Helper to check if image exists
    def has_image(w):
        slug = slugify(w)
        for ext in (".jpg", ".jpeg", ".png", ".webp"):
            if (IMAGES_DIR / f"{slug}{ext}").exists(): return True
            if (IMAGES_DIR / f"{slug}_collage.jpg").exists(): return True
        return False

    if args.query:
        # Just one specific word
        # Find it in CSV to get proper casing if possible, else use raw
        found = False
        for r in rows:
            if (r.get("spanish") or "").strip().lower() == args.query.lower():
                missing.append(r.get("spanish"))
                found = True
                break
        if not found: missing.append(args.query)
    else:
        # Scan CSV
        count = 0
        for r in rows:
            s = (r.get("spanish") or "").strip()
            if not s: continue
            if not has_image(s):
                missing.append(s)
                count += 1
            if args.limit and count >= args.limit: break
    
    print(f"Found {len(missing)} words needing images.")
    if not missing: return

    for i, word in enumerate(missing, 1):
        print(f"\n[{i}/{len(missing)}] Processing: '{word}'")
        
        # 1. Search
        urls = search_pixabay(word, per_page=4)
        if not urls:
            print("  No results from Pixabay.")
            # Fallback?
            continue
            
        # 2. Download candidates
        candidates = []
        for idx, url in enumerate(urls):
            dest = TMP_DIR / f"cand_{idx}.jpg"
            if download_image(url, dest):
                candidates.append(dest)
        
        if not candidates:
            print("  Failed to download candidates.")
            continue
            
        # 3. Create Collage
        collage_path = TMP_DIR / "preview_collage.jpg"
        if create_collage(candidates, collage_path, label_indices=True):
            # 4. Show
            open_image_viewer(collage_path)
        else:
            print("  Could not create collage (Pillow missing?).")
            
        # 5. Ask
        print(f"  Candidates shown for '{word}'. Pick 1-{len(candidates)}:")
        print("  [1-4] = Select image")
        print("  [s]   = Skip")
        print("  [o]   = Open Google Images (manual)")
        print("  [q]   = Quit")
        
        while True:
            ans = input("  > ").strip().lower()
            if ans == 'q':
                print("Quitting.")
                shutil.rmtree(TMP_DIR)
                sys.exit(0)
            if ans == 's':
                break
            if ans == 'o':
                import webbrowser
                from urllib.parse import quote
                webbrowser.open_new_tab(f"https://www.google.com/search?tbm=isch&q={quote(word)}")
                break
            
            if ans.isdigit():
                choice = int(ans)
                if 1 <= choice <= len(candidates):
                    # Winner!
                    winner_src = candidates[choice-1]
                    slug = slugify(word)
                    final_dest = IMAGES_DIR / f"{slug}.jpg"
                    
                    # Move winner to media/images
                    shutil.move(winner_src, final_dest)
                    print(f"  Saved: {final_dest.name}")
                    break
                else:
                    print("Invalid selection.")
            else:
                print("Invalid command.")

    # Cleanup
    if TMP_DIR.exists():
        shutil.rmtree(TMP_DIR)
    print("\nBatch complete.")

if __name__ == "__main__":
    main()
