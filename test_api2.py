import requests
from urllib.parse import quote

def get_multiple_translations(eng: str):
    cands = []
    try:
        url = f"https://api.mymemory.translated.net/get?q={quote(eng)}&langpair=en|es"
        resp = requests.get(url, timeout=5).json()
        matches = resp.get("matches", [])
        for m in matches:
            t = m.get("translation", "").lower().strip()
            if t and t not in cands:
                cands.append(t)
    except Exception as e:
        print(e)
    return cands

print(get_multiple_translations("keyboard"))
