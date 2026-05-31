General reminders:

cd ~/capohm                                     - start map
source .venv/bin/activate                       - source map
tail -100 capohm_errors.log                     - show logs
export OPENAI_API_KEY="ai key hier"             - api key importeren
python3 main_modular.py 2>capohm_errors.log     - run zonder log op scherm

# Capohm Modular Assistant

Capohm is a Raspberry Pi assistant with swappable modules for speech-to-text, text-to-speech, AI backends, UI, and character profiles.

## Current modular knobs

Edit `config.json`:

```json
{
  "tts_backend": "piper_fast",
  "stt_backend": "whispercpp_vad",
  "ai_backend": "ollama",
  "character": "grumpy_shopkeeper",
  "ollama_model_profile": "rpg"
}
```

## Backends

### TTS

Known options:

```json
"tts_backend": "espeak"
"tts_backend": "piper"
"tts_backend": "piper_fast"
"tts_backend": "borg"
```

`piper_fast` can run in CLI mode:

```json
"piper_fast_mode": "cli"
```

### STT

Known options:

```json
"stt_backend": "keyboard"
"stt_backend": "vosk"
"stt_backend": "whispercpp"
"stt_backend": "whispercpp_vad"
"stt_backend": "hybrid"
```

For portable voice mode, use:

```json
"stt_backend": "whispercpp_vad"
```

For testing without microphone:

```json
"stt_backend": "keyboard"
```

### AI

Known options:

```json
"ai_backend": "openai"
"ai_backend": "ollama"
"ai_backend": "echo"
```

For portable local AI:

```json
"ai_backend": "ollama"
```

## Ollama model profiles

Model profiles let you switch local models quickly without hunting through the config.

Apply the profile structure once:

```bash
python3 apply_ollama_model_profiles.py
```

List profiles:

```bash
python3 switch_ollama_profile.py --list
```

Switch profile:

```bash
python3 switch_ollama_profile.py tiny
python3 switch_ollama_profile.py small
python3 switch_ollama_profile.py rpg
python3 switch_ollama_profile.py vision
```

Default profiles:

| Profile | Model | Use |
| --- | --- | --- |
| `tiny` | `smollm2:135m` | Fastest portable mode |
| `small` | `qwen2.5:0.5b` | Small but better than tiny |
| `rpg` | `qwen2.5:1.5b` | Better roleplay/character mode |
| `vision` | `gemma3:4b` | Camera/image capable, slower |

Download models with Ollama before selecting them:

```bash
ollama pull smollm2:135m
ollama pull qwen2.5:0.5b
ollama pull qwen2.5:1.5b
ollama pull gemma3:4b
```

## Character profiles

Character files live in:

```text
characters/
```

Known examples:

```json
"character": "borg"
"character": "natural"
"character": "grumpy_shopkeeper"
```

Voice commands supported by the assistant include:

```text
list characters
current character
switch character to borg
switch character to natural
switch character to grumpy
```

## Echo guard

Capohm uses echo suppression so the microphone does not feed TTS output back into the AI.

Hard guard:

```text
Temporarily allows only stop/barge-in commands right after TTS.
```

Soft guard:

```text
After the hard guard, compares heard text to recent TTS output and ignores probable echoes.
```

Useful config:

```json
"echo_hard_guard_enabled": true,
"echo_base_cooldown_seconds": 0.55,
"echo_seconds_per_word": 0.08,
"echo_max_cooldown_seconds": 8.0,
"echo_tts_speed_factors": {
  "espeak": 1.0,
  "piper": 3.15,
  "piper_fast": 2.4,
  "borg": 3.5
}
```

If a voice still hears itself, raise its factor. If Capohm ignores real speech for too long, lower its factor.

## Run

```bash
cd ~/capohm
source .venv/bin/activate
python3 main_modular.py 2>capohm_errors.log
```

Useful tests:

```bash
python3 main_modular.py --test tts
python3 main_modular.py --test stt
python3 main_modular.py --test ai
```

## Git workflow

Check changes:

```bash
git status
git diff --cached --name-only
```

Commit current stable work:

```bash
git add main_modular.py config.json backends/ characters/ README.md
git commit -m "Update modular assistant configuration"
git push
```

Avoid committing local secrets or logs:

```text
.env
capohm_errors.log
*_before_*.py
*_before_*.json
*.zip
```
