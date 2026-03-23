import sys
import re
sys.path.append("/Users/markgroves/Documents/[06] Development/spanish_anki")
from lib.wiktionary import fetch_wikitext, get_spanish_section

def get_en_gloss_for_es_word(es_word):
    # Fetch from en.wiktionary.org for the Spanish word
    txt = fetch_wikitext(es_word, "en")
    sec = get_spanish_section(txt, "en")
    if not sec:
        return []
    
    # We look for lines starting with # 
    glosses = []
    for line in sec.split('\n'):
        if line.startswith('#') and not line.startswith('#:'):
            # Clean up the line
            clean = re.sub(r'\{\{[^}]+\}\}', '', line[1:])
            clean = re.sub(r'\[\[(?:[^|\]]+\|)?([^\]]+)\]\]', r'\1', clean)
            clean = clean.strip()
            # sometimes they have quotes or other wiki syntax, just simple replace
            clean = clean.replace("'''", "").replace("''", "")
            if clean and clean not in glosses:
                glosses.append(clean)
    return glosses

print("carrera:", get_en_gloss_for_es_word("carrera"))
print("manzana:", get_en_gloss_for_es_word("manzana"))
print("teclado:", get_en_gloss_for_es_word("teclado"))
