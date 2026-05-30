import importlib
import queue
import threading
import time


class STT:
    """
    Generic hybrid STT backend.

    It loads one normal STT backend as the primary listener, for example:
      - google
      - vosk
      - whispercpp later

    Then it optionally adds keyboard input on top.

    Config example:
      "stt_backend": "hybrid",
      "primary_stt_backend": "vosk",
      "keyboard_overlay": true
    """

    def __init__(self, config, ui=None):
        self.config = config
        self.ui = ui

        self.primary_name = config.get("primary_stt_backend", "vosk")

        if self.primary_name in ["hybrid", "keyboard"]:
            raise ValueError(
                "primary_stt_backend cannot be 'hybrid' or 'keyboard'. "
                "Use vosk, google, whispercpp, etc."
            )

        module = importlib.import_module(f"backends.stt_{self.primary_name}")
        PrimarySTT = getattr(module, "STT")
        self.primary = PrimarySTT(config, ui=ui)

        self.keyboard_enabled = bool(config.get("keyboard_overlay", True))
        self.keyboard_queue = queue.Queue()
        self.keyboard_thread = None
        self.running = False

    def start(self):
        if self.running:
            return

        self.running = True

        # Start the selected microphone / STT backend.
        self.primary.start()

        # Add typed input on top, if enabled.
        if self.keyboard_enabled:
            self.keyboard_thread = threading.Thread(
                target=self._keyboard_loop,
                daemon=True
            )
            self.keyboard_thread.start()

        msg = (
            f"Hybrid STT active: {self.primary_name} + "
            f"{'keyboard' if self.keyboard_enabled else 'no keyboard'}."
        )

        if self.ui:
            self.ui.log(msg)
        else:
            print(msg)

    def _keyboard_loop(self):
        while self.running:
            try:
                text = input("> ").strip()
                if text:
                    if self.ui:
                        self.ui.heard(text)
                    self.keyboard_queue.put(text)

            except EOFError:
                time.sleep(0.2)

            except KeyboardInterrupt:
                raise

            except Exception as e:
                if self.ui:
                    self.ui.error(f"Keyboard overlay error: {e}")
                else:
                    print(f"Keyboard overlay error: {e}")
                time.sleep(0.5)

    def listen(self):
        # Keyboard first: typed commands are deliberate and should win.
        try:
            return self.keyboard_queue.get_nowait()
        except queue.Empty:
            pass

        return self.primary.listen()

    def stop(self):
        self.running = False

        try:
            self.primary.stop()
        except Exception:
            pass
