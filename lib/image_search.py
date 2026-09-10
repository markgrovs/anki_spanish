import time
import requests
from pathlib import Path
from .config import PIXABAY_API_KEY

# How many DDGS attempts before giving up on a query (transient scraper failures)
DDGS_RETRIES = 3
DDGS_BACKOFF = 1.5  # seconds, multiplied per attempt


def build_queries(english: str, spanish: str, pos: str = "") -> list[str]:
    """
    Build a prioritized list of search queries for a vocab word.

    Order matters: earlier queries get more collage slots.
      1. English lemma, disambiguated by part of speech
         (verbs get a concrete anchor like "yawn person")
      2. Spanish word (regional/cultural context)
    """
    queries = []
    e = (english or "").strip()
    s = (spanish or "").strip()
    p = (pos or "").strip().lower()

    if e:
        if p == "verb" or e.lower().startswith("to "):
            base = e[3:].strip() if e.lower().startswith("to ") else e
            # Verbs photograph poorly as bare lemmas; anchor on a person doing it
            queries.append(f"{base} person")
        else:
            queries.append(e)

    if s and s.lower() not in [q.lower() for q in queries]:
        queries.append(s)

    return queries


def search_ddgs(query: str, max_results: int = 4, region: str = "wt-wt") -> list[str]:
    """
    Search DuckDuckGo images (via ddgs) for a query. Returns image URLs.

    Free, no API key. Scraped, so retry transient failures with backoff.
    """
    try:
        from ddgs import DDGS
    except ImportError:
        print("[warn] ddgs not installed: pip install ddgs")
        return []

    for attempt in range(1, DDGS_RETRIES + 1):
        try:
            results = list(DDGS().images(query, max_results=max_results, region=region))
            urls = [r.get("image") for r in results if r.get("image")]
            return urls[:max_results]
        except Exception as e:
            if attempt == DDGS_RETRIES:
                print(f"[warn] DDGS search failed for '{query}' after {attempt} attempts: {e}")
                return []
            time.sleep(DDGS_BACKOFF * attempt)

    return []


def search_pixabay(query: str, per_page: int = 4) -> list[str]:
    """
    Search Pixabay for images. Returns list of image URLs (largeImageURL or webformatURL).
    Kept as a fallback source; Pixabay's curated stock index is weak on
    concrete vocabulary but occasionally has good aesthetic shots.
    """
    if not PIXABAY_API_KEY:
        print("[warn] No PIXABAY_API_KEY found in .env")
        return []

    url = "https://pixabay.com/api/"
    params = {
        "key": PIXABAY_API_KEY,
        "q": query,
        "image_type": "photo",
        "per_page": per_page,
        "safesearch": "true",
    }

    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        hits = data.get("hits", [])
        urls = [h.get("webformatURL") for h in hits if h.get("webformatURL")]
        return urls[:per_page]
    except Exception as e:
        print(f"[warn] Pixabay search failed: {e}")
        return []


def gather_candidates(english: str, spanish: str, pos: str = "", n: int = 4) -> list[str]:
    """
    Gather n candidate image URLs from a ladder of query variants.

    Slots are diversified so the 2x2 collage shows genuinely different
    options instead of four near-duplicates:
      - primary query (English, POS-disambiguated): first 2 slots
      - secondary queries (Spanish, etc.): 1 slot each
      - any remaining slots filled from the primary query
    """
    queries = build_queries(english, spanish, pos)
    if not queries:
        return []

    primary, rest = queries[0], queries[1:]

    urls: list[str] = []
    seen: set[str] = set()

    def add(url: str):
        if url and url not in seen:
            seen.add(url)
            urls.append(url)

    # Over-fetch (2x) so failed downloads (403 hotlink blocks, dropped
    # connections) still leave n usable candidates after download.
    want = n * 2

    # Primary query: first half of the slots
    for u in search_ddgs(primary, max_results=want // 2):
        add(u)

    # Secondary queries: fill the rest
    for q in rest:
        if len(urls) >= want:
            break
        for u in search_ddgs(q, max_results=2):
            add(u)

    # Fill any remaining slots from the primary query
    if len(urls) < want:
        for u in search_ddgs(primary, max_results=want):
            add(u)

    return urls[:want]


# Some hosts block default python-requests UA with 403; a browser UA fixes most
HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "image/avif,image/webp,image/*,*/*;q=0.8",
}


def download_image(url: str, dest: Path, retries: int = 2):
    """Download image from URL to path, with browser UA and retries."""
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(url, timeout=15, headers=HTTP_HEADERS)
            r.raise_for_status()
            with dest.open("wb") as f:
                f.write(r.content)
            return True
        except Exception as e:
            if attempt == retries:
                print(f"[warn] Failed to download {url}: {e}")
                return False
            time.sleep(1)
