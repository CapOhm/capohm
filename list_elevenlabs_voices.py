#!/usr/bin/env python3
"""List ElevenLabs voices and IDs using ELEVENLABS_API_KEY from env or .env."""
from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.request import Request, urlopen


def read_dotenv(key: str) -> str | None:
    path = Path(".env")
    if not path.exists():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        if k.strip() == key:
            return v.strip().strip('"').strip("'")
    return None


def main() -> int:
    key = os.environ.get("ELEVENLABS_API_KEY") or read_dotenv("ELEVENLABS_API_KEY")
    if not key:
        print("Missing ELEVENLABS_API_KEY. Put it in .env or export it first.")
        return 1
    req = Request("https://api.elevenlabs.io/v1/voices", headers={"xi-api-key": key})
    with urlopen(req, timeout=30) as res:
        data = json.loads(res.read().decode("utf-8"))
    voices = data.get("voices", [])
    if not voices:
        print("No voices returned.")
        return 0
    for v in voices:
        name = v.get("name", "<unnamed>")
        voice_id = v.get("voice_id", "")
        category = v.get("category", "")
        print(f"{name:32} {voice_id}  {category}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
