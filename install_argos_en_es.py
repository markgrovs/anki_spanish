#!/usr/bin/env python3
import sys

try:
    import argostranslate.package as pkg
    import argostranslate.translate as tr
except Exception:
    print("Argos Translate is not installed. Install it first:")
    print("    python -m pip install argostranslate")
    sys.exit(1)

# Update the package index (API changed across versions)
print("Updating Argos package index…")
try:
    # Newer API
    if hasattr(pkg, "update_package_index"):
        pkg.update_package_index()
    # Older API (fallback)
    elif hasattr(pkg, "update"):
        pkg.update()
    else:
        print("Warning: Could not find update function; continuing anyway.")
except Exception as e:
    print("Failed to update package index:", e)
    print("If you're behind a proxy, set HTTPS_PROXY and HTTP_PROXY env vars.")
    # continue; sometimes catalog is bundled

# Find the en->es package
packages = []
try:
    packages = pkg.get_available_packages()
except Exception as e:
    print("Could not retrieve available packages:", e)
    print("If this persists, try again later or install manually from the Argos catalog.")
    sys.exit(1)

match = None
for p in packages:
    try:
        if getattr(p, 'from_code', None) == 'en' and getattr(p, 'to_code', None) == 'es':
            match = p
            break
    except Exception:
        continue

if not match:
    print("Could not find the English→Spanish package in the catalog.")
    sys.exit(1)

print(f"Downloading: {getattr(match, 'filename', 'en_es')} …")
try:
    path = match.download()
except Exception as e:
    print("Download failed:", e)
    sys.exit(1)

print("Installing model…")
try:
    pkg.install_from_path(path)
except Exception as e:
    print("Installation failed:", e)
    sys.exit(1)

# Verify install
installed = False
try:
    langs = tr.get_installed_languages()
    en_langs = [L for L in langs if getattr(L, 'code', '') == 'en']
    for L in en_langs:
        for t in getattr(L, 'translations', []):
            # Newer versions expose .to_lang; older may expose .code directly
            to_code = getattr(getattr(t, 'to_lang', None), 'code', None) or getattr(t, 'code', None)
            if to_code == 'es':
                installed = True
                break
except Exception:
    pass

if installed:
    print("Success: Argos en→es model installed.")
else:
    print("Model did not register correctly. Try re-running this script.")
