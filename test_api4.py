import sys
import re
sys.path.append("/Users/markgroves/Documents/[06] Development/spanish_anki")
from lib.wiktionary import fetch_wikitext, get_spanish_section

def get_definitions(es_word):
    txt = fetch_wikitext(es_word, "es")
    sec = get_spanish_section(txt, "es")
    if not sec:
        return []
    
    # Simple extraction of numbered lists starting with ;1: or #
    # In es.wiktionary, definitions usually start with "1", ";1", or "#"
    defs = []
    for line in sec.split('\n'):
        if line.startswith(';1'):
            defs.append(line.replace(';1', '').strip())
        elif line.startswith('#') and not line.startswith('#:'):
            # remove wiki links [[word|display]] -> display
            clean = re.sub(r'\[\[(?:[^|\]]+\|)?([^\]]+)\]\]', r'\1', line[1:])
            # remove templates {{...}}
            clean = re.sub(r'\{\{[^}]+\}\}', '', clean)
            clean = clean.strip()
            if clean and clean not in defs:
                defs.append(clean)
    return defs

print("Teclado:")
print(get_definitions("teclado"))
print("\nManzana:")
print(get_definitions("manzana"))
