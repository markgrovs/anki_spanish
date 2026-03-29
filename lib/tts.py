import subprocess
from pathlib import Path
from .config import AUDIO_DIR, VOICE_NAME, SPEAKING_RATE

# Cached preferred voice
_PICKED_VOICE = None

def pick_working_voice(preferred=VOICE_NAME) -> str:
    global _PICKED_VOICE
    if _PICKED_VOICE is not None:
        return _PICKED_VOICE
        
    candidates = [preferred, "Paulina", "Luciana", "Diego", "Monica", "Jorge", None]
    
    test_aiff = AUDIO_DIR / "_voice_test.aiff"
    for v in candidates:
        try:
            cmd = ["say", "-r", str(SPEAKING_RATE), "prueba", "-o", str(test_aiff)]
            if v:
                cmd = ["say", "-v", v, "-r", str(SPEAKING_RATE), "prueba", "-o", str(test_aiff)]
            
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            if test_aiff.exists():
                try: test_aiff.unlink()
                except: pass
            
            _PICKED_VOICE = v or ""
            return _PICKED_VOICE
        except Exception:
            continue
            
    _PICKED_VOICE = ""
    return ""

def tts_to_mp3(text: str, out_mp3: Path):
    """Generate speech (macOS say) -> convert to MP3 with padding."""
    voice = pick_working_voice()
    aiff = out_mp3.with_suffix(".aiff")
    
    cmd = ["say", "-r", str(SPEAKING_RATE), text, "-o", str(aiff)]
    if voice:
        cmd = ["say", "-v", voice, "-r", str(SPEAKING_RATE), text, "-o", str(aiff)]
        
    subprocess.run(cmd, check=True)
    
    # ffmpeg convert + pad
    subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(aiff),
            "-ar", "44100", "-ac", "1",
            "-af", "adelay=120:all=1,apad=pad_dur=0.35",
            "-c:a", "libmp3lame", "-b:a", "160k",
            str(out_mp3),
        ],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    
    try: aiff.unlink()
    except FileNotFoundError: pass
