#!/usr/bin/env python3
"""Sync Capohm character_profiles from config.json to characters/*.json.

main_modular.py currently loads character prompts from characters/<name>.json.
The config UI stores richer editable profiles in config.json under character_profiles.
This bridge writes compatible character JSON files so the bot actually uses the edited prompts.
"""
from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

DEFAULT_EMOTIONS = [
    "neutral", "listening", "thinking", "happy", "angry", "sad", "confused",
    "surprised", "alert", "error", "sleep", "amused", "sounds",
]


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def backup(path: Path) -> Path | None:
    if not path.exists():
        return None
    bdir = Path("backups")
    bdir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = bdir / f"{path.name}.before_character_sync_{stamp}.bak"
    shutil.copy2(path, out)
    return out


def clean_aliases(name: str, display_name: str, profile: dict[str, Any]) -> list[str]:
    aliases: list[str] = []

    def add(value: Any) -> None:
        if not value:
            return
        text = str(value).strip()
        if not text:
            return
        if text not in aliases:
            aliases.append(text)

    for value in profile.get("aliases", []) or []:
        add(value)

    add(name)
    add(name.replace("_", " "))
    add(display_name)
    add(display_name.lower())

    # Nice shortcuts for common current characters.
    if name == "grumpy_shopkeeper":
        for a in ["grumpy", "shopkeeper", "old man", "old shopkeeper", "potion shopkeeper"]:
            add(a)
    elif name == "borg":
        for a in ["hive", "borg hive", "queen", "collective"]:
            add(a)
    elif name == "natural":
        for a in ["normal", "assistant", "natural voice"]:
            add(a)

    return aliases


def build_system_prompt(profile: dict[str, Any]) -> str:
    prompt = (profile.get("system_prompt") or profile.get("personality_prompt") or "").strip()
    if prompt:
        return prompt

    parts = []
    for key in ["description", "background", "lore"]:
        value = str(profile.get(key, "")).strip()
        if value:
            parts.append(value)
    if parts:
        return "\n\n".join(parts)

    return "You are a helpful desktop assistant. Keep replies short, practical, and clear."


def ensure_media_dirs(media_dir: Path) -> None:
    for emotion in DEFAULT_EMOTIONS:
        (media_dir / emotion).mkdir(parents=True, exist_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.json")
    parser.add_argument("--characters-dir", default=None)
    parser.add_argument("--media-dir", default="ui_media")
    parser.add_argument("--no-backup", action="store_true")
    args = parser.parse_args()

    config_path = Path(args.config)
    cfg = load_json(config_path, {})
    profiles = cfg.get("character_profiles") or {}

    if not profiles:
        print("No character_profiles found in config.json. Nothing to sync.")
        return 1

    characters_dir = Path(args.characters_dir or cfg.get("characters_dir", "characters"))
    media_root = Path(args.media_dir)
    characters_dir.mkdir(parents=True, exist_ok=True)

    if not args.no_backup:
        b = backup(config_path)
        if b:
            print(f"Backup: {b}")

    cfg["characters_dir"] = str(characters_dir)

    written = []
    for name, profile in sorted(profiles.items()):
        if not isinstance(profile, dict):
            continue

        path = characters_dir / f"{name}.json"
        old = load_json(path, {})
        if path.exists() and not args.no_backup:
            backup(path)

        display_name = str(profile.get("display_name") or profile.get("name") or name).strip()
        description = str(profile.get("description") or "").strip()
        background = str(profile.get("background") or "").strip()

        media_dir = Path(profile.get("media_dir") or media_root / "characters" / name)
        ensure_media_dirs(media_dir)

        char = {
            "name": name,
            "display_name": display_name,
            "aliases": clean_aliases(name, display_name, profile),
            "description": description,
            "background": background,
            "system_prompt": build_system_prompt(profile),
            "media_dir": str(media_dir),
            "thinking_sound": str(profile.get("thinking_sound", "")).strip(),
            "wake_responses": profile.get("wake_responses") or old.get("wake_responses") or cfg.get("wake_responses", ["Online."]),
            "sleep_responses": profile.get("sleep_responses") or old.get("sleep_responses") or cfg.get("sleep_responses", ["Sleeping."]),
            "switch_response": profile.get("switch_response") or old.get("switch_response") or f"Character profile loaded: {display_name}.",
        }

        # Keep mode/backend details in the file too. main_modular does not use these yet,
        # but the UI and future routers can.
        for key in ["pro", "free"]:
            if isinstance(profile.get(key), dict):
                char[key] = profile[key]

        save_json(path, char)
        written.append(path)

    save_json(config_path, cfg)

    print("Synced character files:")
    for path in written:
        print(f"- {path}")
    print("Done. Restart the bot after syncing.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
