#!/usr/bin/env python3
"""
Capohm character profile helper.

Purpose:
- Add/maintain config.json character_profiles.
- Keep API secrets out of config.json.
- Let each character have Pro and Free AI/TTS/STT settings.
- Apply the selected character+mode back onto the existing top-level config keys,
  so current main_modular.py keeps working before we build the full router.

Usage from ~/capohm:
    python3 capohm_character_profiles.py init
    python3 capohm_character_profiles.py list
    python3 capohm_character_profiles.py set-mode pro
    python3 capohm_character_profiles.py set-character grumpy_shopkeeper
    python3 capohm_character_profiles.py set-voice grumpy_shopkeeper VOICE_ID_HERE
    python3 capohm_character_profiles.py add-character old_wizard "Old Wizard"
    python3 capohm_character_profiles.py apply
"""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import json
import re
from pathlib import Path
from typing import Any

CONFIG_PATH = Path("config.json")
MEDIA_ROOT = Path("ui_media")

DEFAULT_CHARACTERS = {
    "grumpy_shopkeeper": "Grumpy Shopkeeper",
    "borg": "Borg Hive",
    "natural": "Natural Assistant",
}

EMOTIONS = [
    "neutral",
    "listening",
    "thinking",
    "happy",
    "amused",
    "angry",
    "sad",
    "confused",
    "surprised",
    "alert",
    "error",
    "sleep",
]

TOP_LEVEL_KEYS_TO_APPLY = [
    "ai_backend",
    "openai_model",
    "ollama_profile",
    "ollama_model_profile",
    "ollama_model",
    "tts_backend",
    "stt_backend",
    "piper_fast_mode",
    "elevenlabs_voice_id",
    "elevenlabs_model_id",
    "elevenlabs_output_format",
    "elevenlabs_language_code",
]


def slugify(value: str) -> str:
    value = value.strip().lower().replace(" ", "_").replace("-", "_")
    value = re.sub(r"[^a-z0-9_]+", "", value)
    value = re.sub(r"_+", "_", value).strip("_")
    if not value:
        raise SystemExit("Character name became empty after cleanup. Use letters/numbers/underscores.")
    return value


def load_dotenv(path: Path = Path(".env")) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        raise SystemExit("config.json not found. Run this from ~/capohm.")
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def backup_config() -> Path:
    backup_dir = Path("backups")
    backup_dir.mkdir(exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = backup_dir / f"config_before_character_profiles_{stamp}.json"
    backup.write_text(CONFIG_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    return backup


def save_config(cfg: dict[str, Any], do_backup: bool = True) -> None:
    if do_backup:
        backup = backup_config()
        print(f"Backup: {backup}")
    CONFIG_PATH.write_text(json.dumps(cfg, indent=4, ensure_ascii=False) + "\n", encoding="utf-8")


def ensure_media_dirs(character: str) -> None:
    for emotion in EMOTIONS:
        path = MEDIA_ROOT / "characters" / character / emotion
        path.mkdir(parents=True, exist_ok=True)
        keep = path / ".gitkeep"
        if not keep.exists():
            keep.write_text("", encoding="utf-8")
    sounds = MEDIA_ROOT / "characters" / character / "sounds"
    sounds.mkdir(parents=True, exist_ok=True)
    keep = sounds / ".gitkeep"
    if not keep.exists():
        keep.write_text("", encoding="utf-8")


def default_profile_for(character: str, display_name: str, cfg: dict[str, Any], env: dict[str, str]) -> dict[str, Any]:
    active_char = str(cfg.get("character") or "grumpy_shopkeeper")
    current_voice = str(cfg.get("elevenlabs_voice_id") or env.get("ELEVENLABS_VOICE_ID") or "")
    voice_for_this_character = current_voice if character == active_char else ""

    current_stt = str(cfg.get("stt_backend") or "whispercpp_vad")
    current_openai_model = str(cfg.get("openai_model") or "gpt-3.5-turbo")
    current_ollama_profile = str(cfg.get("ollama_model_profile") or cfg.get("ollama_profile") or "rpg")
    current_eleven_model = str(cfg.get("elevenlabs_model_id") or "eleven_flash_v2_5")
    current_eleven_format = str(cfg.get("elevenlabs_output_format") or "pcm_16000")
    current_eleven_language = cfg.get("elevenlabs_language_code") or ""

    free_tts = "borg" if character == "borg" else "piper_fast"
    thinking_name = "analysing.wav" if character == "borg" else "thinking.wav"

    return {
        "display_name": display_name,
        "media_dir": f"ui_media/characters/{character}",
        "thinking_sound": f"ui_media/characters/{character}/sounds/{thinking_name}",
        "pro": {
            "ai_backend": "openai",
            "openai_model": current_openai_model,
            "tts_backend": "elevenlabs",
            "elevenlabs_voice_id": voice_for_this_character,
            "elevenlabs_model_id": current_eleven_model,
            "elevenlabs_output_format": current_eleven_format,
            "elevenlabs_language_code": current_eleven_language,
            "stt_backend": current_stt,
        },
        "free": {
            "ai_backend": "ollama",
            "ollama_profile": current_ollama_profile,
            "ollama_model_profile": current_ollama_profile,
            "tts_backend": free_tts,
            "piper_fast_mode": str(cfg.get("piper_fast_mode") or "cli"),
            "stt_backend": current_stt,
        },
    }


def init_profiles(cfg: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    env = load_dotenv()
    changed: list[str] = []

    if not cfg.get("capohm_mode"):
        # If current config is already OpenAI+ElevenLabs, assume pro. Otherwise safe/free.
        if cfg.get("ai_backend") == "openai" or cfg.get("tts_backend") == "elevenlabs":
            cfg["capohm_mode"] = "pro"
        else:
            cfg["capohm_mode"] = "free"
        changed.append(f"set capohm_mode={cfg['capohm_mode']}")

    cfg.setdefault("_capohm_mode_options", ["free", "pro"])
    cfg.setdefault("_character_profile_version", 1)

    profiles = cfg.setdefault("character_profiles", {})
    active_char = str(cfg.get("character") or "grumpy_shopkeeper")
    characters = dict(DEFAULT_CHARACTERS)
    if active_char not in characters:
        characters[active_char] = active_char.replace("_", " ").title()

    for character, display_name in characters.items():
        if character not in profiles:
            profiles[character] = default_profile_for(character, display_name, cfg, env)
            changed.append(f"added profile {character}")
        else:
            # Non-destructive upgrades for older profile dicts.
            prof = profiles[character]
            prof.setdefault("display_name", display_name)
            prof.setdefault("media_dir", f"ui_media/characters/{character}")
            prof.setdefault("thinking_sound", f"ui_media/characters/{character}/sounds/thinking.wav")
            if "pro" not in prof:
                prof["pro"] = default_profile_for(character, display_name, cfg, env)["pro"]
                changed.append(f"added pro mode to {character}")
            if "free" not in prof:
                prof["free"] = default_profile_for(character, display_name, cfg, env)["free"]
                changed.append(f"added free mode to {character}")
        ensure_media_dirs(character)

    # Keep existing dropdown-ish option lists aware of new ideas, without breaking old UI.
    for key in ("_tts_options", "_backend_options"):
        if isinstance(cfg.get(key), list) and "elevenlabs" not in cfg[key]:
            cfg[key].append("elevenlabs")
            changed.append(f"added elevenlabs to {key}")
    if isinstance(cfg.get("ui options"), list) and "display" not in cfg["ui options"]:
        cfg["ui options"].append("display")
        changed.append("added display to ui options")

    return cfg, changed


def get_selected_profile(cfg: dict[str, Any]) -> dict[str, Any]:
    character = str(cfg.get("character") or "grumpy_shopkeeper")
    mode = str(cfg.get("capohm_mode") or "free")
    profiles = cfg.get("character_profiles") or {}
    if character not in profiles:
        raise SystemExit(f"No character profile for '{character}'. Run: python3 capohm_character_profiles.py init")
    if mode not in profiles[character]:
        raise SystemExit(f"Character '{character}' has no mode '{mode}'.")
    return profiles[character][mode]


def apply_selected_profile(cfg: dict[str, Any]) -> list[str]:
    selected = get_selected_profile(cfg)
    changed: list[str] = []
    for key in TOP_LEVEL_KEYS_TO_APPLY:
        if key in selected and selected[key] not in (None, ""):
            old = cfg.get(key)
            new = selected[key]
            if old != new:
                cfg[key] = new
                changed.append(f"{key}: {old!r} -> {new!r}")

    # UI/display should usually stay display for the project.
    if cfg.get("ui_backend") != "display":
        changed.append(f"ui_backend: {cfg.get('ui_backend')!r} -> 'display'")
        cfg["ui_backend"] = "display"
    return changed


def print_profiles(cfg: dict[str, Any]) -> None:
    mode = str(cfg.get("capohm_mode") or "free")
    active = str(cfg.get("character") or "")
    print(f"Current mode:      {mode}")
    print(f"Current character: {active}")
    print()
    profiles = cfg.get("character_profiles") or {}
    for name, prof in sorted(profiles.items()):
        marker = "*" if name == active else " "
        print(f"{marker} {name} — {prof.get('display_name', '')}")
        for m in ("pro", "free"):
            data = prof.get(m, {})
            voice = data.get("elevenlabs_voice_id", "")
            voice_short = (voice[:6] + "..." + voice[-4:]) if voice and len(voice) > 12 else voice
            bits = [
                f"AI={data.get('ai_backend')}",
                f"TTS={data.get('tts_backend')}",
                f"STT={data.get('stt_backend')}",
            ]
            if data.get("openai_model"):
                bits.append(f"OpenAI={data.get('openai_model')}")
            if data.get("ollama_profile"):
                bits.append(f"Ollama={data.get('ollama_profile')}")
            if voice_short:
                bits.append(f"Voice={voice_short}")
            print(f"    {m:<4} " + " | ".join(bits))
        print(f"    media: {prof.get('media_dir')}")
        print()


def cmd_init(args: argparse.Namespace) -> None:
    cfg = load_config()
    cfg, changed = init_profiles(cfg)
    if args.apply:
        changed.extend(apply_selected_profile(cfg))
    save_config(cfg, do_backup=True)
    print("Character profiles initialized.")
    if changed:
        print("Changes:")
        for item in changed:
            print(f"- {item}")
    else:
        print("No config changes needed. Directories were still checked.")


def cmd_apply(args: argparse.Namespace) -> None:
    cfg = load_config()
    cfg, changed = init_profiles(cfg)
    changed.extend(apply_selected_profile(cfg))
    save_config(cfg, do_backup=True)
    print("Applied selected character profile to top-level config.")
    for item in changed or ["No effective top-level changes."]:
        print(f"- {item}")


def cmd_list(args: argparse.Namespace) -> None:
    cfg = load_config()
    print_profiles(cfg)


def cmd_set_mode(args: argparse.Namespace) -> None:
    cfg = load_config()
    cfg, _ = init_profiles(cfg)
    mode = args.mode.lower().strip()
    if mode not in ("pro", "free"):
        raise SystemExit("Mode must be 'pro' or 'free'.")
    cfg["capohm_mode"] = mode
    changed = [f"capohm_mode set to {mode}"]
    if args.apply:
        changed.extend(apply_selected_profile(cfg))
    save_config(cfg, do_backup=True)
    for item in changed:
        print(f"- {item}")


def cmd_set_character(args: argparse.Namespace) -> None:
    cfg = load_config()
    cfg, _ = init_profiles(cfg)
    character = slugify(args.character)
    if character not in cfg.get("character_profiles", {}):
        raise SystemExit(f"Unknown character '{character}'. Add it first with add-character.")
    cfg["character"] = character
    changed = [f"character set to {character}"]
    if args.apply:
        changed.extend(apply_selected_profile(cfg))
    save_config(cfg, do_backup=True)
    for item in changed:
        print(f"- {item}")


def cmd_add_character(args: argparse.Namespace) -> None:
    cfg = load_config()
    cfg, _ = init_profiles(cfg)
    env = load_dotenv()
    character = slugify(args.character)
    display_name = args.display_name or character.replace("_", " ").title()
    profiles = cfg.setdefault("character_profiles", {})
    if character in profiles and not args.force:
        raise SystemExit(f"Character '{character}' already exists. Use --force to overwrite defaults, not recommended.")
    if args.copy_from and args.copy_from in profiles:
        profiles[character] = copy.deepcopy(profiles[args.copy_from])
        profiles[character]["display_name"] = display_name
        profiles[character]["media_dir"] = f"ui_media/characters/{character}"
        profiles[character]["thinking_sound"] = f"ui_media/characters/{character}/sounds/thinking.wav"
        # Clear copied ElevenLabs voice so accidental voice cloning by config does not happen.
        profiles[character].setdefault("pro", {})["elevenlabs_voice_id"] = ""
    else:
        profiles[character] = default_profile_for(character, display_name, cfg, env)
        profiles[character].setdefault("pro", {})["elevenlabs_voice_id"] = ""
    ensure_media_dirs(character)
    save_config(cfg, do_backup=True)
    print(f"Added character: {character} — {display_name}")
    print(f"Media folder: ui_media/characters/{character}/")


def cmd_set_voice(args: argparse.Namespace) -> None:
    cfg = load_config()
    cfg, _ = init_profiles(cfg)
    character = slugify(args.character)
    mode = args.mode.lower().strip()
    if mode not in ("pro", "free"):
        raise SystemExit("Mode must be 'pro' or 'free'.")
    profiles = cfg.get("character_profiles", {})
    if character not in profiles:
        raise SystemExit(f"Unknown character '{character}'.")
    profiles[character].setdefault(mode, {})["tts_backend"] = "elevenlabs"
    profiles[character][mode]["elevenlabs_voice_id"] = args.voice_id.strip()
    changed = [f"{character}.{mode}.elevenlabs_voice_id updated"]
    if args.apply and cfg.get("character") == character and cfg.get("capohm_mode") == mode:
        changed.extend(apply_selected_profile(cfg))
    save_config(cfg, do_backup=True)
    for item in changed:
        print(f"- {item}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage Capohm character Pro/Free profiles.")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="Initialize character_profiles and media directories.")
    p.add_argument("--apply", action="store_true", help="Also apply current character+mode to top-level config.")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("apply", help="Apply current character+mode to top-level config.")
    p.set_defaults(func=cmd_apply)

    p = sub.add_parser("list", help="List character profiles.")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("set-mode", help="Set capohm_mode.")
    p.add_argument("mode", choices=["pro", "free"])
    p.add_argument("--no-apply", dest="apply", action="store_false", help="Only set the mode; do not update top-level backend keys.")
    p.set_defaults(func=cmd_set_mode, apply=True)

    p = sub.add_parser("set-character", help="Set active character.")
    p.add_argument("character")
    p.add_argument("--no-apply", dest="apply", action="store_false", help="Only set character; do not update top-level backend keys.")
    p.set_defaults(func=cmd_set_character, apply=True)

    p = sub.add_parser("add-character", help="Add a new character profile and media folders.")
    p.add_argument("character", help="Internal name, e.g. old_wizard")
    p.add_argument("display_name", nargs="?", help="Pretty name, e.g. Old Wizard")
    p.add_argument("--copy-from", default="grumpy_shopkeeper", help="Copy defaults from an existing profile when possible.")
    p.add_argument("--force", action="store_true", help="Overwrite an existing character profile. Careful, Captain Chaos.")
    p.set_defaults(func=cmd_add_character)

    p = sub.add_parser("set-voice", help="Set ElevenLabs voice ID for a character mode.")
    p.add_argument("character")
    p.add_argument("voice_id")
    p.add_argument("--mode", choices=["pro", "free"], default="pro")
    p.add_argument("--apply", action="store_true", help="Apply immediately if this character/mode is active.")
    p.set_defaults(func=cmd_set_voice)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
