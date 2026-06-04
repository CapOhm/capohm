#!/usr/bin/env python3
"""
Capohm Control Panel - Character Editor + Guards + Sync Edition

Zero-dependency web control panel for:
- starting/stopping main_modular.py
- Pro/Free mode switching
- active character switching
- adding/editing character profiles
- per-character Pro/Free AI/TTS/STT settings
- per-character ElevenLabs voice IDs
- per-character memory/mood fields
- automatic sync to characters/*.json
- basic config fields + raw config view

Run from ~/capohm:
    python3 capohm_control_panel.py --config config.json --host 0.0.0.0 --port 8765
"""

from __future__ import annotations

import argparse
import copy
import datetime as _dt
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

EMOTIONS = [
    "neutral", "listening", "thinking", "happy", "amused", "angry",
    "sad", "confused", "surprised", "alert", "error", "sleep",
]

DEFAULT_CHARACTERS = {
    "grumpy_shopkeeper": "Grumpy Shopkeeper",
    "borg": "Borg Hive",
    "natural": "Natural Assistant",
}

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
    "borg_volume_db",
    "elevenlabs_volume_db",
    "tts_volume_db",
]

SAFE_DEFAULTS: dict[str, Any] = {
    "whispercpp_vad_rms_threshold": 450,
    "whispercpp_vad_silence_seconds": 0.75,
    "whispercpp_vad_min_speech_seconds": 0.45,
    "whispercpp_vad_max_speech_seconds": 10.0,
    "whispercpp_vad_preroll_seconds": 0.35,
    "whispercpp_input_sample_rate": 48000,
    "whispercpp_recognition_sample_rate": 16000,
}


CHARACTER_GUARD_FIELDS: list[dict[str, Any]] = [
    {"key": "ignore_stt_while_speaking", "label": "Ignore STT while speaking", "type": "bool", "default": True, "help": "Hard guard: do not accept normal STT while TTS is active."},
    {"key": "active_tts_only_barge_in", "label": "Only barge-in during TTS", "type": "bool", "default": True, "help": "During speaking, only stop/cancel style commands should get through."},
    {"key": "echo_hard_guard_enabled", "label": "Hard guard enabled", "type": "bool", "default": True, "help": "Temporary deaf period after TTS to block speaker-to-mic echo."},
    {"key": "echo_base_cooldown_seconds", "label": "Hard base cooldown", "type": "float", "default": 1.0, "help": "Seconds of base deaf time after speaking."},
    {"key": "echo_seconds_per_word", "label": "Hard seconds per word", "type": "float", "default": 0.14, "help": "Adds cooldown based on spoken answer length."},
    {"key": "echo_max_cooldown_seconds", "label": "Hard max cooldown", "type": "float", "default": 12.0, "help": "Maximum hard guard deaf time."},
    {"key": "echo_hard_guard_min_seconds", "label": "Hard min seconds", "type": "float", "default": 0.6, "help": "Minimum hard guard time if supported by current bot code."},
    {"key": "echo_hard_guard_max_seconds", "label": "Hard absolute max", "type": "float", "default": 12.0, "help": "Absolute max hard guard time if supported by current bot code."},
    {"key": "echo_hard_guard_fraction", "label": "Hard guard fraction", "type": "float", "default": 1.0, "help": "Multiplier/fraction for hard guard if supported by current bot code."},
    {"key": "echo_suppression_enabled", "label": "Soft guard enabled", "type": "bool", "default": True, "help": "Soft guard compares heard text to recent TTS and suppresses echoes."},
    {"key": "echo_memory_seconds", "label": "Soft memory seconds", "type": "float", "default": 35.0, "help": "How long recent TTS is remembered for echo matching."},
    {"key": "echo_similarity_threshold", "label": "Soft similarity threshold", "type": "float", "default": 0.42, "help": "Lower = blocks more possible echo; higher = lets more through."},
    {"key": "echo_word_overlap_threshold", "label": "Soft word overlap", "type": "float", "default": 0.42, "help": "Overlap threshold for echo words."},
    {"key": "echo_short_similarity_threshold", "label": "Short phrase threshold", "type": "float", "default": 0.55, "help": "Threshold for short heard phrases."},
    {"key": "echo_min_words", "label": "Echo min words", "type": "int", "default": 2, "help": "Minimum words before soft echo logic gets aggressive."},
    {"key": "show_ignored_stt", "label": "Show ignored STT", "type": "bool", "default": False, "help": "Debug only. Usually off, otherwise the display gets noisy."},
    {"key": "display_show_raw_stt", "label": "Display raw STT", "type": "bool", "default": False, "help": "Debug only. False = only accepted heard text is displayed."},
    {"key": "display_show_accepted_heard", "label": "Display accepted heard", "type": "bool", "default": True, "help": "Show only text that actually reaches the bot."},
    {"key": "display_show_guard_indicators", "label": "Display guard dots", "type": "bool", "default": True, "help": "Show red hard-guard and green soft-guard dots on the display."},
]
CHARACTER_GUARD_KEYS = [f["key"] for f in CHARACTER_GUARD_FIELDS]
CHARACTER_GUARD_TYPES = {f["key"]: f["type"] for f in CHARACTER_GUARD_FIELDS}


def _boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    return text in ("1", "true", "yes", "y", "on", "enabled")


def convert_character_guard_value(key: str, raw: Any, current: Any = None) -> Any:
    typ = CHARACTER_GUARD_TYPES.get(key, "text")
    if raw in (None, ""):
        return current
    if typ == "bool":
        return _boolish(raw)
    if typ == "int":
        return int(float(raw))
    if typ == "float":
        return float(raw)
    return str(raw)


def normalize_profile_aliases(values: Any) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        raw_values = re.split(r"[,\n]+", values)
    elif isinstance(values, list):
        raw_values = values
    else:
        raw_values = [values]
    out: list[str] = []
    seen: set[str] = set()
    for value in raw_values:
        text = str(value).strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out


def default_guard_settings(cfg: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for field in CHARACTER_GUARD_FIELDS:
        key = field["key"]
        default = field.get("default")
        out[key] = cfg.get(key, default)
        if out[key] is None:
            out[key] = default
    return out


DEFAULT_OPTIONS: dict[str, Any] = {
    "title": "Capohm Control Panel",
    "fields": [
        {"key": "tts_backend", "label": "Global TTS backend", "type": "select", "options": ["character", "elevenlabs", "piper_fast", "piper", "espeak", "borg"], "help": "Normally this is managed by the active character/mode. Manual override is here for debugging."},
        {"key": "stt_backend", "label": "Global STT backend", "type": "select", "options": ["whispercpp_vad", "whispercpp", "vosk", "keyboard", "hybrid"], "help": "Normally whispercpp_vad."},
        {"key": "ai_backend", "label": "Global AI backend", "type": "select", "options": ["openai", "ollama", "echo", "character"], "help": "Normally managed by character mode. Manual override is here for debugging."},
        {"key": "ui_backend", "label": "UI backend", "type": "select", "options": ["display", "simple"], "help": "Use display for the browser face/subtitle UI."},
        {"key": "openai_model", "label": "OpenAI model", "type": "text", "help": "Current top-level model. Character profiles can override this per character/mode."},
        {"key": "ollama_profile", "label": "Ollama profile", "type": "select", "options": ["tiny", "small", "rpg", "vision"], "help": "Current top-level Ollama profile."},
        {"key": "elevenlabs_model_id", "label": "ElevenLabs model", "type": "text", "help": "Usually eleven_flash_v2_5 for low latency."},
        {"key": "elevenlabs_output_format", "label": "ElevenLabs output format", "type": "text", "help": "Usually pcm_16000 for direct aplay."},
        {"key": "whispercpp_device_name", "label": "Mic device name", "type": "text", "help": "Example: USB Audio", "optional": True},
        {"key": "whispercpp_device_index", "label": "Mic device index", "type": "nullable_int", "help": "Empty = null/autodetect.", "optional": True},
        {"key": "whispercpp_vad_rms_threshold", "label": "VAD threshold", "type": "int", "default": 450, "help": "Higher = less sensitive; lower = more sensitive."},
        {"key": "echo_similarity_threshold", "label": "Echo similarity threshold", "type": "float", "help": "Soft guard: higher = less aggressive echo blocking."},
        {"key": "echo_base_cooldown_seconds", "label": "Echo base cooldown seconds", "type": "float", "help": "Base deaf period after TTS."},
        {"key": "echo_max_cooldown_seconds", "label": "Echo max cooldown seconds", "type": "float", "help": "Maximum hard guard cooldown."},
    ],
}

INDEX_HTML = r"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Capohm Control Panel</title>
  <style>
    :root { color-scheme: dark; --green:#27c499; --blue:#62c6ff; --red:#ff5f6d; --yellow:#f0b429; }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: radial-gradient(circle at top, #243d52 0, #081018 48%, #04070a 100%);
      color: #e8f4ff;
    }
    header { max-width: 1180px; margin: auto; padding: 24px 24px 8px; }
    h1 { margin: 0 0 8px; font-size: 2rem; }
    h2 { margin: 0 0 12px; }
    h3 { margin: 0 0 10px; color: #cfefff; }
    .subtitle { color: #a9c3d8; margin: 0; }
    main { max-width: 1180px; margin: auto; padding: 16px 24px 48px; display: grid; gap: 18px; }
    .card { background: rgba(9, 18, 28, 0.84); border: 1px solid rgba(161,216,255,0.15); border-radius: 18px; box-shadow: 0 18px 40px rgba(0,0,0,0.35); padding: 18px; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 14px; }
    .two { display: grid; grid-template-columns: repeat(auto-fit, minmax(330px, 1fr)); gap: 16px; }
    .mode-box { border: 1px solid rgba(157,220,255,0.16); background: rgba(3, 7, 11, 0.36); border-radius: 14px; padding: 14px; }
    label { display: block; font-weight: 750; margin-bottom: 6px; color:#f3fbff; }
    select, input, textarea {
      width: 100%; border: 1px solid #33516a; border-radius: 12px; background: #07111b; color: #eef8ff; padding: 10px 12px; font-size: 0.98rem; outline: none;
    }
    textarea { min-height: 86px; resize: vertical; line-height: 1.35; }
    .help { color: #98b3c7; font-size: 0.84rem; margin-top: 5px; min-height: 1.1em; }
    button { border: 0; border-radius: 13px; padding: 10px 14px; font-weight: 850; cursor: pointer; background: var(--green); color: #03110d; margin: 5px 5px 5px 0; }
    button.secondary { background: #27435a; color: #d8ecff; }
    button.warning { background: var(--yellow); color: #211400; }
    button.danger { background: var(--red); color: #210205; }
    button.blue { background: var(--blue); color: #02101a; }
    button:disabled { opacity: 0.45; cursor: not-allowed; }
    .status { white-space: pre-wrap; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; background: #03070b; border-radius: 12px; padding: 12px; border: 1px solid rgba(255,255,255,0.08); color: #cdeeff; overflow-x: auto; max-height: 52vh; }
    .pill { display:inline-block; padding:3px 8px; border:1px solid #33516a; border-radius:999px; color:#9edaff; margin-left:6px; font-size:0.82rem; }
    .pill.running { border-color: var(--green); color:#6dffd9; }
    .pill.stopped { border-color: var(--red); color:#ffadb5; }
    .tiny { color:#91aabd; font-size:0.9rem; }
    .row { display:flex; flex-wrap:wrap; align-items:center; gap:8px; }
    .tabs { display:flex; flex-wrap:wrap; gap:8px; margin-top: 14px; }
    .tab { background:#172c3b; color:#d7edff; }
    .tab.active { background:#67d7ff; color:#05131b; }
    .hidden { display:none; }
    .inline { display:grid; grid-template-columns: 1fr auto; gap:8px; align-items:end; }
    .muted { color:#9cb4c8; }
    .smallgrid { display:grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap:12px; }
  </style>
</head>
<body>
<header>
  <h1>Capohm Control Panel <span class="pill">character profiles</span> <span class="pill">guards v2</span> <span class="pill">autosync v3</span> <span class="pill">runtime voice apply</span> <span class="pill">volume</span> <span class="pill">aliases</span> <span id="botPill" class="pill">bot: checking</span></h1>
  <p class="subtitle">Characters are first-class now: own voice, AI, STT, media folder, background, and Pro/Free profiles.</p>
  <div class="tabs">
    <button class="tab active" onclick="showTab('run', this)">Run</button>
    <button class="tab" onclick="showTab('characters', this)">Characters</button>
    <button class="tab" onclick="showTab('settings', this)">Settings</button>
    <button class="tab" onclick="showTab('logs', this)">Logs / Raw</button>
  </div>
</header>
<main>
  <section id="tab-run" class="tabpage card">
    <h2>Run</h2>
    <div class="row">
      <button id="startBtn" type="button" onclick="botAction('start')">Start bot</button>
      <button id="stopBtn" class="danger" type="button" onclick="botAction('stop')">Stop bot</button>
      <button id="restartBtn" class="warning" type="button" onclick="botAction('restart')">Restart bot</button>
      <button class="secondary" type="button" onclick="loadState()">Refresh</button>
    </div>
    <p class="tiny">Display server and Firefox still run separately for now. Bot uses whatever character/mode is active in config.json.</p>

    <div class="grid" style="margin-top:16px">
      <div>
        <label>Current mode</label>
        <div class="row">
          <button class="blue" onclick="setMode('pro')">PRO</button>
          <button class="secondary" onclick="setMode('free')">FREE</button>
        </div>
        <div class="help">PRO = online quality/speed profile. FREE = local/offline-ish profile.</div>
      </div>
      <div>
        <label>Active character</label>
        <select id="activeCharacterSelect"></select>
        <div class="row">
          <button onclick="selectActiveCharacter()">Use character</button>
        </div>
        <div class="help">Switches config.character and applies this character's current Pro/Free backend settings.</div>
      </div>
    </div>
  </section>

  <section id="tab-characters" class="tabpage card hidden">
    <h2>Character editor</h2>
    <div class="grid">
      <div>
        <label>Edit character</label>
        <select id="editCharacterSelect" onchange="loadCharacterEditor()"></select>
      </div>
      <div class="inline">
        <div>
          <label>Add new character</label>
          <input id="newCharacterName" placeholder="old_wizard">
        </div>
        <button onclick="addCharacter()">Add</button>
      </div>
    </div>
    <p class="tiny">Internal names use lowercase/underscores. Example: <b>old_wizard</b>. The pretty name goes below.</p>

    <div class="grid" style="margin-top:14px">
      <div>
        <label>Internal name</label>
        <input id="char_internal" readonly>
      </div>
      <div>
        <label>Display name</label>
        <input id="char_display_name" placeholder="Old Wizard">
      </div>
      <div>
        <label>Voice aliases</label>
        <input id="char_aliases" placeholder="shopkeeper, bartender, barkeeper">
        <div class="help">Comma-separated names you can say, e.g. “switch character to barkeeper”.</div>
      </div>
      <div>
        <label>Media folder</label>
        <input id="char_media_dir" placeholder="ui_media/characters/old_wizard">
      </div>
      <div>
        <label>Thinking filler sound</label>
        <input id="char_thinking_sound" placeholder="ui_media/characters/old_wizard/sounds/thinking.wav">
      </div>
      <div>
        <label>Reaction style</label>
        <input id="char_reaction_style" placeholder="polite, grumpy, theatrical, bites back when insulted...">
        <div class="help">Short behavioral note; the full behavior still belongs in the personality prompt.</div>
      </div>
    </div>

    <h3 style="margin-top:18px">Memory / mood</h3>
    <div class="smallgrid">
      <div>
        <label>AI history messages</label>
        <input id="char_ai_history_messages" type="number" min="0" max="40" step="1" placeholder="6">
        <div class="help">How many recent chat messages this character remembers. 6 ≈ last 3 turns.</div>
      </div>
      <div>
        <label>Emotion memory turns</label>
        <input id="char_emotion_memory_turns" type="number" min="0" max="20" step="1" placeholder="2">
        <div class="help">How long mood may stay angry/happy/etc. Future behavior hook.</div>
      </div>
      <div>
        <label>Default mood</label>
        <select id="char_default_mood">
          <option value="neutral">neutral</option>
          <option value="happy">happy</option>
          <option value="amused">amused</option>
          <option value="grumpy">grumpy</option>
          <option value="suspicious">suspicious</option>
          <option value="sleepy">sleepy</option>
        </select>
        <div class="help">Stored now. Mood engine comes next.</div>
      </div>
      <div>
        <label>Insult sensitivity</label>
        <select id="char_insult_sensitivity">
          <option value="low">low</option>
          <option value="normal">normal</option>
          <option value="high">high</option>
          <option value="ridiculous">ridiculous</option>
        </select>
        <div class="help">How quickly this character gets offended. Future behavior hook.</div>
      </div>
      <div>
        <label>Forgiveness speed</label>
        <select id="char_forgiveness_speed">
          <option value="fast">fast</option>
          <option value="normal">normal</option>
          <option value="slow">slow</option>
          <option value="never">never</option>
        </select>
        <div class="help">How quickly mood returns to neutral. Future behavior hook.</div>
      </div>
    </div>

    <div class="grid" style="margin-top:14px">
      <div>
        <label>Short description</label>
        <textarea id="char_description" placeholder="One or two lines: who is this character?"></textarea>
      </div>
      <div>
        <label>Background / lore</label>
        <textarea id="char_background" placeholder="Backstory, world, relation to the user, running jokes..."></textarea>
      </div>
    </div>
    <div style="margin-top:14px">
      <label>Personality prompt</label>
      <textarea id="char_personality_prompt" placeholder="How should this character behave, speak, joke, refuse, think, etc."></textarea>
      <div class="help">Saved and synced automatically to characters/*.json so the bot can use this prompt after restart.</div>
    </div>

    <div class="two" style="margin-top:18px">
      <div class="mode-box">
        <h3>PRO profile</h3>
        <div id="proFields" class="smallgrid"></div>
      </div>
      <div class="mode-box">
        <h3>FREE profile</h3>
        <div id="freeFields" class="smallgrid"></div>
      </div>
    </div>

    <div class="mode-box" style="margin-top:18px">
      <h3>Character guard settings</h3>
      <p class="tiny">These are applied to the old top-level guard keys whenever this character is selected or saved as active. Restart the bot after changing them.</p>
      <div id="guardFields" class="smallgrid"></div>
    </div>
    <p>
      <button onclick="saveCharacter()">Save character profile</button>
      <button class="blue" onclick="saveCharacter(true)">Save + use now</button>
      <button class="secondary" onclick="openMediaFolderHint()">Show media folder</button>
    </p>
  </section>

  <section id="tab-settings" class="tabpage card hidden">
    <h2>General settings</h2>
    <p class="tiny">This is the safe/general page. More guard/STT/display fields can be added, but we keep it organized instead of dumping the entire JSON sewer in your lap.</p>
    <form id="settingsForm">
      <div id="fields" class="grid"></div>
      <p>
        <button type="submit">Save general config</button>
        <button class="secondary" type="button" onclick="loadState()">Reload</button>
      </p>
    </form>
  </section>

  <section id="tab-logs" class="tabpage card hidden">
    <h2>Logs / Raw config</h2>
    <p>
      <button class="secondary" onclick="loadLog('errors')">Show errors log</button>
      <button class="secondary" onclick="loadLog('stdout')">Show stdout log</button>
      <button class="warning" onclick="showRaw()">Show raw config</button>
    </p>
    <div id="status" class="status">Loading...</div>
  </section>

  <section class="card">
    <h2>Status</h2>
    <div id="statusBottom" class="status">Loading...</div>
  </section>
</main>
<script>
let state = null;
let currentTab = 'run';

const modeFields = [
  {key:'ai_backend', label:'AI backend', type:'select', options:['openai','ollama','echo']},
  {key:'openai_model', label:'OpenAI model', type:'text', placeholder:'gpt-3.5-turbo'},
  {key:'ollama_profile', label:'Ollama profile', type:'select', options:['tiny','small','rpg','vision']},
  {key:'tts_backend', label:'TTS backend', type:'select', options:['elevenlabs','piper_fast','piper','espeak','borg']},
  {key:'tts_volume_db', label:'TTS volume dB', type:'text', placeholder:'0 = normal, -3 quieter, +3 louder'},
  {key:'elevenlabs_voice_id', label:'ElevenLabs voice ID', type:'text', placeholder:'voice id'},
  {key:'elevenlabs_model_id', label:'ElevenLabs model', type:'select', options:['eleven_flash_v2_5','eleven_flash_v2','eleven_multilingual_v2','eleven_turbo_v2_5','eleven_v3']},
  {key:'elevenlabs_output_format', label:'ElevenLabs format', type:'select', options:['pcm_16000','pcm_22050','pcm_24000','mp3_44100_128','mp3_22050_32']},
  {key:'elevenlabs_language_code', label:'Language code', type:'text', placeholder:'optional, e.g. en'},
  {key:'stt_backend', label:'STT backend', type:'select', options:['whispercpp_vad','whispercpp','vosk','keyboard','hybrid']},
  {key:'piper_fast_mode', label:'Piper fast mode', type:'select', options:['cli','api']},
];


const guardFields = [
  {key:'ignore_stt_while_speaking', label:'Ignore STT while speaking', type:'bool', help:'Hard guard: ignore normal microphone input while TTS is active.'},
  {key:'active_tts_only_barge_in', label:'Only barge-in during TTS', type:'bool', help:'Only stop/cancel commands get through while speaking.'},
  {key:'echo_hard_guard_enabled', label:'Hard guard enabled', type:'bool', help:'Temporary deaf period after the character speaks.'},
  {key:'echo_base_cooldown_seconds', label:'Hard base cooldown', type:'float', help:'Base seconds after TTS.'},
  {key:'echo_seconds_per_word', label:'Hard seconds per word', type:'float', help:'Extra guard time based on answer length.'},
  {key:'echo_max_cooldown_seconds', label:'Hard max cooldown', type:'float', help:'Maximum hard guard time.'},
  {key:'echo_hard_guard_min_seconds', label:'Hard min seconds', type:'float', help:'Minimum hard guard time, if supported.'},
  {key:'echo_hard_guard_max_seconds', label:'Hard absolute max', type:'float', help:'Absolute hard max, if supported.'},
  {key:'echo_hard_guard_fraction', label:'Hard guard fraction', type:'float', help:'Multiplier/fraction, if supported.'},
  {key:'echo_suppression_enabled', label:'Soft guard enabled', type:'bool', help:'Compare heard text to recent TTS and suppress echoes.'},
  {key:'echo_memory_seconds', label:'Soft memory seconds', type:'float', help:'How long recent TTS is remembered.'},
  {key:'echo_similarity_threshold', label:'Soft similarity threshold', type:'float', help:'Lower = blocks more echo. Higher = lets more through.'},
  {key:'echo_word_overlap_threshold', label:'Soft word overlap', type:'float', help:'Overlap threshold.'},
  {key:'echo_short_similarity_threshold', label:'Short phrase threshold', type:'float', help:'Threshold for short phrases.'},
  {key:'echo_min_words', label:'Echo min words', type:'int', help:'Minimum word count before echo matching gets serious.'},
  {key:'show_ignored_stt', label:'Show ignored STT', type:'bool', help:'Debug only.'},
  {key:'display_show_raw_stt', label:'Display raw STT', type:'bool', help:'Debug only. Usually false.'},
  {key:'display_show_accepted_heard', label:'Display accepted heard', type:'bool', help:'Usually true.'},
];

function esc(s) { return String(s ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c])); }

async function api(path, options) {
  const res = await fetch(path, options);
  const data = await res.json();
  if (!res.ok || data.ok === false) throw new Error(data.error || res.statusText);
  return data;
}

function statusText(text) {
  document.getElementById('status').textContent = text;
  document.getElementById('statusBottom').textContent = text;
}

function showTab(name, btn) {
  currentTab = name;
  document.querySelectorAll('.tabpage').forEach(x => x.classList.add('hidden'));
  document.getElementById('tab-' + name).classList.remove('hidden');
  document.querySelectorAll('.tab').forEach(x => x.classList.remove('active'));
  if (btn) btn.classList.add('active');
}

function characters() { return state?.config?.character_profiles || {}; }

function buildCharacterSelects() {
  const chars = characters();
  const active = state.config.character || '';
  for (const id of ['activeCharacterSelect','editCharacterSelect']) {
    const sel = document.getElementById(id);
    const old = sel.value;
    sel.innerHTML = '';
    Object.entries(chars).sort().forEach(([name, prof]) => {
      const opt = document.createElement('option');
      opt.value = name;
      opt.textContent = `${prof.display_name || name} (${name})`;
      sel.appendChild(opt);
    });
    sel.value = (id === 'activeCharacterSelect') ? active : (old || active);
  }
}

function modeControlHTML(mode, f, value) {
  const name = `${mode}_${f.key}`;
  let control = '';
  if (f.type === 'select') {
    const vals = Array.from(new Set([...(f.options || []), value].filter(v => v !== undefined && v !== null && v !== '')));
    control = `<select id="${esc(name)}">${vals.map(o => `<option value="${esc(o)}" ${o === value ? 'selected' : ''}>${esc(o)}</option>`).join('')}</select>`;
  } else {
    control = `<input id="${esc(name)}" value="${esc(value ?? '')}" placeholder="${esc(f.placeholder || '')}">`;
  }
  return `<div><label>${esc(f.label)}</label>${control}</div>`;
}

function buildModeFields(mode, data) {
  const holder = document.getElementById(mode + 'Fields');
  holder.innerHTML = modeFields.map(f => modeControlHTML(mode, f, data?.[f.key])).join('');
}


function guardControlHTML(f, value) {
  const id = `guard_${f.key}`;
  let control = '';
  if (f.type === 'bool') {
    const v = String(value === undefined ? '' : value).toLowerCase();
    const isTrue = ['true','1','yes','on'].includes(v) || value === true;
    control = `<select id="${esc(id)}"><option value="true" ${isTrue ? 'selected' : ''}>true</option><option value="false" ${!isTrue ? 'selected' : ''}>false</option></select>`;
  } else {
    control = `<input id="${esc(id)}" value="${esc(value ?? '')}">`;
  }
  return `<div><label>${esc(f.label)}</label>${control}<div class="help">${esc(f.help || '')}</div></div>`;
}

function buildGuardFields(data) {
  const holder = document.getElementById('guardFields');
  if (!holder) return;
  holder.innerHTML = guardFields.map(f => guardControlHTML(f, data?.[f.key])).join('');
}

function readGuards() {
  const out = {};
  for (const f of guardFields) {
    const el = document.getElementById(`guard_${f.key}`);
    if (!el) continue;
    out[f.key] = el.value;
  }
  return out;
}

function loadCharacterEditor() {
  if (!state) return;
  const name = document.getElementById('editCharacterSelect').value || state.config.character;
  const prof = characters()[name] || {};
  document.getElementById('char_internal').value = name || '';
  document.getElementById('char_display_name').value = prof.display_name || '';
  document.getElementById('char_aliases').value = Array.isArray(prof.aliases) ? prof.aliases.join(', ') : '';
  document.getElementById('char_media_dir').value = prof.media_dir || `ui_media/characters/${name}`;
  document.getElementById('char_thinking_sound').value = prof.thinking_sound || `ui_media/characters/${name}/sounds/thinking.wav`;
  document.getElementById('char_reaction_style').value = prof.reaction_style || '';
  document.getElementById('char_ai_history_messages').value = prof.ai_history_messages ?? state.config.ai_history_messages ?? 6;
  document.getElementById('char_emotion_memory_turns').value = prof.emotion_memory_turns ?? 2;
  document.getElementById('char_default_mood').value = prof.default_mood || 'neutral';
  document.getElementById('char_insult_sensitivity').value = prof.insult_sensitivity || 'normal';
  document.getElementById('char_forgiveness_speed').value = prof.forgiveness_speed || 'normal';
  document.getElementById('char_description').value = prof.description || '';
  document.getElementById('char_background').value = prof.background || '';
  document.getElementById('char_personality_prompt').value = prof.personality_prompt || '';
  buildModeFields('pro', prof.pro || {});
  buildModeFields('free', prof.free || {});
  buildGuardFields(prof.guards || {});
}

function readMode(mode) {
  const out = {};
  for (const f of modeFields) {
    const el = document.getElementById(`${mode}_${f.key}`);
    if (!el) continue;
    out[f.key] = el.value;
  }
  if (!out.ollama_model_profile && out.ollama_profile) out.ollama_model_profile = out.ollama_profile;
  return out;
}

function readCharacterForm() {
  const name = document.getElementById('char_internal').value;
  return {
    character: name,
    profile: {
      display_name: document.getElementById('char_display_name').value,
      aliases: document.getElementById('char_aliases').value.split(',').map(x => x.trim()).filter(Boolean),
      media_dir: document.getElementById('char_media_dir').value,
      thinking_sound: document.getElementById('char_thinking_sound').value,
      reaction_style: document.getElementById('char_reaction_style').value,
      ai_history_messages: document.getElementById('char_ai_history_messages').value,
      emotion_memory_turns: document.getElementById('char_emotion_memory_turns').value,
      default_mood: document.getElementById('char_default_mood').value,
      insult_sensitivity: document.getElementById('char_insult_sensitivity').value,
      forgiveness_speed: document.getElementById('char_forgiveness_speed').value,
      description: document.getElementById('char_description').value,
      background: document.getElementById('char_background').value,
      personality_prompt: document.getElementById('char_personality_prompt').value,
      pro: readMode('pro'),
      free: readMode('free'),
      guards: readGuards(),
    }
  };
}

function buildGeneralFields() {
  const holder = document.getElementById('fields');
  holder.innerHTML = '';
  for (const f of state.options.fields) {
    const value = state.config[f.key];
    const div = document.createElement('div');
    let control = '';
    if (f.type === 'select') {
      const vals = Array.from(new Set([...(f.options || []), value].filter(v => v !== undefined && v !== null && v !== '')));
      control = `<select name="${esc(f.key)}">${vals.map(o => `<option value="${esc(o)}" ${o === value ? 'selected' : ''}>${esc(o)}</option>`).join('')}</select>`;
    } else {
      control = `<input name="${esc(f.key)}" value="${esc(value === null || value === undefined ? '' : value)}" placeholder="${f.type === 'nullable_int' ? 'null' : ''}">`;
    }
    div.innerHTML = `<label>${esc(f.label || f.key)}</label>${control}<div class="help">${esc(f.help || '')}</div>`;
    holder.appendChild(div);
  }
}

function updateBotControls() {
  const bot = state.bot || {};
  const running = !!bot.running;
  const pill = document.getElementById('botPill');
  const mode = state.config.capohm_mode || 'free';
  const charName = state.config.character || '?';
  pill.textContent = running ? `bot: running pid ${bot.pid} · ${mode} · ${charName}` : `bot: stopped · ${mode} · ${charName}`;
  pill.className = running ? 'pill running' : 'pill stopped';
  document.getElementById('startBtn').disabled = running;
  document.getElementById('stopBtn').disabled = !running;
}

async function loadState() {
  try {
    state = await api('/api/state');
    buildCharacterSelects();
    loadCharacterEditor();
    buildGeneralFields();
    updateBotControls();
    const bot = state.bot || {};
    const botText = bot.running ? `Bot running. PID: ${bot.pid}.` : 'Bot stopped.';
    statusText(`${botText}\nMode: ${state.config.capohm_mode || 'free'}\nCharacter: ${state.config.character || '?'}\n\n${state.status || 'Ready.'}`);
  } catch (err) { statusText('ERROR: ' + err.message); }
}

async function botAction(action) {
  try {
    statusText(`${action}...`);
    const result = await api(`/api/bot/${action}`, {method:'POST'});
    statusText(result.status);
    await loadState();
  } catch (err) { statusText('ERROR: ' + err.message); await loadState(); }
}

async function setMode(mode) {
  try {
    const result = await api('/api/mode', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({mode})});
    statusText(result.status);
    await loadState();
  } catch (err) { statusText('ERROR: ' + err.message); }
}

async function selectActiveCharacter() {
  try {
    const character = document.getElementById('activeCharacterSelect').value;
    const result = await api('/api/select-character', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({character})});
    statusText(result.status);
    await loadState();
  } catch (err) { statusText('ERROR: ' + err.message); }
}

async function addCharacter() {
  try {
    const character = document.getElementById('newCharacterName').value;
    const result = await api('/api/add-character', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({character})});
    statusText(result.status);
    await loadState();
    document.getElementById('editCharacterSelect').value = result.character;
    loadCharacterEditor();
  } catch (err) { statusText('ERROR: ' + err.message); }
}

async function saveCharacter(useNow=false) {
  try {
    const payload = readCharacterForm();
    payload.use_now = !!useNow;
    const result = await api('/api/save-character', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
    statusText(result.status);
    await loadState();
  } catch (err) { statusText('ERROR: ' + err.message); }
}

async function saveGeneralForm(ev) {
  ev.preventDefault();
  const form = new FormData(document.getElementById('settingsForm'));
  const values = {};
  for (const [k, v] of form.entries()) values[k] = v;
  try {
    const result = await api('/api/save', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({values})});
    statusText(result.status);
    await loadState();
  } catch (err) { statusText('ERROR: ' + err.message); }
}

async function loadLog(which) {
  try {
    const result = await api(`/api/log?which=${encodeURIComponent(which)}`);
    statusText(result.status + '\n\n' + (result.content || ''));
  } catch (err) { statusText('ERROR: ' + err.message); }
}

function showRaw() { statusText(JSON.stringify(state.config, null, 2)); }

function openMediaFolderHint() {
  const dir = document.getElementById('char_media_dir').value;
  statusText(`Media folder for this character:\n${dir}\n\nOn the Pi:\ncd ~/capohm\nfind ${dir} -maxdepth 2 -type d\n\nPut images/gifs/videos in the emotion folders.`);
}

document.getElementById('settingsForm').addEventListener('submit', saveGeneralForm);
loadState();
setInterval(async () => {
  try {
    const fresh = await api('/api/state');
    state.bot = fresh.bot;
    state.config.capohm_mode = fresh.config.capohm_mode;
    state.config.character = fresh.config.character;
    updateBotControls();
  } catch (_) {}
}, 3000);
</script>
</body>
</html>
"""


def slugify(value: str) -> str:
    value = value.strip().lower().replace(" ", "_").replace("-", "_")
    value = re.sub(r"[^a-z0-9_]+", "", value)
    value = re.sub(r"_+", "_", value).strip("_")
    if not value:
        raise ValueError("Character name became empty. Use letters/numbers/underscores.")
    return value


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return copy.deepcopy(default)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{path} is not valid JSON: {exc}") from exc


def save_json(path: Path, data: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=4, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def backup_file(path: Path) -> Path | None:
    if not path.exists():
        return None
    backup_dir = path.parent / "backups"
    backup_dir.mkdir(exist_ok=True)
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = backup_dir / f"{path.name}.bak-{stamp}"
    shutil.copy2(path, backup)
    return backup


def repair_config(config: dict[str, Any]) -> dict[str, Any]:
    repaired = dict(config)
    for key, default in SAFE_DEFAULTS.items():
        if repaired.get(key) is None:
            repaired[key] = default
    return repaired


def load_dotenv(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    line_re = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$")
    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        m = line_re.match(line)
        if not m:
            continue
        key, value = m.group(1), m.group(2)
        if value and value[0] in ('"', "'") and value[-1:] == value[0]:
            value = value[1:-1]
        env[key] = value
    return env


def ensure_media_dirs(repo_dir: Path, character: str) -> None:
    root = repo_dir / "ui_media" / "characters" / character
    for emotion in EMOTIONS:
        path = root / emotion
        path.mkdir(parents=True, exist_ok=True)
        (path / ".gitkeep").touch(exist_ok=True)
    sounds = root / "sounds"
    sounds.mkdir(parents=True, exist_ok=True)
    (sounds / ".gitkeep").touch(exist_ok=True)


def default_character_profile(character: str, display_name: str, cfg: dict[str, Any], repo_dir: Path) -> dict[str, Any]:
    env = load_dotenv(repo_dir / ".env")
    active_char = str(cfg.get("character") or "grumpy_shopkeeper")
    current_voice = str(cfg.get("elevenlabs_voice_id") or env.get("ELEVENLABS_VOICE_ID") or "")
    voice_for_this = current_voice if character == active_char else ""
    current_stt = str(cfg.get("stt_backend") or "whispercpp_vad")
    current_openai_model = str(cfg.get("openai_model") or "gpt-3.5-turbo")
    current_ollama_profile = str(cfg.get("ollama_model_profile") or cfg.get("ollama_profile") or "rpg")
    current_eleven_model = str(cfg.get("elevenlabs_model_id") or "eleven_flash_v2_5")
    current_eleven_format = str(cfg.get("elevenlabs_output_format") or "pcm_16000")
    current_language = str(cfg.get("elevenlabs_language_code") or "")
    free_tts = "borg" if character == "borg" else "piper_fast"
    thinking_name = "analysing.wav" if character == "borg" else "thinking.wav"
    return {
        "display_name": display_name,
        "description": "",
        "background": "",
        "personality_prompt": "",
        "media_dir": f"ui_media/characters/{character}",
        "thinking_sound": f"ui_media/characters/{character}/sounds/{thinking_name}",
        "reaction_style": "",
        "ai_history_messages": int(cfg.get("ai_history_messages") or 6),
        "emotion_memory_turns": 2,
        "default_mood": "neutral",
        "insult_sensitivity": "normal",
        "forgiveness_speed": "normal",
        "guards": default_guard_settings(cfg),
        "pro": {
            "ai_backend": "openai",
            "openai_model": current_openai_model,
            "ollama_profile": current_ollama_profile,
            "ollama_model_profile": current_ollama_profile,
            "tts_backend": "elevenlabs",
            "tts_volume_db": 0.0,
            "elevenlabs_volume_db": 0.0,
            "elevenlabs_voice_id": voice_for_this,
            "elevenlabs_model_id": current_eleven_model,
            "elevenlabs_output_format": current_eleven_format,
            "elevenlabs_language_code": current_language,
            "stt_backend": current_stt,
            "piper_fast_mode": str(cfg.get("piper_fast_mode") or "cli"),
        },
        "free": {
            "ai_backend": "ollama",
            "openai_model": current_openai_model,
            "ollama_profile": current_ollama_profile,
            "ollama_model_profile": current_ollama_profile,
            "tts_backend": free_tts,
            "tts_volume_db": 0.0,
            "elevenlabs_volume_db": 0.0,
            "elevenlabs_voice_id": "",
            "elevenlabs_model_id": current_eleven_model,
            "elevenlabs_output_format": current_eleven_format,
            "elevenlabs_language_code": current_language,
            "stt_backend": current_stt,
            "piper_fast_mode": str(cfg.get("piper_fast_mode") or "cli"),
        },
    }


def ensure_character_profiles(cfg: dict[str, Any], repo_dir: Path) -> tuple[dict[str, Any], list[str]]:
    changed: list[str] = []
    if not cfg.get("capohm_mode"):
        cfg["capohm_mode"] = "pro" if cfg.get("ai_backend") == "openai" or cfg.get("tts_backend") == "elevenlabs" else "free"
        changed.append(f"capohm_mode={cfg['capohm_mode']}")
    cfg.setdefault("_capohm_mode_options", ["free", "pro"])
    cfg.setdefault("_character_profile_version", 2)
    profiles = cfg.get("character_profiles")
    if not isinstance(profiles, dict):
        profiles = {}
        cfg["character_profiles"] = profiles
        changed.append("repaired character_profiles container")
    active_char = str(cfg.get("character") or "grumpy_shopkeeper")
    chars = dict(DEFAULT_CHARACTERS)
    if active_char not in chars:
        chars[active_char] = active_char.replace("_", " ").title()
    for character, display_name in chars.items():
        if character not in profiles:
            profiles[character] = default_character_profile(character, display_name, cfg, repo_dir)
            changed.append(f"added profile {character}")
        else:
            prof = profiles.get(character)
            if not isinstance(prof, dict):
                prof = default_character_profile(character, display_name, cfg, repo_dir)
                profiles[character] = prof
                changed.append(f"repaired profile {character}")
            prof.setdefault("display_name", display_name)
            prof.setdefault("description", "")
            prof.setdefault("background", "")
            prof.setdefault("personality_prompt", "")
            prof.setdefault("media_dir", f"ui_media/characters/{character}")
            prof.setdefault("thinking_sound", f"ui_media/characters/{character}/sounds/thinking.wav")
            prof.setdefault("reaction_style", "")
            prof.setdefault("ai_history_messages", int(cfg.get("ai_history_messages") or 6))
            prof.setdefault("emotion_memory_turns", 2)
            prof.setdefault("default_mood", "neutral")
            prof.setdefault("insult_sensitivity", "normal")
            prof.setdefault("forgiveness_speed", "normal")
            guards = prof.setdefault("guards", {})
            if not isinstance(guards, dict):
                guards = {}
                prof["guards"] = guards
            for gk, gv in default_guard_settings(cfg).items():
                guards.setdefault(gk, gv)
            for mode in ("pro", "free"):
                if mode not in prof or not isinstance(prof.get(mode), dict):
                    prof[mode] = default_character_profile(character, display_name, cfg, repo_dir)[mode]
                    changed.append(f"added {mode} mode to {character}")
                else:
                    defaults = default_character_profile(character, display_name, cfg, repo_dir)[mode]
                    for k, v in defaults.items():
                        prof[mode].setdefault(k, v)
        ensure_media_dirs(repo_dir, character)
    return cfg, changed


def apply_selected_profile(cfg: dict[str, Any]) -> list[str]:
    changed: list[str] = []
    character = str(cfg.get("character") or "grumpy_shopkeeper")
    mode = str(cfg.get("capohm_mode") or "free")
    profiles = cfg.get("character_profiles") or {}
    if not isinstance(profiles, dict) or character not in profiles or not isinstance(profiles.get(character), dict):
        raise ValueError(f"No usable profile for character '{character}'.")
    selected = profiles[character].get(mode)
    if not isinstance(selected, dict):
        raise ValueError(f"Character '{character}' has no mode '{mode}'.")
    for key in TOP_LEVEL_KEYS_TO_APPLY:
        if key in selected:
            old = cfg.get(key)
            new = selected[key]
            if old != new:
                cfg[key] = new
                changed.append(f"{key}: {old!r} -> {new!r}")
    guard_settings = profiles[character].get("guards") or {}
    for key in CHARACTER_GUARD_KEYS:
        if key in guard_settings:
            old = cfg.get(key)
            new = convert_character_guard_value(key, guard_settings[key], old)
            if old != new:
                cfg[key] = new
                changed.append(f"{key}: {old!r} -> {new!r}")
    profile = profiles[character]
    if "ai_history_messages" in profile:
        try:
            new_history = int(float(profile.get("ai_history_messages") or cfg.get("ai_history_messages") or 6))
            old = cfg.get("ai_history_messages")
            if old != new_history:
                cfg["ai_history_messages"] = new_history
                changed.append(f"ai_history_messages: {old!r} -> {new_history!r}")
        except Exception:
            pass
    if cfg.get("ui_backend") != "display":
        old = cfg.get("ui_backend")
        cfg["ui_backend"] = "display"
        changed.append(f"ui_backend: {old!r} -> 'display'")
    return changed


def convert_value(raw: Any, field: dict[str, Any], current: Any = None) -> Any:
    typ = field.get("type", "text")
    if typ == "nullable_int":
        if raw in ("", None, "null", "None"):
            return None
        return int(raw)
    if typ == "int":
        if raw in ("", None):
            if "default" in field:
                return int(field["default"])
            if field.get("optional"):
                return current
        return int(raw)
    if typ == "float":
        if raw in ("", None):
            if "default" in field:
                return float(field["default"])
            if field.get("optional"):
                return current
        return float(raw)
    if typ == "bool":
        if isinstance(raw, bool):
            return raw
        return str(raw).lower() in ("1", "yes", "true", "on")
    return "" if raw is None else str(raw)


def apply_values(config: dict[str, Any], options: dict[str, Any], raw_values: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    changed: dict[str, Any] = {}
    fields_by_key = {f["key"]: f for f in options.get("fields", []) if "key" in f}
    new_config = dict(config)
    for key, raw in raw_values.items():
        field = fields_by_key.get(key, {"key": key, "type": "text"})
        value = convert_value(raw, field, new_config.get(key))
        if new_config.get(key) != value:
            changed[key] = value
        new_config[key] = value
    repaired = repair_config(new_config)
    for key, value in repaired.items():
        if new_config.get(key) != value:
            changed[key] = value
    return repaired, changed


def is_pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def read_pid(pid_path: Path) -> int | None:
    try:
        return int(pid_path.read_text(encoding="utf-8").strip())
    except Exception:
        return None


def find_main_processes(repo_dir: Path) -> list[int]:
    proc = Path("/proc")
    if not proc.exists():
        return []
    found: list[int] = []
    me = os.getpid()
    for p in proc.iterdir():
        if not p.name.isdigit():
            continue
        pid = int(p.name)
        if pid == me:
            continue
        try:
            cmdline = (p / "cmdline").read_bytes().replace(b"\x00", b" ").decode("utf-8", errors="ignore")
            if "main_modular.py" not in cmdline:
                continue
            cwd = (p / "cwd").resolve()
            if cwd == repo_dir.resolve():
                found.append(pid)
        except Exception:
            continue
    return sorted(found)


def choose_python(repo_dir: Path) -> str:
    venv_python = repo_dir / ".venv" / "bin" / "python"
    return str(venv_python) if venv_python.exists() else sys.executable


def tail_file(path: Path, max_lines: int = 160) -> str:
    if not path.exists():
        return f"{path.name} does not exist yet."
    try:
        return "\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[-max_lines:])
    except Exception as exc:
        return f"Could not read {path.name}: {exc}"




def character_aliases(name: str, display_name: str, profile: dict[str, Any]) -> list[str]:
    aliases: list[str] = []

    def add(value: Any) -> None:
        if not value:
            return
        text = str(value).strip()
        if text and text not in aliases:
            aliases.append(text)

    for value in profile.get("aliases", []) or []:
        add(value)
    add(name)
    add(name.replace("_", " "))
    add(display_name)
    add(display_name.lower())

    if name == "grumpy_shopkeeper":
        for a in ["grumpy", "shopkeeper", "old man", "old shopkeeper", "potion shopkeeper"]:
            add(a)
    elif name == "borg":
        for a in ["hive", "borg hive", "queen", "collective"]:
            add(a)
    elif name == "natural":
        for a in ["normal", "assistant", "natural voice"]:
            add(a)
    elif name == "jolly_bartender":
        for a in ["bartender", "barkeeper", "bar keeper", "barkeep", "bar man", "barman", "tavern keeper", "tavernkeeper", "innkeeper", "inn keeper", "jolly bartender", "jolly barkeeper"]:
            add(a)
    return aliases


def build_character_system_prompt(profile: dict[str, Any]) -> str:
    prompt = str(profile.get("system_prompt") or profile.get("personality_prompt") or "").strip()
    if prompt:
        return prompt
    parts: list[str] = []
    for key in ("description", "background", "lore"):
        value = str(profile.get(key, "")).strip()
        if value:
            parts.append(value)
    if parts:
        return "\n\n".join(parts)
    return "You are a helpful tabletop character. Keep replies short, useful, and in character."


def sync_character_files_from_config(cfg: dict[str, Any], repo_dir: Path) -> list[str]:
    profiles = cfg.get("character_profiles") or {}
    if not isinstance(profiles, dict):
        return []
    characters_dir = repo_dir / str(cfg.get("characters_dir") or "characters")
    characters_dir.mkdir(parents=True, exist_ok=True)
    try:
        cfg["characters_dir"] = str(characters_dir.relative_to(repo_dir))
    except Exception:
        cfg["characters_dir"] = str(characters_dir)
    written: list[str] = []
    for name, profile in sorted(profiles.items()):
        if not isinstance(profile, dict):
            continue
        display_name = str(profile.get("display_name") or profile.get("name") or name).strip()
        media_dir = str(profile.get("media_dir") or f"ui_media/characters/{name}").strip()
        ensure_media_dirs(repo_dir, name)
        char = {
            "name": name,
            "display_name": display_name,
            "aliases": character_aliases(name, display_name, profile),
            "description": str(profile.get("description") or "").strip(),
            "background": str(profile.get("background") or "").strip(),
            "system_prompt": build_character_system_prompt(profile),
            "media_dir": media_dir,
            "thinking_sound": str(profile.get("thinking_sound") or "").strip(),
            "reaction_style": str(profile.get("reaction_style") or "").strip(),
            "ai_history_messages": profile.get("ai_history_messages", cfg.get("ai_history_messages", 6)),
            "emotion_memory_turns": profile.get("emotion_memory_turns", 2),
            "default_mood": str(profile.get("default_mood") or "neutral"),
            "insult_sensitivity": str(profile.get("insult_sensitivity") or "normal"),
            "forgiveness_speed": str(profile.get("forgiveness_speed") or "normal"),
            "wake_responses": profile.get("wake_responses") or cfg.get("wake_responses", ["Online."]),
            "sleep_responses": profile.get("sleep_responses") or cfg.get("sleep_responses", ["Sleeping."]),
            "switch_response": profile.get("switch_response") or f"Character profile loaded: {display_name}.",
        }
        for mode in ("pro", "free"):
            if isinstance(profile.get(mode), dict):
                char[mode] = profile[mode]
        path = characters_dir / f"{name}.json"
        save_json(path, char)
        try:
            written.append(str(path.relative_to(repo_dir)))
        except Exception:
            written.append(str(path))
    return written

class BotManager:
    def __init__(self, repo_dir: Path):
        self.repo_dir = repo_dir
        self.main_script = repo_dir / "main_modular.py"
        self.pid_path = repo_dir / ".capohm.pid"
        self.stdout_path = repo_dir / "capohm_stdout.log"
        self.stderr_path = repo_dir / "capohm_errors.log"

    def status(self) -> dict[str, Any]:
        pid = read_pid(self.pid_path)
        if pid and is_pid_alive(pid):
            return {"running": True, "pid": pid, "source": "pidfile"}
        if pid and not is_pid_alive(pid):
            try:
                self.pid_path.unlink()
            except OSError:
                pass
        discovered = find_main_processes(self.repo_dir)
        if discovered:
            return {"running": True, "pid": discovered[0], "extra_pids": discovered[1:], "source": "discovered"}
        return {"running": False, "pid": None, "source": "none"}

    def start(self) -> str:
        st = self.status()
        if st["running"]:
            return f"Capohm is already running. PID: {st['pid']} ({st.get('source')})."
        if not self.main_script.exists():
            raise RuntimeError(f"main_modular.py not found in {self.repo_dir}")
        python_bin = choose_python(self.repo_dir)
        env = os.environ.copy()
        env.update(load_dotenv(self.repo_dir / ".env"))
        env.setdefault("PYTHONUNBUFFERED", "1")
        out = self.stdout_path.open("a", buffering=1, encoding="utf-8")
        err = self.stderr_path.open("a", buffering=1, encoding="utf-8")
        stamp = _dt.datetime.now().isoformat(timespec="seconds")
        out.write(f"\n--- Capohm start {stamp} ---\n")
        err.write(f"\n--- Capohm start {stamp} ---\n")
        try:
            proc = subprocess.Popen(
                [python_bin, str(self.main_script.name)],
                cwd=str(self.repo_dir),
                stdout=out,
                stderr=err,
                env=env,
                start_new_session=True,
            )
        finally:
            out.close()
            err.close()
        self.pid_path.write_text(str(proc.pid), encoding="utf-8")
        time.sleep(0.6)
        if proc.poll() is not None:
            try:
                self.pid_path.unlink()
            except OSError:
                pass
            raise RuntimeError(f"Capohm started but exited with code {proc.returncode}.\n\nLast errors:\n{tail_file(self.stderr_path, 80)}")
        return f"Started Capohm. PID: {proc.pid}.\nCommand: {python_bin} main_modular.py"

    def stop(self) -> str:
        st = self.status()
        if not st["running"]:
            return "Capohm is not running. Nothing to stop."
        pids = [int(st["pid"])] + [int(p) for p in st.get("extra_pids", [])]
        messages: list[str] = []
        for pid in pids:
            if not is_pid_alive(pid):
                continue
            try:
                os.killpg(pid, signal.SIGTERM)
                messages.append(f"Sent SIGTERM to process group {pid}.")
            except Exception:
                try:
                    os.kill(pid, signal.SIGTERM)
                    messages.append(f"Sent SIGTERM to PID {pid}.")
                except Exception as exc:
                    messages.append(f"Could not stop PID {pid}: {exc}")
        deadline = time.time() + 5
        while time.time() < deadline:
            if not any(is_pid_alive(pid) for pid in pids):
                break
            time.sleep(0.2)
        still_alive = [pid for pid in pids if is_pid_alive(pid)]
        for pid in still_alive:
            try:
                os.killpg(pid, signal.SIGKILL)
                messages.append(f"PID {pid} needed SIGKILL.")
            except Exception:
                try:
                    os.kill(pid, signal.SIGKILL)
                    messages.append(f"PID {pid} killed.")
                except Exception as exc:
                    messages.append(f"Could not kill PID {pid}: {exc}")
        try:
            self.pid_path.unlink()
        except OSError:
            pass
        return "Stopped Capohm.\n" + "\n".join(messages)

    def restart(self) -> str:
        stop_msg = self.stop()
        time.sleep(0.8)
        start_msg = self.start()
        return stop_msg + "\n\n" + start_msg


class App:
    def __init__(self, config_path: Path, options_path: Path):
        self.config_path = config_path
        self.options_path = options_path
        self.repo_dir = config_path.parent
        self.bot = BotManager(self.repo_dir)
        self.last_status = "Ready."

    def load_options(self) -> dict[str, Any]:
        raw_options = load_json(self.options_path, DEFAULT_OPTIONS)
        if not isinstance(raw_options, dict):
            raw_options = {}
        options = dict(raw_options)
        raw_fields = options.get("fields", [])
        if not isinstance(raw_fields, list):
            raw_fields = []
        fields: list[dict[str, Any]] = []
        for item in raw_fields:
            if isinstance(item, dict) and item.get("key"):
                fields.append(item)
        existing = {str(f.get("key")) for f in fields}
        for f in DEFAULT_OPTIONS["fields"]:
            if f["key"] not in existing:
                fields.append(dict(f))
                existing.add(f["key"])
        options["fields"] = fields
        options.setdefault("title", DEFAULT_OPTIONS.get("title", "Capohm Control Panel"))
        return options

    def load_config(self) -> dict[str, Any]:
        cfg = repair_config(load_json(self.config_path, {}))
        cfg, init_changed = ensure_character_profiles(cfg, self.repo_dir)
        if init_changed:
            backup_file(self.config_path)
            save_json(self.config_path, cfg)
            self.last_status = "Initialized/upgraded character profiles:\n" + "\n".join(f"- {x}" for x in init_changed)
        return cfg

    def save_config(self, cfg: dict[str, Any]) -> Path | None:
        backup = backup_file(self.config_path)
        try:
            sync_character_files_from_config(cfg, self.repo_dir)
        except Exception as exc:
            self.last_status = f"Warning: character file sync failed: {exc}"
        save_json(self.config_path, cfg)
        return backup

    def load_state(self) -> dict[str, Any]:
        return {
            "ok": True,
            "config": self.load_config(),
            "options": self.load_options(),
            "status": self.last_status,
            "bot": self.bot.status(),
        }

    def save_general(self, values: dict[str, Any]) -> dict[str, Any]:
        options = self.load_options()
        cfg = self.load_config()
        cfg, changed = apply_values(cfg, options, values)
        cfg, init_changed = ensure_character_profiles(cfg, self.repo_dir)
        changed.update({f"init:{i}": x for i, x in enumerate(init_changed)})
        backup = self.save_config(cfg)
        changed_list = ", ".join(k for k in changed.keys()) if changed else "nothing"
        running_note = "\nCapohm is running; hit Restart bot to apply changes." if self.bot.status()["running"] else "\nStart Capohm when ready."
        self.last_status = f"Saved general config. Changed: {changed_list}.\nBackup: {backup.name if backup else 'none'}{running_note}"
        return {"ok": True, "status": self.last_status}

    def set_mode(self, mode: str) -> dict[str, Any]:
        mode = mode.lower().strip()
        if mode not in ("pro", "free"):
            raise ValueError("mode must be pro or free")
        cfg = self.load_config()
        cfg["capohm_mode"] = mode
        changed = [f"capohm_mode -> {mode}"]
        changed.extend(apply_selected_profile(cfg))
        backup = self.save_config(cfg)
        note = "\nRestart bot to apply." if self.bot.status()["running"] else ""
        self.last_status = "Mode saved and applied:\n" + "\n".join(f"- {x}" for x in changed) + f"\nBackup: {backup.name if backup else 'none'}" + note
        return {"ok": True, "status": self.last_status}

    def select_character(self, character: str) -> dict[str, Any]:
        character = slugify(character)
        cfg = self.load_config()
        if character not in cfg.get("character_profiles", {}):
            raise ValueError(f"Unknown character: {character}")
        cfg["character"] = character
        ensure_media_dirs(self.repo_dir, character)
        changed = [f"character -> {character}"]
        changed.extend(apply_selected_profile(cfg))
        backup = self.save_config(cfg)
        note = "\nRestart bot to apply." if self.bot.status()["running"] else ""
        self.last_status = "Character selected and applied:\n" + "\n".join(f"- {x}" for x in changed) + f"\nBackup: {backup.name if backup else 'none'}" + note
        return {"ok": True, "status": self.last_status}

    def add_character(self, character: str) -> dict[str, Any]:
        character = slugify(character)
        cfg = self.load_config()
        profiles = cfg.setdefault("character_profiles", {})
        if character in profiles:
            raise ValueError(f"Character already exists: {character}")
        display_name = character.replace("_", " ").title()
        profiles[character] = default_character_profile(character, display_name, cfg, self.repo_dir)
        # New characters should not accidentally inherit a paid voice ID.
        profiles[character]["pro"]["elevenlabs_voice_id"] = ""
        ensure_media_dirs(self.repo_dir, character)
        backup = self.save_config(cfg)
        self.last_status = f"Added character {character}.\nSynced character file.\nMedia folder: ui_media/characters/{character}/\nBackup: {backup.name if backup else 'none'}"
        return {"ok": True, "status": self.last_status, "character": character}

    def save_character(self, character: str, profile: dict[str, Any], use_now: bool = False) -> dict[str, Any]:
        character = slugify(character)
        cfg = self.load_config()
        profiles = cfg.setdefault("character_profiles", {})
        if character not in profiles:
            raise ValueError(f"Unknown character: {character}")
        old = profiles[character]
        # Preserve unknown future keys, overwrite known UI keys.
        new_prof = dict(old)
        incoming_aliases = profile.get("aliases", old.get("aliases", []))
        new_prof["aliases"] = normalize_profile_aliases(incoming_aliases)
        for key in ("display_name", "description", "background", "personality_prompt", "media_dir", "thinking_sound", "reaction_style", "default_mood", "insult_sensitivity", "forgiveness_speed"):
            new_prof[key] = str(profile.get(key, ""))
        for key, default in (("ai_history_messages", 6), ("emotion_memory_turns", 2)):
            raw = profile.get(key, old.get(key, default))
            try:
                new_prof[key] = int(float(raw))
            except Exception:
                new_prof[key] = int(default)
        old_guards = old.get("guards", {}) if isinstance(old.get("guards", {}), dict) else {}
        incoming_guards = profile.get("guards", {}) if isinstance(profile.get("guards", {}), dict) else {}
        new_prof["guards"] = {}
        defaults = default_guard_settings(cfg)
        for field in CHARACTER_GUARD_FIELDS:
            key = field["key"]
            raw = incoming_guards.get(key, old_guards.get(key, defaults.get(key)))
            new_prof["guards"][key] = convert_character_guard_value(key, raw, defaults.get(key))
        for mode in ("pro", "free"):
            new_prof[mode] = dict(old.get(mode, {}))
            incoming = profile.get(mode, {}) if isinstance(profile.get(mode, {}), dict) else {}
            for key, value in incoming.items():
                new_prof[mode][key] = "" if value is None else str(value)
            if new_prof[mode].get("ollama_profile") and not new_prof[mode].get("ollama_model_profile"):
                new_prof[mode]["ollama_model_profile"] = new_prof[mode]["ollama_profile"]
        profiles[character] = new_prof
        ensure_media_dirs(self.repo_dir, character)
        changed = [f"saved profile {character}"]
        if use_now:
            cfg["character"] = character
            changed.append(f"character -> {character}")
        if cfg.get("character") == character:
            changed.extend(apply_selected_profile(cfg))
        backup = self.save_config(cfg)
        note = "\nRestart bot to apply." if self.bot.status()["running"] else ""
        self.last_status = "Character profile saved and synced:\n" + "\n".join(f"- {x}" for x in changed) + f"\nBackup: {backup.name if backup else 'none'}" + note
        return {"ok": True, "status": self.last_status}

    def bot_action(self, action: str) -> dict[str, Any]:
        if action == "start":
            msg = self.bot.start()
        elif action == "stop":
            msg = self.bot.stop()
        elif action == "restart":
            msg = self.bot.restart()
        else:
            raise ValueError(f"Unknown bot action: {action}")
        self.last_status = msg
        return {"ok": True, "status": msg, "bot": self.bot.status()}

    def log(self, which: str) -> dict[str, Any]:
        if which == "stdout":
            path = self.bot.stdout_path
        elif which == "errors":
            path = self.bot.stderr_path
        else:
            raise ValueError("which must be stdout or errors")
        return {"ok": True, "status": f"Showing last lines from {path.name}", "content": tail_file(path)}


class Handler(BaseHTTPRequestHandler):
    app: App

    def _send(self, status: int, body: bytes, content_type: str = "text/plain; charset=utf-8") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, data: Any) -> None:
        self._send(status, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/":
            self._send(200, INDEX_HTML.encode("utf-8"), "text/html; charset=utf-8")
            return
        if path == "/api/state":
            try:
                self._json(200, self.app.load_state())
            except Exception as exc:
                self._json(500, {"ok": False, "error": str(exc)})
            return
        if path == "/api/log":
            try:
                qs = parse_qs(parsed.query)
                self._json(200, self.app.log(qs.get("which", ["errors"])[0]))
            except Exception as exc:
                self._json(400, {"ok": False, "error": str(exc)})
            return
        self._json(404, {"ok": False, "error": "Not found"})

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8") if length else "{}"
        try:
            if self.headers.get("Content-Type", "").startswith("application/json"):
                payload = json.loads(body or "{}")
            else:
                payload = {k: v[-1] for k, v in parse_qs(body).items()}
        except Exception as exc:
            self._json(400, {"ok": False, "error": f"Bad request: {exc}"})
            return
        try:
            if path == "/api/save":
                values = payload.get("values", payload)
                if not isinstance(values, dict):
                    raise ValueError("values must be an object")
                self._json(200, self.app.save_general(values))
                return
            if path == "/api/mode":
                self._json(200, self.app.set_mode(str(payload.get("mode", ""))))
                return
            if path == "/api/select-character":
                self._json(200, self.app.select_character(str(payload.get("character", ""))))
                return
            if path == "/api/add-character":
                self._json(200, self.app.add_character(str(payload.get("character", ""))))
                return
            if path == "/api/save-character":
                profile = payload.get("profile", {})
                if not isinstance(profile, dict):
                    raise ValueError("profile must be an object")
                self._json(200, self.app.save_character(str(payload.get("character", "")), profile, bool(payload.get("use_now"))))
                return
            if path.startswith("/api/bot/"):
                self._json(200, self.app.bot_action(path.rsplit("/", 1)[-1]))
                return
        except Exception as exc:
            self._json(400, {"ok": False, "error": str(exc)})
            return
        self._json(404, {"ok": False, "error": "Not found"})

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("[control] " + fmt % args + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Capohm control panel with character editor")
    parser.add_argument("--config", default="config.json", help="Path to config.json")
    parser.add_argument("--options", default=None, help="Path to capohm_options.json")
    parser.add_argument("--host", default="127.0.0.1", help="Use 0.0.0.0 for LAN access")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    config_path = Path(args.config).expanduser().resolve()
    options_path = Path(args.options).expanduser().resolve() if args.options else config_path.parent / "capohm_options.json"
    if not config_path.exists():
        print(f"Warning: {config_path} does not exist yet.")
    Handler.app = App(config_path=config_path, options_path=options_path)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Capohm Control Panel running at http://{args.host}:{args.port}")
    print(f"Config:  {config_path}")
    print(f"Options: {options_path}")
    print("Press Ctrl+C to stop the control panel. The bot keeps running unless you press Stop bot.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nControl panel stopped.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
