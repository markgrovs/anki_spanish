#!/usr/bin/env python3
import requests
import json
import sys
from pathlib import Path

ANKI_URL = "http://127.0.0.1:8765"
MODEL_NAME = "Picture Word"

def anki(action, **params):
    try:
        r = requests.post(ANKI_URL, json={"action": action, "version": 6, "params": params}, timeout=10)
    except requests.exceptions.ConnectionError:
        print("Error: Anki is not running or AnkiConnect is missing.")
        sys.exit(1)
    return r.json().get("result")

print(f"--- Exporting Card Design for '{MODEL_NAME}' ---\n")

# 1. Get Styling (CSS)
styling = anki("modelStyling", modelName=MODEL_NAME)
if not styling:
    print(f"Could not find model '{MODEL_NAME}'. Check the name in Anki.")
    sys.exit(1)

css = styling.get("css", "")
with open("current_styling.css", "w", encoding="utf-8") as f:
    f.write(css)
print(f"Saved 'current_styling.css' ({len(css)} chars)")

# 2. Get Templates (HTML)
templates = anki("modelTemplates", modelName=MODEL_NAME)
if not templates:
    print("No templates found.")
    sys.exit(1)

# Dump templates to files
for card_name, tmpl in templates.items():
    safe_name = card_name.replace(" ", "_")
    
    front = tmpl.get("Front", "")
    with open(f"template_{safe_name}_front.html", "w", encoding="utf-8") as f:
        f.write(front)
        
    back = tmpl.get("Back", "")
    with open(f"template_{safe_name}_back.html", "w", encoding="utf-8") as f:
        f.write(back)
        
    print(f"Saved templates for card type: '{card_name}'")

print("\nDone! Please verify the content of 'current_styling.css'.")
