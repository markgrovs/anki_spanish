import requests
from urllib.parse import quote

def mymemory_translate(eng: str):
    candidates = []
    try:
        url = f"https://api.mymemory.translated.net/get?q={quote(eng)}&langpair=en|es"
        resp = requests.get(url, timeout=5).json()
        matches = resp.get("matches", [])
        for m in matches:
            t = m.get("translation", "")
            if t: candidates.append(t.lower())
    except Exception as e:
        print(e)
    return candidates

print(mymemory_translate("apple"))
