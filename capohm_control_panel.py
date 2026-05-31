#!/usr/bin/env python3
"""
Capohm Control Panel
A tiny zero-dependency web UI for switching Capohm backends/models by editing
config.json safely, plus start/stop/restart controls for main_modular.py.

Run from your Capohm repo:
    python3 capohm_control_panel.py --config config.json --host 0.0.0.0 --port 8765

Then open:
    http://<pi-ip>:8765

It creates capohm_options.json on first run. Add new dropdown choices there later.

Notes:
- Start runs main_modular.py in the background.
- stdout goes to capohm_stdout.log.
- stderr goes to capohm_errors.log.
- PID is stored in .capohm.pid.
"""

from __future__ import annotations

import argparse
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

DEFAULT_OPTIONS: dict[str, Any] = {
    "title": "Capohm Control Panel",
    "fields": [
        {
            "key": "tts_backend",
            "label": "TTS / Voice",
            "type": "select",
            "options": ["piper_fast", "piper", "espeak", "borg"],
            "help": "Welke stem-engine Capohm gebruikt.",
        },
        {
            "key": "piper_fast_mode",
            "label": "Piper Fast mode",
            "type": "select",
            "options": ["cli", "api"],
            "help": "Voor nu is 'cli' de veilige keuze; 'api' gaf eerder WAV-header gezeur.",
        },
        {
            "key": "stt_backend",
            "label": "STT / Luisteren",
            "type": "select",
            "options": ["whispercpp_vad", "whispercpp", "vosk", "keyboard", "hybrid"],
            "help": "Speech-to-text backend. whispercpp_vad is de huidige beste route.",
        },
        {
            "key": "ai_backend",
            "label": "AI backend",
            "type": "select",
            "options": ["ollama", "openai", "echo"],
            "help": "Lokaal via Ollama, online via OpenAI, of echo/debug.",
        },
        {
            "key": "ollama_profile",
            "label": "Ollama model profile",
            "type": "select",
            "options": ["tiny", "small", "rpg", "vision"],
            "help": "Voor normale chat meestal 'rpg'. 'vision' liever alleen als losse vision-tool gebruiken.",
            "optional": True,
        },
        {
            "key": "character",
            "label": "Character",
            "type": "select",
            "options": ["borg", "natural", "grumpy_shopkeeper"],
            "help": "Persoonlijkheid/profiel. Chat-history reset gebeurt in de assistant zelf.",
        },
        {
            "key": "ui_backend",
            "label": "Assistant UI backend",
            "type": "select",
            "options": ["simple", "display"],
            "help": "simple = terminal output, display = browser frontend on port 8777.",
            "optional": True,
        },
        {
            "key": "whispercpp_device_name",
            "label": "Mic device name",
            "type": "text",
            "help": "Bijvoorbeeld: USB Audio",
            "optional": True,
        },
        {
            "key": "whispercpp_device_index",
            "label": "Mic device index",
            "type": "nullable_int",
            "help": "Leeg laten = null/autodetect. PyAudio wil soms een nummer; uiteraard, want audio moest moeilijk doen.",
            "optional": True,
        },
        {
            "key": "whispercpp_vad_rms_threshold",
            "label": "VAD threshold",
            "type": "int",
            "default": 450,
            "help": "Hoger = minder snel luisteren; lager = gevoeliger. Leeg laten wordt automatisch 450.",
            "optional": True,
        },
    ],
    "profiles": {
        "portable_default": {
            "label": "Portable default",
            "values": {
                "tts_backend": "piper_fast",
                "piper_fast_mode": "cli",
                "stt_backend": "whispercpp_vad",
                "ai_backend": "ollama",
                "ollama_profile": "rpg",
                "character": "grumpy_shopkeeper",
            },
        },
        "fast_tiny": {
            "label": "Fast tiny test",
            "values": {
                "tts_backend": "piper_fast",
                "piper_fast_mode": "cli",
                "stt_backend": "whispercpp_vad",
                "ai_backend": "ollama",
                "ollama_profile": "tiny",
                "character": "natural",
            },
        },
        "keyboard_debug": {
            "label": "Keyboard debug",
            "values": {
                "tts_backend": "espeak",
                "stt_backend": "keyboard",
                "ai_backend": "echo",
                "character": "natural",
            },
        },
        "openai_voice": {
            "label": "OpenAI + voice",
            "values": {
                "tts_backend": "piper_fast",
                "piper_fast_mode": "cli",
                "stt_backend": "whispercpp_vad",
                "ai_backend": "openai",
                "character": "natural",
            },
        },
    },
}

INDEX_HTML = r"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Capohm Control Panel</title>
  <style>
    :root { color-scheme: dark; }
    body {
      margin: 0;
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: radial-gradient(circle at top, #20384b 0, #081018 45%, #04070a 100%);
      color: #e8f4ff;
    }
    header {
      padding: 28px 24px 12px;
      max-width: 980px;
      margin: auto;
    }
    h1 { margin: 0 0 8px; font-size: 2rem; }
    h2 { margin-top: 0; }
    .subtitle { color: #a9c3d8; margin: 0; }
    main {
      max-width: 980px;
      margin: 0 auto;
      padding: 16px 24px 48px;
      display: grid;
      gap: 18px;
    }
    .card {
      background: rgba(9, 18, 28, 0.84);
      border: 1px solid rgba(161, 216, 255, 0.14);
      border-radius: 18px;
      box-shadow: 0 18px 40px rgba(0,0,0,0.35);
      padding: 18px;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 14px;
    }
    label { display: block; font-weight: 700; margin-bottom: 7px; }
    select, input {
      width: 100%;
      box-sizing: border-box;
      border: 1px solid #33516a;
      border-radius: 12px;
      background: #07111b;
      color: #eef8ff;
      padding: 10px 12px;
      font-size: 1rem;
    }
    .help { color: #98b3c7; font-size: 0.87rem; margin-top: 6px; min-height: 2.2em; }
    button {
      border: 0;
      border-radius: 13px;
      padding: 10px 14px;
      font-weight: 800;
      cursor: pointer;
      background: #27c499;
      color: #03110d;
      margin: 5px 5px 5px 0;
    }
    button.secondary { background: #27435a; color: #d8ecff; }
    button.warning { background: #f0b429; color: #211400; }
    button.danger { background: #ff5f6d; color: #210205; }
    button:disabled { opacity: 0.45; cursor: not-allowed; }
    .status {
      white-space: pre-wrap;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      background: #03070b;
      border-radius: 12px;
      padding: 12px;
      border: 1px solid rgba(255,255,255,0.08);
      color: #cdeeff;
      overflow-x: auto;
    }
    .pill {
      display: inline-block;
      padding: 3px 8px;
      border: 1px solid #33516a;
      border-radius: 999px;
      color: #9edaff;
      margin-left: 6px;
      font-size: 0.8rem;
    }
    .pill.running { border-color: #27c499; color: #6dffd9; }
    .pill.stopped { border-color: #ff5f6d; color: #ffadb5; }
    .profiles { display: flex; flex-wrap: wrap; gap: 8px; }
    .tiny { color: #91aabd; font-size: 0.9rem; }
    .bot-row { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
  </style>
</head>
<body>
<header>
  <h1>Capohm Control Panel <span class="pill">config.json</span> <span id="botPill" class="pill">bot: checking</span></h1>
  <p class="subtitle">Switch AI, TTS, STT, characters and start/stop the bot without hand-editing JSON like a medieval punishment.</p>
</header>
<main>
  <section class="card">
    <h2>Bot control</h2>
    <div class="bot-row">
      <button id="startBtn" type="button" onclick="botAction('start')">Start bot</button>
      <button id="stopBtn" class="danger" type="button" onclick="botAction('stop')">Stop bot</button>
      <button id="restartBtn" class="warning" type="button" onclick="botAction('restart')">Restart bot</button>
      <button class="secondary" type="button" onclick="loadState()">Refresh</button>
      <button class="secondary" type="button" onclick="loadLog('errors')">Show errors log</button>
      <button class="secondary" type="button" onclick="loadLog('stdout')">Show stdout log</button>
    </div>
    <p class="tiny">Start runs main_modular.py in the background. Logs go to capohm_stdout.log and capohm_errors.log.</p>
  </section>

  <section class="card">
    <h2>Profiles</h2>
    <p class="tiny">One click presets. They update the fields below; hit Save to write config.</p>
    <div id="profiles" class="profiles"></div>
  </section>

  <section class="card">
    <h2>Backends</h2>
    <form id="settingsForm">
      <div id="fields" class="grid"></div>
      <p>
        <button type="submit">Save config</button>
        <button class="secondary" type="button" onclick="loadState()">Reload</button>
        <button class="warning" type="button" onclick="showRaw()">Show raw config</button>
      </p>
    </form>
  </section>

  <section class="card">
    <h2>Status</h2>
    <div id="status" class="status">Loading...</div>
  </section>
</main>
<script>
let state = null;

function esc(s) {
  return String(s ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
}

async function api(path, options) {
  const res = await fetch(path, options);
  const data = await res.json();
  if (!res.ok || data.ok === false) throw new Error(data.error || res.statusText);
  return data;
}

function buildFields() {
  const holder = document.getElementById('fields');
  holder.innerHTML = '';
  for (const f of state.options.fields) {
    const value = state.config[f.key];
    const div = document.createElement('div');
    let control = '';
    if (f.type === 'select') {
      control = `<select name="${esc(f.key)}">` +
        (f.options || []).map(o => `<option value="${esc(o)}" ${o === value ? 'selected' : ''}>${esc(o)}</option>`).join('') +
        `</select>`;
    } else {
      control = `<input name="${esc(f.key)}" value="${esc(value === null || value === undefined ? '' : value)}" placeholder="${f.type === 'nullable_int' ? 'null' : ''}">`;
    }
    div.innerHTML = `<label>${esc(f.label || f.key)}</label>${control}<div class="help">${esc(f.help || '')}</div>`;
    holder.appendChild(div);
  }
}

function buildProfiles() {
  const holder = document.getElementById('profiles');
  holder.innerHTML = '';
  const profiles = state.options.profiles || {};
  Object.entries(profiles).forEach(([name, profile]) => {
    const btn = document.createElement('button');
    btn.className = 'secondary';
    btn.type = 'button';
    btn.textContent = profile.label || name;
    btn.onclick = () => applyProfile(name);
    holder.appendChild(btn);
  });
}

function setStatus(text) {
  document.getElementById('status').textContent = text;
}

function updateBotControls() {
  const bot = state.bot || {};
  const running = !!bot.running;
  const pill = document.getElementById('botPill');
  pill.textContent = running ? `bot: running pid ${bot.pid}` : 'bot: stopped';
  pill.className = running ? 'pill running' : 'pill stopped';
  document.getElementById('startBtn').disabled = running;
  document.getElementById('stopBtn').disabled = !running;
  document.getElementById('restartBtn').disabled = false;
}

async function loadState() {
  try {
    state = await api('/api/state');
    buildProfiles();
    buildFields();
    updateBotControls();
    const bot = state.bot || {};
    const botText = bot.running ? `Bot running. PID: ${bot.pid}. Source: ${bot.source || 'pidfile'}.` : 'Bot stopped.';
    setStatus(`${botText}\n\n${state.status || 'Ready.'}`);
  } catch (err) {
    setStatus('ERROR: ' + err.message);
  }
}

async function applyProfile(name) {
  try {
    const profile = state.options.profiles[name];
    if (!profile) throw new Error('Unknown profile: ' + name);
    const values = profile.values || {};
    for (const [key, value] of Object.entries(values)) {
      const el = document.querySelector(`[name="${CSS.escape(key)}"]`);
      if (el) el.value = value ?? '';
    }
    setStatus(`Profile loaded into form: ${profile.label || name}\nHit Save config to apply it.`);
  } catch (err) {
    setStatus('ERROR: ' + err.message);
  }
}

async function saveForm(ev) {
  ev.preventDefault();
  const form = new FormData(document.getElementById('settingsForm'));
  const values = {};
  for (const [k, v] of form.entries()) values[k] = v;
  try {
    const result = await api('/api/save', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({values})
    });
    setStatus(result.status);
    await loadState();
  } catch (err) {
    setStatus('ERROR: ' + err.message);
  }
}

async function botAction(action) {
  try {
    setStatus(`${action}...`);
    const result = await api(`/api/bot/${action}`, {method: 'POST'});
    setStatus(result.status);
    await loadState();
  } catch (err) {
    setStatus('ERROR: ' + err.message);
    await loadState();
  }
}

async function loadLog(which) {
  try {
    const result = await api(`/api/log?which=${encodeURIComponent(which)}`);
    setStatus(result.status + '\n\n' + (result.content || ''));
  } catch (err) {
    setStatus('ERROR: ' + err.message);
  }
}

function showRaw() {
  setStatus(JSON.stringify(state.config, null, 2));
}

document.getElementById('settingsForm').addEventListener('submit', saveForm);
loadState();
setInterval(async () => {
  try {
    const fresh = await api('/api/state');
    state.bot = fresh.bot;
    updateBotControls();
  } catch (_) {}
}, 3000);
</script>
</body>
</html>
"""


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
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
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = path.with_name(f"{path.name}.bak-{stamp}")
    shutil.copy2(path, backup)
    return backup


SAFE_DEFAULTS: dict[str, Any] = {
    "whispercpp_vad_rms_threshold": 450,
    "whispercpp_vad_silence_seconds": 0.75,
    "whispercpp_vad_min_speech_seconds": 0.45,
    "whispercpp_vad_max_speech_seconds": 10.0,
    "whispercpp_vad_preroll_seconds": 0.35,
    "whispercpp_input_sample_rate": 48000,
    "whispercpp_recognition_sample_rate": 16000,
}


def repair_config(config: dict[str, Any]) -> dict[str, Any]:
    """Repair values that should never be null."""
    repaired = dict(config)
    for key, default in SAFE_DEFAULTS.items():
        if repaired.get(key) is None:
            repaired[key] = default
    return repaired


def ensure_options(options_path: Path) -> dict[str, Any]:
    if not options_path.exists():
        save_json(options_path, DEFAULT_OPTIONS)
        return DEFAULT_OPTIONS
    data = load_json(options_path, DEFAULT_OPTIONS)
    if "fields" not in data:
        data["fields"] = DEFAULT_OPTIONS["fields"]
    if "profiles" not in data:
        data["profiles"] = DEFAULT_OPTIONS["profiles"]
    return data


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
    if typ == "select":
        opts = field.get("options", [])
        if raw not in opts:
            raise ValueError(f"{field.get('key')} must be one of: {', '.join(opts)}")
        return raw
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
    repaired_config = repair_config(new_config)
    for key, value in repaired_config.items():
        if new_config.get(key) != value:
            changed[key] = value
    return repaired_config, changed


def run_ollama_profile_if_needed(repo_dir: Path, changed: dict[str, Any], all_values: dict[str, Any]) -> str:
    profile = changed.get("ollama_profile")
    if not profile:
        return ""
    switcher = repo_dir / "switch_ollama_profile.py"
    if not switcher.exists():
        return f"\nNote: ollama_profile set to {profile!r}, but switch_ollama_profile.py was not found."
    try:
        result = subprocess.run(
            [sys.executable, str(switcher), str(profile)],
            cwd=str(repo_dir),
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        return "\nWarning: switch_ollama_profile.py timed out after 30 seconds."
    except Exception as exc:
        return f"\nWarning: could not run switch_ollama_profile.py: {exc}"

    out = (result.stdout or "").strip()
    err = (result.stderr or "").strip()
    if result.returncode != 0:
        return f"\nWarning: switch_ollama_profile.py failed with code {result.returncode}.\n{out}\n{err}".strip()
    return "\nOllama switcher ran successfully." + (f"\n{out}" if out else "")


def load_dotenv(path: Path) -> dict[str, str]:
    """Small .env loader so OpenAI keys are available when started from the web UI."""
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
    """Find main_modular.py running from this repo, without needing psutil."""
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
    if venv_python.exists():
        return str(venv_python)
    return sys.executable


def tail_file(path: Path, max_lines: int = 120) -> str:
    if not path.exists():
        return f"{path.name} does not exist yet."
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[-max_lines:])
    except Exception as exc:
        return f"Could not read {path.name}: {exc}"


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

        self.stdout_path.parent.mkdir(parents=True, exist_ok=True)
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
            # Started and immediately died. Leave logs for the user, remove stale pid.
            try:
                self.pid_path.unlink()
            except OSError:
                pass
            errors = tail_file(self.stderr_path, 60)
            raise RuntimeError(f"Capohm started but exited immediately with code {proc.returncode}.\n\nLast errors:\n{errors}")
        return f"Started Capohm. PID: {proc.pid}.\nCommand: {python_bin} main_modular.py\nLogs: {self.stdout_path.name}, {self.stderr_path.name}"

    def stop(self) -> str:
        st = self.status()
        if not st["running"]:
            return "Capohm is not running. Nothing to stop. Suspiciously well-behaved."

        pids = [int(st["pid"])] + [int(p) for p in st.get("extra_pids", [])]
        messages: list[str] = []
        for pid in pids:
            if not is_pid_alive(pid):
                continue
            try:
                os.killpg(pid, signal.SIGTERM)
                messages.append(f"Sent SIGTERM to process group {pid}.")
            except ProcessLookupError:
                messages.append(f"PID {pid} was already gone.")
            except Exception:
                # If process group kill fails, try the pid itself.
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
                messages.append(f"PID {pid} ignored the polite request, so SIGKILL was used. Rude, but effective.")
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

    def load_state(self) -> dict[str, Any]:
        options = ensure_options(self.options_path)
        config = repair_config(load_json(self.config_path, {}))
        return {
            "ok": True,
            "config": config,
            "options": options,
            "status": self.last_status,
            "bot": self.bot.status(),
        }

    def save(self, values: dict[str, Any]) -> dict[str, Any]:
        options = ensure_options(self.options_path)
        config = load_json(self.config_path, {})
        new_config, changed = apply_values(config, options, values)
        backup = backup_file(self.config_path)
        save_json(self.config_path, new_config)
        switch_status = run_ollama_profile_if_needed(self.repo_dir, changed, values)
        changed_list = ", ".join(changed.keys()) if changed else "nothing"
        backup_text = f"Backup: {backup.name}" if backup else "No previous config found; created new config."
        running_note = "\nCapohm is running; hit Restart bot to apply changes." if self.bot.status()["running"] else "\nStart Capohm when ready."
        self.last_status = f"Saved config.json. Changed: {changed_list}.\n{backup_text}{switch_status}{running_note}"
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

    def do_GET(self) -> None:  # noqa: N802 - http.server API
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
                which = qs.get("which", ["errors"])[0]
                self._json(200, self.app.log(which))
            except Exception as exc:
                self._json(400, {"ok": False, "error": str(exc)})
            return
        self._json(404, {"ok": False, "error": "Not found"})

    def do_POST(self) -> None:  # noqa: N802 - http.server API
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

        if path == "/api/save":
            try:
                values = payload.get("values", payload)
                if not isinstance(values, dict):
                    raise ValueError("values must be an object")
                self._json(200, self.app.save(values))
            except Exception as exc:
                self._json(400, {"ok": False, "error": str(exc)})
            return

        if path.startswith("/api/bot/"):
            try:
                action = path.rsplit("/", 1)[-1]
                self._json(200, self.app.bot_action(action))
            except Exception as exc:
                self._json(400, {"ok": False, "error": str(exc)})
            return

        self._json(404, {"ok": False, "error": "Not found"})

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("[ui] " + fmt % args + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Capohm backend/model switching UI + bot control")
    parser.add_argument("--config", default="config.json", help="Path to Capohm config.json")
    parser.add_argument("--options", default=None, help="Path to capohm_options.json")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host. Use 0.0.0.0 for access from another PC.")
    parser.add_argument("--port", type=int, default=8765, help="Web UI port")
    args = parser.parse_args()

    config_path = Path(args.config).expanduser().resolve()
    options_path = Path(args.options).expanduser().resolve() if args.options else config_path.parent / "capohm_options.json"

    if not config_path.exists():
        print(f"Warning: {config_path} does not exist yet; it will be created on first save.")
    ensure_options(options_path)

    Handler.app = App(config_path=config_path, options_path=options_path)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Capohm Control Panel running at http://{args.host}:{args.port}")
    print(f"Config:  {config_path}")
    print(f"Options: {options_path}")
    print(f"Bot:     {config_path.parent / 'main_modular.py'}")
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
