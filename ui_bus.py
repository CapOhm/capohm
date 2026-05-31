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

from __future__ import annotations

import argparse
import json
import os
from typing import Any
from urllib.request import Request, urlopen

DEFAULT_URL = os.environ.get("CAPOHM_UI_URL", "http://127.0.0.1:8777")


def guess_emotion(text: str | None, fallback: str = "neutral") -> str:
    if not text:
        return fallback
    t = text.lower()
    rules = [
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


def ui_heard(text: str, character: str | None = None) -> bool:
    return send_ui_event("heard", text, emotion="listening", character=character)


def ui_response(text: str, emotion: str | None = None, character: str | None = None) -> bool:
    return send_ui_event("response", text, emotion=emotion, character=character)


def ui_media(media: str, emotion: str = "neutral", text: str = "", character: str | None = None) -> bool:
    return send_ui_event("media", text, emotion=emotion, media=media, character=character)


def ui_emotion(emotion: str, text: str = "", character: str | None = None) -> bool:
    return send_ui_event("emotion", text, emotion=emotion, character=character)


def main() -> int:
    parser = argparse.ArgumentParser(description="Send an event to Capohm Display UI")
    parser.add_argument("kind", choices=["heard", "response", "media", "emotion", "thinking", "sleep", "listening"])
    parser.add_argument("text_or_media", nargs="?", default="")
    parser.add_argument("--emotion", default=None)
    parser.add_argument("--media", default=None)
    parser.add_argument("--character", default=None)
    parser.add_argument("--url", default=DEFAULT_URL)
    args = parser.parse_args()

    if args.kind == "media":
        ok = send_ui_event("media", "", emotion=args.emotion or "neutral", media=args.text_or_media, character=args.character, url=args.url)
    elif args.kind == "emotion":
        ok = send_ui_event("emotion", "", emotion=args.text_or_media or args.emotion or "neutral", character=args.character, url=args.url)
    else:
        ok = send_ui_event(args.kind, args.text_or_media, emotion=args.emotion, media=args.media, character=args.character, url=args.url)
    print("ok" if ok else "not sent")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
