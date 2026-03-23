import sys
import re
sys.path.append("/Users/markgroves/Documents/[06] Development/spanish_anki")

try:
    from deep_translator import GoogleTranslator
except ImportError:
    GoogleTranslator = None

def get_english_definition(es_word):
    if not GoogleTranslator: return ""
    return GoogleTranslator(source='es', target='en').translate(es_word)

print(get_english_definition("teclado"))
