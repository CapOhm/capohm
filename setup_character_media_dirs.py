#!/usr/bin/env python3
"""Create character-specific media folders for Capohm display UI.

Layout created:
    ui_media/characters/<character>/<emotion>/

It reads character names from characters/*.json when available, and also adds
borg, natural, and grumpy_shopkeeper.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

EMOTIONS = [
    "neutral",
    "listening",
    "thinking",
    "happy",
    "amused",
    "alert",
    "error",
    "sleep",
    "sad",
    "confused",
]
DEFAULT_CHARACTERS = {"borg", "natural", "grumpy_shopkeeper"}


def safe_name(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "_", name).strip("_") or "default"


def get_characters() -> set[str]:
    names = set(DEFAULT_CHARACTERS)
    cdir = Path("characters")
    if cdir.exists():
        for path in sorted(cdir.glob("*.json")):
            names.add(path.stem)
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if data.get("name"):
                    names.add(str(data["name"]))
            except Exception:
                pass
    return {safe_name(n) for n in names}


def main() -> int:
    root = Path("ui_media")
    char_root = root / "characters"
    for emotion in EMOTIONS:
        (root / emotion).mkdir(parents=True, exist_ok=True)
    for char in sorted(get_characters()):
        for emotion in EMOTIONS:
            (char_root / char / emotion).mkdir(parents=True, exist_ok=True)

    print("Created character media folders:")
    for char in sorted(get_characters()):
        print(f"  ui_media/characters/{char}/")
    print("\nExample:")
    print("  cp ~/Pictures/faces\\ normal/ponder_face.png ui_media/characters/grumpy_shopkeeper/thinking/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
