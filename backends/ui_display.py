import threading
import time
import re



SHOPKEEPER_INSULT_WORDS = [
    "useless", "weak", "stupid", "idiot", "fool", "trash", "garbage", "dump",
    "cheap", "expired", "senile", "greedy", "smells", "smell", "old weak",
    "old fool", "moldy", "rotten", "sack of potatoes", "potions are trash",
    "shop is a dump", "worthless", "pathetic",
    "waardeloos", "dom", "idioot", "stom", "troep", "vuilnis", "oude zak",
    "zwak", "seniel", "rot", "stinkt", "prut", "rommel"
]

SHOPKEEPER_ANGRY_REPLY_WORDS = [
    "fool", "idiot", "goblin", "turnip", "mold", "moldy", "insult",
    "trash", "garbage", "whelp", "cur", "pest", "sack", "smell", "boot",
    "wafer", "waffle", "nitwit", "clod", "barbs", "manners"
]


def is_shopkeeper_insult(text: str) -> bool:
    t = (text or "").lower()
    return any(w in t for w in SHOPKEEPER_INSULT_WORDS)


def is_shopkeeper_angry_reply(text: str) -> bool:
    t = (text or "").lower()
    return any(w in t for w in SHOPKEEPER_ANGRY_REPLY_WORDS)


try:
    from ui_bus import send_ui_event
except Exception:
    def send_ui_event(*a, **k): return False


class UI:
    """Capohm browser display backend.

    Drop this file into: backends/ui_display.py
    Then set in config.json: "ui_backend": "display"

    It keeps terminal logging, but also forwards heard/response/status/error
    events to capohm_display_ui.py through ui_bus.py.

    v2 adds character metadata so media can be selected from:
        ui_media/characters/<character>/<emotion>/
    """

    def __init__(self, config: dict):
        self._lock = threading.Lock()
        self.config = config
        self.error_log = config.get("error_log", "capohm_errors.log")
        self.forward_logs = bool(config.get("display_forward_logs", False))
        self._last_input_emotion = "neutral"

    def _character(self) -> str:
        return str(self.config.get("character", "default") or "default")

    def _print(self, text: str) -> None:
        with self._lock:
            print(text, flush=True)

    def start(self) -> None:
        self.log("=== CAPOHM DISPLAY UI BACKEND ===")
        self.log("Browser display bridge active.")
        send_ui_event(
            "state",
            "Display bridge active.",
            emotion="neutral",
            status="bot connected",
            character=self._character(),
        )

    def status(self, state: str) -> None:
        state = str(state or "").upper()
        self._print(f"[System: {state}]")
        if state == "ASLEEP":
            send_ui_event("sleep", "", emotion="sleep", status="ASLEEP", character=self._character())
        elif state == "AWAKE":
            send_ui_event("state", "", emotion="neutral", status="AWAKE", character=self._character())
        else:
            send_ui_event("state", "", status=state, character=self._character())

    def heard(self, text: str) -> None:
        if not text:
            return
        self._print(f"Heard: {text}")
        heard_emotion = "listening"
        if self._character() == "grumpy_shopkeeper" and is_shopkeeper_insult(text):
            heard_emotion = "angry"
        self._last_input_emotion = heard_emotion
        send_ui_event("heard", text, emotion=heard_emotion, character=self._character())

    def assistant(self, text: str) -> None:
        if not text:
            return
        self._print(f"\nAssistant: {text}\n")
        reply_emotion = None
        if self._character() == "grumpy_shopkeeper" and (
            self._last_input_emotion == "angry" or is_shopkeeper_angry_reply(text)
        ):
            reply_emotion = "angry"
        send_ui_event("response", text, emotion=reply_emotion, character=self._character())
        self._last_input_emotion = "neutral"

    def sleep_note(self, text: str) -> None:
        if not text:
            return
        self._print(f"[sleep] {text}")
        send_ui_event("sleep", text, emotion="sleep", status="ASLEEP", character=self._character())

    def log(self, text: str) -> None:
        if not text:
            return
        self._print(str(text))
        if self.forward_logs:
            send_ui_event("state", str(text), status=str(text), character=self._character())

    def error(self, text: str) -> None:
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        try:
            with open(self.error_log, "a", encoding="utf-8") as f:
                f.write(f"{stamp} {text}\n")
        except Exception:
            pass
        self._print(f"[error] {text}")
        send_ui_event("response", str(text), emotion="error", status="error", character=self._character())
