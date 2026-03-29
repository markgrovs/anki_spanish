import os
from pathlib import Path

# Base paths
BASE_DIR = Path(__file__).resolve().parent.parent
# Load .env explicitly if present
ENV_PATH = BASE_DIR / ".env"
if ENV_PATH.exists():
    with ENV_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip() and not line.startswith("#") and "=" in line:
                k, v = line.strip().split("=", 1)
                os.environ[k] = v

DATA_DIR = BASE_DIR / "data"
MEDIA_DIR = BASE_DIR / "media"
IMAGES_DIR = MEDIA_DIR / "images"
AUDIO_DIR = MEDIA_DIR / "audio"
GENDER_DIR = MEDIA_DIR / "gender"
SENTENCES_AUDIO_DIR = MEDIA_DIR / "sentences_audio"

CSV_PATH = BASE_DIR / "625_structured.es.csv"
HINTS_PATH = BASE_DIR / "hints_es.yaml"

# Anki settings
ANKI_URL = "http://127.0.0.1:8765"
DECK_NAME = "My Spanish Deck::625"
MODEL_NAME = "Picture Word"
SENTENCES_DECK = "My Spanish Deck::Sentences"
SENTENCES_MODEL = "Cloze"

# Voice settings
VOICE_NAME = "Paulina"
SPEAKING_RATE = 150

# CSV Field structure (canonical)
FIELDNAMES = ["english", "sense", "pos", "spanish", "gender", "ipa", "notes"]

# Ensure directories exist
def ensure_dirs():
    for d in [DATA_DIR, MEDIA_DIR, IMAGES_DIR, AUDIO_DIR, GENDER_DIR, SENTENCES_AUDIO_DIR]:
        d.mkdir(parents=True, exist_ok=True)

PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY", "")
