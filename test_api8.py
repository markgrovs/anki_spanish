import requests
import json
from urllib.parse import quote

def translate_and_define(eng: str):
    # Free API for definitions
    try:
        url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{quote(eng)}"
        r = requests.get(url, timeout=3).json()
        print(f"EN Def for {eng}:")
        for m in r[0].get('meanings', [])[:1]:
            for d in m.get('definitions', [])[:1]:
                print(d.get('definition'))
    except: pass

translate_and_define("apple")
