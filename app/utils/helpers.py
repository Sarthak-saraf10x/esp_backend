def clean_text_for_header(text):
    """Remove or replace characters that can't be in HTTP headers"""
    cleaned = ''.join(char for char in text if ord(char) < 128)
    cleaned = ' '.join(cleaned.split())
    return cleaned.strip()

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
