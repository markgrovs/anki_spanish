import sys
import re
sys.path.append("/Users/markgroves/Documents/[06] Development/spanish_anki")
from lib.wiktionary import fetch_wikitext, get_spanish_section

def get_wiktionary_gloss_for_es_word(es_word: str):
    """Fetches English definitions of a Spanish word from EN Wiktionary."""
    txt = fetch_wikitext(es_word, "en")
    if not txt: return []
    sec = get_spanish_section(txt, "en")
    if not sec: return []
    
    glosses = []
    for line in sec.split('\n'):
        if line.startswith('#') and not line.startswith('#:'):
            # Remove templates {{...}}
            clean = re.sub(r'\{\{[^}]+\}\}', '', line[1:])
            # Remove wikitext links [[word|display]] -> display
            clean = re.sub(r'\[\[(?:[^|\]]+\|)?([^\]]+)\]\]', r'\1', clean)
            # Remove quotes
            clean = clean.replace("'''", "").replace("''", "").strip()
            # Clean up lingering wikitext artifacts like leading commas or colons
            clean = re.sub(r'^[:\s,]+', '', clean)
            if clean and clean not in glosses and len(clean) > 2:
                glosses.append(clean)
    return glosses[:3]  # Return top 3 definitions

print("carrera:", get_wiktionary_gloss_for_es_word("carrera"))
print("manzana:", get_wiktionary_gloss_for_es_word("manzana"))
print("teclado:", get_wiktionary_gloss_for_es_word("teclado"))
