import requests
import random
from pathlib import Path
from .config import PIXABAY_API_KEY

def search_pixabay(query: str, per_page: int = 4) -> list[str]:
    """
    Search Pixabay for images. Returns list of image URLs (largeImageURL or webformatURL).
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
        "lang": "es"  # Try Spanish search first
    }
    
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        hits = data.get("hits", [])
        
        # Fallback to English if Spanish returns few results (optional logic, usually Pixabay handles langs well)
        if len(hits) < 2 and query.lower() != "en":
             # We could try translating query here, but let's stick to Spanish for now
             pass
             
        urls = [h.get("webformatURL") for h in hits if h.get("webformatURL")]
        return urls[:per_page]
    except Exception as e:
        print(f"[warn] Pixabay search failed: {e}")
        return []

def download_image(url: str, dest: Path):
    """Download image from URL to path."""
    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        with dest.open("wb") as f:
            f.write(r.content)
        return True
    except Exception as e:
        print(f"[warn] Failed to download {url}: {e}")
        return False
