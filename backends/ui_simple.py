import threading
import time

class UI:
    def __init__(self, config: dict):
        self._lock = threading.Lock()
        self.error_log = config.get("error_log", "capohm_errors.log")

    def start(self) -> None:
        self.log("=== CAPOHM MODULAR V1 ===")
        self.log("Simple UI. Say 'buddy' or 'hey hive' to wake.")

    def _print(self, text: str) -> None:
        with self._lock:
            print(text, flush=True)

    def status(self, state: str) -> None:
        self._print(f"[System: {state}]")

    def heard(self, text: str) -> None:
        if text:
            self._print(f"Heard: {text}")

    def assistant(self, text: str) -> None:
        if text:
            self._print(f"\nAssistant: {text}\n")

    def sleep_note(self, text: str) -> None:
        if text:
            self._print(f"[sleep] {text}")

    def log(self, text: str) -> None:
        if text:
            self._print(str(text))

    def error(self, text: str) -> None:
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        try:
            with open(self.error_log, "a", encoding="utf-8") as f:
                f.write(f"{stamp} {text}\n")
        except Exception:
            pass
        self._print(f"[error] {text}")
