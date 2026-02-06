#!/usr/bin/env python3
import requests
import json
import sys

ANKI_URL = "http://127.0.0.1:8765"
DECK_NAME = "My Spanish Deck::625"

def anki(action, **params):
    try:
        r = requests.post(ANKI_URL, json={"action": action, "version": 6, "params": params}, timeout=10)
    except requests.exceptions.ConnectionError:
        print("Error: Anki is not running or AnkiConnect is missing.")
        sys.exit(1)
    return r.json()["result"]

print(f"--- Checking Settings for '{DECK_NAME}' ---\n")

# 1. Get the Deck's Configuration Group ID
decks = anki("deckNamesAndIds")
deck_id = decks.get(DECK_NAME)

if not deck_id:
    print(f"Deck '{DECK_NAME}' not found.")
    print("Available decks:", list(decks.keys()))
    sys.exit(1)

config = anki("getDeckConfig", deck=DECK_NAME)

if not config:
    print("Could not retrieve config.")
    sys.exit(1)

# 2. Extract and Print Key Settings
print(f"Config Name: {config['name']}")
print(f"Auto-Bury New (Siblings):   {'[ON]' if config['buryInterdayLearning'] else '[OFF]'} (Recommended: ON)")
print(f"Auto-Bury Reviews (Siblings): {'[ON]' if config['buryInterdayLearning'] else '[OFF]'} (Recommended: ON)")
# Note: V3 scheduler combines these often, but let's check standard keys
# 'buryNew': True/False, 'buryRev': True/False are the classic keys

print(f"Bury New:    {config.get('buryNew', 'Unknown')}")
print(f"Bury Review: {config.get('buryRev', 'Unknown')}")

print("\n[New Cards]")
print(f"  Steps:              {config['new']['delays']} minutes")
print(f"  Starting Ease:      {config['new']['initialFactor'] / 10.0}%")
print(f"  Order:              {'Random' if config['new']['order'] == 0 else 'Added'}")
print(f"  Per Day:            {config['new']['perDay']}")

print("\n[Lapses/Leeches]")
print(f"  Steps:              {config['lapse']['delays']} minutes")
print(f"  Leech Threshold:    {config['lapse']['leechFails']} fails")
print(f"  Leech Action:       {'Suspend' if config['lapse']['leechAction'] == 0 else 'Tag Only'}")

print("\n[Reviews]")
print(f"  Per Day:            {config['rev']['perDay']} (Should be 9999)")
print(f"  Maximum Interval:   {config['rev']['maxIvl']} days")
print(f"  Easy Bonus:         {config['rev']['ease4'] * 100}%")

print("-" * 40)
print("Raw config dump saved to 'anki_settings_dump.json' if you need it.")

with open("anki_settings_dump.json", "w") as f:
    json.dump(config, f, indent=2)
