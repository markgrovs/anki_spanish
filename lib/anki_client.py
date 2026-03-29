import requests
import sys
from .config import ANKI_URL

class AnkiClient:
    def __init__(self, url=ANKI_URL):
        self.url = url

    def invoke(self, action, **params):
        """Generic invoke wrapper for AnkiConnect."""
        try:
            r = requests.post(self.url, json={"action": action, "version": 6, "params": params}, timeout=30)
            r.raise_for_status()
            data = r.json()
            if data.get("error"):
                raise RuntimeError(data["error"])
            return data["result"]
        except requests.exceptions.ConnectionError:
            print(f"ERROR: Cannot connect to Anki at {self.url}. Is Anki open with AnkiConnect?")
            sys.exit(1)
        except Exception as e:
            raise RuntimeError(f"Anki request failed: {e}")

    def find_notes(self, query):
        return self.invoke("findNotes", query=query)

    def notes_info(self, notes):
        return self.invoke("notesInfo", notes=notes)
        
    def add_note(self, note):
        return self.invoke("addNote", note=note)

    def update_note_fields(self, note_id, fields):
        return self.invoke("updateNoteFields", note={"id": note_id, "fields": fields})

    def add_tags(self, note_ids, tags):
        if not isinstance(note_ids, list):
            note_ids = [note_ids]
        return self.invoke("addTags", notes=note_ids, tags=tags)
    
    def store_media_file(self, filename, data_base64):
        return self.invoke("storeMediaFile", filename=filename, data=data_base64)
    
    def delete_notes(self, note_ids):
        return self.invoke("deleteNotes", notes=note_ids)

    def model_field_names(self, model_name):
        return self.invoke("modelFieldNames", modelName=model_name)

# Singleton instance for easy import
anki = AnkiClient()
