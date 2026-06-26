import re

def clean_text_for_tts(text: str) -> str:
    """
    Cleans text for TTS synthesis.
    - Replaces symbols like & and % with words.
    - Strips markdown bold, italic, lists, and headings.
    - Removes emojis and non-speech symbols.
    - Fixes spacing around standard punctuation.
    - Replaces colons and semicolons with commas to avoid TTS literal reading.
    """
    if not text:
        return ""
    
    # 1. Replace word-replacements
    text = re.sub(r'\s*&\s*', ' and ', text)
    text = re.sub(r'\s*%\s*', ' percent ', text)

    # 2. Remove markdown formatting characters
    text = re.sub(r'\*\*([^*]+)\*\*|__([^_]+)__|[\*_]', r'\1\2', text)
    text = re.sub(r'^[>\s#\-+*]+\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'[#>\*\`\~]', '', text)

    # 3. Clean up other symbols that shouldn't be read, keep standard alphanumeric, spaces, and basic punctuation
    text = re.sub(r'[^\w\s.,?!:;\'\"()-]', ' ', text)

    # 4. Fix punctuation spacing (no space before punctuation)
    text = re.sub(r'\s+([.,?!;:’"”])', r'\1', text)

    # 5. Normalize quotes and apostrophes
    text = text.replace('’', "'").replace('‘', "'")
    text = text.replace('“', '"').replace('”', '"')

    # 6. Semicolon and colon handling: replace with comma/period to avoid voice synthesizer pronouncing them
    text = text.replace(';', ',').replace(':', ',')

    # 7. Clean up extra whitespaces
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def clean_text_for_header(text):
    """Remove or replace characters that can't be in HTTP headers"""
    cleaned = ''.join(char for char in text if ord(char) < 128)
    cleaned = ' '.join(cleaned.split())
    cleaned = cleaned.strip()
    if len(cleaned) > 200:
        cleaned = cleaned[:197] + "..."
    return cleaned

def get_pruned_history(history, keep=20):
    if not history:
        return []
    pruned = list(history[-keep:])
    while pruned:
        if pruned[0].role == 'user':
            has_text = any(hasattr(p, 'text') and p.text is not None for p in pruned[0].parts)
            if has_text:
                break
        pruned.pop(0)
    return pruned

