#!/usr/bin/env python3
import json
import re
import csv
from pathlib import Path
from collections import defaultdict

def extract_missing_words():
    """Extract Spanish words from phrases that aren't in the 625 word list."""
    
    # Load phrases
    print("📖 Loading phrase cards...")
    phrases_data = json.loads(Path('data/phrase_cards.json').read_text(encoding='utf-8'))
    print(f"   Loaded {len(phrases_data)} phrases")
    
    # Load CSV and extract existing Spanish words
    print("\n📋 Loading 625 word list...")
    csv_path = Path('625_structured.es.csv')
    csv_lines = csv_path.read_text(encoding='utf-8').strip().split('\n')
    
    csv_spanish = set()
    for line in csv_lines[1:]:  # Skip header
        parts = line.split(',')
        if len(parts) > 3:
            spanish = parts[3].strip().lower()
            if spanish:
                csv_spanish.add(spanish)
    
    print(f"   CSV contains {len(csv_spanish)} Spanish words")
    
    # Extract words from all phrases
    print("\n🔍 Extracting words from phrases...")
    phrase_words = defaultdict(list)
    for phrase in phrases_data:
        spanish_phrase = phrase.get('spanish', '')
        # Extract Spanish words (letters, accents, hyphens, apostrophes)
        words = re.findall(r"[a-záéíóúñü']+(?:-[a-záéíóúñü']+)*", spanish_phrase.lower())
        for word in words:
            phrase_words[word].append(spanish_phrase)
    
    print(f"   Phrases contain {len(phrase_words)} unique word tokens")
    
    # Find missing words
    missing = {w: phrase_words[w] for w in phrase_words if w not in csv_spanish}
    
    # Sort by frequency
    sorted_missing = sorted(missing.items(), key=lambda x: len(x[1]), reverse=True)
    
    print(f"\n✅ Found {len(sorted_missing)} words in phrases NOT in CSV\n")
    
    # Display them
    print("=" * 80)
    print(f"{'Word':<20} {'Freq':<6} {'Example Phrase':<50}")
    print("=" * 80)
    
    for word, phrases_list in sorted_missing:
        freq = len(phrases_list)
        example = phrases_list[0][:47] + "..." if len(phrases_list[0]) > 50 else phrases_list[0]
        print(f"{word:<20} {freq:<6} {example:<50}")
    
    # Save to file for easy reference
    output_file = Path('missing_words_from_phrases.txt')
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("Missing Spanish Words from Phrases\n")
        f.write("=" * 80 + "\n\n")
        for word, phrases_list in sorted_missing:
            f.write(f"{word} ({len(phrases_list)} phrases)\n")
            for phrase in phrases_list:
                f.write(f"  - {phrase}\n")
            f.write("\n")
    
    print(f"\n💾 Saved to: {output_file}")
    
    return sorted_missing

if __name__ == '__main__':
    missing = extract_missing_words()