#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

CONFIG_PATH = Path("config.json")


def load_config():
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_config(config):
    with CONFIG_PATH.open("w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
        f.write("\n")


def main():
    parser = argparse.ArgumentParser(description="Switch Capohm Ollama model profile")
    parser.add_argument("profile", nargs="?", help="Profile name, e.g. tiny, small, rpg, vision")
    parser.add_argument("--list", action="store_true", help="List available profiles")
    args = parser.parse_args()

    config = load_config()
    profiles = config.get("ollama_model_profiles", {}) or {}

    if args.list or not args.profile:
        current = config.get("ollama_model_profile")
        print("Available Ollama profiles:")
        for name, profile in profiles.items():
            marker = "*" if name == current else " "
            label = profile.get("label", "")
            model = profile.get("model", "")
            print(f" {marker} {name:<8} {model:<18} {label}")
        if not args.profile:
            return

    requested = args.profile.strip().lower()
    if requested not in profiles:
        raise SystemExit(f"Unknown profile: {requested}. Use --list to see options.")

    config["ai_backend"] = "ollama"
    config["ollama_model_profile"] = requested
    config["ollama_model"] = profiles[requested].get("model", config.get("ollama_model"))
    save_config(config)

    print("Switched Ollama profile to:", requested)
    print("Model:", config["ollama_model"])


if __name__ == "__main__":
    main()
