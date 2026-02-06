#!/usr/bin/env python3
import sys
import os
import shutil
from pathlib import Path

try:
    import argostranslate.package as pkg
    import argostranslate.translate as tr
    from argostranslate import settings
except ImportError:
    print("Argos Translate is not installed. Run: pip install argostranslate")
    sys.exit(1)

def print_installed():
    print("\n--- Current Installed Languages ---")
    try:
        # Force reload of languages if possible
        if hasattr(pkg, 'load_available_packages'):
            pkg.load_available_packages()
        
        langs = tr.get_installed_languages()
        if not langs:
            print("(None found)")
        for L in langs:
            code = getattr(L, 'code', '???')
            name = getattr(L, 'name', '???')
            print(f"  [{code}] {name}")
            for t in getattr(L, 'translations', []):
                 to_lang = getattr(t, 'to_lang', None)
                 to_code = getattr(to_lang, 'code', None) if to_lang else "???"
                 print(f"      -> {to_code}")
    except Exception as e:
        print(f"Error listing languages: {e}")
    print("-----------------------------------\n")

print(f"Argos Data Path: {settings.data_dir}")
print(f"Package Cache:   {settings.package_data_dir}")

# 1. Update Index
print("\n[1/3] Updating package index...")
try:
    pkg.update_package_index()
except Exception as e:
    print(f"Warning: Index update failed ({e}), trying to proceed with cached index.")

# 2. Find Package
print("[2/3] Searching for en->es package...")
available_packages = pkg.get_available_packages()
target_pkg = next(
    (p for p in available_packages if p.from_code == 'en' and p.to_code == 'es'),
    None
)

if not target_pkg:
    print("Error: Could not find 'en -> es' package in the catalog.")
    print("Available pairs found:")
    for p in available_packages[:5]: # just show a few
        print(f"  {p.from_code} -> {p.to_code}")
    sys.exit(1)

print(f"Found package: {target_pkg}")

# 3. Download and Install
print("[3/3] Downloading and installing...")
try:
    download_path = target_pkg.download()
    print(f"Downloaded to: {download_path}")
    pkg.install_from_path(download_path)
    print("Install function returned successfully.")
except Exception as e:
    print(f"CRITICAL ERROR during install: {e}")
    sys.exit(1)

# 4. Verify
print_installed()

# Final Check
is_working = False
try:
    t = tr.get_translation_from_codes("en", "es")
    if t:
        res = t.translate("Hello world")
        print(f"Test Translation: 'Hello world' -> '{res}'")
        if res:
            is_working = True
except Exception as e:
    print(f"Translation test failed: {e}")

if is_working:
    print("\nSUCCESS: Argos Translate is ready.")
else:
    print("\nFAILURE: Package installed but translation is not working.")
    print("Try deleting the data directory manually and re-running:")
    print(f"  rm -rf {settings.data_dir}")
