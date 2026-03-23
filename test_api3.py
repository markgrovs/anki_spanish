import sys
sys.path.append("/Users/markgroves/Documents/[06] Development/spanish_anki")
try:
    from deep_translator import GoogleTranslator, MyMemoryTranslator
except ImportError as e:
    print("No deep_translator", e)
    sys.exit(0)

print("MyMemory translations:")
try:
    print(MyMemoryTranslator(source='en', target='es').translate("keyboard"))
except Exception as e:
    print("MyMemory error", e)

print("Google back-translation:")
print(GoogleTranslator(source='es', target='en').translate("teclado"))

# Multiple options from google?
