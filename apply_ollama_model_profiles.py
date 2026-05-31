#!/usr/bin/env python3
import json
from pathlib import Path

CONFIG_PATH = Path("config.json")

profiles = {
    "tiny": {
        "label": "SmolLM2 135M - fastest portable mode",
        "model": "smollm2:135m",
        "num_predict": 60,
        "num_ctx": 1024,
        "temperature": 0.4,
        "keep_alive": "30m"
    },
    "small": {
        "label": "Qwen2.5 0.5B - small but less stupid",
        "model": "qwen2.5:0.5b",
        "num_predict": 80,
        "num_ctx": 1024,
        "temperature": 0.5,
        "keep_alive": "30m"
    },
    "rpg": {
        "label": "Qwen2.5 1.5B - better character/RPG mode",
        "model": "qwen2.5:1.5b",
        "num_predict": 110,
        "num_ctx": 1536,
        "temperature": 0.65,
        "keep_alive": "30m"
    },
    "vision": {
        "label": "Gemma3 4B - vision capable, slower",
        "model": "gemma3:4b",
        "num_predict": 120,
        "num_ctx": 2048,
        "temperature": 0.55,
        "keep_alive": "20m"
    }
}

with CONFIG_PATH.open("r", encoding="utf-8") as f:
    config = json.load(f)

config["_ai_options"] = "openai, echo, ollama"
config["_ollama_model_profile_options"] = ", ".join(profiles.keys())
config.setdefault("ai_backend", "ollama")
config.setdefault("ollama_base_url", "http://localhost:11434/v1")
config.setdefault("ollama_model_profile", "rpg")
config["ollama_model_profiles"] = profiles

# Keep ollama_model in sync with the selected profile for readability.
selected = config.get("ollama_model_profile", "rpg")
if selected in profiles:
    config["ollama_model"] = profiles[selected]["model"]

with CONFIG_PATH.open("w", encoding="utf-8") as f:
    json.dump(config, f, indent=2)
    f.write("\n")

print("Added Ollama model profiles.")
print("Selected profile:", config.get("ollama_model_profile"))
print("Selected model:", config.get("ollama_model"))
