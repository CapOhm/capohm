import argparse
import importlib
import json
import random
import re
import time
from difflib import SequenceMatcher
from pathlib import Path

from core.wake import is_sleep_command, is_wake_word

CONFIG_FILE = "config.json"


def load_config(path: str = CONFIG_FILE) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        config = json.load(f)
    config["_config_path"] = path
    return config


def save_config(config: dict) -> None:
    """Persist safe runtime settings such as selected character."""
    path = config.get("_config_path", CONFIG_FILE)
    data = {k: v for k, v in config.items() if not k.startswith("_runtime_") and k != "_config_path"}

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")



PROFILE_APPLY_KEYS = [
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
    "tts_volume_db",
    "elevenlabs_volume_db",
]

PROFILE_GUARD_KEYS = [
    "ignore_stt_while_speaking",
    "active_tts_only_barge_in",
    "echo_hard_guard_enabled",
    "echo_base_cooldown_seconds",
    "echo_seconds_per_word",
    "echo_max_cooldown_seconds",
    "echo_hard_guard_min_seconds",
    "echo_hard_guard_max_seconds",
    "echo_hard_guard_fraction",
    "echo_suppression_enabled",
    "echo_memory_seconds",
    "echo_similarity_threshold",
    "echo_word_overlap_threshold",
    "echo_short_similarity_threshold",
    "echo_min_words",
    "show_ignored_stt",
    "display_show_raw_stt",
    "display_show_accepted_heard",
]


def apply_selected_character_profile_runtime(config: dict) -> list[str]:
    """Apply current character+pro/free profile onto legacy top-level keys.

    This lets the existing backends keep working while character_profiles becomes
    the central source of truth.
    """
    changed: list[str] = []
    character = str(config.get("character") or "").strip()
    mode = str(config.get("capohm_mode") or "free").strip().lower()
    if mode not in ("pro", "free"):
        mode = "free"
        config["capohm_mode"] = mode
    profiles = config.get("character_profiles") or {}
    profile = profiles.get(character) if isinstance(profiles, dict) else None
    if not isinstance(profile, dict):
        return changed

    mode_settings = profile.get(mode) if isinstance(profile.get(mode), dict) else {}
    for key in PROFILE_APPLY_KEYS:
        if key in mode_settings and mode_settings.get(key) not in (None, ""):
            old = config.get(key)
            new = mode_settings.get(key)
            if old != new:
                config[key] = new
                changed.append(f"{key} -> {new}")
    # CAPOHM VOLUME MIRROR
    if config.get("tts_volume_db") not in (None, "") and config.get("elevenlabs_volume_db") in (None, ""):
        config["elevenlabs_volume_db"] = config.get("tts_volume_db")
    if config.get("tts_volume_db") not in (None, ""):
        # For ElevenLabs, use the general TTS volume unless a mode explicitly set elevenlabs_volume_db.
        if "elevenlabs_volume_db" not in mode_settings or mode_settings.get("elevenlabs_volume_db") in (None, ""):
            config["elevenlabs_volume_db"] = config.get("tts_volume_db")

    # Keep these two Ollama profile names mirrored for older/newer code.
    if config.get("ollama_profile") and not config.get("ollama_model_profile"):
        config["ollama_model_profile"] = config["ollama_profile"]
    if config.get("ollama_model_profile") and not config.get("ollama_profile"):
        config["ollama_profile"] = config["ollama_model_profile"]

    if profile.get("ai_history_messages") not in (None, ""):
        try:
            new_history = int(float(profile.get("ai_history_messages")))
            if config.get("ai_history_messages") != new_history:
                config["ai_history_messages"] = new_history
                changed.append(f"ai_history_messages -> {new_history}")
        except Exception:
            pass

    guards = profile.get("guards") if isinstance(profile.get("guards"), dict) else {}
    for key in PROFILE_GUARD_KEYS:
        if key in guards and guards.get(key) is not None:
            old = config.get(key)
            new = guards.get(key)
            if old != new:
                config[key] = new
                changed.append(f"{key} -> {new}")
    return changed


def load_backend(kind: str, name: str, class_name: str):
    module = importlib.import_module(f"backends.{kind}_{name}")
    return getattr(module, class_name)


def default_character() -> dict:
    return {
        "name": "borg",
        "display_name": "Borg Hive",
        "aliases": ["borg", "hive"],
        "system_prompt": (
            "You are the Borg Hive. You are precise, efficient, and serve Terry. "
            "Keep replies short and useful. Do not give long theatrical monologues. "
            "Use the Borg flavor lightly. Do not overuse 'resistance is futile'."
        ),
        "wake_responses": ["Hive online.", "We are awake.", "Input required."],
        "sleep_responses": ["Hive disengaging.", "Low power mode.", "Silence restored."],
        "switch_response": "Character profile loaded: Borg Hive."
    }


def characters_dir(config: dict) -> Path:
    return Path(config.get("characters_dir", "characters"))


def load_character(config: dict, character_name: str | None = None) -> dict:
    name = character_name or config.get("character", "borg")
    path = characters_dir(config) / f"{name}.json"

    if not path.exists():
        return default_character()

    try:
        with open(path, "r", encoding="utf-8") as f:
            character = json.load(f)
    except Exception:
        return default_character()

    fallback = default_character()
    for key, value in fallback.items():
        character.setdefault(key, value)

    return character


def load_all_characters(config: dict) -> list[tuple[str, dict]]:
    cdir = characters_dir(config)
    chars = []

    if cdir.exists():
        for path in sorted(cdir.glob("*.json")):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    char = json.load(f)
                char.setdefault("name", path.stem)
                char.setdefault("display_name", char["name"])
                char.setdefault("aliases", [])
                chars.append((path.stem, char))
            except Exception:
                pass

    if not chars:
        chars.append(("borg", default_character()))

    return chars


def find_character(config: dict, requested: str) -> tuple[str, dict] | None:
    requested = requested.lower().strip(" .!?:;")
    if not requested:
        return None

    for filename, char in load_all_characters(config):
        names = [
            filename,
            char.get("name", ""),
            char.get("display_name", ""),
            *char.get("aliases", []),
        ]

        for name in names:
            clean = str(name).lower().strip()
            if not clean:
                continue
            if requested == clean or clean in requested or requested in clean:
                return filename, char

    return None


def parse_character_command(text: str) -> tuple[str | None, str | None]:
    """Return (action, value). Actions: list, who, switch."""
    lower = text.lower().strip(" .!?:;")

    if lower in [
        "list characters",
        "list character",
        "lists characters",
        "list personalities",
        "show characters",
        "show personalities",
        "characters",
        "personalities",
    ]:
        return "list", None

    if lower in [
        "who are you",
        "what character are you",
        "which character are you",
        "current character",
        "current personality",
    ]:
        return "who", None

    prefixes = [
        "switch character to",
        "change character to",
        "set character to",
        "use character",
        "switch personality to",
        "change personality to",
        "set personality to",
        "use personality",
        "become",
        "be",
    ]

    for prefix in prefixes:
        if lower.startswith(prefix + " "):
            return "switch", lower[len(prefix):].strip()

    # Short convenience commands, useful when Vosk butchers longer sentences.
    suffixes = ["mode", "character", "personality"]
    for suffix in suffixes:
        if lower.endswith(" " + suffix):
            return "switch", lower[: -len(suffix)].strip()

    return None, None


def build_system_prompt(character: dict) -> str:
    return character.get("system_prompt", default_character()["system_prompt"])


def tts_is_speaking(tts) -> bool:
    """Return True if the selected TTS backend is currently generating or playing speech."""
    is_speaking = getattr(tts, "is_speaking", None)
    if callable(is_speaking):
        try:
            return bool(is_speaking())
        except Exception:
            return False
    return False


def is_barge_in_command(text: str, config: dict) -> bool:
    """Commands that are allowed through while TTS is talking."""
    lower = text.lower().strip()
    commands = config.get(
        "barge_in_commands",
        ["stop", "cancel", "enough", "genoeg", "hou op", "stil"],
    )
    return any(command.lower() in lower for command in commands)






# Capohm patched: browser guard indicator helpers.
# hard = temporary deaf window after/around TTS.
# soft = echo memory/similarity filter window after TTS.
import threading as _capohm_guard_threading
import time as _capohm_guard_time
_capohm_guard_seq = {"hard": 0, "soft": 0}
_capohm_guard_lock = _capohm_guard_threading.Lock()


def capohm_guard_status(hard=None, soft=None):
    try:
        from ui_bus import ui_guard_status
        ui_guard_status(hard=hard, soft=soft)
    except Exception:
        pass


def capohm_guard_hard_until(until_ts):
    try:
        until = float(until_ts or 0)
    except Exception:
        capohm_guard_status(hard=False)
        return
    remaining = max(0.0, until - _capohm_guard_time.time())
    with _capohm_guard_lock:
        _capohm_guard_seq["hard"] += 1
        seq = _capohm_guard_seq["hard"]
    if remaining <= 0.02:
        capohm_guard_status(hard=False)
        return
    capohm_guard_status(hard=True)

    def _expire():
        _capohm_guard_time.sleep(remaining)
        with _capohm_guard_lock:
            if _capohm_guard_seq.get("hard") != seq:
                return
        capohm_guard_status(hard=False)

    _capohm_guard_threading.Thread(target=_expire, daemon=True).start()


    try:
        if not bool(config.get("echo_suppression_enabled", True)):
            capohm_guard_status(soft=False)
            return
        duration = float(config.get("echo_memory_seconds", 35.0) or 0)
    except Exception:
        duration = 35.0
    with _capohm_guard_lock:
        _capohm_guard_seq["soft"] += 1
        seq = _capohm_guard_seq["soft"]
    if duration <= 0.02:
        capohm_guard_status(soft=False)
        return
    capohm_guard_status(soft=True)

    def _expire():
        _capohm_guard_time.sleep(duration)
        with _capohm_guard_lock:
            if _capohm_guard_seq.get("soft") != seq:
                return
        capohm_guard_status(soft=False)

    _capohm_guard_threading.Thread(target=_expire, daemon=True).start()


def is_stop_speaking_command(text: str, config: dict) -> bool:
    """Commands that mean: stop the current spoken audio, do not ask the AI."""
    lower = text.lower().strip(" .!?:;")
    commands = config.get(
        "stop_speaking_commands",
        ["stop", "cancel", "enough", "genoeg", "hou op", "stil", "stop talking", "stop speaking", "be quiet", "shut up", "silence"],
    )
    for command in commands:
        cmd = str(command).lower().strip(" .!?:;")
        if not cmd:
            continue
        if lower == cmd or lower.startswith(cmd + " ") or cmd in lower:
            return True
    return False


def normalize_for_echo(text: str) -> str:
    """Normalize text so STT variants of the same TTS sentence still compare well."""
    text = text.lower()
    text = re.sub(r"[^a-z0-9'\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def echo_words(text: str) -> list[str]:
    return [word for word in normalize_for_echo(text).split() if word]


def word_overlap_ratio(candidate: str, reference: str) -> float:
    candidate_words = echo_words(candidate)
    reference_words = set(echo_words(reference))

    if not candidate_words or not reference_words:
        return 0.0

    matches = sum(1 for word in candidate_words if word in reference_words)
    return matches / max(1, len(candidate_words))


def text_similarity_ratio(candidate: str, reference: str) -> float:
    candidate_norm = normalize_for_echo(candidate)
    reference_norm = normalize_for_echo(reference)

    if not candidate_norm or not reference_norm:
        return 0.0

    return SequenceMatcher(None, candidate_norm, reference_norm).ratio()


def count_words(text: str) -> int:
    return len(echo_words(text))


def get_tts_echo_speed_factor(config: dict) -> float:
    """Per-TTS multiplier for dynamic echo cooldown.

    Higher = longer echo guard. Use this for slower voices.
    Lower = shorter echo guard. Useful for fast espeak tests.
    """
    override = config.get("echo_tts_speed_factor", None)
    if override is not None:
        try:
            return float(override)
        except (TypeError, ValueError):
            pass

    backend = config.get("tts_backend", "")
    factors = config.get("echo_tts_speed_factors", {})
    try:
        return float(factors.get(backend, 1.0))
    except (TypeError, ValueError):
        return 1.0


def dynamic_echo_cooldown(text: str, config: dict) -> float:
    base = float(config.get("echo_base_cooldown_seconds", 0.6))
    seconds_per_word = float(config.get("echo_seconds_per_word", 0.08))
    max_seconds = float(config.get("echo_max_cooldown_seconds", 8.0))
    min_seconds = float(config.get("speech_cooldown_seconds", 0.25))
    factor = get_tts_echo_speed_factor(config)

    seconds = base + (count_words(text) * seconds_per_word * factor)
    seconds = max(min_seconds, seconds)
    return min(max_seconds, seconds)


def dynamic_hard_echo_guard(text: str, config: dict) -> float:
    """Return a stopword-only mute window after TTS starts.

    This is intentionally stronger than similarity matching. It is useful when
    Whisper/VAD returns speaker echo with altered words, e.g.
    "Our presence has been felt" -> "Our presence has been vaulted".
    """
    if not config.get("echo_hard_guard_enabled", True):
        return 0.0

    base_cooldown = dynamic_echo_cooldown(text, config)
    fraction = float(config.get("echo_hard_guard_fraction", 1.0))
    min_seconds = float(config.get("echo_hard_guard_min_seconds", 1.4))
    max_seconds = float(config.get("echo_hard_guard_max_seconds", config.get("echo_max_cooldown_seconds", 8.0)))

    seconds = base_cooldown * fraction
    seconds = max(min_seconds, seconds)
    return min(max_seconds, seconds)


def keyboard_only_stt(config: dict) -> bool:
    return str(config.get("stt_backend", "")).lower().strip() == "keyboard"


def looks_like_recent_tts_echo(text: str, recent_tts_texts: list[dict], config: dict):
    """Return (True, reason) if STT text is probably the assistant hearing itself."""
    if not config.get("echo_suppression_enabled", True):
        return False, ""

    candidate_words = count_words(text)
    min_words = int(config.get("echo_min_words", 2))
    now = time.time()

    if candidate_words < min_words:
        return False, ""

    similarity_threshold = float(config.get("echo_similarity_threshold", 0.58))
    overlap_threshold = float(config.get("echo_word_overlap_threshold", 0.65))
    short_similarity_threshold = float(config.get("echo_short_similarity_threshold", 0.86))

    best_reason = ""
    best_score = 0.0

    for entry in list(recent_tts_texts):
        if now > entry.get("expires_at", 0):
            continue

        spoken = entry.get("text", "")
        similarity = text_similarity_ratio(text, spoken)
        overlap = word_overlap_ratio(text, spoken)
        score = max(similarity, overlap)

        if score > best_score:
            best_score = score
            best_reason = f"similarity={similarity:.2f}, overlap={overlap:.2f}"

        # Short phrases need stricter matching, otherwise normal answers like
        # "what time" could get swallowed too easily.
        if candidate_words <= 3:
            if similarity >= short_similarity_threshold or overlap >= 0.95:
                return True, best_reason
        else:
            if similarity >= similarity_threshold or overlap >= overlap_threshold:
                return True, best_reason

    return False, best_reason


def test_tts(tts):
    tts.speak("The modular hive voice interface is online.")
    time.sleep(8)


def test_ai(ai, character):
    messages = [
        {"role": "system", "content": build_system_prompt(character)},
        {"role": "user", "content": "Say one short sentence confirming you are online."},
    ]
    print(ai.reply(messages))


def test_stt(stt, timeout=15):
    print("Say something. Waiting up to 15 seconds...")
    stt.start()
    start = time.time()
    while time.time() - start < timeout:
        text = stt.listen()
        if text:
            print("Recognized:", text)
            return
        time.sleep(0.2)
    print("No speech recognized.")




def character_response(character: dict, key: str, fallback=None, default: str = "Ready.") -> str:
    """Pick a response from the active character first, then fallback config.

    This prevents a bartender/shopkeeper from using Borg/Hive lifecycle lines.
    """
    values = character.get(key) if isinstance(character, dict) else None
    if isinstance(values, str) and values.strip():
        return values.strip()
    if isinstance(values, list):
        clean = [str(v).strip() for v in values if str(v).strip()]
        if clean:
            return random.choice(clean)

    if isinstance(fallback, str) and fallback.strip():
        return fallback.strip()
    if isinstance(fallback, list):
        clean = [str(v).strip() for v in fallback if str(v).strip()]
        if clean:
            return random.choice(clean)
    return default

def run_assistant(config: dict):
    apply_selected_character_profile_runtime(config)
    UI = load_backend("ui", config["ui_backend"], "UI")
    TTS = load_backend("tts", config["tts_backend"], "TTS")
    STT = load_backend("stt", config["stt_backend"], "STT")
    AI = load_backend("ai", config["ai_backend"], "AI")
    ui = UI(config)
    tts = TTS(config)
    stt = STT(config, ui=ui)
    ai = AI(config)

    current_character = load_character(config)

    ignore_while_speaking = config.get("ignore_stt_while_speaking", True)
    speech_cooldown_seconds = float(config.get("speech_cooldown_seconds", 0.25))
    show_ignored_stt = config.get("show_ignored_stt", False)
    echo_memory_seconds = float(config.get("echo_memory_seconds", 25.0))
    recent_tts_texts = []
    ignore_until = 0.0
    hard_guard_until = 0.0
    capohm_guard_hard_until(hard_guard_until)

    def remember_tts_echo(text: str) -> float:
        """Remember spoken text and return the dynamic cooldown window."""
        if not config.get("echo_suppression_enabled", True):
            return speech_cooldown_seconds

        now = time.time()
        cooldown = dynamic_echo_cooldown(text, config)

        recent_tts_texts[:] = [
            entry for entry in recent_tts_texts
            if now <= entry.get("expires_at", 0)
        ]
        recent_tts_texts.append({
            "text": text,
            "expires_at": now + echo_memory_seconds,
            "cooldown_until": now + cooldown,
        })
        return cooldown

    def show_accepted_heard(text: str) -> None:
        """Send only guard-approved input to the UI HEARD panel."""
        if not config.get("display_show_accepted_heard", True):
            return
        try:
            ui.heard(text)
        except Exception:
            pass

    def speak(text: str) -> None:
        nonlocal ignore_until, hard_guard_until
        tts.speak(text)
        cooldown = remember_tts_echo(text)
        ignore_until = time.time() + cooldown

        hard_guard_seconds = dynamic_hard_echo_guard(text, config)
        hard_guard_until = time.time() + hard_guard_seconds
        capohm_guard_hard_until(hard_guard_until)

        if show_ignored_stt and config.get("echo_debug_timing", False):
            ui.log(
                f"Echo guard: soft={cooldown:.2f}s hard={hard_guard_seconds:.2f}s "
                f"words={count_words(text)} tts={config.get('tts_backend')}"
            )

    def character_wake_responses() -> list[str]:
        return current_character.get("wake_responses") or config.get("wake_responses", ["Online."])

    def character_sleep_responses() -> list[str]:
        return current_character.get("sleep_responses") or config.get("sleep_responses", ["Sleeping."])

    def switch_character(requested: str) -> tuple[bool, str]:
        nonlocal current_character, tts, ai, messages
        found = find_character(config, requested)
        if not found:
            names = ", ".join(char.get("display_name", name) for name, char in load_all_characters(config))
            return False, f"Character not found. Available characters: {names}."

        filename, char = found
        old_tts_signature = (
            config.get("tts_backend"),
            config.get("elevenlabs_voice_id"),
            config.get("elevenlabs_model_id"),
            config.get("elevenlabs_output_format"),
            config.get("elevenlabs_language_code"),
            config.get("tts_volume_db"),
            config.get("elevenlabs_volume_db"),
        )
        old_ai_signature = (
            config.get("ai_backend"),
            config.get("openai_model"),
            config.get("ollama_profile"),
            config.get("ollama_model_profile"),
            config.get("ollama_model"),
        )

        current_character = char
        config["character"] = filename
        applied = apply_selected_character_profile_runtime(config)

        new_tts_signature = (
            config.get("tts_backend"),
            config.get("elevenlabs_voice_id"),
            config.get("elevenlabs_model_id"),
            config.get("elevenlabs_output_format"),
            config.get("elevenlabs_language_code"),
            config.get("tts_volume_db"),
            config.get("elevenlabs_volume_db"),
        )
        new_ai_signature = (
            config.get("ai_backend"),
            config.get("openai_model"),
            config.get("ollama_profile"),
            config.get("ollama_model_profile"),
            config.get("ollama_model"),
        )

        if new_tts_signature != old_tts_signature:
            try:
                try:
                    tts.stop()
                except Exception:
                    pass
                NewTTS = load_backend("tts", config["tts_backend"], "TTS")
                tts = NewTTS(config)
                if show_ignored_stt:
                    ui.log(f"TTS reloaded for character {filename}: {config.get('tts_backend')}")
            except Exception as exc:
                ui.error(f"Failed to reload TTS for character {filename}: {exc}")

        if new_ai_signature != old_ai_signature:
            try:
                NewAI = load_backend("ai", config["ai_backend"], "AI")
                ai = NewAI(config)
                if show_ignored_stt:
                    ui.log(f"AI reloaded for character {filename}: {config.get('ai_backend')}")
            except Exception as exc:
                ui.error(f"Failed to reload AI for character {filename}: {exc}")

        messages = []  # prevent previous character from bleeding into the new one
        save_config(config)
        response = character_response(char, "switch_response", default=f"Character switched to {char.get('display_name', filename)}.")
        return True, response

    ui.start()
    stt.start()
    is_awake = False
    messages = []
    ui.status("ASLEEP")
    ui.log(f"Character: {current_character.get('display_name', current_character.get('name', 'unknown'))}")

    while True:
        user_input = stt.listen()
        if not user_input:
            time.sleep(0.1)
            continue

        lower = user_input.lower().strip()

        # Capohm patched: hard stop speaking command.
        # This must happen before echo guards, sleep/wake logic, and AI routing.
        if is_stop_speaking_command(user_input, config):
            try:
                tts.stop()
            except Exception as exc:
                try:
                    ui.error(f"TTS stop failed: {exc}")
                except Exception:
                    pass
            ignore_until = time.time() + speech_cooldown_seconds
            hard_guard_until = time.time() + 0.1
            capohm_guard_hard_until(hard_guard_until)
            try:
                recent_tts_texts.clear()
            except Exception:
                pass
            try:
                ui.log("Speech stopped.")
            except Exception:
                pass
            # Do not speak a confirmation by default; speaking "stopped" is not stopping.
            if not bool(config.get("stop_command_silent", True)):
                try:
                    ui.assistant("Stopped.")
                except Exception:
                    pass
            continue

        if lower in ["exit", "quit"]:
            ui.log("Exiting.")
            break

        if is_barge_in_command(user_input, config):
            show_accepted_heard(user_input)
            tts.stop()
            ignore_until = time.time() + speech_cooldown_seconds
            hard_guard_until = time.time() + 0.1
            capohm_guard_hard_until(hard_guard_until)
            ui.log("Speech interrupted.")
            continue

        is_speaking_now = tts_is_speaking(tts)
        in_dynamic_cooldown = time.time() < ignore_until
        in_hard_echo_guard = time.time() < hard_guard_until

        looks_echo, echo_reason = looks_like_recent_tts_echo(user_input, recent_tts_texts, config)

        # While the TTS backend is actively speaking, only barge-in commands are allowed.
        # During the post-speech cooldown, do NOT blindly swallow everything; only ignore
        # text that actually resembles the recent TTS output. This keeps new questions
        # like "what is 2+2" from getting eaten by the echo guard. Tiny mercy.
        if ignore_while_speaking and is_speaking_now:
            if looks_echo:
                if show_ignored_stt:
                    ui.log(f"Ignored active TTS echo ({echo_reason}): {user_input}")
                continue

            if config.get("active_tts_only_barge_in", True):
                if show_ignored_stt:
                    ui.log(f"Ignored while TTS is speaking: {user_input}")
                continue

        # After TTS starts, keep the microphone in stopword-only mode for a
        # dynamic period based on the number of spoken words and the selected
        # TTS speed factor. This catches Whisper speaker-echo that is too
        # mutated for similarity matching. Keyboard-only mode is exempt so
        # typed tests stay responsive.
        if (
            ignore_while_speaking
            and in_hard_echo_guard
            and config.get("echo_hard_guard_enabled", True)
            and not keyboard_only_stt(config)
        ):
            if show_ignored_stt:
                ui.log(f"Ignored during hard TTS echo guard: {user_input}")
            continue

        if ignore_while_speaking and in_dynamic_cooldown and looks_echo:
            if show_ignored_stt:
                ui.log(f"Ignored probable TTS echo ({echo_reason}): {user_input}")
            continue

        if lower in ["stop", "cancel"]:
            show_accepted_heard(user_input)
            tts.stop()
            speak("Stopped.")
            continue

        action, value = parse_character_command(user_input)
        if action == "list":
            show_accepted_heard(user_input)
            names = ", ".join(char.get("display_name", name) for name, char in load_all_characters(config))
            reply = f"Available characters: {names}."
            ui.assistant(reply)
            speak(reply)
            continue

        if action == "who":
            show_accepted_heard(user_input)
            reply = f"Current character: {current_character.get('display_name', current_character.get('name', 'unknown'))}."
            ui.assistant(reply)
            speak(reply)
            continue

        if action == "switch" and value:
            show_accepted_heard(user_input)
            ok, reply = switch_character(value)
            messages = []  # prevent the previous character from bleeding into the new one
            ui.assistant(reply)
            speak(reply)
            continue

        if not is_awake:
            if is_wake_word(user_input, config):
                show_accepted_heard(user_input)
                is_awake = True
                ui.status("AWAKE")
                reply = random.choice(character_wake_responses())
                ui.assistant(reply)
                speak(reply)
            else:
                ui.sleep_note("Still asleep. Say 'buddy' or 'hey hive' to wake.")
            continue

        if is_sleep_command(user_input, config):
            show_accepted_heard(user_input)
            is_awake = False
            ui.status("ASLEEP")
            reply = random.choice(character_sleep_responses())
            ui.assistant(reply)
            speak(reply)
            continue

        show_accepted_heard(user_input)
        history_limit = int(config.get("ai_history_messages", 6))
        messages = [{"role": "system", "content": build_system_prompt(current_character)}] + messages[-history_limit:]
        messages.append({"role": "user", "content": user_input})

        try:
            reply = ai.reply(messages)
            messages.append({"role": "assistant", "content": reply})
            ui.assistant(reply)
            speak(reply)
        except Exception as e:
            ui.error(f"AI error: {e}")
            speak("There was an AI error. Check the log.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=CONFIG_FILE)
    parser.add_argument("--test", choices=["tts", "stt", "ai", "all"])
    args = parser.parse_args()
    config = load_config(args.config)

    if args.test:
        UI = load_backend("ui", config["ui_backend"], "UI")
        ui = UI(config)
        ui.start()
        character = load_character(config)

        if args.test in ["tts", "all"]:
            TTS = load_backend("tts", config["tts_backend"], "TTS")
            test_tts(TTS(config))

        if args.test in ["ai", "all"]:
            AI = load_backend("ai", config["ai_backend"], "AI")
            test_ai(AI(config), character)

        if args.test in ["stt", "all"]:
            STT = load_backend("stt", config["stt_backend"], "STT")
            test_stt(STT(config, ui=ui))

        return

    run_assistant(config)


if __name__ == "__main__":
    main()
