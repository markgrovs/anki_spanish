#!/usr/bin/env python3
"""
Interactive Image Picker:
1. Finds words missing images in CSV.
2. Fetches 4 candidates from DuckDuckGo images (ddgs), diversified
   across English/Spanish query variants. Pixabay kept as fallback.
3. Shows a 2x2 collage in 'Preview'.
4. Asks user to pick 1, 2, 3, 4.
5. Saves the winner.
"""
import sys
import shutil
import argparse
import subprocess
from pathlib import Path

# Add parent to path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from lib.config import CSV_PATH, IMAGES_DIR
from lib.csv_store import read_rows
from lib.slugify import slugify
from lib.image_search import gather_candidates, search_ddgs, search_pixabay, download_image
from lib.collage import create_collage

# Temp dir for candidates
TMP_DIR = Path("tmp/candidates")


def spawn_viewer(cmd: list[str]):
    """
    Launch an external process WITHOUT fork().

    ddgs uses primp (Rust HTTP client) which spawns background threads.
    Forking a multi-threaded process crashes on macOS: the Network
    framework's atfork handler segfaults in the child before exec runs
    (SIGSEGV in nw_settings_child_has_forked). posix_spawn is safe in
    multi-threaded processes, but subprocess only takes that path when
    the executable is an absolute path AND close_fds=False.
    """
    exe = shutil.which(cmd[0])
    if exe is None:
        print(f"[warn] Could not find '{cmd[0]}' on PATH")
        return
    subprocess.run([exe] + cmd[1:], close_fds=False)


def open_image_viewer(path: Path):
    """Open image in default OS viewer (Preview on macOS)."""
    if sys.platform == "darwin":
        spawn_viewer(["open", str(path)])
    else:
        # Linux/Windows fallback
        spawn_viewer(["xdg-open", str(path)])


def open_google_images(spanish, english, search_term):
    """Open Google Images with both Spanish and English terms for manual search."""
    import webbrowser
    from urllib.parse import quote

    # Prefer a combined query so the manual search matches the intended meaning
    if spanish and english:
        q = f"{spanish} {english}"
    else:
        q = search_term
    url = f"https://www.google.com/search?tbm=isch&q={quote(q)}"
    # webbrowser also forks internally; use the posix_spawn-safe path
    if sys.platform == "darwin":
        spawn_viewer(["open", url])
    else:
        spawn_viewer(["xdg-open", url])


def show_manual_fallback(spanish, english, search_term):
    """Show the manual fallback menu when search fails or returns nothing."""
    print(f"  Search failed for '{search_term}'. Manual fallback:")
    print("  [o]   = Open Google Images")
    print("  [s]   = Skip")
    print("  [q]   = Quit")
    while True:
        ans = input("  > ").strip().lower()
        if ans == 'q':
            print("Quitting.")
            if TMP_DIR.exists():
                shutil.rmtree(TMP_DIR)
            sys.exit(0)
        if ans == 's':
            return
        if ans == 'o':
            open_google_images(spanish, english, search_term)
            return
        print("Invalid command.")


def fetch_and_show(spanish, english, pos, custom_query=None):
    """
    Fetch candidates, build collage, open in Preview.
    Returns list of candidate paths on success, else [].
    """
    TMP_DIR.mkdir(parents=True, exist_ok=True)

    if custom_query:
        urls = search_ddgs(custom_query, max_results=4)
    else:
        urls = gather_candidates(english, spanish, pos, n=4)

    # Fallback: try Pixabay if DDGS came up empty
    if not urls:
        fallback_term = english if english else spanish
        if fallback_term:
            urls = search_pixabay(fallback_term, per_page=4)

    if not urls:
        return []

    candidates = []
    for idx, url in enumerate(urls):
        if len(candidates) >= 4:
            break
        dest = TMP_DIR / f"cand_{idx}.jpg"
        if download_image(url, dest):
            candidates.append(dest)

    if not candidates:
        return []

    collage_path = TMP_DIR / "preview_collage.jpg"
    if create_collage(candidates, collage_path, label_indices=True):
        open_image_viewer(collage_path)
    else:
        print("  Could not create collage (Pillow missing?).")
        return []

    return candidates


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

    # Identify missing - now stores tuples of (spanish, english, pos)
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
        found = False
        for r in rows:
            if (r.get("spanish") or "").strip().lower() == args.query.lower():
                spanish = (r.get("spanish") or "").strip()
                english = (r.get("english") or "").strip()
                pos = (r.get("pos") or "").strip()
                missing.append((spanish, english, pos))
                found = True
                break
        if not found:
            missing.append((args.query, "", ""))
    else:
        # Scan CSV
        count = 0
        for r in rows:
            s = (r.get("spanish") or "").strip()
            if not s: continue
            if not has_image(s):
                e = (r.get("english") or "").strip()
                p = (r.get("pos") or "").strip()
                missing.append((s, e, p))
                count += 1
            if args.limit and count >= args.limit: break

    print(f"Found {len(missing)} words needing images.")
    if not missing: return

    for i, (spanish, english, pos) in enumerate(missing, 1):
        # Display Spanish and English translation
        display_text = f"'{spanish}'" if not english else f"'{spanish}' ({english})"
        print(f"\n[{i}/{len(missing)}] Processing: {display_text}")

        # Default search term (English preferred for image search)
        search_term = english if english else spanish

        # 1. Fetch candidates + show collage
        candidates = fetch_and_show(spanish, english, pos)

        if not candidates:
            print(f"  No usable candidates for '{search_term}'.")
            show_manual_fallback(spanish, english, search_term)
            continue

        # 2. Ask
        print(f"  Candidates shown for {display_text}. Pick 1-{len(candidates)}:")
        print("  [1-4] = Select image")
        print("  [r]   = Re-query with a custom search term")
        print("  [s]   = Skip")
        print("  [o]   = Open Google Images (manual)")
        print("  [q]   = Quit")

        while True:
            ans = input("  > ").strip()
            if ans == 'q':
                print("Quitting.")
                shutil.rmtree(TMP_DIR)
                sys.exit(0)
            if ans == 's':
                break
            if ans == 'o':
                open_google_images(spanish, english, search_term)
                break
            if ans == 'r':
                custom = input("  New search term: ").strip()
                if not custom:
                    print("  Empty query, keeping current candidates.")
                    continue
                new_candidates = fetch_and_show(spanish, english, pos, custom_query=custom)
                if new_candidates:
                    candidates = new_candidates
                    print(f"  New candidates shown. Pick 1-{len(candidates)}:")
                else:
                    print("  Re-query returned nothing; keeping current candidates.")
                continue

            if ans.isdigit():
                choice = int(ans)
                if 1 <= choice <= len(candidates):
                    # Winner!
                    winner_src = candidates[choice-1]
                    slug = slugify(spanish)
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
