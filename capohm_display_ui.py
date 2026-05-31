#!/usr/bin/env python3
"""
Capohm Display UI
A full-screen display layer for Capohm/NEXUS with character-specific media folders.

- Serves a browser UI at http://localhost:8777
- Receives events from the assistant via POST /api/event
- Streams updates to the browser with Server-Sent Events
- Shows images, GIFs, videos, and audio from ui_media/
- Shows heard/response as subtitle overlay without a blocking box

No external Python packages required.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import queue
import random
import re
import signal
import sys
import threading
import time
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

SUPPORTED_IMAGE = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"}
SUPPORTED_VIDEO = {".mp4", ".webm", ".mov", ".m4v", ".avi", ".mkv"}
SUPPORTED_AUDIO = {".mp3", ".wav", ".ogg", ".flac", ".m4a"}
SUPPORTED_MEDIA = SUPPORTED_IMAGE | SUPPORTED_VIDEO | SUPPORTED_AUDIO
DEFAULT_EMOTIONS = [
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


def now_ms() -> int:
    return int(time.time() * 1000)


def guess_emotion(text: str | None, fallback: str = "neutral") -> str:
    """Tiny local emotion guesser. Good enough until the LLM returns metadata."""
    if not text:
        return fallback
    t = text.lower()

    rules: list[tuple[str, list[str]]] = [
        ("error", ["error", "failed", "crash", "exception", "traceback", "stuk", "kapot", "werkt niet", "fail"]),
        ("alert", ["warning", "danger", "stop", "cancel", "alarm", "alert", "pas op", "hou op", "stil"]),
        ("happy", ["done", "gelukt", "success", "mooi", "nice", "great", "top", "perfect", "werkt"]),
        ("amused", ["haha", "lol", "sarcas", "typical", "natuurlijk", "obviously", "brilliant"]),
        ("thinking", ["thinking", "denk", "hmm", "maybe", "misschien", "checking", "even kijken"]),
        ("sleep", ["sleep", "asleep", "low-power", "powering down", "go to sleep", "slaap"]),
        ("sad", ["sorry", "helaas", "jammer", "unfortunately"]),
        ("confused", ["unknown", "not sure", "geen idee", "begrijp", "unclear"]),
    ]
    for emotion, words in rules:
        if any(w in t for w in words):
            return emotion
    return fallback


@dataclass
class UiState:
    started_ms: int = field(default_factory=now_ms)
    updated_ms: int = field(default_factory=now_ms)
    mode: str = "idle"
    emotion: str = "neutral"
    character: str = "default"
    heard: str = ""
    response: str = ""
    media: str | None = None
    media_type: str | None = None
    status: str = "display online"
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "started_ms": self.started_ms,
            "updated_ms": self.updated_ms,
            "mode": self.mode,
            "emotion": self.emotion,
            "character": self.character,
            "heard": self.heard,
            "response": self.response,
            "media": self.media,
            "media_type": self.media_type,
            "status": self.status,
            "raw": self.raw,
        }


class DisplayApp:
    def __init__(self, media_dir: Path):
        self.media_dir = media_dir.resolve()
        self.state = UiState()
        self.lock = threading.Lock()
        self.clients: list[queue.Queue[dict[str, Any]]] = []
        self.commands = self._load_commands()
        self.ensure_media_folders()

    def ensure_media_folders(self) -> None:
        self.media_dir.mkdir(parents=True, exist_ok=True)
        for folder in DEFAULT_EMOTIONS:
            (self.media_dir / folder).mkdir(parents=True, exist_ok=True)

        # Optional character-specific layout:
        # ui_media/characters/<character>/<emotion>/*.png|gif|mp4|mp3
        char_root = self.media_dir / "characters"
        char_root.mkdir(parents=True, exist_ok=True)
        known_characters = {"borg", "natural", "grumpy_shopkeeper"}
        cdir = Path("characters")
        if cdir.exists():
            for path in cdir.glob("*.json"):
                known_characters.add(path.stem)
        for char in sorted(known_characters):
            safe = re.sub(r"[^a-zA-Z0-9_.-]+", "_", char).strip("_") or "default"
            for folder in DEFAULT_EMOTIONS:
                (char_root / safe / folder).mkdir(parents=True, exist_ok=True)

    def _load_commands(self) -> dict[str, Any]:
        path = Path("ui_commands.json")
        if not path.exists():
            example = {
                "assimilate": {
                    "triggers": ["assimilate", "resistance is futile"],
                    "emotion": "alert",
                    "media": "alert/assimilate.gif",
                },
                "thinking": {
                    "triggers": ["think", "denk", "processing"],
                    "emotion": "thinking",
                    "media": "thinking",
                },
            }
            try:
                path.write_text(json.dumps(example, indent=4) + "\n", encoding="utf-8")
            except OSError:
                pass
            return example
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def subscribe(self) -> queue.Queue[dict[str, Any]]:
        q: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=50)
        with self.lock:
            self.clients.append(q)
            state = self.state.to_dict()
        q.put({"type": "state", "state": state})
        return q

    def unsubscribe(self, q: queue.Queue[dict[str, Any]]) -> None:
        with self.lock:
            if q in self.clients:
                self.clients.remove(q)

    def broadcast(self, event: dict[str, Any]) -> None:
        dead: list[queue.Queue[dict[str, Any]]] = []
        with self.lock:
            clients = list(self.clients)
        for q in clients:
            try:
                q.put_nowait(event)
            except queue.Full:
                dead.append(q)
        for q in dead:
            self.unsubscribe(q)

    def media_kind(self, rel: str | None) -> str | None:
        if not rel:
            return None
        ext = Path(rel).suffix.lower()
        if ext in SUPPORTED_IMAGE:
            return "image"
        if ext in SUPPORTED_VIDEO:
            return "video"
        if ext in SUPPORTED_AUDIO:
            return "audio"
        return None

    def resolve_media(self, wanted: str | None, emotion: str, character: str | None = None) -> str | None:
        """Resolve media name, file, folder, or emotion folder into a relative media path.

        Priority:
        1. Explicit file/folder/name requested by command.
        2. Character-specific emotion folder.
        3. Global emotion folder.
        4. Character neutral.
        5. Global neutral.
        """
        candidates: list[Path] = []
        character = (character or "default").strip().strip("/")
        character = re.sub(r"[^a-zA-Z0-9_.-]+", "_", character).strip("_") or "default"

        def add_files_from(folder: Path) -> None:
            if folder.exists() and folder.is_dir():
                for p in sorted(folder.iterdir()):
                    if p.is_file() and p.suffix.lower() in SUPPORTED_MEDIA:
                        candidates.append(p)

        def rel_or_none(p: Path) -> str | None:
            try:
                return str(p.relative_to(self.media_dir)).replace(os.sep, "/")
            except ValueError:
                return None

        char_root = self.media_dir / "characters" / character

        if wanted:
            wanted = wanted.strip().strip("/")

            # Exact path inside ui_media.
            p = (self.media_dir / wanted).resolve()
            try:
                p.relative_to(self.media_dir)
            except ValueError:
                p = self.media_dir / "__invalid__"

            if p.is_file() and p.suffix.lower() in SUPPORTED_MEDIA:
                return rel_or_none(p)
            if p.is_dir():
                add_files_from(p)

            # Character-local exact path or folder.
            cp = (char_root / wanted).resolve()
            try:
                cp.relative_to(self.media_dir)
            except ValueError:
                cp = self.media_dir / "__invalid__"
            if cp.is_file() and cp.suffix.lower() in SUPPORTED_MEDIA:
                return rel_or_none(cp)
            if cp.is_dir():
                add_files_from(cp)

            # Search by stem/name, preferring current character.
            needle = wanted.lower()
            search_roots = [char_root, self.media_dir]
            for root in search_roots:
                if not root.exists():
                    continue
                for file in root.rglob("*"):
                    if file.is_file() and file.suffix.lower() in SUPPORTED_MEDIA:
                        rel = str(file.relative_to(self.media_dir)).replace(os.sep, "/").lower()
                        if needle in file.stem.lower() or needle in rel:
                            candidates.append(file)

        if not candidates:
            add_files_from(char_root / emotion)
        if not candidates:
            add_files_from(self.media_dir / emotion)
        if not candidates and emotion != "neutral":
            add_files_from(char_root / "neutral")
        if not candidates and emotion != "neutral":
            add_files_from(self.media_dir / "neutral")

        if not candidates:
            return None
        chosen = random.choice(candidates)
        return str(chosen.relative_to(self.media_dir)).replace(os.sep, "/")

    def command_for_text(self, text: str) -> dict[str, Any] | None:
        t = text.lower()
        for name, spec in self.commands.items():
            triggers = spec.get("triggers", []) if isinstance(spec, dict) else []
            if any(str(trigger).lower() in t for trigger in triggers):
                out = dict(spec)
                out["command"] = name
                return out
        return None

    def apply_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        event_type = str(payload.get("type", payload.get("kind", "event"))).lower()
        text = str(payload.get("text", "") or "")
        emotion = str(payload.get("emotion", "") or "").lower().strip()
        media_wanted = payload.get("media") or payload.get("file") or payload.get("asset")
        status = str(payload.get("status", "") or "")
        character = str(payload.get("character", "") or "").strip()

        if not emotion:
            emotion = guess_emotion(text, fallback="neutral")

        # Commands can override emotion/media.
        if event_type in {"heard", "command"} and text:
            cmd = self.command_for_text(text)
            if cmd:
                emotion = str(cmd.get("emotion", emotion)).lower()
                media_wanted = cmd.get("media", media_wanted)
                event_type = "command"
                if not status:
                    status = f"command: {cmd.get('command', 'unknown')}"

        if event_type == "listening":
            emotion = "listening"
        elif event_type == "thinking":
            emotion = "thinking"
        elif event_type == "sleep":
            emotion = "sleep"

        with self.lock:
            current_character = self.state.character
        selected_character = character or current_character or "default"
        media_rel = self.resolve_media(str(media_wanted), emotion, selected_character) if media_wanted else self.resolve_media(None, emotion, selected_character)
        media_type = self.media_kind(media_rel)

        with self.lock:
            if event_type == "heard":
                self.state.heard = text
                self.state.mode = "listening"
            elif event_type == "response":
                self.state.response = text
                self.state.mode = "speaking"
            elif event_type == "media":
                self.state.mode = "media"
                if text:
                    self.state.response = text
            elif event_type == "command":
                self.state.mode = "command"
                if text:
                    self.state.heard = text
            elif event_type in {"emotion", "state", "listening", "thinking", "sleep"}:
                self.state.mode = event_type
                if text:
                    self.state.response = text
            else:
                self.state.mode = event_type
                if text:
                    self.state.response = text

            self.state.emotion = emotion or self.state.emotion
            self.state.character = selected_character
            self.state.media = media_rel
            self.state.media_type = media_type
            if status:
                self.state.status = status
            self.state.updated_ms = now_ms()
            self.state.raw = payload
            state = self.state.to_dict()

        event = {"type": "state", "state": state}
        self.broadcast(event)
        return state


HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Capohm Display NOBOX v4 CHAR</title>
<style>
  :root {
    --text: #e7fffb;
    --muted: #8fb9b4;
    --accent: #00ffe2;
    --warn: #ffbf40;
    --danger: #ff4e6d;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    width: 100vw;
    height: 100vh;
    overflow: hidden;
    background: radial-gradient(circle at 50% 45%, #10363d 0%, #02070a 55%, #000 100%);
    color: var(--text);
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
  }
  .scanlines::after {
    content: "";
    position: fixed;
    inset: 0;
    pointer-events: none;
    background: repeating-linear-gradient(
      to bottom,
      rgba(255,255,255,0.030), rgba(255,255,255,0.030) 1px,
      rgba(0,0,0,0.035) 2px, rgba(0,0,0,0.035) 4px
    );
    mix-blend-mode: overlay;
    z-index: 30;
  }
  .stage {
    position: fixed;
    inset: 0;
    display: grid;
    place-items: center;
    padding: 0;
  }
  #mediaLayer {
    position: absolute;
    inset: 0;
    display: grid;
    place-items: center;
    opacity: 0.96;
  }
  #mediaLayer img, #mediaLayer video {
    max-width: 100vw;
    max-height: 100vh;
    width: auto;
    height: auto;
    object-fit: contain;
    filter: drop-shadow(0 0 18px rgba(0,255,226,0.18));
  }
  #mediaLayer video { background: #000; }
  .orb {
    width: min(42vw, 42vh);
    aspect-ratio: 1;
    border-radius: 50%;
    border: 2px solid rgba(0, 255, 226, 0.32);
    background:
      radial-gradient(circle at 48% 42%, rgba(255,255,255,0.90) 0%, rgba(0,255,226,0.75) 12%, rgba(0,110,120,0.25) 36%, rgba(0,0,0,0) 70%),
      conic-gradient(from 40deg, rgba(0,255,226,0.0), rgba(0,255,226,0.32), rgba(0,0,0,0), rgba(0,255,226,0.45), rgba(0,0,0,0));
    box-shadow: 0 0 45px rgba(0,255,226,0.28), inset 0 0 60px rgba(0,255,226,0.14);
    animation: pulse 2.8s ease-in-out infinite;
  }
  body[data-emotion="error"] .orb { box-shadow: 0 0 55px rgba(255,78,109,0.55), inset 0 0 45px rgba(255,78,109,0.22); border-color: rgba(255,78,109,0.55); }
  body[data-emotion="alert"] .orb { box-shadow: 0 0 55px rgba(255,191,64,0.55), inset 0 0 45px rgba(255,191,64,0.22); border-color: rgba(255,191,64,0.55); }
  body[data-emotion="sleep"] .orb { opacity: 0.35; animation-duration: 6s; }
  body[data-emotion="thinking"] .orb { animation-duration: 1.2s; }
  @keyframes pulse {
    0%, 100% { transform: scale(0.985); opacity: 0.82; }
    50% { transform: scale(1.035); opacity: 1; }
  }

  /* Tiny status pills only. The big text panel is gone: subtitles now sit over the image. */
  .topbar {
    position: fixed;
    top: 12px;
    left: 14px;
    display: flex;
    gap: 12px;
    align-items: center;
    color: var(--muted);
    font-size: 10px;
    opacity: 0.50;
    z-index: 40;
    text-shadow: 0 2px 4px #000, 0 0 10px #000;
  }
  .pill {
    border: 0;
    border-radius: 0;
    padding: 0;
    background: transparent;
    backdrop-filter: none;
  }
  .emotion { color: var(--accent); }
  .corner-title {
    position: fixed;
    right: 18px;
    top: 13px;
    font-size: 12px;
    letter-spacing: 0.24em;
    color: rgba(216,255,251,0.56);
    z-index: 40;
  }

  .subtitle-wrap {
    position: fixed;
    left: 3.5vw;
    right: 3.5vw;
    bottom: max(10px, 2.6vh);
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 5px;
    pointer-events: none;
    z-index: 50;
    background: transparent !important;
    border: 0 !important;
    box-shadow: none !important;
  }
  .heard-line {
    position: fixed;
    /* Move this off the black rounded CRT edge and onto the bright display area. */
    left: clamp(54px, 7.2vw, 86px);
    bottom: max(94px, 15.0vh);
    max-width: min(70vw, 760px);
    color: rgba(0, 255, 226, 0.86);
    /* Same visual scale as the top status text, just a touch stronger for readability. */
    font-size: clamp(10px, 1.18vw, 13px);
    font-weight: 600;
    line-height: 1.18;
    letter-spacing: 0.02em;
    white-space: normal;
    overflow: hidden;
    overflow-wrap: anywhere;
    word-break: normal;
    max-height: 2.55em;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    text-shadow:
      0 2px 4px rgba(0,0,0,1),
      0 0 9px rgba(0,0,0,1),
      0 0 12px rgba(0,255,226,0.34);
    opacity: 0.92;
    background: transparent !important;
    border: 0 !important;
    box-shadow: none !important;
  }
  .heard-line::before {
    content: "HEARD  ";
    color: rgba(216,255,251,0.70);
    font-size: 0.92em;
    letter-spacing: 0.12em;
  }
  .subtitle {
    width: min(92vw, 980px);
    min-height: 1.15em;
    max-height: 3.55em;
    background: transparent !important;
    border: 0 !important;
    box-shadow: none !important;
    color: var(--text);
    font-size: clamp(15px, 2.65vw, 28px);
    font-weight: 700;
    line-height: 1.16;
    text-align: center;
    letter-spacing: 0.01em;
    overflow: hidden;
    display: -webkit-box;
    -webkit-line-clamp: 3;
    -webkit-box-orient: vertical;
    text-shadow:
      0 2px 2px rgba(0,0,0,1),
      0 0 5px rgba(0,0,0,1),
      0 0 12px rgba(0,0,0,0.95),
      0 0 16px rgba(0,255,226,0.32);
    -webkit-text-stroke: 0.45px rgba(0, 18, 22, 0.85);
  }
  body[data-emotion="error"] .subtitle { text-shadow: 0 2px 2px #000, 0 0 8px #000, 0 0 16px rgba(255,78,109,0.40); }
  body[data-emotion="alert"] .subtitle { text-shadow: 0 2px 2px #000, 0 0 8px #000, 0 0 16px rgba(255,191,64,0.42); }
  body[data-emotion="sleep"] .subtitle { opacity: 0.68; }
  body[data-mode="listening"] .subtitle { opacity: 0.55; }

  .hidden { display: none !important; }
</style>
</head>
<body class="scanlines" data-emotion="neutral" data-mode="idle">
  <div class="stage">
    <div id="mediaLayer"><div class="orb"></div></div>
  </div>
  <div class="corner-title">CAPOHM · NOBOX v4 CHAR</div>
  <div class="topbar">
    <div class="pill">mode: <span id="mode">idle</span></div>
    <div class="pill">emotion: <span class="emotion" id="emotion">neutral</span></div>
    <div class="pill">char: <span class="emotion" id="character">default</span></div>
    <div class="pill" id="status">display online</div>
  </div>
  <div class="subtitle-wrap">
    <div class="heard-line" id="heard">—</div>
    <div class="subtitle" id="response">Awaiting directive. Dramatic pause included.</div>
  </div>
<script>
const mediaLayer = document.getElementById('mediaLayer');
const heard = document.getElementById('heard');
const response = document.getElementById('response');
const mode = document.getElementById('mode');
const emotion = document.getElementById('emotion');
const statusEl = document.getElementById('status');
const characterEl = document.getElementById('character');
let lastMedia = null;

function esc(s) {
  return String(s || '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
}
function renderMedia(state) {
  const media = state.media;
  const type = state.media_type;
  if (!media) {
    if (lastMedia !== null) {
      mediaLayer.innerHTML = '<div class="orb"></div>';
      lastMedia = null;
    }
    return;
  }
  const url = '/media/' + encodeURIComponent(media).replaceAll('%2F', '/') + '?t=' + state.updated_ms;
  if (lastMedia === media + ':' + type + ':' + state.updated_ms) return;
  lastMedia = media + ':' + type + ':' + state.updated_ms;

  if (type === 'image') {
    mediaLayer.innerHTML = `<img src="${url}" alt="${esc(media)}">`;
  } else if (type === 'video') {
    mediaLayer.innerHTML = `<video src="${url}" autoplay loop playsinline></video>`;
    const v = mediaLayer.querySelector('video');
    v.muted = false;
    v.volume = 0.9;
    v.play().catch(() => { v.muted = true; v.play().catch(()=>{}); });
  } else if (type === 'audio') {
    mediaLayer.innerHTML = '<div class="orb"></div><audio id="aud" autoplay></audio>';
    const a = document.getElementById('aud');
    a.src = url;
    a.volume = 0.9;
    a.play().catch(()=>{});
  }
}
function applyState(state) {
  const m = state.mode || 'idle';
  document.body.dataset.emotion = state.emotion || 'neutral';
  document.body.dataset.mode = m;
  mode.textContent = m;
  emotion.textContent = state.emotion || 'neutral';
  statusEl.textContent = state.status || 'display online';
  characterEl.textContent = state.character || 'default';
  if (state.heard) {
    heard.textContent = state.heard;
    heard.title = state.heard;
  }
  if (state.response) {
    response.textContent = state.response;
    response.title = state.response;
  }
  renderMedia(state);
}
async function loadState() {
  try {
    const res = await fetch('/api/state');
    applyState(await res.json());
  } catch (e) {}
}
loadState();
const es = new EventSource('/events');
es.onmessage = (msg) => {
  try {
    const event = JSON.parse(msg.data);
    if (event.state) applyState(event.state);
  } catch (e) {}
};
es.onerror = () => { statusEl.textContent = 'display reconnecting...'; };
</script>
</body>
</html>
"""

def safe_media_path(media_dir: Path, url_path: str) -> Path | None:
    rel = unquote(url_path.removeprefix("/media/")).split("?", 1)[0].strip("/")
    if not rel:
        return None
    path = (media_dir / rel).resolve()
    try:
        path.relative_to(media_dir)
    except ValueError:
        return None
    if not path.is_file():
        return None
    return path


def make_handler(app: DisplayApp):
    class Handler(BaseHTTPRequestHandler):
        server_version = "CapohmDisplay/0.6-nobox-v4-character"

        def log_message(self, fmt: str, *args: Any) -> None:
            sys.stdout.write("[display] " + fmt % args + "\n")

        def send_json(self, obj: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
            data = json.dumps(obj).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/":
                data = HTML.encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(data)
                return

            if parsed.path == "/api/state":
                with app.lock:
                    state = app.state.to_dict()
                self.send_json(state)
                return

            if parsed.path == "/events":
                q = app.subscribe()
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.end_headers()
                try:
                    while True:
                        try:
                            event = q.get(timeout=15)
                            data = json.dumps(event)
                            self.wfile.write(f"data: {data}\n\n".encode("utf-8"))
                        except queue.Empty:
                            self.wfile.write(b": keepalive\n\n")
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, TimeoutError):
                    pass
                finally:
                    app.unsubscribe(q)
                return

            if parsed.path.startswith("/media/"):
                media_path = safe_media_path(app.media_dir, parsed.path)
                if not media_path:
                    self.send_error(HTTPStatus.NOT_FOUND, "media not found")
                    return
                ctype, _ = mimetypes.guess_type(str(media_path))
                ctype = ctype or "application/octet-stream"
                data = media_path.read_bytes()
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(data)
                return

            self.send_error(HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path not in {"/api/event", "/api/media"}:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            length = int(self.headers.get("Content-Length", "0") or "0")
            raw = self.rfile.read(length) if length else b"{}"
            try:
                payload = json.loads(raw.decode("utf-8"))
                if not isinstance(payload, dict):
                    raise ValueError("payload must be object")
            except Exception as exc:
                self.send_json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            if parsed.path == "/api/media":
                payload.setdefault("type", "media")
            state = app.apply_event(payload)
            self.send_json({"ok": True, "state": state})

    return Handler


def main() -> int:
    parser = argparse.ArgumentParser(description="Capohm full-screen display UI")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8777)
    parser.add_argument("--media-dir", default="ui_media")
    args = parser.parse_args()

    media_dir = Path(args.media_dir)
    app = DisplayApp(media_dir)
    handler = make_handler(app)
    server = ThreadingHTTPServer((args.host, args.port), handler)

    def shutdown(signum: int, frame: Any) -> None:
        print("\n[display] shutting down")
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    print(f"[display] media dir: {app.media_dir}")
    print(f"[display] open: http://localhost:{args.port}")
    print("[display] tip: global files go in ui_media/happy etc.; character files go in ui_media/characters/<character>/<emotion>/")
    try:
        server.serve_forever()
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
