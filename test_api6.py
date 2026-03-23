import requests
from urllib.parse import quote

def get_mymemory_candidates(eng: str):
    cands = []
    try:
        url = f"https://api.mymemory.translated.net/get?q={quote(eng)}&langpair=en|es"
        resp = requests.get(url, timeout=3).json()
        matches = resp.get("matches", [])
        for m in matches:
            t = m.get("translation", "").strip()
            # Clean up things like "la manzana" -> "manzana"
            t_lower = t.lower()
            for art in ["el ", "la ", "los ", "las ", "un ", "una ", "unos ", "unas "]:
                if t_lower.startswith(art):
                    t = t[len(art):]
                    break
            
            if t and t.lower() not in [c.lower() for c in cands]:
                # Exclude long sentences
                if len(t.split()) <= 3:
                    cands.append(t.lower())
    except:
        pass
    return cands

print(get_mymemory_candidates("keyboard"))
print(get_mymemory_candidates("apple"))
print(get_mymemory_candidates("run"))
