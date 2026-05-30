def contains_any(text: str, phrases: list[str]) -> bool:
    text = (text or "").lower()
    return any(p.lower() in text for p in phrases)

def is_wake_word(text: str, config: dict) -> bool:
    return contains_any(text, config.get("wake_words", []))

def is_sleep_command(text: str, config: dict) -> bool:
    return contains_any(text, config.get("sleep_commands", []))
