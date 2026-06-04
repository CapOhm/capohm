from __future__ import annotations
import threading
import time
#!/usr/bin/env python3
"""
Small helper module for sending events from Capohm to the display UI.

Adds optional character metadata so the display can choose media from:
    ui_media/characters/<character>/<emotion>/

Usage from code:
    from ui_bus import ui_heard, ui_response, ui_media, ui_emotion
    ui_heard(user_input, character="grumpy_shopkeeper")
    ui_response(reply, character="grumpy_shopkeeper")

Usage from terminal:
    python3 ui_bus.py heard "hey borg" --character grumpy_shopkeeper
    python3 ui_bus.py response "Done. Obviously I had to fix it." --character grumpy_shopkeeper
    python3 ui_bus.py media alert/assimilate.gif --emotion alert --character borg
"""


import argparse
import json
import os
from typing import Any
from urllib.request import Request, urlopen

DEFAULT_URL = os.environ.get("CAPOHM_UI_URL", "http://127.0.0.1:8777")



# Capohm guard indicator auto-off state. Patched final version.
_capohm_guard_tokens = {"hard": 0, "soft": 0}
_capohm_guard_lock = threading.Lock()


def _capohm_load_config_float(key: str, default: float) -> float:
    try:
        cfg_path = Path("config.json")
        if not cfg_path.exists():
            return float(default)
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        return float(cfg.get(key, default))
    except Exception:
        return float(default)


def _capohm_send_guard_event(*, hard=None, soft=None, status=None, url=DEFAULT_URL, timeout: float = 0.35) -> bool:
    payload: dict[str, Any] = {"type": "guard_status"}
    if hard is not None:
        payload["hard"] = bool(hard)
    if soft is not None:
        payload["soft"] = bool(soft)
    if status:
        payload["status"] = status
    data = json.dumps(payload).encode("utf-8")
    req = Request(
        url.rstrip("/") + "/api/event",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=timeout) as res:
            return 200 <= res.status < 300
    except Exception:
        return False


def _capohm_schedule_guard_off(which: str, seconds: float, *, url=DEFAULT_URL, timeout: float = 0.35) -> None:
    try:
        seconds = float(seconds)
    except Exception:
        seconds = 0.0
    if seconds <= 0:
        _capohm_send_guard_event(**{which: False}, url=url, timeout=timeout)
        return

    with _capohm_guard_lock:
        _capohm_guard_tokens[which] = _capohm_guard_tokens.get(which, 0) + 1
        token = _capohm_guard_tokens[which]

    def _worker() -> None:
        time.sleep(seconds)
        with _capohm_guard_lock:
            if _capohm_guard_tokens.get(which) != token:
                return
        _capohm_send_guard_event(**{which: False}, url=url, timeout=timeout)

    threading.Thread(target=_worker, daemon=True).start()


def guess_emotion(text: str | None, fallback: str = "neutral") -> str:
    if not text:
        return fallback
    t = text.lower()
    rules = [
        ("error", ["error", "failed", "crash", "exception", "traceback", "stuk", "kapot", "werkt niet", "fail"]),
        ("angry", ["insult", "angry", "furious", "fool", "idiot", "stupid", "useless", "trash", "garbage", "dump", "cheap", "senile", "weak", "old weak", "old fool", "moldy", "rot", "sack of potatoes", "potions are trash", "shop is a dump", "beledigd", "boos", "waardeloos", "rot", "troep", "vuilnis"]),
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



def send_ui_payload(payload: dict[str, Any], *, url: str = DEFAULT_URL, timeout: float = 0.35) -> bool:
    """Send an arbitrary JSON payload to the display UI."""
    data = json.dumps(payload).encode("utf-8")
    req = Request(
        url.rstrip("/") + "/api/event",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=timeout) as res:
            return 200 <= res.status < 300
    except Exception:
        return False

def send_ui_event(
    kind: str,
    text: str = "",
    *,
    emotion: str | None = None,
    media: str | None = None,
    status: str | None = None,
    character: str | None = None,
    url: str = DEFAULT_URL,
    timeout: float = 0.35,
) -> bool:
    payload: dict[str, Any] = {"type": kind}
    if text:
        payload["text"] = text
    if emotion:
        payload["emotion"] = emotion
    elif text and kind == "response":
        payload["emotion"] = guess_emotion(text)
    if media:
        payload["media"] = media
    if status:
        payload["status"] = status
    if character:
        payload["character"] = character

    data = json.dumps(payload).encode("utf-8")
    req = Request(
        url.rstrip("/") + "/api/event",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=timeout) as res:
            return 200 <= res.status < 300
    except Exception:
        # The display should never be allowed to crash the bot. Tiny mercy, for once.
        return False




def ui_guard_status(
    hard=None,
    soft=None,
    *,
    hard_seconds=None,
    soft_seconds=None,
    reason: str | None = None,
    similarity=None,
    overlap=None,
    blocked: str | None = None,
    accepted: bool | None = None,
    url: str = DEFAULT_URL,
) -> bool:
    """
    Update guard indicator dots.

    hard=True/False controls the red hard-guard dot.
    soft=True/False controls the green soft-guard dot.
    hard_seconds/soft_seconds should be the real durations from main_modular.py.
    Extra values are optional debug telemetry for tuning echo suppression.
    """
    payload: dict[str, Any] = {"type": "guard"}
    if hard is not None:
        payload["hard"] = bool(hard)
    if soft is not None:
        payload["soft"] = bool(soft)
    if hard_seconds is not None:
        try:
            payload["hard_seconds"] = float(hard_seconds)
        except Exception:
            pass
    if soft_seconds is not None:
        try:
            payload["soft_seconds"] = float(soft_seconds)
        except Exception:
            pass
    if reason:
        payload["reason"] = str(reason)
    if similarity is not None:
        try:
            payload["similarity"] = float(similarity)
        except Exception:
            pass
    if overlap is not None:
        try:
            payload["overlap"] = float(overlap)
        except Exception:
            pass
    if blocked:
        payload["blocked"] = str(blocked)
    if accepted is not None:
        payload["accepted"] = bool(accepted)
    return send_ui_payload(payload, url=url)


def ui_heard(text: str, character: str | None = None) -> bool:
    return send_ui_event("heard", text, emotion="listening", character=character)


def ui_response(text: str, emotion: str | None = None, character: str | None = None) -> bool:
    return send_ui_event("response", text, emotion=emotion, character=character)


def ui_media(media: str, emotion: str = "neutral", text: str = "", character: str | None = None) -> bool:
    return send_ui_event("media", text, emotion=emotion, media=media, character=character)


def ui_emotion(emotion: str, text: str = "", character: str | None = None) -> bool:
    return send_ui_event("emotion", text, emotion=emotion, character=character)





# Capohm patched: guard indicator auto-off support.
# The display has no clock of its own for the soft guard dot; this helper
# sends an automatic soft=False after echo_memory_seconds.


def _capohm_load_config_float(key: str, default: float) -> float:
    try:
        from pathlib import Path as _Path
        cfg_path = _Path("config.json")
        if not cfg_path.exists():
            return float(default)
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        return float(cfg.get(key, default) or default)
    except Exception:
        return float(default)


def _capohm_send_guard_payload(payload: dict[str, Any], *, url: str = DEFAULT_URL, timeout: float = 0.35) -> bool:
    data = json.dumps(payload).encode("utf-8")
    req = Request(
        url.rstrip("/") + "/api/event",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=timeout) as res:
            return 200 <= res.status < 300
    except Exception:
        return False


def _capohm_schedule_guard_off(kind: str, seconds: float, *, url: str = DEFAULT_URL, timeout: float = 0.35) -> None:
    try:
        seconds = float(seconds)
    except Exception:
        return
    if seconds <= 0:
        return

    with _capohm_guard_lock:
        _capohm_guard_tokens[kind] = _capohm_guard_tokens.get(kind, 0) + 1
        token = _capohm_guard_tokens[kind]

    def _worker() -> None:
        time.sleep(seconds)
        with _capohm_guard_lock:
            if _capohm_guard_tokens.get(kind) != token:
                return
        if kind == "soft":
            _capohm_send_guard_payload({"type": "guard_status", "soft": False, "status": "soft guard expired"}, url=url, timeout=timeout)
        elif kind == "hard":
            _capohm_send_guard_payload({"type": "guard_status", "hard": False, "status": "hard guard expired"}, url=url, timeout=timeout)

    t = threading.Thread(target=_worker, daemon=True)
    t.start()


def ui_guard_status(
    hard: bool | None = None,
    soft: bool | None = None,
    *,
    status: str | None = None,
    url: str = DEFAULT_URL,
    timeout: float = 0.35,
    hard_seconds: float | None = None,
    soft_seconds: float | None = None,
) -> bool:
    """Update the display guard indicator dots.

    hard=True  -> red dot on
    hard=False -> red dot off
    soft=True  -> green dot on, then auto-off after echo_memory_seconds
    soft=False -> green dot off immediately
    None means leave that dot unchanged.
    """
    payload: dict[str, Any] = {"type": "guard_status"}
    if hard is not None:
        payload["hard"] = bool(hard)
    if soft is not None:
        payload["soft"] = bool(soft)
    if status:
        payload["status"] = status

    ok = _capohm_send_guard_payload(payload, url=url, timeout=timeout)

    # Reset/cancel timers when the dot changes state.
    if soft is True:
        if soft_seconds is None:
            soft_seconds = _capohm_load_config_float("echo_memory_seconds", 35.0)
        _capohm_schedule_guard_off("soft", soft_seconds, url=url, timeout=timeout)
    elif soft is False:
        with _capohm_guard_lock:
            _capohm_guard_tokens["soft"] = _capohm_guard_tokens.get("soft", 0) + 1

    if hard is True and hard_seconds is not None:
        _capohm_schedule_guard_off("hard", hard_seconds, url=url, timeout=timeout)
    elif hard is False:
        with _capohm_guard_lock:
            _capohm_guard_tokens["hard"] = _capohm_guard_tokens.get("hard", 0) + 1

    return ok

def main() -> int:
    parser = argparse.ArgumentParser(description="Send an event to Capohm Display UI")
    parser.add_argument("kind", choices=["heard", "response", "media", "emotion", "thinking", "sleep", "listening", "guard"])
    parser.add_argument("text_or_media", nargs="?", default="")
    parser.add_argument("--emotion", default=None)
    parser.add_argument("--media", default=None)
    parser.add_argument("--character", default=None)
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--hard", choices=["on", "off"], default=None, help="Guard test: hard dot on/off")
    parser.add_argument("--soft", choices=["on", "off"], default=None, help="Guard test: soft dot on/off")
    parser.add_argument("--hard-seconds", type=float, default=None)
    parser.add_argument("--soft-seconds", type=float, default=None)
    args = parser.parse_args()

    if args.kind == "guard":
        hard = None if args.hard is None else args.hard == "on"
        soft = None if args.soft is None else args.soft == "on"
        ok = ui_guard_status(
            hard=hard,
            soft=soft,
            hard_seconds=args.hard_seconds,
            soft_seconds=args.soft_seconds,
            status="guard test",
            url=args.url,
        )
    elif args.kind == "media":
        ok = send_ui_event("media", "", emotion=args.emotion or "neutral", media=args.text_or_media, character=args.character, url=args.url)
    elif args.kind == "emotion":
        ok = send_ui_event("emotion", "", emotion=args.text_or_media or args.emotion or "neutral", character=args.character, url=args.url)
    else:
        ok = send_ui_event(args.kind, args.text_or_media, emotion=args.emotion, media=args.media, character=args.character, url=args.url)
    print("ok" if ok else "not sent")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())


def ui_heard(text: str) -> bool:
    # If accepted user speech reached the bot/UI, hard guard is no longer active.
    ui_guard_status(hard=False)
    return send_ui_event("heard", text, emotion="listening")

